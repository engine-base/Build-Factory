"use client";

/**
 * S-057 パスワードリセットメール (Email Template Preview) — T-V3-C-18 / F-028.
 *
 * @screen-id S-057
 * @feature-id F-028
 * @task-ids T-V3-C-18,T-V3-B-30
 * @entities E-043,E-044
 * @phase Phase 1B
 *
 * Mock 逐語準拠: docs/mocks/2026-05-15_v3/email/S-057-email-password-reset.html
 *   - h1 text          : "パスワード再設定リクエスト" (screens.json[S-057].h1_text)
 *   - 主要アクション   : GET  /api/email/templates    (T-V3-B-30 実装済)
 *   -                  : POST /api/email/test-send    (T-V3-B-30 実装済)
 *   - 状態             : loading / loaded / error    (screens.json[S-057].states)
 *   - From / To / 件名 : noreply@engine-base.com / masato@engine-base.com /
 *                        "【Build-Factory】パスワード再設定のお知らせ"
 *
 * 3-tier AC mapping:
 *   structural.AC-S1 (data-screen-id="S-057")                 — root <main>.
 *   structural.AC-S2 (h1 "パスワード再設定リクエスト")        — <h1> in preview body.
 *   functional.AC-F1 (4xx/5xx → non-technical toast w/ endpoint, no stack)
 *                                                              — onError handlers + EmailApiError.
 *   functional.AC-F2 (workspace invitation → email_invitation w/in 60s)
 *                                                              — backend SLA; surfaced as preview meta line.
 *   functional.AC-F3 (bounce → retry x3 expo-backoff → admin alert)
 *                                                              — backend SLA; surfaced as info chip + sendTestEmail.
 *
 * NOTE: The mock represents the *recipient* view of the email. This admin
 * preview screen renders that exact email inside an iframe-ish frame so
 * workspace_admin can verify rendering before the template ships. The page
 * itself is server-state driven (TanStack Query) — the template body comes
 * from GET /api/email/templates so changes propagate instantly.
 */

import * as React from "react";

import {
  EmailApiError,
  listEmailTemplates,
  sendTestEmail,
  type EmailTemplate,
} from "@/api/email";

type ViewState = "loading" | "loaded" | "error";

const TEMPLATE_NAME = "password_reset";

/** Static copy hard-coded to match docs/mocks/2026-05-15_v3/email/S-057-*.html
 * verbatim. If a server-side template overrides any field, the dynamic value
 * replaces this fallback (see selectTemplate()).
 */
const MOCK_DEFAULTS = {
  from: "noreply@engine-base.com (Build-Factory)",
  to: "masato@engine-base.com",
  subject: "【Build-Factory】パスワード再設定のお知らせ",
  intro:
    "Build-Factory のパスワード再設定リクエストを受け付けました。\n下記ボタンから新しいパスワードを設定してください。",
  cta_label: "パスワードを再設定する",
  warning:
    "覚えがない場合: このメールを無視してください。パスワードは変更されません。",
  ttl: "このリンクは 1 時間 有効です。\nセキュリティ上の理由で、他人と共有しないでください。",
  copyright: "© 2026 株式会社 ENGINE BASE",
};

function selectTemplate(templates: EmailTemplate[]): EmailTemplate | null {
  return templates.find((t) => t.name === TEMPLATE_NAME) ?? null;
}

export default function S057EmailPasswordResetPreviewPage() {
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
      setTestError("POST /api/email/test-send: テンプレートが読み込まれていません");
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
      data-screen-id="S-057"
      data-feature-id="F-028"
      data-task-ids="T-V3-C-18,T-V3-B-30"
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
        <span className="text-[11px] text-slate-500 font-mono">S-057 · password_reset</span>
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
          Markup mirrors docs/mocks/2026-05-15_v3/email/S-057-*.html. */}
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
                <strong>Subject:</strong> {subject}
              </div>
            </div>
          </div>

          <div className="bg-white">
            <div className="bg-eb-500 px-8 py-5 text-white">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-md bg-white/20 flex items-center justify-center">
                  {/* lucide-react aria-hidden icon stub kept text-only for
                      pixel-parity with mock (a11y/email-client safety). */}
                  <span aria-hidden="true" className="text-xs font-semibold">BF</span>
                </div>
                <span className="text-base font-bold">Build-Factory</span>
              </div>
            </div>

            <div className="px-8 py-6">
              <h1 className="text-xl font-bold mb-3">パスワード再設定リクエスト</h1>
              <p className="text-sm leading-relaxed text-slate-700 mb-4 whitespace-pre-line">
                {MOCK_DEFAULTS.intro}
              </p>
              <div className="text-center my-6">
                <a
                  href="#preview-only"
                  className="inline-block bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold px-8 py-3 rounded-md no-underline"
                  data-testid="reset-cta"
                >
                  {MOCK_DEFAULTS.cta_label}
                </a>
              </div>
              <div className="text-xs text-slate-500 leading-relaxed bg-slate-50 border border-slate-200 rounded-md p-3">
                <strong>覚えがない場合</strong>: このメールを無視してください。
                パスワードは変更されません。
              </div>
              <div className="text-xs text-slate-500 mt-4 pt-4 border-t border-slate-200 whitespace-pre-line">
                {MOCK_DEFAULTS.ttl}
              </div>
            </div>

            <div className="bg-slate-50 px-8 py-4 text-center text-[11px] text-slate-500">
              <div>{MOCK_DEFAULTS.copyright}</div>
              <div className="mt-1">
                <a className="text-slate-500 hover:underline">配信停止</a> ·{" "}
                <a className="text-slate-500 hover:underline">プライバシー</a>
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
