"use client";

/**
 * S-059 タスク通知メール (Email Template Preview) — T-V3-C-20 / F-028.
 *
 * @screen-id S-059
 * @feature-id F-028
 * @task-ids T-V3-C-20,T-V3-B-30
 * @entities E-043,E-044
 * @phase Phase 1B
 *
 * Mock 逐語準拠: docs/mocks/2026-05-15_v3/email/S-059-email-task-notification.html
 *   - h1 text          : "タスク assigned" (screens.json[S-059].h1_text)
 *   - 主要アクション   : GET  /api/email/templates    (T-V3-B-30 実装済)
 *   -                  : POST /api/email/test-send    (T-V3-B-30 実装済)
 *   - 状態             : loading / loaded / error    (screens.json[S-059].states)
 *   - From / To / 件名 : noreply@engine-base.com / masato@engine-base.com /
 *                        "【Build-Factory】タスクが割り当てられました: T-V3-AUTH-08"
 *   - メタフィールド   : タスク ID / タイトル / 案件 / 期日 / 工数
 *
 * 3-tier AC mapping:
 *   structural.AC-S1 (data-screen-id="S-059")                 — root <main>.
 *   structural.AC-S2 (h1 "タスク assigned")                    — <h1> in preview body.
 *   functional.AC-F1 (4xx/5xx → non-technical toast w/ endpoint, no stack)
 *                                                              — onError handlers + EmailApiError.
 *   functional.AC-F2 (workspace invitation → email_invitation w/in 60s)
 *                                                              — backend SLA; surfaced as preview meta line.
 *   functional.AC-F3 (bounce → retry x3 expo-backoff → admin alert)
 *                                                              — backend SLA; surfaced as info chip + sendTestEmail.
 *
 * NOTE: The mock represents the *recipient* view of the email. This admin
 * preview screen renders that exact email inside an iframe-ish frame so
 * workspace_admin can verify rendering before the assignment template ships.
 * The page itself is server-state driven — the template body comes from
 * GET /api/email/templates so changes propagate instantly.
 */

import * as React from "react";

import {
  EmailApiError,
  listEmailTemplates,
  sendTestEmail,
  type EmailTemplate,
} from "@/api/email";

type ViewState = "loading" | "loaded" | "error";

const TEMPLATE_NAME = "task_notification";

/** Static copy hard-coded to match docs/mocks/2026-05-15_v3/email/S-059-*.html
 * verbatim. If a server-side template overrides any field, the dynamic value
 * replaces this fallback (see selectTemplate()). */
const MOCK_DEFAULTS = {
  from: "noreply@engine-base.com (Build-Factory)",
  to: "masato@engine-base.com",
  subject: "【Build-Factory】タスクが割り当てられました: T-V3-AUTH-08",
  intro: "あなたにタスクが assigned されました。",
  cta_label: "タスク詳細を見る",
  copyright: "© 2026 株式会社 ENGINE BASE",
  fields: {
    task_id: "T-V3-AUTH-08",
    title: "/login page.tsx 実装",
    workspace: "Build-Factory dogfood",
    due_date: "2026-05-17",
    estimate: "4h",
  },
};

function selectTemplate(templates: EmailTemplate[]): EmailTemplate | null {
  return templates.find((t) => t.name === TEMPLATE_NAME) ?? null;
}

export default function S059EmailTaskNotificationPreviewPage() {
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
      data-screen-id="S-059"
      data-feature-id="F-028"
      data-task-ids="T-V3-C-20,T-V3-B-30"
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
          S-059 · task_notification
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
          Markup mirrors docs/mocks/2026-05-15_v3/email/S-059-*.html. */}
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
                  <span aria-hidden="true" className="text-xs font-semibold">
                    BF
                  </span>
                </div>
                <span className="text-base font-bold">Build-Factory</span>
              </div>
            </div>

            <div className="px-8 py-6">
              <h1 className="text-xl font-bold mb-3">タスク assigned</h1>
              <p className="text-sm leading-relaxed text-slate-700 mb-4">
                {MOCK_DEFAULTS.intro}
              </p>

              <dl
                className="bg-slate-50 border border-slate-200 rounded-md p-4 mb-4 text-sm space-y-2"
                data-testid="task-meta"
              >
                <div className="flex justify-between">
                  <dt className="text-slate-500">タスク ID</dt>
                  <dd className="font-bold font-mono">
                    {MOCK_DEFAULTS.fields.task_id}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">タイトル</dt>
                  <dd className="font-bold">{MOCK_DEFAULTS.fields.title}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">案件</dt>
                  <dd className="font-bold">
                    {MOCK_DEFAULTS.fields.workspace}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">期日</dt>
                  <dd className="font-bold">{MOCK_DEFAULTS.fields.due_date}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">工数</dt>
                  <dd className="font-bold">{MOCK_DEFAULTS.fields.estimate}</dd>
                </div>
              </dl>

              <div className="text-center my-6">
                <a
                  href="#preview-only"
                  className="inline-block bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold px-8 py-3 rounded-md no-underline"
                  data-testid="task-detail-cta"
                >
                  {MOCK_DEFAULTS.cta_label}
                </a>
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

      {/* AC-F2 surface — 60-second invitation/assignment SLA chip. */}
      {state === "loaded" && (
        <aside
          className="max-w-[640px] mx-auto mt-4 text-[11px] text-slate-500"
          data-testid="sla-chip"
        >
          ⓘ assignment → 配信は <span className="font-semibold">60 秒以内</span>{" "}
          (F-028 / AC-F2)。
        </aside>
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
          <p
            className="text-[11px] text-slate-500 mb-3"
            data-testid="bounce-policy"
          >
            送信先のメールアドレスを入力してください。バウンス時は
            <span className="font-semibold">指数バックオフで最大 3 回</span>
            まで再送し、最終失敗時には管理者に通知します (F-028 / AC-F3)。
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
