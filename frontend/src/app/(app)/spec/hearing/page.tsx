"use client";

/**
 * S-020 ヒアリングセッション — T-V3-C-46 / F-005.
 *
 * @screen-id S-020
 * @feature-id F-005
 * @task-ids T-V3-C-46,T-V3-SCR-05
 * @entities E-016,E-032,E-033
 * @phase Phase 1
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/spec/S-020-hearing-session.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-46.md):
 *   structural.AC-S1: h1 == "ヒアリングセッション"
 *     — page heading inside the data-screen-id="S-020" root element.
 *   structural.AC-S2: Lucide icons only (no emoji glyphs).
 *
 *   functional.AC-F1: On mount for an authenticated workspace member, the
 *     system shall call WS /ws/hearing/{session_id} and render its 2xx body;
 *     on 4xx the system shall render an inline error toast and an empty state.
 *   functional.AC-F2: Unauthenticated visitor → redirect /login (S-001), no
 *     workspace-scoped data is rendered.
 *   functional.AC-F3: When a client connects to WS /ws/hearing/{session_id},
 *     the system shall stream chat messages and slot_state updates.
 *
 * Mock fixtures the UI mirrors (逐語 from S-020-hearing-session.html):
 *   h1                : "ヒアリングセッション"
 *   subtitle          : "mary (BA) と対話して案件のヒアリングを進める"
 *   step indicator   : ビジョン / ターゲット / 機能 / 制約 (4 steps)
 *   primary CTA      : "成果物保存" (Save)
 *
 * The page integrates with POST /api/workspaces/{id}/hearing/save (T-V3-B-07
 * implemented) for the persistence path requested by the masato directive,
 * and with WS /ws/hearing/{session_id} for the live streaming chat.
 */

import * as React from "react";
import {
  ArrowLeft,
  FileOutput,
  Mic,
  Package,
  Save,
  Send,
  Sparkles,
} from "lucide-react";

import {
  HearingSessionApiError,
  hearingSaveEndpoint,
  hearingWsEndpoint,
} from "@/api/hearing-session";
import { useHearingSession } from "@/hooks/useHearingSession";

// --------------------------------------------------------------------------
// Mock-derived screen literals — 逐語コピー (h1_text from screens.json#S-020).
// AC-S1: h1_text === "ヒアリングセッション"
// --------------------------------------------------------------------------
const S020_H1_TEXT = "ヒアリングセッション";
const S020_SUBTITLE = "mary (BA) と対話して案件のヒアリングを進める";
const S020_SAVE_LABEL = "成果物保存";
const S020_INPUT_PLACEHOLDER = "メッセージを入力... (Cmd+Enter で送信)";
const S020_DRAFT_LABEL = "要件ドラフトに送る";
const S020_EXTRACTED_LABEL = "抽出済み情報";

interface StepDescriptor {
  key: string;
  label: string;
  /** 1-based step number used by the indicator badges. */
  index: number;
}

const STEPS: ReadonlyArray<StepDescriptor> = [
  { key: "vision", label: "ビジョン", index: 1 },
  { key: "target", label: "ターゲット", index: 2 },
  { key: "features", label: "機能", index: 3 },
  { key: "constraints", label: "制約", index: 4 },
] as const;

// --------------------------------------------------------------------------
// Auth / workspace / session resolution helpers
// --------------------------------------------------------------------------

function readAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("bf.auth.token");
  } catch {
    return null;
  }
}

function readQueryParam(name: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    const url = new URL(window.location.href);
    const val = url.searchParams.get(name);
    return val && val.length > 0 ? val : null;
  } catch {
    return null;
  }
}

function readStorage(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    const val = window.localStorage.getItem(key);
    return val && val.length > 0 ? val : null;
  } catch {
    return null;
  }
}

function resolveWorkspaceId(): string | null {
  return readQueryParam("workspace") ?? readStorage("bf.workspace.id");
}

function resolveSessionId(): string | null {
  return readQueryParam("session") ?? readStorage("bf.hearing.session_id");
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  } catch {
    return iso;
  }
}

// --------------------------------------------------------------------------
// Skeleton loader — AC-F2: role="status" aria-live="polite" while loading.
// --------------------------------------------------------------------------
function HearingSkeleton(): React.ReactElement {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="読み込み中"
      data-testid="hearing-skeleton"
      className="flex-1 px-6 py-6 space-y-4"
    >
      <div className="h-6 w-1/3 bg-slate-200 rounded animate-pulse" />
      <div className="h-20 max-w-3xl bg-slate-200 rounded animate-pulse" />
      <div className="h-20 max-w-3xl bg-slate-200 rounded animate-pulse" />
      <span className="sr-only">読み込み中…</span>
    </div>
  );
}

// --------------------------------------------------------------------------
// Page component
// --------------------------------------------------------------------------

export default function HearingSessionPage(): React.ReactElement {
  const [authToken, setAuthToken] = React.useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = React.useState<string | null>(null);
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [authChecked, setAuthChecked] = React.useState(false);
  const [inlineError, setInlineError] = React.useState<string | null>(null);
  const [draftMessage, setDraftMessage] = React.useState("");
  const [unauthorized, setUnauthorized] = React.useState(false);

  // ---- Auth + workspace + session resolution (AC-F2) ---------------------
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const token = readAuthToken();
    if (!token) {
      // AC-F2 UNWANTED: never render workspace-scoped data for anon visitors.
      setUnauthorized(true);
      try {
        window.location.replace("/login");
      } catch {
        // jsdom may swallow the assignment; the unauthorized branch below
        // still prevents any workspace-scoped UI from rendering.
      }
      setAuthChecked(true);
      return;
    }
    setAuthToken(token);
    setWorkspaceId(resolveWorkspaceId());
    setSessionId(resolveSessionId());
    setAuthChecked(true);
  }, []);

  const session = useHearingSession({
    sessionId,
    workspaceId,
    authToken,
    autoConnect: authChecked && !!authToken,
  });

  // Surface hook errors (WS close ≥ 4000, save failures) as inline error toast.
  React.useEffect(() => {
    if (session.error instanceof HearingSessionApiError) {
      setInlineError(session.error.toUserMessage());
    } else if (session.error) {
      setInlineError(session.error.message);
    }
  }, [session.error]);

  // ---- AC-F2 guard: render nothing workspace-scoped for anon visitors ----
  if (unauthorized) {
    return (
      <div
        data-screen-id="S-020"
        data-feature-id="F-005"
        data-screen-name="hearing_session"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  // While we're still resolving auth/session, show a skeleton.
  if (!authChecked) {
    return (
      <div
        data-screen-id="S-020"
        data-feature-id="F-005"
        data-screen-name="hearing_session"
        className="min-h-screen bg-slate-50 flex flex-col"
      >
        <HearingSkeleton />
      </div>
    );
  }

  const activeStep = STEPS.find((s) => {
    const slot = session.slotStates.find((x) => x.key === s.key);
    return slot?.status === "active";
  });

  const handleSave = async () => {
    setInlineError(null);
    try {
      await session.save(null);
    } catch (err) {
      if (err instanceof HearingSessionApiError) {
        setInlineError(err.toUserMessage());
      }
    }
  };

  const handleSendMessage = () => {
    // In Wave 1 the server still drives the conversation through the WS;
    // we keep the local draft so the textarea is controllable + testable.
    if (!draftMessage.trim()) return;
    setDraftMessage("");
  };

  return (
    <div
      data-screen-id="S-020"
      data-feature-id="F-005"
      data-screen-name="hearing_session"
      data-ws-endpoint={sessionId ? hearingWsEndpoint(sessionId) : undefined}
      data-save-endpoint={
        workspaceId ? hearingSaveEndpoint(workspaceId) : undefined
      }
      className="min-h-screen flex flex-col bg-slate-50 text-slate-900 font-sans"
    >
      {/* Top bar */}
      <div className="px-6 py-3 border-b border-slate-200 bg-white flex items-center justify-between">
        <div className="flex items-center gap-3">
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900"
            aria-label="ダッシュボードに戻る"
          >
            <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
            <span>戻る</span>
          </a>
          <div>
            <h1 className="text-lg font-bold flex items-center gap-2">
              <Mic className="w-5 h-5 text-eb-500" aria-hidden />
              {S020_H1_TEXT}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">{S020_SUBTITLE}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span
            className="inline-flex items-center gap-1.5 text-xs text-emerald-600"
            data-testid="hearing-status"
            data-ready-state={session.readyState}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            {session.isStreaming ? "session active" : "session offline"}
          </span>
          <button
            type="button"
            onClick={handleSave}
            disabled={session.isSaving || !workspaceId || !sessionId}
            data-testid="hearing-save-button"
            className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md flex items-center gap-2 disabled:opacity-50"
          >
            <Save className="w-4 h-4" aria-hidden />
            <span>{S020_SAVE_LABEL}</span>
          </button>
        </div>
      </div>

      {/* Inline error banner (AC-F1 4xx branch) */}
      {inlineError ? (
        <div
          role="alert"
          data-testid="hearing-error-toast"
          className="px-6 py-2 bg-rose-50 border-b border-rose-200 text-rose-700 text-sm flex items-center justify-between"
        >
          <span>{inlineError}</span>
          <button
            type="button"
            onClick={() => setInlineError(null)}
            className="text-xs text-rose-600 underline"
          >
            閉じる
          </button>
        </div>
      ) : null}

      {/* Step indicator */}
      <div
        className="px-6 py-4 border-b border-slate-200 bg-white"
        aria-label="hearing-stepper"
        data-testid="hearing-stepper"
      >
        <div className="flex items-center gap-2 max-w-3xl mx-auto">
          {STEPS.map((step, idx) => {
            const slot = session.slotStates.find((s) => s.key === step.key);
            const status = slot?.status ?? "pending";
            const isActive = status === "active";
            const isFilled = status === "filled";
            const isLast = idx === STEPS.length - 1;
            return (
              <React.Fragment key={step.key}>
                <div
                  className={`flex items-center gap-2 text-xs font-semibold ${
                    isActive || isFilled ? "text-eb-500" : "text-slate-500"
                  }`}
                  data-testid={`hearing-step-${step.key}`}
                  data-step-status={status}
                >
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                      isActive
                        ? "bg-eb-500 text-white"
                        : isFilled
                          ? "bg-eb-400 text-white"
                          : "bg-slate-200 text-slate-600"
                    }`}
                  >
                    {step.index}
                  </div>
                  {step.label}
                </div>
                {isLast ? null : (
                  <div className="flex-1 h-px bg-slate-300" />
                )}
              </React.Fragment>
            );
          })}
        </div>
        {activeStep ? (
          <p className="sr-only" data-testid="hearing-active-step">
            current step: {activeStep.key}
          </p>
        ) : null}
      </div>

      {/* Chat area + extracted sidebar */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-[1fr_320px] overflow-hidden">
        <div className="flex flex-col overflow-hidden bg-slate-50">
          <div
            className="flex-1 overflow-y-auto px-6 py-6 space-y-4"
            data-testid="hearing-chat-log"
            aria-live="polite"
            aria-relevant="additions"
          >
            {session.messages.length === 0 && !session.isStreaming ? (
              <div
                className="text-sm text-slate-500 text-center py-8"
                data-testid="hearing-empty-state"
              >
                ヒアリングセッションが開始されると、ここに会話が表示されます。
              </div>
            ) : null}
            {session.messages.map((msg) => {
              const isAi = msg.role === "ai";
              return (
                <div
                  key={msg.id}
                  data-testid="hearing-message"
                  data-role={msg.role}
                  className={`flex gap-3 max-w-3xl ${
                    isAi ? "" : "ml-auto flex-row-reverse"
                  }`}
                >
                  <div
                    className={`w-8 h-8 rounded-full text-xs font-bold flex items-center justify-center shrink-0 text-white ${
                      isAi ? "bg-emerald-500" : "bg-eb-500"
                    }`}
                  >
                    {isAi ? "AI" : "M"}
                  </div>
                  <div className="flex-1">
                    <div
                      className={`text-xs text-slate-500 mb-1 ${
                        isAi ? "" : "text-right"
                      }`}
                    >
                      <strong>{msg.author ?? (isAi ? "mary (BA)" : "you")}</strong>
                      <span> · {formatTime(msg.created_at)}</span>
                    </div>
                    <div
                      className={`border rounded-lg p-4 text-sm leading-relaxed whitespace-pre-wrap ${
                        isAi
                          ? "bg-white border-slate-200"
                          : "bg-eb-50 border-eb-200"
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                </div>
              );
            })}
            {session.isStreaming && session.messages.length > 0 ? (
              <div
                className="flex items-center gap-2 text-xs text-slate-500"
                data-testid="hearing-typing-indicator"
              >
                <Sparkles className="w-3 h-3" aria-hidden />
                <span>次の質問を考えています…</span>
              </div>
            ) : null}
          </div>

          {/* Input */}
          <div className="border-t border-slate-200 bg-white px-6 py-3">
            <div className="flex items-end gap-2 max-w-3xl mx-auto">
              <button
                type="button"
                className="text-slate-500 hover:text-eb-500 h-9 w-9 rounded-md hover:bg-slate-100 flex items-center justify-center"
                title="音声入力"
                aria-label="音声入力"
              >
                <Mic className="w-4 h-4" aria-hidden />
              </button>
              <textarea
                value={draftMessage}
                onChange={(e) => setDraftMessage(e.target.value)}
                placeholder={S020_INPUT_PLACEHOLDER}
                data-testid="hearing-input"
                className="flex-1 border border-slate-200 bg-white text-sm px-3 py-2 rounded-md min-h-[40px] max-h-[120px] resize-y focus-visible:outline-none focus-visible:border-eb-500"
              />
              <button
                type="button"
                onClick={handleSendMessage}
                data-testid="hearing-send-button"
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md flex items-center gap-2"
              >
                <span>送信</span>
                <Send className="w-4 h-4" aria-hidden />
              </button>
            </div>
          </div>
        </div>

        {/* Extracted artifacts sidebar */}
        <aside className="hidden md:flex border-l border-slate-200 bg-white flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
            <Package className="w-4 h-4 text-eb-500" aria-hidden />
            <span className="text-sm font-bold">{S020_EXTRACTED_LABEL}</span>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3 text-sm">
            {STEPS.map((step) => {
              const slot = session.slotStates.find((s) => s.key === step.key);
              const filled = slot?.status === "filled" || slot?.status === "active";
              return (
                <div
                  key={step.key}
                  data-testid={`hearing-slot-${step.key}`}
                  className={`border rounded-md p-3 ${
                    filled
                      ? "border-eb-200 bg-eb-50"
                      : "border-slate-200 opacity-60"
                  }`}
                >
                  <div
                    className={`text-[10px] uppercase tracking-wider font-bold mb-1 ${
                      filled ? "text-eb-700" : "text-slate-500"
                    }`}
                  >
                    Step {step.index}: {step.label}
                  </div>
                  <div
                    className={`text-xs ${
                      filled ? "text-slate-700" : "text-slate-500"
                    }`}
                  >
                    {slot?.extracted ?? "— 未抽出 —"}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="border-t border-slate-200 p-3">
            <button
              type="button"
              data-testid="hearing-draft-button"
              className="w-full bg-white border border-eb-200 hover:bg-eb-50 text-eb-700 text-sm font-semibold h-9 rounded-md flex items-center justify-center gap-2"
            >
              <FileOutput className="w-4 h-4" aria-hidden />
              <span>{S020_DRAFT_LABEL}</span>
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
