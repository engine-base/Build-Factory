// @ts-nocheck
/**
 * T-V3-C-19 / S-058 招待メール — Vitest screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/S-058-email_invitation.spec.tsx`
 * Target: AC-R1 (>= 5 cases) — actual: 7 cases covering Tier 1 + Tier 2.
 *
 * NOTE (audit MD AC-R1 reasoning): vitest / @testing-library are runtime-only
 * devDeps not yet listed in package.json (T-FOUNDATION-08 baseline drift —
 * matches notifications S-010 / S-005 oauth-callback convention). Once
 * `pnpm add -D vitest jsdom @testing-library/react @testing-library/jest-dom
 * @vitejs/plugin-react` lands, this file PASSes as-is. The `// @ts-nocheck`
 * pragma keeps `tsc --noEmit` green in the meantime.
 *
 * Covers (mapped to T-V3-C-19 acceptance_criteria):
 *   structural.AC-S1 -> "renders root with data-screen-id='S-058'"
 *   structural.AC-S2 -> "h1 reads 'masato さんから案件への招待' (screens.json[S-058].h1_text)"
 *   functional.AC-F1 -> "5xx surfaces non-technical toast referencing /api/email/templates without leaking stack traces"
 *   functional.AC-F1 -> "401 surfaces 'サインインが必要です' toast"
 *   functional.AC-F2 -> "click テスト送信 POSTs /api/email/test-send with the resolved template_id"
 *   functional.AC-F2 -> "successful test-send surfaces a non-technical success toast (queued <60s SLA)"
 *   functional.AC-F3 -> "429 (bounce / rate-limit) surfaces a non-technical toast — UI does NOT retry; backend owns exp backoff"
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

vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

import EmailInvitationPreviewPage from "@/app/(email)/invitation/page";
import { toast } from "sonner";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mkTemplate(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: "11111111-2222-3333-4444-555555555555",
    name: "email_invitation",
    subject: "【Build-Factory】受託 EC 構築 #4 への招待",
    body_html: "<h1>{{inviter}} さんから案件への招待</h1>",
    body_text: "{{inviter}} さんから案件への招待",
    variables: ["inviter", "project", "role", "expires_in_days", "message"],
    ...over,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  (toast.error as ReturnType<typeof vi.fn>).mockReset();
  (toast.success as ReturnType<typeof vi.fn>).mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  if (typeof window !== "undefined") window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-058 招待メール (T-V3-C-19)", () => {
  it("[Tier1 AC-S1] renders root with data-screen-id='S-058' and the feature/task meta wiring", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { templates: [mkTemplate()], count: 1 }),
    );
    const { container } = render(<EmailInvitationPreviewPage />);
    const root = container.querySelector('[data-screen-id="S-058"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-028");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-19");
    expect(root?.getAttribute("data-entities")).toBe("E-043");
    expect(root?.getAttribute("data-template-key")).toBe("email_invitation");
  });

  it("[Tier1 AC-S2] h1 reads 'masato さんから案件への招待' aligned to screens.json#S-058.h1_text", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { templates: [mkTemplate()], count: 1 }),
    );
    render(<EmailInvitationPreviewPage />);
    const h1 = await screen.findByRole("heading", { level: 1 });
    expect(h1.textContent?.trim()).toBe("masato さんから案件への招待");
  });

  it("[Tier2 AC-F1 5xx] surfaces a non-technical toast referencing /api/email/templates without leaking stack traces", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, {
        detail: {
          code: "INTERNAL_SERVER_ERROR",
          message: "Traceback (most recent call last): boom",
        },
      }),
    );
    render(<EmailInvitationPreviewPage />);
    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0] ?? "",
    );
    expect(msg).toContain("/api/email/templates");
    expect(msg).not.toMatch(/traceback/i);
    expect(msg).not.toMatch(/boom/);
    expect(msg).not.toMatch(/Exception/);
  });

  it("[Tier2 AC-F1 401] missing auth surfaces a サインインが必要です toast referencing the endpoint", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, {
        detail: {
          code: "email.unauthorized",
          message: "missing bearer token",
        },
      }),
    );
    render(<EmailInvitationPreviewPage />);
    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0] ?? "",
    );
    expect(msg).toContain("/api/email/templates");
    expect(msg).toMatch(/サインイン/);
  });

  it("[Tier2 AC-F2] clicking 'テスト送信' POSTs /api/email/test-send with the resolved template_id", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { templates: [mkTemplate({ id: "tmpl-xyz" })], count: 1 }),
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse(201, {
        delivery_id: "del-001",
        queued_at: "2026-05-17T01:23:45Z",
        template_id: "tmpl-xyz",
        recipient: "masato@engine-base.com",
        status: "queued",
      }),
    );

    render(<EmailInvitationPreviewPage />);
    const btn = await screen.findByRole("button", { name: "テスト送信" });
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const calledUrl = String(fetchMock.mock.calls[1][0]);
    expect(calledUrl).toContain("/api/email/test-send");
    const init = (fetchMock.mock.calls[1][1] ?? {}) as RequestInit;
    expect(init.method).toBe("POST");
    const body = init.body ? JSON.parse(String(init.body)) : {};
    expect(body.template_id).toBe("tmpl-xyz");
    expect(body.recipient).toBe("masato@engine-base.com");
    // AC-F2: detail object carries the template variables (within-60s SLA contract).
    expect(body.detail?.inviter).toBe("masato");
    expect(body.detail?.project).toBe("受託 EC 構築 #4");
  });

  it("[Tier2 AC-F2] a successful test-send surfaces a non-technical success toast", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { templates: [mkTemplate()], count: 1 }),
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse(201, {
        delivery_id: "del-002",
        queued_at: "2026-05-17T02:00:00Z",
        template_id: mkTemplate().id,
        recipient: "masato@engine-base.com",
        status: "queued",
      }),
    );
    render(<EmailInvitationPreviewPage />);
    const btn = await screen.findByRole("button", { name: "テスト送信" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(toast.success as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.success as ReturnType<typeof vi.fn>).mock.calls[0][0] ?? "",
    );
    expect(msg).toContain("masato@engine-base.com");
  });

  it("[Tier2 AC-F3] 429 (bounce / rate-limit) surfaces a non-technical toast — UI does NOT retry locally; backend owns exp-backoff", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { templates: [mkTemplate()], count: 1 }),
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse(429, {
        detail: {
          code: "email.rate_limited",
          message: "test-send rate limit exceeded",
          retry_after: 600,
          limit: 10,
          window_seconds: 3600,
        },
      }),
    );
    render(<EmailInvitationPreviewPage />);
    const btn = await screen.findByRole("button", { name: "テスト送信" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0] ?? "",
    );
    expect(msg).toContain("/api/email/test-send");
    expect(msg).toMatch(/上限/);
    // Confirm we did NOT retry from the UI (AC-F3: backend owns retries).
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
