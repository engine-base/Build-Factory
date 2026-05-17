"use client";

/**
 * S-056 サインアップ確認メール — T-V3-C-17 / F-028.
 *
 * @screen-id S-056
 * @feature-id F-028
 * @task-ids T-V3-C-17
 * @entities E-043
 * @phase Phase 1B
 *
 * Implements the v3 email-template preview screen documented at:
 *   docs/mocks/2026-05-15_v3/email/S-056-email-signup-verify.html
 *
 * Mock parity (逐語 — see screens.json[S-056]):
 *   - h1 text  : "ようこそ、masato さん"  (screens.json[S-056].h1_text)
 *   - 状態     : loading / loaded / error (screens.json[S-056].states)
 *   - layout   : email-template (mail-client frame, sidebar bypassed via the
 *                (email) route group layout).
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-17.md):
 *   structural.AC-S1 (data-screen-id="S-056")        — root <div>.
 *   structural.AC-S2 (h1 == "ようこそ、masato さん") — page heading.
 *   functional.AC-F1 (4xx/5xx -> non-technical toast referencing endpoint)
 *     — `EmailApiError.toUserMessage()` consumed via local `errorMessage`.
 *   functional.AC-F2 (workspace invitation → email_invitation within 60s)
 *     — backend AC (cron / Resend queue, T-V3-B-30 / EMAIL-01). UI surface:
 *     the preview shows the rendered template content the backend will send.
 *   functional.AC-F3 (bounce → 3 retries with exponential backoff)
 *     — backend AC (delivery retry worker). UI surface: render the active
 *     template body so admins can verify the wording before any retry.
 */

import * as React from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Factory,
  Mail,
  RefreshCw,
} from "lucide-react";

import {
  EMAIL_TEMPLATES_ENDPOINT,
  EmailApiError,
  findSignupVerifyTemplate,
  listEmailTemplates,
  type EmailTemplate,
} from "@/api/email";

// --------------------------------------------------------------------------
// Defaults (mock parity) — used when no template row is returned, so the
// preview still renders the canonical wording that ships with the codebase.
// --------------------------------------------------------------------------

const DEFAULT_SUBJECT = "【Build-Factory】メールアドレス認証のお願い";
const DEFAULT_RECIPIENT_DISPLAY = "masato@engine-base.com";
const DEFAULT_SENDER_DISPLAY = "noreply@engine-base.com (Build-Factory)";
const DEFAULT_VERIFY_LINK_HOST = "https://build-factory-nine.vercel.app";

/** Strip simple HTML tags and decode the most common entities for the preview body fallback. */
function htmlToText(html: string | undefined | null): string {
  if (!html) return "";
  return html
    .replace(/<br\s*\/?>(?=\s|$|<)/gi, "\n")
    .replace(/<\/(p|div|li|h1|h2|h3)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .trim();
}

/** Resolve preview body text from a template row, with sensible fallbacks. */
function resolveBodyText(tpl: EmailTemplate | null): string {
  if (!tpl) {
    return [
      "Build-Factory にサインアップいただきありがとうございます。",
      "下記ボタンをクリックしてメールアドレスを認証してください。",
    ].join("\n");
  }
  if (typeof tpl.body_text === "string" && tpl.body_text.trim().length > 0) {
    return tpl.body_text;
  }
  if (typeof tpl.body_md === "string" && tpl.body_md.trim().length > 0) {
    return tpl.body_md;
  }
  const fromHtml = htmlToText(tpl.body_html);
  if (fromHtml.length > 0) return fromHtml;
  return "(本文未設定のテンプレートです)";
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function EmailSignupVerifyPreviewPage() {
  const [templates, setTemplates] = React.useState<EmailTemplate[] | null>(
    null,
  );
  const [loading, setLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  // ----------------------------------------------------------------------
  // AC-F1 helper: surface a non-technical message referencing the failing
  // endpoint without leaking server stack traces.
  // ----------------------------------------------------------------------
  const surfaceError = React.useCallback(
    (err: unknown, fallbackEndpoint: string) => {
      const msg =
        err instanceof EmailApiError
          ? err.toUserMessage()
          : `通信に失敗しました (${fallbackEndpoint})`;
      setErrorMessage(msg);
    },
    [],
  );

  const loadTemplates = React.useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await listEmailTemplates();
      setTemplates(res.templates ?? []);
    } catch (err) {
      surfaceError(err, EMAIL_TEMPLATES_ENDPOINT);
      setTemplates(null);
    } finally {
      setLoading(false);
    }
  }, [surfaceError]);

  React.useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  const signupTpl = React.useMemo(
    () => findSignupVerifyTemplate(templates ?? undefined),
    [templates],
  );

  const subject = signupTpl?.subject?.trim() || DEFAULT_SUBJECT;
  const bodyText = resolveBodyText(signupTpl);

  return (
    <div
      data-screen-id="S-056"
      data-feature-id="F-028"
      data-task-ids="T-V3-C-17"
      data-entities="E-043"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-100 py-8 px-4"
    >
      {/* Back-to-index style anchor, matches mock corner control. */}
      <a
        href="/dashboard"
        data-testid="back-to-dashboard"
        className="fixed top-3 right-3 z-50 inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/95 border border-slate-200 rounded-md text-xs font-semibold text-eb-500 shadow-sm hover:bg-white"
      >
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
        ダッシュボードに戻る
      </a>

      {/* Header / preview controls (NOT inside the mail frame). */}
      <div className="max-w-[640px] mx-auto mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Mail className="w-3.5 h-3.5" aria-hidden />
          <span>email_signup_verify · template preview</span>
        </div>
        <button
          type="button"
          data-testid="reload-template"
          onClick={() => void loadTemplates()}
          disabled={loading}
          aria-busy={loading}
          className="bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs h-7 px-2.5 rounded-md font-semibold flex items-center gap-1.5 disabled:opacity-50"
        >
          <RefreshCw className="w-3.5 h-3.5" aria-hidden />
          {loading ? "読み込み中…" : "再読み込み"}
        </button>
      </div>

      {/* Error banner (AC-F1) */}
      {errorMessage && (
        <div
          role="alert"
          data-testid="email-template-error"
          className="max-w-[640px] mx-auto mb-4 p-3 rounded-md bg-amber-50 border border-amber-300 text-amber-800 text-xs flex items-start gap-2"
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Mail-client preview frame (matches mock S-056) */}
      <div
        className="max-w-[640px] mx-auto bg-white rounded-lg shadow-sm overflow-hidden"
        data-testid="email-preview-frame"
      >
        {/* Mail headers */}
        <div className="border-b border-slate-200 p-4 bg-slate-50">
          <div className="text-xs text-slate-500 space-y-1">
            <div>
              <strong>From:</strong> {DEFAULT_SENDER_DISPLAY}
            </div>
            <div>
              <strong>To:</strong> {DEFAULT_RECIPIENT_DISPLAY}
            </div>
            <div>
              <strong>Subject:</strong>{" "}
              <span data-testid="email-subject">{subject}</span>
            </div>
          </div>
        </div>

        {/* Email body */}
        <div className="bg-white">
          <div className="bg-eb-500 px-8 py-5 text-white">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-md bg-white/20 flex items-center justify-center">
                <Factory className="w-4 h-4" aria-hidden />
              </div>
              <span className="text-base font-bold">Build-Factory</span>
            </div>
          </div>

          <div className="px-8 py-6">
            {/* Visible greeting heading inside the rendered mail (mock parity).
                AC-S2: this is the single <h1> matching screens.json[S-056].h1_text. */}
            <h1
              className="text-xl font-bold mb-3"
              data-testid="email-greeting"
            >
              ようこそ、masato さん
            </h1>

            {loading && !templates && (
              <div
                className="text-xs text-slate-500"
                data-testid="email-template-loading"
              >
                テンプレート読み込み中…
              </div>
            )}

            {!loading && (
              <>
                <p
                  className="text-sm leading-relaxed text-slate-700 mb-4 whitespace-pre-line"
                  data-testid="email-body"
                >
                  {bodyText}
                </p>

                <div className="text-center my-6">
                  <a
                    data-testid="email-verify-button"
                    href={`${DEFAULT_VERIFY_LINK_HOST}/verify?token=preview`}
                    className="inline-block bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold px-8 py-3 rounded-md no-underline"
                  >
                    メールアドレスを認証する
                  </a>
                </div>

                <div className="text-xs text-slate-500 leading-relaxed bg-slate-50 border border-slate-200 rounded-md p-3">
                  <strong>ボタンが動かない場合</strong>
                  はこの URL をブラウザに貼り付け:
                  <br />
                  <code
                    className="text-eb-500 break-all mono"
                    data-testid="email-verify-link"
                  >
                    {`${DEFAULT_VERIFY_LINK_HOST}/verify?token=eyJhbGciOi...`}
                  </code>
                </div>

                <div className="text-xs text-slate-500 mt-4 pt-4 border-t border-slate-200">
                  このリンクは <strong>24 時間</strong> 有効です。
                  <br />
                  心当たりがない場合はこのメールを無視してください。
                </div>
              </>
            )}
          </div>

          <div className="bg-slate-50 px-8 py-4 text-center text-[11px] text-slate-500">
            <div>© 2026 株式会社 ENGINE BASE</div>
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
      </div>

      {/* Template metadata footer (admin-only, mock-aligned helper info). */}
      <div className="max-w-[640px] mx-auto mt-4 text-[11px] text-slate-500 font-mono">
        template_name: {signupTpl?.name ?? "signup_verify"} · locale:{" "}
        {signupTpl?.locale ?? "ja"} · source: {EMAIL_TEMPLATES_ENDPOINT}
      </div>
    </div>
  );
}
