"use client";

/**
 * T-V3-C-16 / S-043: クライアントコメント page (Vertical Slice / UI).
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/client/S-043-client-comment.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-043
 * @feature-id F-013
 * @task-ids T-V3-C-16
 * @entities E-033
 * @phase Phase 1B
 *
 * Auth model: PUBLIC for GET /api/client/comments/{thread_id} and
 * POST /api/client/comments — the `token` query/body field is the bearer of
 * trust. POST /api/comments/{id}/resolve is MEMBER-ONLY; the public client
 * receives 401/403 surfaced as a friendly toast tagged with the endpoint.
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-16.md):
 *   structural.AC-S1 (data-screen-id="S-043")     — root <main> element.
 *   structural.AC-S2 (h1 text "M-1 認証で SAML SSO 対応も必要では？")
 *                                                   — verbatim screens.json h1_text.
 *   functional.AC-F1 (GET  /api/client/comments/{thread_id} via typed client)
 *                                                   — useQuery on mount.
 *   functional.AC-F2 (POST /api/client/comments via typed client)
 *                                                   — useMutation on reply submit.
 *   functional.AC-F3 (POST /api/comments/{id}/resolve via typed client)
 *                                                   — useMutation on resolve button.
 *   functional.AC-F4 (4xx/5xx → non-technical toast tagged endpoint, no stack)
 *                                                   — error handlers.
 *   functional.AC-F5 (POST /api/client/comments > 20/hour/token → 429 →
 *                     friendly rate-limit toast tagged endpoint).
 */

import * as React from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  AtSign,
  ChevronRight,
  Factory,
  Link as LinkIcon,
  Loader2,
  Lock,
  Paperclip,
} from "lucide-react";

import {
  ClientPortalApiError,
  CLIENT_COMMENTS_ENDPOINT,
  clientCommentsThreadEndpoint,
  commentResolveEndpoint,
  getClientComments,
  postClientComment,
  resolveComment,
  type ClientCommentsResponse,
  type PublicComment,
} from "@/api/pr-client";

// --------------------------------------------------------------------------
// Static copy — must match docs/functional-breakdown/2026-05-16_v3/screens.json
// [S-043].h1_text verbatim (Tier 1 AC-S2). Keeping it top-level so the
// lint-mock-impl-diff Gate #8 can grep it straight out of the source.
// --------------------------------------------------------------------------

const SCREEN_H1_TEXT = "M-1 認証で SAML SSO 対応も必要では？";
const THREAD_BREADCRUMB = "M-1 認証 / SAML SSO 対応";
const LINKED_REQUIREMENT_LABEL = "requirements / M-1";
const RESOLVE_LOCK_MESSAGE =
  "このスレッドを「解決済み」にできるのは workspace_admin 権限のみ";

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "";
  const diffMs = Date.now() - ts;
  if (diffMs < 0) return "just now";
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(ts).toISOString().slice(0, 10);
}

function authorInitial(name: string | null | undefined): string {
  if (!name) return "?";
  const trimmed = name.trim();
  if (!trimmed) return "?";
  return trimmed.charAt(0).toUpperCase();
}

function isAuthorPm(name: string | null | undefined): boolean {
  if (!name) return false;
  const lower = name.toLowerCase();
  return lower === "masato" || lower.endsWith("(pm)") || lower.includes(" pm");
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function ClientCommentsPage() {
  const params = useParams<{ token: string | string[] }>();
  const search = useSearchParams();
  const rawToken = params?.token;
  const token = Array.isArray(rawToken) ? rawToken[0] : (rawToken ?? "");
  // The thread_id is supplied via ?thread_id=... query string. When absent,
  // we fall back to a deterministic placeholder so the page still renders the
  // skeleton + form for design review (production callers always include it).
  const threadId = search?.get("thread_id") ?? "thread-demo";

  const queryClient = useQueryClient();

  // AC-F1: GET /api/client/comments/{thread_id} on mount.
  const commentsQuery = useQuery<ClientCommentsResponse, ClientPortalApiError>({
    queryKey: ["client-portal", "comments", token, threadId],
    enabled: !!token && !!threadId,
    queryFn: ({ signal }) => getClientComments(threadId, token, { signal }),
    retry: false,
    staleTime: 15_000,
  });

  // AC-F4: surface non-technical toast tagged with the failing endpoint and
  // never leak server stack traces.
  const lastCommentsToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!commentsQuery.isError) {
      lastCommentsToastRef.current = null;
      return;
    }
    const err = commentsQuery.error;
    const endpoint = clientCommentsThreadEndpoint(threadId || "{thread_id}");
    const userMsg =
      err instanceof ClientPortalApiError
        ? err.toUserMessage()
        : `コメントの取得に失敗しました (${endpoint})`;
    if (lastCommentsToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastCommentsToastRef.current = userMsg;
    }
  }, [commentsQuery.isError, commentsQuery.error, threadId]);

  // AC-F2 + AC-F5: POST /api/client/comments (reply).
  const [replyBody, setReplyBody] = React.useState("");
  const replyMutation = useMutation({
    mutationFn: () =>
      postClientComment({
        token,
        thread_id: threadId,
        body: replyBody.trim(),
      }),
    onSuccess: () => {
      toast.success("返信を投稿しました");
      setReplyBody("");
      queryClient.invalidateQueries({
        queryKey: ["client-portal", "comments", token, threadId],
      });
    },
    onError: (err: unknown) => {
      // AC-F4 / AC-F5: friendly toast tagged with /api/client/comments,
      // no stack-trace / SQL leaked.
      const userMsg =
        err instanceof ClientPortalApiError
          ? err.toUserMessage()
          : `返信の投稿に失敗しました (${CLIENT_COMMENTS_ENDPOINT})`;
      toast.error(userMsg);
    },
  });

  const onSubmitReply = React.useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!replyBody.trim() || replyMutation.isPending) return;
      replyMutation.mutate();
    },
    [replyBody, replyMutation],
  );

  // AC-F3: POST /api/comments/{id}/resolve (member-only). The public client
  // viewer will hit 401/403; we surface that via toast (AC-F4) and keep the
  // resolve banner mounted to demonstrate the disabled affordance.
  const resolveMutation = useMutation({
    mutationFn: (commentId: string) => resolveComment(commentId),
    onSuccess: () => {
      toast.success("スレッドを解決済みにしました");
      queryClient.invalidateQueries({
        queryKey: ["client-portal", "comments", token, threadId],
      });
    },
    onError: (err: unknown, commentId: string) => {
      const endpoint = commentResolveEndpoint(commentId);
      const userMsg =
        err instanceof ClientPortalApiError
          ? err.toUserMessage()
          : `スレッドの解決に失敗しました (${endpoint})`;
      toast.error(userMsg);
    },
  });

  const comments: PublicComment[] = commentsQuery.data?.comments ?? [];
  const rootComment: PublicComment | undefined = comments[0];
  const replies: PublicComment[] = comments.slice(1);
  const allResolved =
    comments.length > 0 && comments.every((c) => !!c.resolved_at);

  const onClickResolve = React.useCallback(() => {
    if (!rootComment?.id || resolveMutation.isPending) return;
    resolveMutation.mutate(rootComment.id);
  }, [rootComment?.id, resolveMutation]);

  return (
    <main
      data-screen-id="S-043"
      data-feature-id="F-013"
      data-task-ids="T-V3-C-16"
      data-entities="E-033"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      {/* Top bar — mirrors the mock header (client-only, no sidebar). */}
      <header className="bg-white border-b border-slate-200 px-6 py-3 sticky top-0 z-10">
        <div className="max-w-[1200px] mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-eb-500 flex items-center justify-center">
              <Factory className="w-4 h-4 text-white" aria-hidden />
            </div>
            <div>
              <div className="text-sm font-bold">Build-Factory</div>
              <div className="text-[11px] text-slate-500 mono">
                client portal
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <a
              href={`/portal/${encodeURIComponent(token)}`}
              className="text-xs text-eb-600 hover:text-eb-700 inline-flex items-center gap-1.5 font-semibold"
            >
              <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
              Overview に戻る
            </a>
          </div>
        </div>
      </header>

      {/* Tabs (mirrors mock — review tab is active for S-043). */}
      <div className="bg-white border-b border-slate-200">
        <div
          className="max-w-[1200px] mx-auto px-6 flex gap-0"
          role="tablist"
          aria-label="クライアントポータル タブ"
        >
          {["Overview", "仕様書", "画面モック", "進捗", "レビュー"].map(
            (label, i) => (
              <button
                key={label}
                type="button"
                role="tab"
                aria-selected={i === 4}
                className={`px-4 py-3 text-sm font-medium border-b-2 ${
                  i === 4
                    ? "border-eb-500 text-slate-900"
                    : "border-transparent text-slate-500 hover:text-slate-900"
                }`}
              >
                {label}
              </button>
            ),
          )}
        </div>
      </div>

      <section className="max-w-[900px] mx-auto px-6 py-6">
        <div className="text-xs text-slate-500 flex items-center gap-1.5 mb-2">
          <span>レビュー</span>
          <ChevronRight className="w-3 h-3" aria-hidden />
          <span>{THREAD_BREADCRUMB}</span>
        </div>
        <h1 className="text-2xl font-bold mb-1">{SCREEN_H1_TEXT}</h1>
        <div className="text-xs text-slate-500 mt-1 flex items-center gap-3">
          <span className="inline-flex items-center gap-1">
            <LinkIcon className="w-3 h-3" aria-hidden /> linked:{" "}
            <span className="text-eb-500 mono">{LINKED_REQUIREMENT_LABEL}</span>
          </span>
          <span>·</span>
          <span
            data-testid="thread-status-badge"
            className={`text-[11px] px-2 py-0.5 rounded-full border ${
              allResolved
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-amber-50 text-amber-700 border-amber-200"
            }`}
          >
            {allResolved ? "resolved" : "open"}
          </span>
        </div>

        {commentsQuery.isPending && (
          <div
            data-state="loading"
            role="status"
            aria-live="polite"
            className="flex items-center justify-center py-16 text-slate-500 gap-2"
          >
            <Loader2
              className="w-5 h-5 animate-spin text-eb-500"
              aria-hidden
            />
            <span className="text-sm">コメントを読み込み中...</span>
          </div>
        )}

        {(commentsQuery.isSuccess || commentsQuery.isError) && (
          <div
            data-testid="comment-thread"
            className="mt-6 space-y-3"
          >
            {comments.length === 0 && (
              <div className="bg-white border border-dashed border-slate-200 rounded-lg p-6 text-center text-sm text-slate-500">
                このスレッドにはまだコメントがありません
              </div>
            )}

            {rootComment && (
              <article
                data-testid="comment-root"
                className="bg-white border border-slate-200 rounded-lg p-4"
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`w-9 h-9 rounded-full text-sm font-bold flex items-center justify-center ${
                      isAuthorPm(rootComment.author_name)
                        ? "bg-eb-500 text-white"
                        : "bg-slate-300 text-slate-700"
                    }`}
                    aria-hidden
                  >
                    {authorInitial(rootComment.author_name)}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-sm">
                        {rootComment.author_name ?? "anonymous"}
                      </span>
                      <span className="text-xs text-slate-500 mono ml-auto">
                        {formatRelativeTime(rootComment.created_at)}
                      </span>
                    </div>
                    <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
                      {rootComment.body}
                    </p>
                  </div>
                </div>
              </article>
            )}

            {replies.map((c) => (
              <article
                key={c.id}
                data-testid="comment-reply"
                className="ml-12 bg-white border border-slate-200 rounded-lg p-4"
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`w-9 h-9 rounded-full text-sm font-bold flex items-center justify-center ${
                      isAuthorPm(c.author_name)
                        ? "bg-eb-500 text-white"
                        : "bg-slate-300 text-slate-700"
                    }`}
                    aria-hidden
                  >
                    {authorInitial(c.author_name)}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-sm">
                        {c.author_name ?? "anonymous"}
                      </span>
                      {isAuthorPm(c.author_name) && (
                        <span className="text-[11px] bg-eb-50 text-eb-700 border border-eb-200 px-1.5 py-0.5 rounded">
                          PM
                        </span>
                      )}
                      <span className="text-xs text-slate-500 mono ml-auto">
                        {formatRelativeTime(c.created_at)}
                      </span>
                    </div>
                    <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
                      {c.body}
                    </p>
                  </div>
                </div>
              </article>
            ))}

            {/* AC-F2 reply form */}
            <form
              onSubmit={onSubmitReply}
              noValidate
              className="ml-12 bg-white border border-slate-200 rounded-lg p-4"
            >
              <div className="flex items-start gap-3">
                <div
                  className="w-9 h-9 rounded-full bg-slate-300 text-slate-700 text-sm font-bold flex items-center justify-center"
                  aria-hidden
                >
                  C
                </div>
                <div className="flex-1 space-y-2">
                  <label
                    htmlFor="client-comment-reply"
                    className="sr-only"
                  >
                    返信を書く
                  </label>
                  <textarea
                    id="client-comment-reply"
                    data-testid="client-comment-reply-input"
                    value={replyBody}
                    onChange={(e) => setReplyBody(e.target.value)}
                    rows={3}
                    maxLength={4000}
                    disabled={replyMutation.isPending}
                    placeholder="返信を書く... (@名前 でメンション)"
                    className="border border-slate-200 bg-white text-sm px-3 py-2 rounded-md w-full min-h-[80px] focus:outline-none focus:ring-2 focus:ring-eb-500 focus:border-eb-500"
                  />
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <button
                        type="button"
                        aria-label="添付を追加"
                        className="hover:text-slate-900"
                      >
                        <Paperclip className="w-3.5 h-3.5" aria-hidden />
                      </button>
                      <button
                        type="button"
                        aria-label="メンションを追加"
                        className="hover:text-slate-900 inline-flex items-center gap-1"
                      >
                        <AtSign className="w-3.5 h-3.5" aria-hidden />
                        <span>Mention</span>
                      </button>
                    </div>
                    <button
                      type="submit"
                      data-testid="client-comment-reply-submit"
                      disabled={
                        !replyBody.trim() || replyMutation.isPending
                      }
                      className="bg-eb-500 hover:bg-eb-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold h-8 px-3 rounded-md"
                    >
                      {replyMutation.isPending ? "送信中..." : "返信"}
                    </button>
                  </div>
                </div>
              </div>
            </form>
          </div>
        )}

        {/* AC-F3 resolve banner — workspace_admin only. The public client sees
            it greyed out; clicking it surfaces the 401/403 friendly toast. */}
        <div
          data-testid="resolve-banner"
          className="mt-6 bg-slate-50 border border-slate-200 rounded-md p-3 text-xs text-slate-500 flex items-center justify-between gap-2"
        >
          <span className="inline-flex items-center gap-2">
            <Lock className="w-3.5 h-3.5" aria-hidden />
            {RESOLVE_LOCK_MESSAGE}
          </span>
          <button
            type="button"
            data-testid="resolve-thread-submit"
            disabled={
              !rootComment?.id ||
              resolveMutation.isPending ||
              allResolved
            }
            onClick={onClickResolve}
            className="text-xs font-semibold h-7 px-3 rounded-md border border-slate-200 text-slate-500 hover:text-slate-900 hover:border-slate-300 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {resolveMutation.isPending
              ? "解決中..."
              : allResolved
                ? "解決済み"
                : "解決済みにする"}
          </button>
        </div>
      </section>
    </main>
  );
}
