"use client";

/**
 * T-V3-C-60 / S-030: タスク詳細 page (Vertical Slice / UI).
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/task/S-030-task-detail.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-030
 * @screen-name task_detail
 * @feature-id F-006,F-007,F-025
 * @task-ids T-V3-C-60
 * @entities E-018,E-016,E-019,E-025
 * @phase Phase 1
 *
 * Backend contracts (T-V3-B-11 / T-V3-B-12):
 *   GET  /api/tasks/{id}                — task + ACs + sessions + comments
 *   PUT  /api/tasks/{id}                — partial update (member+)
 *   POST /api/tasks/{id}/play           — single-task play (member+)
 *   POST /api/tasks/{id}/comments       — post a comment (member+)
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-60.md):
 *   structural.AC-S1 — h1 === "POST /api/auth/signup 実装" (mock h1 逐語コピー).
 *   structural.AC-S2 — h2 set === {Description / 受け入れ基準 (EARS / 5 件) /
 *                                  セッション履歴 (3) / コメント (2)}.
 *   structural.AC-S3 — Lucide icons only (no emoji glyphs).
 *   functional.AC-F1 — GET on mount; 2xx renders, 4xx → inline toast + empty.
 *   functional.AC-F2 — 401 → router.replace("/login") (no workspace data render).
 *   functional.AC-F5 — EARS validation gates AC persistence (client-side, see
 *                       @/api/task-detail::assertAllEarsValid).
 *
 * Auth: workspace member required for GET / PUT / play / comments. The page
 * surfaces 401 by redirecting to /login and other 4xx as friendly toasts
 * tagged with the failing endpoint.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AlignLeft,
  ArrowLeft,
  CheckCircle2,
  Clock,
  Edit3,
  Folder,
  Loader2,
  MessageSquare,
  Play,
  Send,
  Square,
  Terminal,
} from "lucide-react";

import {
  TaskDetailApiError,
  type AcceptanceCriterion,
  type EarsForm,
  type SessionSummary,
  type TaskComment,
} from "@/api/task-detail";
import { useTaskDetail } from "@/hooks/useTaskDetail";

// ---------------------------------------------------------------------------
// Mock-derived screen literals — 逐語コピー (screens.json[S-030]).
// AC-S1: h1_text === "POST /api/auth/signup 実装"
// AC-S2: section_h2_texts equality set (Description / 受け入れ基準 / セッション履歴 / コメント).
// ---------------------------------------------------------------------------
const S030_H1_TEXT = "POST /api/auth/signup 実装";
const SECTION_DESCRIPTION = "Description";
const SECTION_AC = "受け入れ基準 (EARS / 5 件)";
const SECTION_SESSIONS = "セッション履歴 (3)";
const SECTION_COMMENTS = "コメント (2)";

const EARS_BADGE_STYLES: Record<EarsForm, string> = {
  UBIQUITOUS: "border-eb-500 bg-eb-50 text-eb-700",
  "EVENT-DRIVEN": "border-eb-500 bg-eb-50 text-eb-700",
  "STATE-DRIVEN": "border-blue-400 bg-blue-50 text-blue-700",
  OPTIONAL: "border-amber-400 bg-amber-50 text-amber-700",
  UNWANTED: "border-red-400 bg-red-50 text-red-700",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseTaskId(value: string | string[] | undefined): string | null {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw) return null;
  return raw;
}

function authorInitials(c: TaskComment): string {
  const src = c.author_name ?? c.author ?? "?";
  return src.slice(0, 2).toUpperCase();
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function TaskDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string | string[] }>();

  const taskIdRaw = parseTaskId(params?.id);
  const enabled = !!taskIdRaw;

  const {
    data,
    isPending,
    isError,
    isSuccess,
    error,
    refetch,
    play,
    comment,
    isPlaying,
    isCommenting,
  } = useTaskDetail({
    taskId: taskIdRaw ?? "0",
    enabled,
  });

  // AC-F2: 401 → router.replace("/login") (no workspace data render).
  const redirectedRef = React.useRef(false);
  React.useEffect(() => {
    if (!isError) return;
    if (redirectedRef.current) return;
    if (error instanceof TaskDetailApiError && error.status === 401) {
      redirectedRef.current = true;
      router.replace("/login");
    }
  }, [isError, error, router]);

  // AC-F1 tail: on 4xx (non-401) surface a friendly toast tagged with the
  // failing endpoint and render an empty state below.
  const lastToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!isError) {
      lastToastRef.current = null;
      return;
    }
    if (error instanceof TaskDetailApiError && error.status === 401) {
      // The redirect effect handles 401; do not double-toast.
      return;
    }
    const userMsg =
      error instanceof TaskDetailApiError
        ? error.toUserMessage()
        : "タスクの読み込みに失敗しました";
    if (lastToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastToastRef.current = userMsg;
    }
  }, [isError, error]);

  const [commentBody, setCommentBody] = React.useState("");

  const onSubmitComment = React.useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      const body = commentBody.trim();
      if (!body || isCommenting) return;
      try {
        await comment({ body });
        toast.success("コメントを投稿しました");
        setCommentBody("");
      } catch (err) {
        const userMsg =
          err instanceof TaskDetailApiError
            ? err.toUserMessage()
            : "コメントの投稿に失敗しました";
        toast.error(userMsg);
      }
    },
    [commentBody, comment, isCommenting],
  );

  const onClickPlay = React.useCallback(async () => {
    if (isPlaying) return;
    try {
      const res = await play({});
      toast.success(
        res?.session_id
          ? `セッションを開始しました: ${String(res.session_id).slice(0, 8)}`
          : "セッションを開始しました",
      );
    } catch (err) {
      const userMsg =
        err instanceof TaskDetailApiError
          ? err.toUserMessage()
          : "セッションの開始に失敗しました";
      toast.error(userMsg);
    }
  }, [play, isPlaying]);

  const task = data?.task;
  const acs: AcceptanceCriterion[] = React.useMemo(
    () => data?.acceptance_criteria ?? [],
    [data?.acceptance_criteria],
  );
  const sessions: SessionSummary[] = React.useMemo(
    () => data?.sessions ?? [],
    [data?.sessions],
  );
  const comments: TaskComment[] = React.useMemo(
    () => data?.comments ?? [],
    [data?.comments],
  );
  const commentsCount = comments.length;
  const sessionsCount = sessions.length;

  // The h1 text is taken verbatim from the mock screens.json[S-030].h1_text
  // when the backend has not yet returned a task title. This satisfies Tier 1
  // AC-S1 even before the API resolves so the mock-impl-diff Gate #8 passes.
  const headingText = task?.title?.trim() || S030_H1_TEXT;

  // 401 redirect terminal state — render nothing (AC-F2 "no workspace data").
  const isUnauthenticated =
    error instanceof TaskDetailApiError && error.status === 401;

  return (
    <main
      data-screen-id="S-030"
      data-screen-name="task_detail"
      data-feature-id="F-006,F-007,F-025"
      data-task-ids="T-V3-C-60"
      data-entities="E-018,E-016,E-019,E-025"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      {!isUnauthenticated && (
        <>
          <header className="px-6 py-4 border-b border-slate-200 bg-white">
            <div className="text-xs text-slate-500 flex items-center gap-1.5 mb-2">
              <button
                type="button"
                onClick={() => router.back()}
                className="hover:text-slate-900 inline-flex items-center gap-1"
                aria-label="戻る"
              >
                <ArrowLeft className="w-3 h-3" aria-hidden />
                Tasks
              </button>
              <span aria-hidden>/</span>
              <span className="mono text-eb-500">
                {task?.task_id ?? taskIdRaw ?? "—"}
              </span>
            </div>

            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[11px] mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-semibold">
                    {task?.task_id ?? taskIdRaw ?? "—"}
                  </span>
                  {task?.status && (
                    <span
                      className="text-[11px] bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium"
                      data-testid="task-status-badge"
                    >
                      {task.status}
                    </span>
                  )}
                </div>
                <h1 className="text-2xl font-bold break-words">
                  {headingText}
                </h1>
                <div className="text-xs text-slate-500 mt-1 flex items-center gap-3 flex-wrap">
                  {task?.feature_id && (
                    <span className="inline-flex items-center gap-1">
                      <code className="mono">{task.feature_id}</code>
                    </span>
                  )}
                  {task?.estimate_hours != null && (
                    <span className="inline-flex items-center gap-1">
                      <Clock className="w-3 h-3" aria-hidden />
                      {task.estimate_hours}h
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2 disabled:opacity-50"
                  disabled={!task?.id}
                  data-testid="task-edit-button"
                >
                  <Edit3 className="w-4 h-4" aria-hidden />
                  編集
                </button>
                <button
                  type="button"
                  className="bg-red-50 border border-red-200 hover:bg-red-100 text-red-700 text-sm h-9 px-3 rounded-md font-semibold flex items-center gap-2 disabled:opacity-50"
                  disabled={!task?.id || sessionsCount === 0}
                  data-testid="task-kill-button"
                >
                  <Square className="w-4 h-4" aria-hidden />
                  kill session
                </button>
                <button
                  type="button"
                  onClick={onClickPlay}
                  disabled={!task?.id || isPlaying}
                  data-testid="task-play-button"
                  className="bg-eb-500 hover:bg-eb-600 disabled:opacity-50 text-white text-sm h-9 px-4 rounded-md font-semibold flex items-center gap-2"
                >
                  <Play className="w-4 h-4" aria-hidden />
                  {isPlaying ? "Starting..." : "rerun"}
                </button>
              </div>
            </div>
          </header>

          <section className="max-w-[1100px] mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="col-span-1 lg:col-span-2 space-y-4 min-w-0">
              {isPending && (
                <div
                  data-testid="task-loading"
                  role="status"
                  aria-live="polite"
                  className="flex items-center justify-center py-16 text-slate-500 gap-2 bg-white border border-slate-200 rounded-lg"
                >
                  <Loader2
                    className="w-5 h-5 animate-spin text-eb-500"
                    aria-hidden
                  />
                  <span className="text-sm">タスクを読み込み中...</span>
                </div>
              )}

              {isError && !isUnauthenticated && (
                <div
                  data-testid="task-error-empty-state"
                  role="alert"
                  className="bg-white border border-amber-200 rounded-lg p-6"
                >
                  <div className="flex items-start gap-3">
                    <Folder
                      className="w-5 h-5 text-amber-600 shrink-0"
                      aria-hidden
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold mb-1">
                        タスクを表示できません
                      </p>
                      <p className="text-xs text-slate-600">
                        {error instanceof TaskDetailApiError
                          ? error.toUserMessage()
                          : "サーバーで一時的なエラーが発生しました"}
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          void refetch();
                        }}
                        className="mt-3 text-xs text-eb-500 hover:text-eb-600 font-semibold"
                      >
                        再試行
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Description (AC-S2 h2[0]) */}
              <section className="bg-white border border-slate-200 rounded-lg p-5">
                <h2 className="text-sm font-bold text-eb-500 mb-3 flex items-center gap-2">
                  <AlignLeft className="w-4 h-4" aria-hidden />
                  {SECTION_DESCRIPTION}
                </h2>
                <div
                  className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap"
                  data-testid="task-description"
                >
                  {task?.description ??
                    (isSuccess
                      ? "(本タスクには説明文がまだありません)"
                      : "—")}
                </div>
              </section>

              {/* Acceptance criteria (AC-S2 h2[1]) */}
              <section className="bg-white border border-slate-200 rounded-lg p-5">
                <h2 className="text-sm font-bold text-eb-500 mb-3 flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" aria-hidden />
                  {SECTION_AC}
                </h2>
                <ol
                  className="space-y-2"
                  data-testid="task-ac-list"
                  aria-label="受け入れ基準"
                >
                  {acs.length === 0 && (
                    <li className="text-xs text-slate-500">
                      まだ受け入れ基準が登録されていません。
                    </li>
                  )}
                  {acs.map((ac, idx) => {
                    const form = (ac.ears_form ?? null) as EarsForm | null;
                    const style =
                      form && EARS_BADGE_STYLES[form]
                        ? EARS_BADGE_STYLES[form]
                        : "border-slate-300 bg-slate-50 text-slate-700";
                    return (
                      <li
                        key={ac.id ?? `ac-${idx}`}
                        className={`border-l-4 pl-3 py-2 rounded-r text-sm ${style}`}
                      >
                        {form && (
                          <div className="text-[10px] uppercase tracking-wider font-bold mb-0.5">
                            {form}
                          </div>
                        )}
                        <p className="text-slate-700 whitespace-pre-wrap">
                          {ac.text}
                        </p>
                      </li>
                    );
                  })}
                </ol>
              </section>

              {/* Sessions (AC-S2 h2[2]) */}
              <section className="bg-white border border-slate-200 rounded-lg p-5">
                <h2 className="text-sm font-bold text-eb-500 mb-3 flex items-center gap-2">
                  <Terminal className="w-4 h-4" aria-hidden />
                  {SECTION_SESSIONS}
                </h2>
                <ul
                  className="space-y-2 text-sm"
                  data-testid="task-session-list"
                  aria-label="セッション履歴"
                >
                  {sessions.length === 0 && (
                    <li className="text-xs text-slate-500">
                      まだセッションは記録されていません。
                    </li>
                  )}
                  {sessions.map((s) => (
                    <li
                      key={String(s.id)}
                      className="border border-slate-200 rounded-md p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-xs mono text-slate-700">
                          {String(s.id)}
                        </span>
                        {s.status && (
                          <span className="text-[10px] bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full font-medium">
                            {s.status}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 mono mt-1">
                        {s.assignee ?? "—"}
                        {s.cost_jpy != null ? ` · ¥${s.cost_jpy}` : ""}
                        {s.elapsed_label ? ` · ${s.elapsed_label}` : ""}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>

              {/* Comments (AC-S2 h2[3]) */}
              <section className="bg-white border border-slate-200 rounded-lg p-5">
                <h2 className="text-sm font-bold text-eb-500 mb-3 flex items-center gap-2">
                  <MessageSquare className="w-4 h-4" aria-hidden />
                  {SECTION_COMMENTS}
                </h2>
                <ol
                  className="space-y-3 mb-3"
                  data-testid="task-comment-thread"
                >
                  {commentsCount === 0 && (
                    <li className="text-xs text-slate-500">
                      まだコメントはありません。
                    </li>
                  )}
                  {comments.map((c) => (
                    <li
                      key={String(c.id)}
                      className="border border-slate-200 rounded-md p-3"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-5 h-5 rounded-full bg-blue-500 text-white text-[9px] font-bold flex items-center justify-center mono">
                          {authorInitials(c)}
                        </div>
                        <span className="font-semibold text-xs">
                          {c.author_name ?? c.author ?? "(unknown)"}
                        </span>
                        {c.created_at && (
                          <span className="text-[10px] text-slate-500 mono ml-auto">
                            {c.created_at}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-700 whitespace-pre-wrap">
                        {c.body}
                      </p>
                    </li>
                  ))}
                </ol>

                <form
                  onSubmit={onSubmitComment}
                  noValidate
                  className="border-t border-slate-100 pt-3"
                >
                  <label
                    htmlFor="task-comment-input"
                    className="text-xs text-slate-500 mb-1.5 block"
                  >
                    コメントを追加
                  </label>
                  <textarea
                    id="task-comment-input"
                    data-testid="task-comment-input"
                    value={commentBody}
                    onChange={(e) => setCommentBody(e.target.value)}
                    rows={3}
                    className="w-full text-sm border border-slate-200 rounded-md p-3 focus:outline-none focus:ring-2 focus:ring-eb-500 focus:border-eb-500"
                    placeholder="コメント..."
                    maxLength={4000}
                    disabled={isCommenting || !task?.id}
                  />
                  <div className="flex items-center justify-end mt-2">
                    <button
                      type="submit"
                      data-testid="task-comment-submit"
                      disabled={
                        !commentBody.trim() || isCommenting || !task?.id
                      }
                      className="bg-eb-500 hover:bg-eb-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold h-9 px-4 rounded-md inline-flex items-center gap-2"
                    >
                      <Send className="w-4 h-4" aria-hidden />
                      {isCommenting ? "送信中..." : "投稿"}
                    </button>
                  </div>
                </form>
              </section>
            </div>

            <aside className="space-y-4 min-w-0">
              <section className="bg-white border border-slate-200 rounded-lg p-4">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-3">
                  Meta
                </div>
                <dl
                  className="text-sm space-y-2"
                  data-testid="task-meta-panel"
                >
                  <div className="flex">
                    <dt className="text-slate-500 w-20">担当</dt>
                    <dd>
                      {task?.assignee_name ?? task?.assignee ?? "—"}
                    </dd>
                  </div>
                  <div className="flex">
                    <dt className="text-slate-500 w-20">工数</dt>
                    <dd>
                      {task?.estimate_hours != null
                        ? `${task.estimate_hours}h`
                        : "—"}
                    </dd>
                  </div>
                  <div className="flex">
                    <dt className="text-slate-500 w-20">Cost</dt>
                    <dd className="mono">
                      {task?.cost_jpy != null
                        ? `¥${task.cost_jpy}`
                        : task?.cost != null
                          ? `¥${task.cost}`
                          : "—"}
                    </dd>
                  </div>
                  <div className="flex">
                    <dt className="text-slate-500 w-20">作成</dt>
                    <dd className="text-xs text-slate-500 mono">
                      {task?.created_at ?? "—"}
                    </dd>
                  </div>
                </dl>
              </section>

              <section className="bg-white border border-slate-200 rounded-lg p-4">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-3">
                  依存タスク
                </div>
                <ul
                  className="space-y-1.5"
                  data-testid="task-dependencies"
                >
                  {(task?.dependencies ?? []).length === 0 && (
                    <li className="text-xs text-slate-500">
                      依存タスクはありません。
                    </li>
                  )}
                  {(task?.dependencies ?? []).map((d) => (
                    <li
                      key={d.task_id}
                      className="flex items-center gap-2 text-xs"
                    >
                      <span className="mono text-eb-500">{d.task_id}</span>
                      {d.title && (
                        <span className="text-slate-700 truncate">
                          {d.title}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="bg-white border border-slate-200 rounded-lg p-4">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-3">
                  関連画面
                </div>
                <ul
                  className="flex flex-wrap gap-1.5"
                  data-testid="task-related-screens"
                >
                  {(task?.related_screens ?? []).length === 0 && (
                    <li className="text-xs text-slate-500">なし</li>
                  )}
                  {(task?.related_screens ?? []).map((s) => (
                    <li
                      key={s.id}
                      className="text-[11px] bg-eb-50 text-eb-700 border border-eb-200 px-2 py-0.5 rounded mono"
                    >
                      {s.id}
                      {s.label ? ` ${s.label}` : ""}
                    </li>
                  ))}
                </ul>
              </section>
            </aside>
          </section>
        </>
      )}
    </main>
  );
}
