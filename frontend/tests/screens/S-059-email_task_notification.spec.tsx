/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-20 / S-059 — タスク通知 Email template preview spec.
 *
 * Runner: `pnpm vitest run frontend/tests/screens/S-059-email_task_notification.spec.tsx`
 * (AC-R1 target: >= 5 test cases PASS).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 * are *runtime-only* devDeps added by the Wave 2 frontend test harness ticket
 * (T-FOUNDATION-08 / package.json drift). Once installed the suite runs as-is
 * with no further code changes — see frontend/tests/screens/S-057-email_password_reset.spec.tsx
 * for the established baseline drift policy adopted by sibling T-V3-C-17..21
 * email-preview tasks.
 *
 * Covers (mapped to T-V3-C-20 acceptance_criteria):
 *   structural.AC-S1 -> "renders root with data-screen-id=S-059"
 *   structural.AC-S2 -> "h1 reads 'タスク assigned'"
 *   functional.AC-F1 -> "4xx/5xx → non-technical toast w/ endpoint, no stack"
 *   functional.AC-F1 -> "500 normalises to 'サーバーで一時的なエラー' (no stack)"
 *   functional.AC-F2 -> "subject + From/To/Body mirror the recipient email (60s SLA chip rendered)"
 *   functional.AC-F3 -> "test-send dialog posts to /api/email/test-send w/ selected template id"
 *   functional.AC-F3 -> "bounce-policy chip documents 3 retries + exponential backoff"
 *   regression.extra -> "loading state surfaces role=status"
 *   regression.extra -> "EmailApiError carries endpoint + status, no stack in string form"
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
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import S059EmailTaskNotificationPreviewPage from "@/app/(email)/task-notification/page";
import { EmailApiError } from "@/api/email";

let fetchMock: ReturnType<typeof vi.fn>;

const TEMPLATE_FIXTURE = {
  templates: [
    {
      id: "99999999-aaaa-bbbb-cccc-dddddddddddd",
      name: "task_notification",
      subject: "【Build-Factory】タスクが割り当てられました: {{task_id}}",
      body_html: "<h1>タスク assigned</h1>",
      body_text: "タスク assigned",
      variables: ["task_id", "task_title", "due_date", "estimate_hours"],
    },
    {
      id: "11111111-2222-3333-4444-555555555555",
      name: "password_reset",
      subject: "パスワード再設定",
    },
  ],
};

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  cleanup();
});

describe("S-059 タスク通知 email preview (T-V3-C-20)", () => {
  it("[Tier1 AC-S1] renders root element with data-screen-id=\"S-059\" + meta", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(TEMPLATE_FIXTURE));
    const { container } = render(<S059EmailTaskNotificationPreviewPage />);

    const root = container.querySelector('[data-screen-id="S-059"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-028");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-20");
  });

  it("[Tier1 AC-S2] displays an h1 with screens.json[S-059].h1_text (\"タスク assigned\")", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(TEMPLATE_FIXTURE));
    render(<S059EmailTaskNotificationPreviewPage />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
        "タスク assigned",
      );
    });
  });

  it("[Tier2 AC-F1] on 422, surfaces a non-technical error toast with endpoint label and no stack trace", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail:
            "Traceback (most recent call last):\n  File '/srv/email.py', line 12\n    raise SQLError('db dead')",
        }),
        { status: 422, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(<S059EmailTaskNotificationPreviewPage />);

    const toast = await screen.findByTestId("error-toast");
    expect(toast.textContent).toContain("GET /api/email/templates");
    expect(toast.textContent).not.toMatch(/Traceback|SQLError|srv\/email\.py/);
  });

  it("[Tier2 AC-F1 extra] on 500, error copy is generic and never leaks server detail", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("Internal Server Error", { status: 500 }),
    );
    render(<S059EmailTaskNotificationPreviewPage />);

    const toast = await screen.findByTestId("error-toast");
    expect(toast.textContent).toContain("サーバーで一時的なエラー");
    expect(toast.textContent).not.toMatch(/Traceback|router\.py/);
  });

  it("[Tier2 AC-F2] mirrors mock recipient view: From/To/Subject + task meta fields + 60s SLA chip", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(TEMPLATE_FIXTURE));
    render(<S059EmailTaskNotificationPreviewPage />);

    const preview = await screen.findByTestId("email-preview");
    expect(preview.textContent).toContain("noreply@engine-base.com");
    expect(preview.textContent).toContain("masato@engine-base.com");
    expect(preview.textContent).toContain("T-V3-AUTH-08");

    const meta = await screen.findByTestId("task-meta");
    expect(meta.textContent).toContain("タスク ID");
    expect(meta.textContent).toContain("/login page.tsx 実装");
    expect(meta.textContent).toContain("Build-Factory dogfood");

    // AC-F2 — 60-second SLA chip visible to the operator.
    const sla = await screen.findByTestId("sla-chip");
    expect(sla.textContent).toContain("60 秒以内");
  });

  it("[Tier2 AC-F3] test-send dialog posts to /api/email/test-send w/ selected template id", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(TEMPLATE_FIXTURE))
      .mockResolvedValueOnce(
        jsonResponse({ message_id: "msg_abc", status: "queued" }),
      );
    const user = userEvent.setup();
    render(<S059EmailTaskNotificationPreviewPage />);

    await screen.findByTestId("email-preview");

    await user.type(
      screen.getByLabelText(/送信先メールアドレス/),
      "admin@example.com",
    );
    await user.click(screen.getByTestId("test-send-button"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, opts] = fetchMock.mock.calls[1];
    expect(String(url)).toMatch(/\/api\/email\/test-send$/);
    expect(opts.method).toBe("POST");
    const body = JSON.parse(opts.body);
    expect(body.template_id).toBe(TEMPLATE_FIXTURE.templates[0].id);
    expect(body.to).toBe("admin@example.com");

    await screen.findByTestId("test-send-success");
  });

  it("[Tier2 AC-F3 extra] bounce-policy chip documents 3 retries + exponential backoff", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(TEMPLATE_FIXTURE));
    render(<S059EmailTaskNotificationPreviewPage />);

    const chip = await screen.findByTestId("bounce-policy");
    expect(chip.textContent).toContain("3 回");
    expect(chip.textContent).toContain("バックオフ");
  });

  it("[Regression] loading state exposes role=status before the fetch resolves", async () => {
    let resolveFn;
    fetchMock.mockReturnValueOnce(
      new Promise((res) => {
        resolveFn = res;
      }),
    );
    render(<S059EmailTaskNotificationPreviewPage />);

    expect(screen.getByTestId("loading-state").getAttribute("role")).toBe(
      "status",
    );

    resolveFn(jsonResponse(TEMPLATE_FIXTURE));
    await screen.findByTestId("email-preview");
  });

  it("[API client unit] EmailApiError carries endpoint + status and stringifies without stack", () => {
    const err = new EmailApiError("POST /api/email/test-send", 429, "limit");
    expect(err.endpoint).toBe("POST /api/email/test-send");
    expect(err.status).toBe(429);
    expect(String(err)).not.toContain("Traceback");
    expect(String(err)).not.toContain("at Object.");
  });
});
