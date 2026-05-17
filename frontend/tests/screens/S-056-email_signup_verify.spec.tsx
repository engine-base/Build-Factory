// @ts-nocheck
/**
 * T-V3-C-17 / S-056 — サインアップ確認メール (email template preview) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket
 *       (T-V3-C-TEST-01). Same convention as T-V3-C-12 / C-14.
 *
 * Covers (mapped to T-V3-C-17 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-056"
 *   structural.AC-S2  -> "h1 reads 'ようこそ、masato さん'"
 *   functional.AC-F1  -> "4xx/5xx surfaces non-technical toast referencing endpoint"
 *   functional.AC-F2  -> "preview renders the signup_verify template body" (UI surface
 *                         of the email_invitation / signup_verify dispatch backend AC)
 *   functional.AC-F3  -> "bounce/retry backend AC — UI shows active template subject
 *                         so admins can verify wording before any retry"
 *   regression.AC-R1  -> typed client `EmailApiError` carries endpoint label
 *                         without leaking stack traces.
 */

import * as React from "react";
import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
} from "vitest";
import {
  render,
  screen,
  waitFor,
  cleanup,
  fireEvent,
} from "@testing-library/react";

import EmailSignupVerifyPreviewPage from "@/app/(email)/signup-verify/page";
import { EmailApiError, EMAIL_TEMPLATES_ENDPOINT } from "@/api/email";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SIGNUP_TEMPLATE_FIXTURE = {
  id: "tpl-signup-verify",
  name: "signup_verify",
  subject: "【Build-Factory】メールアドレス認証のお願い",
  body_text:
    "Build-Factory にサインアップいただきありがとうございます。\n下記ボタンをクリックしてメールアドレスを認証してください。",
  body_html: "<p>fallback html</p>",
  locale: "ja",
  variables: ["display_name", "verify_url"],
};

const TEMPLATES_RESPONSE_OK = {
  templates: [
    {
      id: "tpl-invite",
      name: "email_invitation",
      subject: "ワークスペースに招待されました",
      body_text: "...",
      locale: "ja",
    },
    SIGNUP_TEMPLATE_FIXTURE,
  ],
  workspace_id: 1,
  count: 2,
};

function defaultFetchImpl(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const method = init?.method ?? "GET";
  if (
    typeof url === "string" &&
    method === "GET" &&
    url.endsWith(EMAIL_TEMPLATES_ENDPOINT)
  ) {
    return Promise.resolve(jsonResponse(200, TEMPLATES_RESPONSE_OK));
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation(defaultFetchImpl);
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-056 サインアップ確認メール (T-V3-C-17)", () => {
  it("[Tier1 AC-S1] renders root with data-screen-id=\"S-056\"", async () => {
    const { container } = render(<EmailSignupVerifyPreviewPage />);
    const root = container.querySelector('[data-screen-id="S-056"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-028");
    expect(root?.getAttribute("data-phase")).toBe("Phase 1B");
  });

  it("[Tier1 AC-S2] displays an h1 with text matching screens.json[S-056].h1_text", async () => {
    render(<EmailSignupVerifyPreviewPage />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toBe("ようこそ、masato さん");
  });

  it("[Tier2 AC-F2] loads templates via GET /api/email/templates on mount and renders the signup_verify body", async () => {
    render(<EmailSignupVerifyPreviewPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/email\/templates$/);
    expect((init as RequestInit | undefined)?.method ?? "GET").toBe("GET");

    const subject = await screen.findByTestId("email-subject");
    expect(subject.textContent).toContain(
      "【Build-Factory】メールアドレス認証のお願い",
    );
    const body = await screen.findByTestId("email-body");
    expect(body.textContent).toContain(
      "Build-Factory にサインアップいただきありがとうございます",
    );
  });

  it("[Tier2 AC-F1] on 5xx, surfaces a non-technical error referencing the endpoint without leaking server stack traces", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(500, {
          detail:
            "Traceback (most recent call last):\n  File '/srv/app/email.py', line 42\n    raise SQLError('db dead')",
        }),
      ),
    );

    render(<EmailSignupVerifyPreviewPage />);
    const toast = await screen.findByTestId("email-template-error");
    expect(toast.textContent).toContain(EMAIL_TEMPLATES_ENDPOINT);
    expect(toast.textContent).not.toMatch(/Traceback|SQLError|email\.py/);
  });

  it("[Tier2 AC-F1] on 401, surfaces a 'sign-in required' message tagged with the endpoint", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(401, { detail: { code: "email.unauthorized", message: "no token" } }),
      ),
    );

    render(<EmailSignupVerifyPreviewPage />);
    const toast = await screen.findByTestId("email-template-error");
    expect(toast.textContent).toContain("サインインが必要です");
    expect(toast.textContent).toContain(EMAIL_TEMPLATES_ENDPOINT);
  });

  it("[Tier2 AC-F3] reload button re-issues GET /api/email/templates so admins can verify the active template body", async () => {
    render(<EmailSignupVerifyPreviewPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const reload = await screen.findByTestId("reload-template");
    fireEvent.click(reload);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const subject = await screen.findByTestId("email-subject");
    expect(subject.textContent).toContain("メールアドレス認証のお願い");
  });

  it("[API unit] EmailApiError carries the failing endpoint without exposing server stack", () => {
    const err = new EmailApiError(
      "email.rate_limited",
      "rate limited (internal: stacktrace+at /srv/app/email.py:42)",
      429,
      EMAIL_TEMPLATES_ENDPOINT,
    );
    expect(err.endpoint).toBe(EMAIL_TEMPLATES_ENDPOINT);
    expect(err.status).toBe(429);
    const friendly = err.toUserMessage();
    expect(friendly).toContain(EMAIL_TEMPLATES_ENDPOINT);
    expect(friendly).not.toMatch(/Traceback|stacktrace|email\.py/);
  });
});
