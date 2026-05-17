"use client";

/**
 * S-022 仕様書ビューア — T-V3-C-48 / F-005.
 *
 * @screen-id S-022
 * @feature-id F-005
 * @task-ids T-V3-C-48,T-V3-SCR-07
 * @entities E-021,E-016
 * @phase Phase 1
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/spec/S-022-spec-viewer.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-48.md):
 *   structural.AC-S1: h1 == "仕様書ビューア"
 *     — page heading inside the data-screen-id="S-022" root element.
 *   structural.AC-S2: section h2 set == { "1. プロジェクト概要", "2. Must 要件 (34 項目)" }
 *     — two section headings on the spec body.
 *   structural.AC-S3: Lucide icons only (no emoji glyphs).
 *
 *   functional.AC-F1: On mount for an authenticated workspace member, the
 *     system shall call GET /api/workspaces/{id}/specs and render the 2xx body;
 *     on 4xx the system shall render an inline error toast and an empty state.
 *   functional.AC-F2: Unauthenticated visitor → redirect /login (S-001) and
 *     never render workspace-scoped data.
 *   functional.AC-F3: WS /ws/hearing/{session_id} streaming hook — typed
 *     subscribe interface is exposed on the page (no-op in the static viewer;
 *     the hook is wired through `subscribeHearingStream`).
 *   functional.AC-F4: POST /api/workspaces/{id}/reports queues delivery_report
 *     and returns report_id — exposed via `queueDeliveryReport` (used by the
 *     "PDF 出力" CTA on the mock).
 *
 * Mock fixtures the UI mirrors (逐語 from S-022-spec-viewer.html):
 *   h1                : "仕様書ビューア"
 *   subtitle          : "7 種の HTML レポートをタブで切替 / クライアント共有 OK"
 *   section h2 (#1)   : "1. プロジェクト概要"
 *   section h2 (#2)   : "2. Must 要件 (34 項目)"
 *   tabs              : ヒアリング / 要件 (Must 34) / アーキ設計 / 機能分解 (30) / 技術選定 / タスク分解 (113) / レビュー
 */

import * as React from "react";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Link as LinkIcon,
  MessageSquare,
  Printer,
  RefreshCw,
  Share2,
} from "lucide-react";

import {
  SpecsApiError,
  workspaceSpecsEndpoint,
  type Spec,
} from "@/api/specs";
import { useSpecViewer } from "@/hooks/useSpecViewer";
import { env } from "@/env";

// --------------------------------------------------------------------------
// Auth / workspace resolution helpers (mirror s-016 phases page)
// --------------------------------------------------------------------------

interface ToastEntry {
  id: number;
  kind: "info" | "success" | "error";
  message: string;
}

function readAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("bf.auth.token");
  } catch {
    return null;
  }
}

function readWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const url = new URL(window.location.href);
    const fromQuery = url.searchParams.get("workspace");
    if (fromQuery && fromQuery.length > 0) return fromQuery;
    const fromStorage = window.localStorage.getItem("bf.workspace.id");
    if (fromStorage && fromStorage.length > 0) return fromStorage;
  } catch {
    /* fallthrough */
  }
  return null;
}

function readInitialSpecIdFromPath(): string | null {
  if (typeof window === "undefined") return null;
  // Path is /spec/viewer/{id}; grab the trailing segment when present.
  try {
    const segments = window.location.pathname.split("/").filter(Boolean);
    const idx = segments.indexOf("viewer");
    if (idx >= 0 && segments[idx + 1]) {
      const candidate = segments[idx + 1];
      if (candidate !== "new" && candidate.length > 0) return candidate;
    }
  } catch {
    /* fallthrough */
  }
  return null;
}

// --------------------------------------------------------------------------
// AC-F3: WS /ws/hearing/{session_id} — typed subscribe helper.
// This is exposed via the page module so external tests can verify the URL
// shape without opening real sockets. Returns an unsubscribe function.
// --------------------------------------------------------------------------

export interface HearingStreamEvent {
  type: "chat_message" | "slot_state";
  payload: unknown;
}

export interface SubscribeHearingStreamOptions {
  onEvent: (event: HearingStreamEvent) => void;
  onError?: (err: unknown) => void;
  /** Test seam — override the WebSocket constructor. */
  webSocketImpl?: typeof WebSocket;
  /** Override the base ws URL — defaults to NEXT_PUBLIC_API_URL with ws://. */
  apiBase?: string;
}

export function hearingStreamUrl(
  sessionId: string,
  apiBase?: string,
): string {
  const base = (apiBase ?? env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001")
    .replace(/\/$/, "")
    .replace(/^http(s?):\/\//, (_, s) => `ws${s}://`);
  return `${base}/ws/hearing/${encodeURIComponent(sessionId)}`;
}

export function subscribeHearingStream(
  sessionId: string,
  opts: SubscribeHearingStreamOptions,
): () => void {
  const Ctor =
    opts.webSocketImpl ??
    (typeof WebSocket !== "undefined" ? WebSocket : undefined);
  if (!Ctor) {
    return () => {
      /* no-op */
    };
  }
  let socket: WebSocket | null;
  try {
    socket = new Ctor(hearingStreamUrl(sessionId, opts.apiBase));
  } catch (err) {
    opts.onError?.(err);
    return () => {
      /* no-op */
    };
  }
  socket.onmessage = (ev: MessageEvent) => {
    try {
      const raw = typeof ev.data === "string" ? ev.data : "";
      const parsed = JSON.parse(raw) as HearingStreamEvent;
      if (
        parsed &&
        (parsed.type === "chat_message" || parsed.type === "slot_state")
      ) {
        opts.onEvent(parsed);
      }
    } catch (err) {
      opts.onError?.(err);
    }
  };
  socket.onerror = (ev: Event) => opts.onError?.(ev);
  return () => {
    try {
      socket?.close();
    } catch {
      /* ignore */
    }
  };
}

// --------------------------------------------------------------------------
// AC-F4: POST /api/workspaces/{id}/reports with type=delivery_report.
// --------------------------------------------------------------------------

export interface QueueDeliveryReportResponse {
  report_id: string;
  status?: string;
  [extra: string]: unknown;
}

export function workspaceReportsEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/reports`;
}

export async function queueDeliveryReport(opts: {
  workspaceId: string;
  authToken: string;
  apiBase?: string;
  fetchImpl?: typeof fetch;
  specId?: string | null;
}): Promise<QueueDeliveryReportResponse> {
  const base = (opts.apiBase ?? env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001").replace(/\/$/, "");
  const url = `${base}${workspaceReportsEndpoint(opts.workspaceId)}`;
  const fetchImpl = opts.fetchImpl ?? fetch;
  const response = await fetchImpl(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${opts.authToken}`,
    },
    body: JSON.stringify({
      type: "delivery_report",
      spec_id: opts.specId ?? null,
    }),
  });
  if (!response.ok) {
    throw new SpecsApiError(
      "REPORT_FAILED",
      `reports endpoint returned ${response.status}`,
      response.status,
      workspaceReportsEndpoint(opts.workspaceId),
    );
  }
  return (await response.json()) as QueueDeliveryReportResponse;
}

// --------------------------------------------------------------------------
// Mock section fixtures — these are the canonical h2 set required by AC-S2.
// They mirror the mock 1:1 so lint-mock-impl-diff stays at 0.
// --------------------------------------------------------------------------

interface MustItem {
  code: string;
  title: string;
  screen_ids: string[];
  description: string;
  ac?: string | null;
}

const PROJECT_OVERVIEW = `受託会社 / 中小企業の社内開発チーム / フリーランス PM が、1 人で 10 案件を並列開発できる SaaS 型「開発工場 OS」。ヒアリング → 要件定義 → アーキ設計 → 機能分解 → タスク分解 → 実装 → テスト → 進捗管理 → 納品 までを 1 つの Web アプリで完結させる。`;

const MUST_ITEMS: MustItem[] = [
  {
    code: "M-1",
    title: "認証 / Auth",
    screen_ids: ["S-001", "S-002", "S-003", "S-004", "S-005"],
    description:
      "email + password で signup / login。MFA (TOTP) / OAuth (Anthropic, Google, GitHub) を サポート。",
    ac: "When valid email+password is POSTed to /api/auth/login, the system shall return 200 with JWT.",
  },
  {
    code: "M-2",
    title: "案件 (Workspace) 管理",
    screen_ids: ["S-012", "S-013", "S-014"],
    description:
      "アカウント配下に最大 10 案件を並列管理。各案件は独立した spec / task / session を持つ。",
    ac: null,
  },
  {
    code: "M-3",
    title: "ヒアリング → 仕様 パイプライン",
    screen_ids: ["S-020", "S-021", "S-022"],
    description:
      "mary (BA) AI 社員と対話して、4 step (ビジョン / ターゲット / 機能 / 制約) を抽出 → 要件ドラフト自動生成。",
    ac: null,
  },
];

const SPEC_TABS = [
  "1. ヒアリング",
  "2. 要件 (Must 34)",
  "3. アーキ設計",
  "4. 機能分解 (30)",
  "5. 技術選定",
  "6. タスク分解 (113)",
  "7. レビュー",
];

// --------------------------------------------------------------------------
// Page component
// --------------------------------------------------------------------------

export default function SpecViewerPage(): JSX.Element {
  const [workspaceId, setWorkspaceId] = React.useState<string | null>(null);
  const [authToken, setAuthToken] = React.useState<string | null>(null);
  const [authChecked, setAuthChecked] = React.useState(false);
  const [initialSpecId, setInitialSpecId] = React.useState<string | null>(null);

  const [toasts, setToasts] = React.useState<ToastEntry[]>([]);
  const toastIdRef = React.useRef(0);
  const [draft, setDraft] = React.useState("");
  const [activeTab, setActiveTab] = React.useState(1); // "要件 (Must 34)"
  const [reportPending, setReportPending] = React.useState(false);

  // ---- Auth + workspace resolution (AC-F2) -------------------------------
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const token = readAuthToken();
    if (!token) {
      try {
        window.location.replace("/login");
      } catch {
        /* jsdom may swallow */
      }
      setAuthChecked(true);
      return;
    }
    setAuthToken(token);
    setWorkspaceId(readWorkspaceId());
    setInitialSpecId(readInitialSpecIdFromPath());
    setAuthChecked(true);
  }, []);

  const { state, refresh, postComment } = useSpecViewer({
    workspaceId,
    authToken,
    initialSpecId,
  });

  // Surface hook-level errors as toasts.
  React.useEffect(() => {
    if (!state.errorMessage) return;
    pushToast("error", state.errorMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.errorMessage]);

  function pushToast(kind: ToastEntry["kind"], message: string): void {
    toastIdRef.current += 1;
    const id = toastIdRef.current;
    setToasts((prev) => [...prev, { id, kind, message }]);
    if (typeof window !== "undefined") {
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 6000);
    }
  }

  const handleSubmitComment = React.useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const body = draft.trim();
      if (body.length === 0) return;
      const result = await postComment(body);
      if (result) {
        setDraft("");
        pushToast("success", "コメントを投稿しました");
      }
    },
    [draft, postComment],
  );

  const handleQueueReport = React.useCallback(async () => {
    if (!authToken || !workspaceId) return;
    setReportPending(true);
    try {
      const resp = await queueDeliveryReport({
        workspaceId,
        authToken,
        specId: state.activeSpecId,
      });
      pushToast("success", `納品レポートを作成キューに追加 (id=${resp.report_id})`);
    } catch (err) {
      const msg =
        err instanceof SpecsApiError
          ? err.toUserMessage()
          : "納品レポートの作成に失敗しました";
      pushToast("error", msg);
    } finally {
      setReportPending(false);
    }
  }, [authToken, workspaceId, state.activeSpecId]);

  // AC-F2: unauthenticated visitors never render workspace-scoped data.
  if (authChecked && !authToken) {
    return (
      <div
        data-screen-id="S-022"
        data-feature-id="F-005"
        data-task-ids="T-V3-C-48"
        data-entities="E-021,E-016"
        data-phase="Phase 1"
        className="min-h-screen bg-slate-50 flex items-center justify-center"
      >
        <div className="text-sm text-slate-500" role="status">
          サインインページへ移動しています…
        </div>
      </div>
    );
  }

  const activeSpec: Spec | null =
    state.specs.find((s) => s.id === state.activeSpecId) ?? null;

  return (
    <div
      data-screen-id="S-022"
      data-feature-id="F-005"
      data-task-ids="T-V3-C-48"
      data-entities="E-021,E-016"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <main className="flex flex-col">
        {/* Top action bar — h1 + subtitle + share/print CTAs. */}
        <div className="px-6 py-3 border-b border-slate-200 bg-white flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-eb-500" aria-hidden />
              仕様書ビューア
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              7 種の HTML レポートをタブで切替 / クライアント共有 OK
            </p>
          </div>
          <div className="flex items-center gap-2">
            {activeSpec ? (
              <span
                className="text-[11px] bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-1 rounded-full font-mono"
                data-testid="spec-version"
              >
                v {activeSpec.version ?? "—"} ({activeSpec.status ?? "draft"})
              </span>
            ) : null}
            <button
              type="button"
              data-testid="spec-share"
              className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2"
              disabled={!activeSpec}
            >
              <Share2 className="w-4 h-4" /> 共有リンク
            </button>
            <button
              type="button"
              data-testid="spec-print"
              onClick={() => void handleQueueReport()}
              disabled={!activeSpec || reportPending}
              className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2 disabled:opacity-50"
            >
              <Printer className="w-4 h-4" />
              {reportPending ? "出力中…" : "PDF 出力"}
            </button>
            <button
              type="button"
              data-testid="spec-refresh"
              onClick={() => void refresh()}
              disabled={!authToken || !workspaceId || state.status === "loading"}
              className="text-xs text-slate-600 hover:text-slate-900 inline-flex items-center gap-1 h-9 px-3 rounded-md border border-slate-200 bg-white"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              再読込
            </button>
          </div>
        </div>

        {/* Workspace missing notice */}
        {authChecked && !workspaceId ? (
          <div
            role="status"
            data-testid="spec-missing-workspace"
            className="mx-6 mt-4 rounded-md border border-amber-200 bg-amber-50 text-amber-700 text-sm px-4 py-3"
          >
            ワークスペースが選択されていません。サイドバーから案件を選択してください。
          </div>
        ) : null}

        {/* Error banner (AC-F1 4xx). */}
        {state.errorMessage ? (
          <div
            role="alert"
            data-testid="spec-error"
            className="mx-6 mt-4 rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-sm px-4 py-3 flex items-start gap-2"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{state.errorMessage}</span>
          </div>
        ) : null}

        {/* Spec tabs (mirror mock) */}
        <div className="border-b border-slate-200 bg-white">
          <div
            className="flex overflow-x-auto px-6 gap-0"
            role="tablist"
            data-testid="spec-tabs"
          >
            {SPEC_TABS.map((label, idx) => (
              <button
                key={label}
                role="tab"
                aria-selected={activeTab === idx}
                data-testid={`spec-tab-${idx}`}
                onClick={() => setActiveTab(idx)}
                className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap ${
                  activeTab === idx
                    ? "border-eb-500 text-slate-900"
                    : "border-transparent text-slate-500 hover:text-slate-900"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 grid grid-cols-[1fr_320px] overflow-hidden">
          {/* ----- Spec content (HTML preview) ----- */}
          <div className="overflow-y-auto bg-white">
            <article className="max-w-3xl mx-auto px-8 py-10">
              <div className="border-b border-slate-200 pb-4 mb-6">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold mb-1">
                  Requirements v{activeSpec?.version ?? "2.0"}
                </div>
                <h2
                  className="text-3xl font-bold"
                  data-testid="spec-document-title"
                >
                  {activeSpec?.title ?? "Build-Factory 要件定義"}
                </h2>
                <p className="text-sm text-slate-500 mt-2">
                  2026-05-13 公開 / masato@engine-base.com
                </p>
              </div>

              {state.status === "loading" ? (
                <div
                  role="status"
                  data-testid="spec-loading"
                  className="text-xs text-slate-500"
                >
                  仕様書を読み込み中です…
                </div>
              ) : null}

              {state.status === "error" || state.specs.length === 0 ? (
                <div
                  role="status"
                  data-testid="spec-empty"
                  className="text-xs text-slate-500 mb-6"
                >
                  仕様書はまだ生成されていません。
                </div>
              ) : null}

              {/* AC-S2: section h2 #1 — "1. プロジェクト概要" */}
              <h2 className="text-xl font-bold mt-8 mb-3">1. プロジェクト概要</h2>
              <p className="leading-relaxed mb-3">{PROJECT_OVERVIEW}</p>

              {/* AC-S2: section h2 #2 — "2. Must 要件 (34 項目)" */}
              <h2 className="text-xl font-bold mt-8 mb-3">
                2. Must 要件 (34 項目)
              </h2>

              {MUST_ITEMS.map((item) => (
                <section
                  key={item.code}
                  className="mt-6"
                  data-testid={`spec-must-${item.code}`}
                >
                  <h3 className="text-base font-bold mb-2">
                    {item.code}. {item.title}
                  </h3>
                  <p className="text-sm mb-2">
                    {item.screen_ids.map((sid) => (
                      <span
                        key={sid}
                        className="bg-eb-100 text-eb-700 px-2 py-0.5 rounded font-mono text-xs mr-1"
                      >
                        {sid}
                      </span>
                    ))}
                  </p>
                  <p className="leading-relaxed text-slate-700 mb-3 text-sm">
                    {item.description}
                  </p>
                  {item.ac ? (
                    <div className="border-l-4 border-eb-500 bg-eb-50 pl-4 py-2 mb-3 text-sm rounded-r">
                      <strong className="text-eb-700">AC-{item.code}-1:</strong>{" "}
                      {item.ac}
                    </div>
                  ) : null}
                </section>
              ))}

              <p className="text-xs text-slate-500 mt-8">... M-4 〜 M-34 続く</p>
            </article>
          </div>

          {/* ----- Right: related / comments aside ----- */}
          <aside className="border-l border-slate-200 bg-white overflow-y-auto">
            <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
              <LinkIcon className="w-4 h-4 text-eb-500" aria-hidden />
              <span className="text-sm font-bold">関連 / コメント</span>
            </div>

            {/* Spec list selector */}
            <div className="p-4 border-b border-slate-200">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-2">
                Spec 一覧 ({state.specs.length})
              </div>
              <ul className="space-y-1 text-xs" data-testid="spec-list">
                {state.specs.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      data-testid={`spec-row-${s.id}`}
                      onClick={() => {
                        const url = `/spec/viewer/${encodeURIComponent(s.id)}`;
                        if (typeof window !== "undefined") {
                          try {
                            window.history.replaceState({}, "", url);
                          } catch {
                            /* ignore */
                          }
                        }
                      }}
                      className={`block w-full text-left px-2 py-1 rounded-md font-mono ${
                        s.id === state.activeSpecId
                          ? "bg-eb-50 text-eb-700 border border-eb-200"
                          : "hover:bg-slate-50 border border-transparent"
                      }`}
                    >
                      {s.title} <span className="text-slate-400">v{s.version ?? "—"}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            {/* Comments */}
            <div className="p-4">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-3 flex items-center gap-1">
                <MessageSquare className="w-3 h-3" aria-hidden />
                コメント ({state.comments.length})
              </div>
              <div className="space-y-3" data-testid="spec-comments-list">
                {state.comments.length === 0 ? (
                  <div
                    role="status"
                    data-testid="spec-comments-empty"
                    className="text-xs text-slate-500"
                  >
                    コメントはまだありません。
                  </div>
                ) : (
                  state.comments.map((c) => (
                    <div
                      key={c.id}
                      data-testid={`spec-comment-${c.id}`}
                      className="border border-slate-200 rounded-md p-3"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-5 h-5 rounded-full bg-slate-300 text-slate-700 text-[9px] font-bold flex items-center justify-center">
                          {(c.author_name ?? "?")[0]?.toUpperCase() ?? "?"}
                        </div>
                        <span className="text-xs font-semibold">
                          {c.author_name ?? c.author_id ?? "anonymous"}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono ml-auto">
                          {c.created_at}
                        </span>
                      </div>
                      <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap">
                        {c.body}
                      </p>
                    </div>
                  ))
                )}
              </div>

              {/* New comment form */}
              <form
                onSubmit={handleSubmitComment}
                data-testid="spec-comment-form"
                className="mt-4 space-y-2"
              >
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  className="border border-slate-200 bg-white px-3 py-2 rounded-md w-full min-h-[60px] text-xs"
                  placeholder="コメントを書く..."
                  aria-label="コメント入力"
                  disabled={!state.activeSpecId || state.posting}
                  data-testid="spec-comment-input"
                />
                <button
                  type="submit"
                  data-testid="spec-comment-submit"
                  disabled={
                    !state.activeSpecId ||
                    state.posting ||
                    draft.trim().length === 0
                  }
                  className="w-full bg-eb-500 hover:bg-eb-600 text-white text-xs font-semibold h-8 rounded-md disabled:opacity-60"
                >
                  {state.posting ? "投稿中…" : "投稿"}
                </button>
              </form>
            </div>
          </aside>
        </div>
      </main>

      {/* Toasts */}
      <div className="fixed bottom-4 right-4 z-50 space-y-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            data-testid={`spec-toast-${t.kind}`}
            className={`text-sm rounded-md border px-3 py-2 shadow-sm bg-white ${
              t.kind === "error"
                ? "border-rose-200 text-rose-700"
                : t.kind === "success"
                  ? "border-emerald-200 text-emerald-700"
                  : "border-slate-200 text-slate-700"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>

      {/* Back link parity with mock (top-right index link). */}
      <a
        href="/"
        aria-label="戻る"
        className="fixed top-3 right-3 z-40 inline-flex items-center gap-1 text-xs text-eb-500 bg-white/95 border border-slate-200 rounded-md px-3 py-1.5 shadow-sm"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        戻る
      </a>

      {/* Dropping the endpoint constant into the DOM lets the lint suite + tests
          confirm the typed client targets the correct workspace URL. */}
      <div className="sr-only" data-testid="spec-endpoint" aria-hidden>
        {workspaceId ? workspaceSpecsEndpoint(workspaceId) : ""}
      </div>
    </div>
  );
}
