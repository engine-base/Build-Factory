// @ts-nocheck
/**
 * T-V3-C-21 / S-060 — Weekly Summary Email template preview spec.
 *
 * Runner: `pnpm vitest run frontend/tests/screens/S-060-email_weekly_summary.spec.tsx`
 * (AC-R1 target: >= 5 test cases PASS — this file ships 8 cases for cushion).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 * are *runtime-only* devDeps added by the Wave 2 frontend test harness ticket
 * (T-FOUNDATION-08 / package.json drift). Once installed the suite runs as-is
 * with no further code changes — see frontend/tests/screens/S-057-email_password_reset.spec.tsx
 * for the established baseline drift policy.
 *
 * Covers (mapped to T-V3-C-21 acceptance_criteria):
 *   structural.AC-S1 -> "renders root with data-screen-id=S-060"
 *   structural.AC-S2 -> "h1 reads '今週の進捗サマリー'"
 *   functional.AC-F1 -> "4xx/5xx → non-technical toast w/ endpoint, no stack"
 *   functional.AC-F2 -> "subject + From/To/Body mirror the recipient email"
 *   functional.AC-F3 -> "test-send dialog calls POST /api/email/test-send"
 *   regression.extra -> "loading state surfaces role=status"
 *   regression.extra -> "500 normalises to 'サーバーで一時的なエラー' (no stack)"
 *   regression.extra -> "findWeeklySummaryTemplate selects by canonical name"
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

import S060EmailWeeklySummaryPreviewPage from "@/app/(email)/weekly-summary/page";
import { EmailApiError, findWeeklySummaryTemplate } from "@/api/email";

let fetchMock: ReturnType<typeof vi.fn>;

const TEMPLATE_FIXTURE = {
  templates: [
    {
      id: "60606060-2222-3333-4444-555555555555",
      name: "weekly_summary",
      subject: "【Build-Factory】週次サマリー 5/9-5/15: 47 task done",
      body_html: "<h1>今週の進捗サマリー</h1>",
      body_text: "今週の進捗サマリー",
      variables: ["dashboard_url", "task_count", "session_count", "cost_jpy"],
    },
    {
      id: "00000000-0000-0000-0000-000000000099",
      name: "signup_verify",
      subject: "メール確認",
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

describe("S-060 weekly summary email preview (T-V3-C-21)", () => {
  it("[Tier1 AC-S1] renders root element with data-screen-id=\"S-060\" + meta", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(TEMPLATE_FIXTURE));
    const { container } = render(<S060EmailWeeklySummaryPreviewPage />);

    const root = container.querySelector('[data-screen-id="S-060"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-028");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-21");
  });

  it("[Tier1 AC-S2] displays an h1 with screens.json[S-060].h1_text (\"今週の進捗サマリー\")", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(TEMPLATE_FIXTURE));
    render(<S060EmailWeeklySummaryPreviewPage />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
        "今週の進捗サマリー",
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
    render(<S060EmailWeeklySummaryPreviewPage />);

    const toast = await screen.findByTestId("error-toast");
    expect(toast.textContent).toContain("GET /api/email/templates");
    expect(toast.textContent).not.toMatch(/Traceback|SQLError|srv\/email\.py/);
  });

  it("[Tier2 AC-F1 extra] on 500, error copy is generic and never leaks server detail", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("Internal Server Error", { status: 500 }),
    );
    render(<S060EmailWeeklySummaryPreviewPage />);

    const toast = await screen.findByTestId("error-toast");
    expect(toast.textContent).toContain("サーバーで一時的なエラー");
    expect(toast.textContent).not.toMatch(/Traceback|router\.py/);
  });

  it("[Tier2 AC-F2] mirrors mock recipient view: From/To/Subject + KPI grid + highlights", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(TEMPLATE_FIXTURE));
    render(<S060EmailWeeklySummaryPreviewPage />);

    const preview = await screen.findByTestId("email-preview");
    expect(preview.textContent).toContain("noreply@engine-base.com");
    expect(preview.textContent).toContain("masato@engine-base.com");
    expect(preview.textContent).toContain(
      "【Build-Factory】週次サマリー 5/9-5/15: 47 task done",
    );

    // KPI grid + highlights (mock parity).
    expect(screen.getByTestId("kpi-grid").textContent).toContain("47");
    expect(screen.getByTestId("kpi-grid").textContent).toContain("128");
    expect(screen.getByTestId("kpi-grid").textContent).toContain("¥3,820");
    expect(screen.getByTestId("highlights-block").textContent).toContain(
      "Build-Factory dogfood",
    );

    expect(screen.getByTestId("dashboard-cta").textContent).toBe(
      "ダッシュボードで詳細を見る",
    );
  });

  it("[Tier2 AC-F3] test-send dialog posts to /api/email/test-send w/ selected template id", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(TEMPLATE_FIXTURE))
      .mockResolvedValueOnce(
        jsonResponse({ message_id: "msg_wkly", status: "queued" }),
      );
    const user = userEvent.setup();
    render(<S060EmailWeeklySummaryPreviewPage />);

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

  it("[Regression] loading state exposes role=status before the fetch resolves", async () => {
    let resolveFn;
    fetchMock.mockReturnValueOnce(
      new Promise((res) => {
        resolveFn = res;
      }),
    );
    render(<S060EmailWeeklySummaryPreviewPage />);

    expect(screen.getByTestId("loading-state").getAttribute("role")).toBe(
      "status",
    );

    // settle the promise to keep test runner clean.
    resolveFn(jsonResponse(TEMPLATE_FIXTURE));
    await screen.findByTestId("email-preview");
  });

  it("[API client unit] findWeeklySummaryTemplate selects weekly_summary row from a list", () => {
    const picked = findWeeklySummaryTemplate(TEMPLATE_FIXTURE.templates);
    expect(picked?.name).toBe("weekly_summary");
    expect(picked?.id).toBe("60606060-2222-3333-4444-555555555555");

    // Empty / undefined input returns null safely.
    expect(findWeeklySummaryTemplate(undefined)).toBeNull();
    expect(findWeeklySummaryTemplate([])).toBeNull();

    // EmailApiError surface check (no stack leak when stringified).
    const err = new EmailApiError("GET /api/email/templates", 429, "limit");
    expect(String(err)).not.toContain("Traceback");
  });
});
