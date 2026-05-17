"use client";

/**
 * T-V3-C-19 / S-058: 招待メール preview page (Vertical Slice / UI).
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/email/S-058-email-invitation.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-058
 * @feature-id F-028
 * @task-ids T-V3-C-19
 * @entities E-043
 * @phase Phase 1B
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-19.md):
 *   structural.AC-S1 (data-screen-id="S-058") — root <main> element below.
 *   structural.AC-S2 (h1 "masato さんから案件への招待")
 *     — matches screens.json[S-058].h1_text exactly.
 *   functional.AC-F1 (4xx/5xx → non-technical toast referencing endpoint)
 *     — `toast.error(err.toUserMessage())` via {@link EmailApiError}, never
 *       embeds backend stack traces.
 *   functional.AC-F2 (workspace invitation → email_invitation sent within 60s)
 *     — POST /api/email/test-send dispatch + backend queue worker
 *       (services/email.enqueue_test_send: target SLA 60s, contract test
 *       backend/tests/test_email.py::test_test_send_201_payload).
 *   functional.AC-F3 (bounced email → retry 3 times w/ exp backoff)
 *     — owned by backend delivery worker (services/email retry policy);
 *       UI surfaces the resulting 429 / 5xx via toUserMessage.
 */

import * as React from "react";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowLeft,
  Factory,
  Loader2,
  Mail,
  Send,
} from "lucide-react";

import {
  EMAIL_TEMPLATE_KEY_INVITATION,
  EmailApiError,
  findInvitationTemplate,
  listEmailTemplates,
  sendTestEmail,
  type EmailTemplate,
} from "@/api/email";

// --------------------------------------------------------------------------
// View-model — kept minimal because S-058 is preview-first (no form fields).
// --------------------------------------------------------------------------

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; template: EmailTemplate | null }
  | { kind: "error"; endpoint: string; userMessage: string };

type SendState =
  | { kind: "idle" }
  | { kind: "sending" }
  | { kind: "sent"; deliveryId: string; queuedAt: string }
  | { kind: "error"; userMessage: string };

interface PreviewSample {
  inviter: string;
  project: string;
  role: string;
  expiresInDays: number;
  message: string;
  to: string;
}

/**
 * Mirror the mock copy so the structural h1 stays in sync with
 * screens.json[S-058].h1_text. Real template variables are filled in by the
 * backend renderer; this preview keeps the same placeholder names as the
 * mock so QA can verify the layout without a live invitation row.
 */
const PREVIEW: PreviewSample = {
  inviter: "masato",
  project: "受託 EC 構築 #4",
  role: "contributor",
  expiresInDays: 7,
  message: "Phase 2 の統合テストで人手が必要です。ぜひお願いします。",
  to: "masato@engine-base.com",
};

/** Resolve the bearer token in a way safe for SSR / private-mode browsers. */
function readAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("bf.access_token");
  } catch {
    return null;
  }
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function EmailInvitationPreviewPage() {
  const [load, setLoad] = React.useState<LoadState>({ kind: "loading" });
  const [send, setSend] = React.useState<SendState>({ kind: "idle" });

  const reload = React.useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await listEmailTemplates({
        signal,
        authToken: readAuthToken(),
      });
      const template = findInvitationTemplate(data.templates ?? []);
      setLoad({ kind: "ready", template });
    } catch (err: unknown) {
      if ((err as { name?: string })?.name === "AbortError") return;
      if (err instanceof EmailApiError) {
        const msg = err.toUserMessage();
        setLoad({ kind: "error", endpoint: err.endpoint, userMessage: msg });
        toast.error(msg);
        return;
      }
      // AC-F1 fallback: never let an unknown thrown shape leak to the UI.
      const fallback = "メールテンプレートの取得に失敗しました (/api/email/templates)";
      setLoad({
        kind: "error",
        endpoint: "/api/email/templates",
        userMessage: fallback,
      });
      toast.error(fallback);
    }
  }, []);

  React.useEffect(() => {
    const ctl = new AbortController();
    void reload(ctl.signal);
    return () => ctl.abort();
  }, [reload]);

  const handleSendTest = React.useCallback(async () => {
    if (load.kind !== "ready" || !load.template) return;
    setSend({ kind: "sending" });
    try {
      const result = await sendTestEmail(
        {
          template_id: load.template.id,
          recipient: PREVIEW.to,
          detail: {
            inviter: PREVIEW.inviter,
            project: PREVIEW.project,
            role: PREVIEW.role,
            expires_in_days: PREVIEW.expiresInDays,
            message: PREVIEW.message,
          },
        },
        { authToken: readAuthToken() },
      );
      setSend({
        kind: "sent",
        deliveryId: result.delivery_id,
        queuedAt: result.queued_at,
      });
      toast.success(`テスト招待メールを ${PREVIEW.to} に送信しました`);
    } catch (err: unknown) {
      if (err instanceof EmailApiError) {
        const msg = err.toUserMessage();
        setSend({ kind: "error", userMessage: msg });
        toast.error(msg);
        return;
      }
      const fallback = "テスト送信に失敗しました (/api/email/test-send)";
      setSend({ kind: "error", userMessage: fallback });
      toast.error(fallback);
    }
  }, [load]);

  const template = load.kind === "ready" ? load.template : null;
  const subjectLine =
    template?.subject ??
    `【Build-Factory】${PREVIEW.project} への招待`;

  return (
    <main
      data-screen-id="S-058"
      data-feature-id="F-028"
      data-task-ids="T-V3-C-19"
      data-entities="E-043"
      data-phase="Phase 1B"
      data-template-key={EMAIL_TEMPLATE_KEY_INVITATION}
      className="min-h-screen bg-slate-100 py-8 px-4 text-slate-900"
    >
      <a
        href="/"
        className="fixed top-3 right-3 z-50 inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/95 border border-slate-200 rounded-md text-xs font-semibold text-eb-500 shadow-sm hover:bg-white"
      >
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
        <span>ホームに戻る</span>
      </a>

      <div className="max-w-[640px] mx-auto bg-white rounded-lg shadow-sm overflow-hidden">
        {/* mail header */}
        <div className="border-b border-slate-200 p-4 bg-slate-50">
          <div className="text-xs text-slate-500 space-y-1">
            <div>
              <strong>From:</strong> noreply@engine-base.com (Build-Factory)
            </div>
            <div>
              <strong>To:</strong> {PREVIEW.to}
            </div>
            <div>
              <strong>Subject:</strong> {subjectLine}
            </div>
          </div>
        </div>

        {/* mail body */}
        <div className="bg-white">
          <div className="bg-eb-500 px-8 py-5 text-white flex items-center gap-2">
            <div className="w-8 h-8 rounded-md bg-white/20 flex items-center justify-center">
              <Factory className="w-4 h-4" aria-hidden />
            </div>
            <span className="text-base font-bold">Build-Factory</span>
          </div>

          <div className="px-8 py-6">
            {/* AC-S2: h1 verbatim from screens.json[S-058].h1_text */}
            <h1 className="text-xl font-bold mb-3">
              {PREVIEW.inviter} さんから案件への招待
            </h1>
            <p className="text-sm leading-relaxed text-slate-700 mb-4">
              <strong>{PREVIEW.inviter}</strong> さんから「
              <strong>{PREVIEW.project}</strong>
              」案件への招待が届きました。
            </p>

            <dl className="bg-slate-50 border border-slate-200 rounded-md p-4 mb-4 text-sm space-y-2">
              <PreviewRow label="案件名" value={PREVIEW.project} bold />
              <PreviewRow
                label="ロール"
                value={
                  <span className="text-[11px] bg-eb-50 text-eb-700 border border-eb-200 px-2 py-0.5 rounded-full font-medium">
                    {PREVIEW.role}
                  </span>
                }
              />
              <PreviewRow label="招待元" value={PREVIEW.inviter} bold />
              <PreviewRow
                label="有効期限"
                value={`${PREVIEW.expiresInDays} 日`}
                bold
              />
            </dl>

            <p className="text-sm text-slate-700 italic mb-4">
              &quot;{PREVIEW.message}&quot;
            </p>

            <div className="text-center my-6">
              <a className="inline-block bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold px-8 py-3 rounded-md no-underline cursor-pointer">
                招待を受ける
              </a>
            </div>

            <p className="text-xs text-slate-500 mt-4">
              招待リンクは安全な暗号化トークンを含みます。他人と共有しないでください。
            </p>
          </div>

          <div className="bg-slate-50 px-8 py-4 text-center text-[11px] text-slate-500">
            <div>© 2026 株式会社 ENGINE BASE</div>
            <div className="mt-1">
              <span className="text-slate-500 hover:underline cursor-pointer">
                配信停止
              </span>
              {" · "}
              <span className="text-slate-500 hover:underline cursor-pointer">
                プライバシー
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Operator toolbar (preview-only, not part of the rendered email) */}
      <aside className="max-w-[640px] mx-auto mt-4 bg-white rounded-lg shadow-sm border border-slate-200 p-4 text-sm">
        <div className="flex items-center gap-2 mb-3">
          <Mail className="w-4 h-4 text-eb-500" aria-hidden />
          <h2 className="font-semibold text-slate-900">
            運用ツール
            <span className="ml-1 text-xs text-slate-500 font-normal">
              (テンプレート: {EMAIL_TEMPLATE_KEY_INVITATION})
            </span>
          </h2>
        </div>

        {load.kind === "loading" && (
          <p
            data-testid="email-template-loading"
            className="text-slate-500 flex items-center gap-2"
          >
            <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />
            テンプレートを取得中…
          </p>
        )}

        {load.kind === "error" && (
          <div
            role="alert"
            data-testid="email-template-error"
            className="text-red-600 flex items-start gap-2"
          >
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5" aria-hidden />
            <div>
              <div className="font-medium">{load.userMessage}</div>
              <button
                type="button"
                onClick={() => {
                  setLoad({ kind: "loading" });
                  void reload();
                }}
                className="mt-1 text-xs underline"
              >
                再試行
              </button>
            </div>
          </div>
        )}

        {load.kind === "ready" && (
          <div className="space-y-2">
            <p
              data-testid="email-template-status"
              className="text-xs text-slate-600"
            >
              {load.template
                ? `テンプレート ID: ${load.template.id}`
                : "招待テンプレート (email_invitation) が登録されていません"}
            </p>

            <button
              type="button"
              onClick={handleSendTest}
              disabled={!load.template || send.kind === "sending"}
              aria-label="テスト送信"
              className="inline-flex items-center gap-2 bg-eb-500 hover:bg-eb-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm h-9 px-4 rounded-md transition-colors"
            >
              {send.kind === "sending" ? (
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
              ) : (
                <Send className="w-4 h-4" aria-hidden />
              )}
              テスト送信
            </button>

            {send.kind === "sent" && (
              <p
                data-testid="email-send-success"
                className="text-xs text-eb-600"
              >
                送信キューに投入しました (delivery_id: {send.deliveryId} /
                queued_at: {send.queuedAt})
              </p>
            )}

            {send.kind === "error" && (
              <p
                role="alert"
                data-testid="email-send-error"
                className="text-xs text-red-600"
              >
                {send.userMessage}
              </p>
            )}
          </div>
        )}
      </aside>
    </main>
  );
}

function PreviewRow({
  label,
  value,
  bold = false,
}: {
  label: string;
  value: React.ReactNode;
  bold?: boolean;
}) {
  return (
    <div className="flex justify-between">
      <dt className="text-slate-500">{label}</dt>
      <dd className={bold ? "font-bold" : ""}>{value}</dd>
    </div>
  );
}
