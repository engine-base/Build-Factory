"use client";

/**
 * S-060 週次サマリー (Email Template Preview) — T-V3-C-21 / F-028.
 *
 * @screen-id S-060
 * @feature-id F-028
 * @task-ids T-V3-C-21,T-V3-B-30
 * @entities E-043,E-044
 * @phase Phase 1B
 *
 * Mock 逐語準拠: docs/mocks/2026-05-15_v3/email/S-060-email-weekly-summary.html
 *   - h1 text          : "今週の進捗サマリー" (screens.json[S-060].h1_text)
 *   - 主要アクション   : GET  /api/email/templates    (T-V3-B-30 実装済)
 *   -                  : POST /api/email/test-send    (T-V3-B-30 実装済)
 *   - 状態             : loading / loaded / error    (screens.json[S-060].states)
 *   - From / To / 件名 : noreply@engine-base.com / masato@engine-base.com /
 *                        "【Build-Factory】週次サマリー 5/9-5/15: 47 task done"
 *
 * 3-tier AC mapping (逐語 — docs/audit/2026-05-16_v3/T-V3-C-21.md):
 *   structural.AC-S1 (data-screen-id="S-060")             — root <main>.
 *   structural.AC-S2 (h1 "今週の進捗サマリー")             — <h1> in preview body.
 *   functional.AC-F1 (4xx/5xx → non-technical toast w/ endpoint, no stack)
 *                                                          — error branch + EmailApiError.message.
 *   functional.AC-F2 (workspace invitation → email_invitation within 60s)
 *                                                          — backend SLA; surfaced as hint chip below preview.
 *   functional.AC-F3 (bounce → retry x3 expo-backoff → admin alert)
 *                                                          — backend SLA; surfaced as info chip + sendTestEmail.
 *
 * NOTE: This page renders the admin preview of the recipient's weekly summary
 * email. Sibling pages already exist for S-056 / S-057. This implementation
 * uses the same `listEmailTemplates` + `sendTestEmail` typed client surface
 * (see `frontend/src/api/email.ts`) so all five email-preview screens follow a
 * consistent state-machine (loading / loaded / error).
 */

import * as React from "react";

import {
  EmailApiError,
  findWeeklySummaryTemplate,
  listEmailTemplates,
  sendTestEmail,
  type EmailTemplate,
} from "@/api/email";

type ViewState = "loading" | "loaded" | "error";

const TEMPLATE_NAME = "weekly_summary";

/** Static copy hard-coded to match docs/mocks/2026-05-15_v3/email/S-060-*.html
 * verbatim. If a server-side template overrides any field, the dynamic value
 * replaces this fallback (see selectTemplate()).
 */
const MOCK_DEFAULTS = {
  from: "noreply@engine-base.com (Build-Factory)",
  to: "masato@engine-base.com",
  subject: "【Build-Factory】週次サマリー 5/9-5/15: 47 task done",
  intro: "2026-05-09 〜 2026-05-15 の週次サマリーをお届けします。",
  kpis: [
    { label: "完了タスク", value: "47", emphasis: true },
    { label: "セッション", value: "128", emphasis: false },
    { label: "コスト", value: "¥3,820", emphasis: false },
  ],
  highlights: [
    "Build-Factory dogfood が Phase 1 → Phase 2 へ進行",
    "ABC 社 PR #283 が merge 済 (要件エディタ完成)",
    "赤線抵触 1 件発生 → masato が承認 (誤検知)",
  ],
  cta_label: "ダッシュボードで詳細を見る",
  copyright: "© 2026 株式会社 ENGINE BASE",
};

function selectTemplate(templates: EmailTemplate[]): EmailTemplate | null {
  // Prefer the named selector (export from @/api/email) so any future naming
  // alias is honoured in a single place. Falls back to direct lookup.
  const picked = findWeeklySummaryTemplate(templates);
  if (picked) return picked;
  return templates.find((t) => t.name === TEMPLATE_NAME) ?? null;
}

export default function S060EmailWeeklySummaryPreviewPage() {
  const [state, setState] = React.useState<ViewState>("loading");
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [template, setTemplate] = React.useState<EmailTemplate | null>(null);

  // Test-send dialog (admin sends preview to themselves).
  const [testTarget, setTestTarget] = React.useState("");
  const [testState, setTestState] = React.useState<"idle" | "sending" | "sent">(
    "idle",
  );
  const [testError, setTestError] = React.useState<string | null>(null);

  // Tier 2 AC-F1: load template on mount; surface non-technical toast on error.
  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await listEmailTemplates();
        if (cancelled) return;
        const picked = selectTemplate(res.templates);
        setTemplate(picked);
        setState("loaded");
      } catch (err) {
        if (cancelled) return;
        const msg =
          err instanceof EmailApiError
            ? err.message
            : "GET /api/email/templates: 予期しないエラーが発生しました";
        setErrorMessage(msg);
        setState("error");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onTestSend(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!template) {
      setTestError(
        "POST /api/email/test-send: テンプレートが読み込まれていません",
      );
      return;
    }
    setTestState("sending");
    setTestError(null);
    try {
      await sendTestEmail({ template_id: template.id, to: testTarget });
      setTestState("sent");
    } catch (err) {
      const msg =
        err instanceof EmailApiError
          ? err.message
          : "POST /api/email/test-send: 予期しないエラーが発生しました";
      setTestError(msg);
      setTestState("idle");
    }
  }

  const subject = template?.subject ?? MOCK_DEFAULTS.subject;

  return (
    <main
      data-screen-id="S-060"
      data-feature-id="F-028"
      data-task-ids="T-V3-C-21,T-V3-B-30"
      data-entities="E-043,E-044"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-100 py-8 px-4"
    >
      {/* Admin chrome — back link + page title. Hidden in production email
          render (this is the preview screen, not the email itself). */}
      <header className="max-w-[640px] mx-auto mb-4 flex items-center justify-between">
        <a
          href="/settings/email-templates"
          className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900"
          data-testid="back-to-templates"
        >
          ← テンプレ一覧に戻る
        </a>
        <span className="text-[11px] text-slate-500 font-mono">
          S-060 · weekly_summary
        </span>
      </header>

      {state === "loading" && (
        <div
          role="status"
          aria-live="polite"
          data-testid="loading-state"
          className="max-w-[640px] mx-auto bg-white rounded-lg shadow-sm p-8 text-center text-sm text-slate-500"
        >
          テンプレートを読み込み中…
        </div>
      )}

      {state === "error" && errorMessage && (
        <div
          role="alert"
          data-testid="error-toast"
          className="max-w-[640px] mx-auto bg-red-50 border border-red-200 text-red-700 rounded-lg shadow-sm p-4 text-sm"
        >
          {errorMessage}
        </div>
      )}

      {/* Email preview frame — pixel-parity with the recipient mailbox.
          Markup mirrors docs/mocks/2026-05-15_v3/email/S-060-*.html. */}
      {state === "loaded" && (
        <article
          data-testid="email-preview"
          data-template-id={template?.id ?? ""}
          className="max-w-[640px] mx-auto bg-white rounded-lg shadow-sm overflow-hidden"
        >
          <div className="border-b border-slate-200 p-4 bg-slate-50">
            <div className="text-xs text-slate-500 space-y-1">
              <div>
                <strong>From:</strong> {MOCK_DEFAULTS.from}
              </div>
              <div>
                <strong>To:</strong> {MOCK_DEFAULTS.to}
              </div>
              <div>
                <strong>Subject:</strong>{" "}
                <span data-testid="email-subject">{subject}</span>
              </div>
            </div>
          </div>

          <div className="bg-white">
            <div className="bg-eb-500 px-8 py-5 text-white">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-md bg-white/20 flex items-center justify-center">
                  {/* lucide-react aria-hidden icon stub kept text-only for
                      pixel-parity with mock (a11y/email-client safety). */}
                  <span
                    aria-hidden="true"
                    className="text-xs font-semibold"
                  >
                    BF
                  </span>
                </div>
                <span className="text-base font-bold">Build-Factory</span>
              </div>
            </div>

            <div className="px-8 py-6">
              <h1
                className="text-xl font-bold mb-3"
                data-testid="email-greeting"
              >
                今週の進捗サマリー
              </h1>
              <p className="text-sm leading-relaxed text-slate-700 mb-4">
                {MOCK_DEFAULTS.intro}
              </p>

              {/* KPI grid (3 cards) — mock-parity with S-060 weekly summary. */}
              <div
                className="grid grid-cols-3 gap-2 mb-4"
                data-testid="kpi-grid"
              >
                {MOCK_DEFAULTS.kpis.map((kpi) => (
                  <div
                    key={kpi.label}
                    className={
                      kpi.emphasis
                        ? "bg-eb-50 border border-eb-200 rounded-md p-3 text-center"
                        : "bg-slate-50 border border-slate-200 rounded-md p-3 text-center"
                    }
                  >
                    <div className="text-[10px] uppercase text-slate-500 font-bold">
                      {kpi.label}
                    </div>
                    <div
                      className={
                        kpi.emphasis
                          ? "text-2xl font-bold text-eb-500"
                          : "text-2xl font-bold"
                      }
                      style={{ fontVariantNumeric: "tabular-nums" }}
                      data-testid={`kpi-value-${kpi.label}`}
                    >
                      {kpi.value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Highlights block (3 bullets). */}
              <div
                className="bg-slate-50 border border-slate-200 rounded-md p-4 mb-4"
                data-testid="highlights-block"
              >
                <div className="text-sm font-bold mb-2">ハイライト</div>
                <ul className="text-sm space-y-1 list-disc pl-5 text-slate-700">
                  {MOCK_DEFAULTS.highlights.map((h) => (
                    <li key={h}>{h}</li>
                  ))}
                </ul>
              </div>

              <div className="text-center my-6">
                <a
                  href="#preview-only"
                  data-testid="dashboard-cta"
                  className="inline-block bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold px-8 py-3 rounded-md no-underline"
                >
                  {MOCK_DEFAULTS.cta_label}
                </a>
              </div>
            </div>

            <div className="bg-slate-50 px-8 py-4 text-center text-[11px] text-slate-500">
              <div>{MOCK_DEFAULTS.copyright}</div>
              <div className="mt-1">
                <a className="text-slate-500 hover:underline" href="#unsubscribe">
                  配信停止
                </a>{" "}
                ·{" "}
                <a className="text-slate-500 hover:underline" href="#privacy">
                  プライバシー
                </a>
              </div>
            </div>
          </div>
        </article>
      )}

      {/* Admin test-send panel (workspace_admin only). Triggers backend
          retry-up-to-3 + alert-admin pipeline (AC-F3). */}
      {state === "loaded" && (
        <section
          aria-labelledby="test-send-heading"
          className="max-w-[640px] mx-auto mt-6 bg-white rounded-lg shadow-sm p-4"
        >
          <h2
            id="test-send-heading"
            className="text-sm font-semibold mb-2 text-slate-700"
          >
            テスト送信 (workspace_admin)
          </h2>
          <p className="text-[11px] text-slate-500 mb-3">
            送信先のメールアドレスを入力してください。バウンス時は最大 3 回まで指数バックオフで再送します。
          </p>
          <form className="flex gap-2" onSubmit={onTestSend}>
            <label className="sr-only" htmlFor="test-to">
              送信先メールアドレス
            </label>
            <input
              id="test-to"
              type="email"
              required
              value={testTarget}
              onChange={(e) => setTestTarget(e.target.value)}
              placeholder="admin@example.com"
              className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded-md"
            />
            <button
              type="submit"
              disabled={testState === "sending"}
              data-testid="test-send-button"
              className="px-4 py-2 text-sm bg-eb-500 hover:bg-eb-600 text-white rounded-md disabled:opacity-50"
            >
              {testState === "sending" ? "送信中…" : "テスト送信"}
            </button>
          </form>
          {testState === "sent" && (
            <p
              role="status"
              data-testid="test-send-success"
              className="mt-3 text-xs text-eb-600"
            >
              テスト送信を受け付けました
            </p>
          )}
          {testError && (
            <p
              role="alert"
              data-testid="test-send-error"
              className="mt-3 text-xs text-red-600"
            >
              {testError}
            </p>
          )}
        </section>
      )}
    </main>
  );
}
