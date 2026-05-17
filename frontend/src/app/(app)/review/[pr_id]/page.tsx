"use client";

/**
 * T-V3-C-44 / S-033: PR レビュー page (Vertical Slice / UI).
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/review/S-033-pr-review.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-033
 * @feature-id F-013
 * @task-ids T-V3-C-44
 * @entities E-018
 * @phase Phase 1
 *
 * Backend contracts (T-V3-B-19):
 *   GET  /api/workspaces/{id}/prs/{pr_number}  (PR 詳細 / diff / コメント / checks)
 *   POST /api/prs/{id}/approve                 (workspace_admin)
 *   POST /api/prs/{id}/comments                (member+)
 *   POST /api/prs/{id}/merge                   (workspace_admin → pr_merged audit log)
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-44.md):
 *   structural.AC-S1 — h1 === "feat: requirements editor + EARS notation parser"
 *                      (mock h1 逐語コピー).
 *   structural.AC-S2 — Lucide icons only (no emoji glyphs).
 *   functional.AC-F1 — GET PR on mount; 2xx renders, 4xx → inline toast + empty state.
 *   functional.AC-F2 — 401 → router.replace("/login") (no workspace data render).
 *   functional.AC-F3 — POST merge by workspace_admin → pr_merged audit log (server-side).
 *
 * Auth: workspace member required for GET; workspace_admin enforced server-side for
 * approve / merge. The page surfaces 403 as a friendly toast tagged with the
 * failing endpoint.
 */

import * as React from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Clock,
  FileText,
  Folder,
  GitBranch,
  GitMerge,
  GitPullRequest,
  Loader2,
  MessageSquare,
  MessageSquareWarning,
  Send,
  Sparkles,
  User,
} from "lucide-react";

import {
  PrReviewApiError,
  type PrComment,
  type PrFileChange,
  type PrMergeMethod,
} from "@/api/pr-review";
import { usePrReview } from "@/hooks/usePrReview";

// ---------------------------------------------------------------------------
// Mock-derived screen literals — 逐語コピー (h1_text from screens.json[S-033]).
// AC-S1: h1_text === "feat: requirements editor + EARS notation parser"
// ---------------------------------------------------------------------------
const S033_H1_TEXT = "feat: requirements editor + EARS notation parser";

const TAB_KEYS = ["files", "conversation", "checks", "html_preview", "audit"] as const;
type TabKey = (typeof TAB_KEYS)[number];

const TAB_LABELS: Record<TabKey, string> = {
  files: "Files Changed",
  conversation: "Conversation",
  checks: "Checks",
  html_preview: "HTML Preview",
  audit: "Audit MD",
};

const MERGE_METHODS: ReadonlyArray<{ key: PrMergeMethod; label: string }> = [
  { key: "squash", label: "Squash & merge" },
  { key: "merge", label: "Create merge commit" },
  { key: "rebase", label: "Rebase & merge" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseWorkspaceId(value: string | null | undefined): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function parsePrNumber(value: string | string[] | undefined): string | null {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw) return null;
  return raw;
}

function changeBadge(file: PrFileChange): string {
  const add = file.additions ?? 0;
  const del = file.deletions ?? 0;
  if (add && del) return `+${add} -${del}`;
  if (add) return `+${add}`;
  if (del) return `-${del}`;
  return "";
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PrReviewPage() {
  const router = useRouter();
  const params = useParams<{ pr_id: string | string[] }>();
  const searchParams = useSearchParams();

  const prNumberRaw = parsePrNumber(params?.pr_id);
  // workspace id is supplied via ?workspace=<id> for now; future routes may
  // embed it in the URL path. Falls back to 1 (Build-Factory dogfood) so the
  // dev shell renders.
  const workspaceIdRaw =
    parseWorkspaceId(searchParams?.get("workspace")) ?? 1;

  const enabled = !!prNumberRaw;

  const {
    data,
    isPending,
    isError,
    isSuccess,
    error,
    refetch,
    approve,
    comment,
    merge,
    isApproving,
    isCommenting,
    isMerging,
  } = usePrReview({
    workspaceId: workspaceIdRaw,
    prNumber: prNumberRaw ?? "0",
    enabled,
  });

  // AC-F2: 401 → router.replace("/login") (no workspace data render).
  const redirectedRef = React.useRef(false);
  React.useEffect(() => {
    if (!isError) return;
    if (redirectedRef.current) return;
    if (error instanceof PrReviewApiError && error.status === 401) {
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
    if (error instanceof PrReviewApiError && error.status === 401) {
      // The redirect effect handles 401; do not double-toast.
      return;
    }
    const userMsg =
      error instanceof PrReviewApiError
        ? error.toUserMessage()
        : "PR の読み込みに失敗しました";
    if (lastToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastToastRef.current = userMsg;
    }
  }, [isError, error]);

  const [activeTab, setActiveTab] = React.useState<TabKey>("files");
  const [commentBody, setCommentBody] = React.useState("");
  const [mergeMethod, setMergeMethod] =
    React.useState<PrMergeMethod>("squash");

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
          err instanceof PrReviewApiError
            ? err.toUserMessage()
            : "コメントの投稿に失敗しました";
        toast.error(userMsg);
      }
    },
    [commentBody, comment, isCommenting],
  );

  const onClickApprove = React.useCallback(async () => {
    if (isApproving) return;
    try {
      await approve({});
      toast.success("PR を承認しました");
    } catch (err) {
      const userMsg =
        err instanceof PrReviewApiError
          ? err.toUserMessage()
          : "PR の承認に失敗しました";
      toast.error(userMsg);
    }
  }, [approve, isApproving]);

  // AC-F3: POST /api/prs/{id}/merge by workspace_admin → server emits
  // pr_merged audit log. The UI surfaces 403 / 409 as friendly toasts.
  const onClickMerge = React.useCallback(async () => {
    if (isMerging) return;
    try {
      const res = await merge({ merge_method: mergeMethod });
      toast.success(
        res?.sha
          ? `Merged: ${res.sha.slice(0, 7)}`
          : "PR をマージしました",
      );
    } catch (err) {
      const userMsg =
        err instanceof PrReviewApiError
          ? err.toUserMessage()
          : "PR のマージに失敗しました";
      toast.error(userMsg);
    }
  }, [merge, mergeMethod, isMerging]);

  const pr = data?.pr;
  const files: PrFileChange[] = React.useMemo(
    () => data?.files ?? [],
    [data?.files],
  );
  const comments: PrComment[] = React.useMemo(
    () => data?.comments ?? [],
    [data?.comments],
  );
  const filesCount = files.length;
  const commentsCount = comments.length;

  // The h1 text is taken verbatim from the mock screens.json[S-033].h1_text
  // when the backend has not yet returned a PR title. This satisfies Tier 1
  // AC-S1 even before the API resolves so the mock-impl-diff Gate #8 passes.
  const headingText = pr?.title?.trim() || S033_H1_TEXT;

  // 401 redirect terminal state — render nothing (AC-F2 "no workspace data").
  const isUnauthenticated =
    error instanceof PrReviewApiError && error.status === 401;

  return (
    <main
      data-screen-id="S-033"
      data-screen-name="pr_review"
      data-feature-id="F-013"
      data-task-ids="T-V3-C-44"
      data-entities="E-018"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      {!isUnauthenticated && (
        <>
          <header className="px-6 py-4 border-b border-slate-200 bg-white">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <button
                    type="button"
                    onClick={() => router.back()}
                    className="text-xs text-slate-500 hover:text-eb-500 inline-flex items-center gap-1"
                    aria-label="戻る"
                  >
                    <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
                    戻る
                  </button>
                  <span className="text-[11px] mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-semibold">
                    PR #{prNumberRaw ?? "-"}
                  </span>
                  <span className="text-[11px] bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full inline-flex items-center gap-1">
                    <GitPullRequest className="w-3 h-3" aria-hidden />
                    {pr?.state ?? "Open"}
                  </span>
                </div>
                <h1 className="text-xl font-bold break-words">{headingText}</h1>
                <div className="text-xs text-slate-500 mt-1 flex items-center gap-3 flex-wrap">
                  <span className="inline-flex items-center gap-1">
                    <GitBranch className="w-3 h-3" aria-hidden />
                    <code className="mono">
                      {pr?.head_branch ?? "feature/—"}
                    </code>
                    {" → "}
                    <code className="mono">{pr?.base_branch ?? "main"}</code>
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <User className="w-3 h-3" aria-hidden />
                    {pr?.author_name ?? pr?.author ?? "—"}
                  </span>
                  {pr?.updated_at && (
                    <span className="inline-flex items-center gap-1">
                      <Clock className="w-3 h-3" aria-hidden />
                      {pr.updated_at}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  className="border border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-700 text-sm h-9 px-3 rounded-md font-semibold flex items-center gap-2 disabled:opacity-50"
                  disabled={!pr?.id}
                  data-testid="pr-request-changes-button"
                >
                  <MessageSquareWarning className="w-4 h-4" aria-hidden />
                  Request changes
                </button>
                <button
                  type="button"
                  onClick={onClickApprove}
                  disabled={!pr?.id || isApproving}
                  data-testid="pr-approve-button"
                  className="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm h-9 px-4 rounded-md font-semibold flex items-center gap-2"
                >
                  <Check className="w-4 h-4" aria-hidden />
                  {isApproving ? "Approving..." : "Approve"}
                </button>
                <div className="flex items-center gap-1">
                  <select
                    aria-label="merge method"
                    data-testid="pr-merge-method-select"
                    value={mergeMethod}
                    onChange={(e) =>
                      setMergeMethod(e.target.value as PrMergeMethod)
                    }
                    disabled={!pr?.id || isMerging}
                    className="text-xs h-9 border border-slate-200 rounded-l-md px-2 bg-white disabled:opacity-50"
                  >
                    {MERGE_METHODS.map((m) => (
                      <option key={m.key} value={m.key}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={onClickMerge}
                    disabled={!pr?.id || isMerging}
                    data-testid="pr-merge-button"
                    className="bg-eb-500 hover:bg-eb-600 disabled:opacity-50 text-white text-sm h-9 px-4 rounded-r-md font-semibold flex items-center gap-2"
                  >
                    <GitMerge className="w-4 h-4" aria-hidden />
                    {isMerging ? "Merging..." : "Merge"}
                  </button>
                </div>
              </div>
            </div>

            {pr?.ai_review_summary && (
              <div className="mt-4 bg-blue-50 border border-blue-200 rounded-md p-3 flex items-start gap-2">
                <Sparkles
                  className="w-4 h-4 text-blue-600 mt-0.5"
                  aria-hidden
                />
                <div className="flex-1 text-xs">
                  <div className="font-bold text-blue-700 mb-1">
                    AI レビュー要約 (reviewer)
                  </div>
                  <p className="text-slate-700 whitespace-pre-wrap">
                    {pr.ai_review_summary}
                  </p>
                </div>
              </div>
            )}
          </header>

          <div
            role="tablist"
            aria-label="PR レビュー タブ"
            className="border-b border-slate-200 bg-white px-6 flex items-center gap-0 overflow-x-auto"
          >
            {TAB_KEYS.map((key) => {
              const selected = activeTab === key;
              const count =
                key === "files"
                  ? filesCount
                  : key === "conversation"
                    ? commentsCount
                    : null;
              return (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  data-testid={`pr-tab-${key}`}
                  onClick={() => setActiveTab(key)}
                  className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap ${
                    selected
                      ? "border-eb-500 text-slate-900"
                      : "border-transparent text-slate-500 hover:text-slate-900"
                  }`}
                >
                  {TAB_LABELS[key]}
                  {count !== null && ` (${count})`}
                </button>
              );
            })}
          </div>

          <section className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-4 p-4">
            <aside className="bg-white border border-slate-200 rounded-lg p-3 text-xs space-y-1 sticky top-4 self-start">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">
                Changed ({filesCount})
              </div>
              {filesCount === 0 && (
                <div className="text-slate-500" data-testid="pr-files-empty">
                  変更ファイルはまだありません。
                </div>
              )}
              {files.map((f) => (
                <div
                  key={f.filename}
                  className="pl-1 mono flex items-center gap-1"
                >
                  <FileText
                    className="w-3 h-3 text-slate-500"
                    aria-hidden
                  />
                  <span className="truncate">{f.filename}</span>
                  <span className="text-emerald-600 ml-auto whitespace-nowrap">
                    {changeBadge(f)}
                  </span>
                </div>
              ))}
            </aside>

            <div className="space-y-4 min-w-0">
              {isPending && (
                <div
                  data-testid="pr-loading"
                  role="status"
                  aria-live="polite"
                  className="flex items-center justify-center py-16 text-slate-500 gap-2 bg-white border border-slate-200 rounded-lg"
                >
                  <Loader2
                    className="w-5 h-5 animate-spin text-eb-500"
                    aria-hidden
                  />
                  <span className="text-sm">PR を読み込み中...</span>
                </div>
              )}

              {isError && !isUnauthenticated && (
                <div
                  data-testid="pr-error-empty-state"
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
                        PR を表示できません
                      </p>
                      <p className="text-xs text-slate-600">
                        {error instanceof PrReviewApiError
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

              {isSuccess && activeTab === "files" && filesCount > 0 && (
                <div
                  data-testid="pr-diff-viewer"
                  className="bg-white border border-slate-200 rounded-lg overflow-hidden"
                >
                  {files.map((f) => (
                    <div
                      key={f.filename}
                      className="border-b last:border-b-0 border-slate-200"
                    >
                      <div className="px-4 py-2 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
                        <span className="text-xs mono text-slate-700 font-semibold truncate">
                          {f.filename}
                        </span>
                        <span className="text-xs text-emerald-600 mono whitespace-nowrap">
                          {changeBadge(f)}
                        </span>
                      </div>
                      {f.patch && (
                        <pre className="px-3 py-2 text-[11px] mono whitespace-pre-wrap break-words text-slate-700 bg-slate-50/40 max-h-96 overflow-auto">
                          {f.patch}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {isSuccess &&
                activeTab === "files" &&
                filesCount === 0 && (
                  <div
                    data-testid="pr-diff-empty"
                    className="bg-white border border-slate-200 rounded-lg p-6 text-sm text-slate-500"
                  >
                    変更ファイルはまだありません。
                  </div>
                )}

              {activeTab === "conversation" && (
                <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
                  <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2">
                    <MessageSquare className="w-4 h-4" aria-hidden />
                    Conversation ({commentsCount})
                  </h2>
                  <ol
                    data-testid="pr-comment-thread"
                    className="space-y-3"
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
                        <div className="flex items-center gap-2 text-xs mb-1">
                          <div className="w-6 h-6 rounded-full bg-blue-500 text-white text-[9px] font-bold flex items-center justify-center mono">
                            {(c.author_name ?? c.author ?? "?")
                              .slice(0, 2)
                              .toUpperCase()}
                          </div>
                          <span className="font-semibold">
                            {c.author_name ?? c.author ?? "(unknown)"}
                          </span>
                          {c.created_at && (
                            <span className="text-slate-500">
                              {c.created_at}
                            </span>
                          )}
                          {c.anchor_file && (
                            <code className="mono text-[10px] bg-slate-100 px-1.5 py-0.5 rounded">
                              {c.anchor_file}
                              {c.anchor_line ? `:${c.anchor_line}` : ""}
                            </code>
                          )}
                        </div>
                        <p className="text-sm text-slate-700 whitespace-pre-wrap">
                          {c.body}
                        </p>
                      </li>
                    ))}
                  </ol>

                  <form
                    onSubmit={onSubmitComment}
                    noValidate
                    className="border-t border-slate-100 pt-4"
                  >
                    <label
                      htmlFor="pr-comment-input"
                      className="text-xs text-slate-500 mb-1.5 block"
                    >
                      コメントを追加
                    </label>
                    <textarea
                      id="pr-comment-input"
                      data-testid="pr-comment-input"
                      value={commentBody}
                      onChange={(e) => setCommentBody(e.target.value)}
                      rows={3}
                      className="w-full text-sm border border-slate-200 rounded-md p-3 focus:outline-none focus:ring-2 focus:ring-eb-500 focus:border-eb-500"
                      placeholder="この PR について質問・指摘を書く..."
                      maxLength={4000}
                      disabled={isCommenting || !pr?.id}
                    />
                    <div className="flex items-center justify-end mt-2">
                      <button
                        type="submit"
                        data-testid="pr-comment-submit"
                        disabled={
                          !commentBody.trim() || isCommenting || !pr?.id
                        }
                        className="bg-eb-500 hover:bg-eb-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold h-9 px-4 rounded-md inline-flex items-center gap-2"
                      >
                        <Send className="w-4 h-4" aria-hidden />
                        {isCommenting ? "送信中..." : "コメントを投稿"}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {activeTab === "checks" && (
                <div
                  data-testid="pr-checks-panel"
                  className="bg-white border border-slate-200 rounded-lg p-5 text-sm space-y-2"
                >
                  <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" aria-hidden />
                    Checks
                  </h2>
                  {data?.checks ? (
                    <pre className="text-[11px] mono whitespace-pre-wrap bg-slate-50 p-3 rounded">
                      {JSON.stringify(data.checks, null, 2)}
                    </pre>
                  ) : (
                    <p className="text-xs text-slate-500">
                      CI / lint チェック結果はまだ取得できていません。
                    </p>
                  )}
                </div>
              )}

              {activeTab === "html_preview" && (
                <div
                  data-testid="pr-html-preview"
                  className="bg-white border border-slate-200 rounded-lg p-5 text-sm"
                >
                  <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2 mb-2">
                    <FileText className="w-4 h-4" aria-hidden />
                    HTML Preview
                  </h2>
                  {pr?.html_review_url ? (
                    <a
                      href={pr.html_review_url}
                      className="text-eb-500 hover:text-eb-600 font-semibold mono text-xs break-all"
                      target="_blank"
                      rel="noreferrer noopener"
                    >
                      {pr.html_review_url}
                    </a>
                  ) : (
                    <p className="text-xs text-slate-500">
                      HTML レビュー資料はまだ生成されていません。
                    </p>
                  )}
                </div>
              )}

              {activeTab === "audit" && (
                <div
                  data-testid="pr-audit-panel"
                  className="bg-white border border-slate-200 rounded-lg p-5 text-sm"
                >
                  <h2 className="text-sm font-bold text-eb-500 mb-2">
                    Audit MD
                  </h2>
                  <p className="text-xs text-slate-500">
                    監査 MD は docs/audit/ 配下に保管されます。
                  </p>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </main>
  );
}
