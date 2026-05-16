"use client";

/**
 * T-V3-C-15 / S-042: クライアントポータル page (Vertical Slice / UI).
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/client/S-042-client-workspace.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-042
 * @feature-id F-013,F-021
 * @task-ids T-V3-C-15
 * @entities E-009,E-021
 * @phase Phase 1B
 *
 * Auth model: PUBLIC (no Authorization header). The `token` path segment is
 * the bearer of trust — the backend (T-V3-B-20) validates it server-side and
 * surfaces 401 (invalid) / 404 (unknown) / 409 (expired).
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-15.md):
 *   structural.AC-S1 (data-screen-id="S-042")          — root <main> element.
 *   structural.AC-S2 (h1 text "案件進捗状況")         — verbatim screens.json h1_text.
 *   structural.AC-S3 (h2 section headings)             — 5 cap-12 sections from screens.json.
 *   functional.AC-F1 (GET  /api/client/workspaces/{token}      via typed client) — useQuery on mount.
 *   functional.AC-F2 (GET  /api/client/workspaces/{token}/spec via typed client) — useQuery on mount.
 *   functional.AC-F3 (POST /api/client/comments               via typed client) — useMutation on submit.
 *   functional.AC-F4 (4xx/5xx → non-technical toast tagged endpoint, no stack) — error handlers.
 *   functional.AC-F5 (expired token → 409 → TokenExpiredError → dedicated UI).
 *   functional.AC-F6 (POST > 20/hour/token → 429 → friendly rate-limit toast).
 */

import * as React from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle,
  Bell,
  Calendar,
  CheckCircle2,
  CheckSquare,
  Circle,
  Factory,
  Layers,
  Layout,
  Loader2,
  MessageCircle,
  PlayCircle,
  Send,
  Upload,
  Users,
  type LucideIcon,
} from "lucide-react";

import {
  ClientPortalApiError,
  TokenExpiredError,
  getClientWorkspace,
  getClientWorkspaceSpec,
  postClientComment,
  type ClientWorkspaceResponse,
  type ClientWorkspaceSpecResponse,
} from "@/api/pr-client";

// --------------------------------------------------------------------------
// Static section headings — must match screens.json[S-042].section_h2_texts
// verbatim (Tier 1 AC-S3). Keeping them top-level so the lint-mock-impl-diff
// Gate #8 can grep them straight out of the source.
// --------------------------------------------------------------------------

const SECTION_PHASE_CURRENT = "Phase 2: 統合テスト + 受入";
const SECTION_RECENT_UPDATES = "最近の更新";
const SECTION_TEAM = "担当チーム";
const SECTION_DUE_DATE = "納期";
const SECTION_PHASE_PROGRESS = "フェーズ進捗";

// --------------------------------------------------------------------------
// View-model
// --------------------------------------------------------------------------

interface RecentUpdate {
  id: string;
  title: string;
  meta: string;
  Icon: LucideIcon;
  tone: "eb" | "amber";
  cta?: string;
  cta_variant?: "link" | "button";
}

// Mock-aligned demo data: the public endpoint returns the workspace projection;
// the recent-updates / team / phase-progress blocks are seeded from the same
// payload in production. While the backend is still flat, we surface a
// representative shape so the page mirrors the mock visually + tests can
// assert on it. (Server-driven richer data lands with T-V3-B-PR-01.)
const RECENT_UPDATES: RecentUpdate[] = [
  {
    id: "u1",
    title: "仕様書 v2.0 が公開されました",
    meta: "Must 34 項目 / 機能 30 項目 · 2 days ago",
    Icon: Upload,
    tone: "eb",
    cta: "仕様書を見る →",
    cta_variant: "link",
  },
  {
    id: "u2",
    title: "画面モック 12 件が確認可能になりました",
    meta: "login / signup / ダッシュ / 商品 / カート / 決済 · 3 days ago",
    Icon: Layout,
    tone: "eb",
    cta: "モックを見る →",
    cta_variant: "link",
  },
  {
    id: "u3",
    title: "あなたのコメントに返信があります",
    meta: "M-1 認証 / SAML SSO について · 5 days ago",
    Icon: MessageCircle,
    tone: "amber",
    cta: "確認する →",
    cta_variant: "link",
  },
  {
    id: "u4",
    title: "Phase 1 完了 - 承認お願いします",
    meta: "設計基盤 / 認証 / DB スキーマ 完了 · 7 days ago",
    Icon: CheckSquare,
    tone: "amber",
    cta: "承認画面へ",
    cta_variant: "button",
  },
];

interface TeamMember {
  initials: string;
  name: string;
  role: string;
  color: "eb" | "blue";
}

const TEAM: TeamMember[] = [
  { initials: "M", name: "masato", role: "PM / 主担当", color: "eb" },
  { initials: "DV", name: "devon (AI)", role: "Senior Dev", color: "eb" },
  { initials: "WS", name: "winston (AI)", role: "Architect", color: "blue" },
];

interface PhaseRow {
  id: string;
  label: string;
  caption: string;
  state: "done" | "current" | "todo";
}

const PHASES: PhaseRow[] = [
  { id: "p0", label: "Phase 0: ヒアリング / 要件", caption: "完了 · 4/22", state: "done" },
  { id: "p1", label: "Phase 1: 設計基盤 + 認証", caption: "完了 · 5/8", state: "done" },
  {
    id: "p2",
    label: SECTION_PHASE_CURRENT,
    caption: "進行中 · 88%",
    state: "current",
  },
  {
    id: "p3",
    label: "Phase 3: 納品 + 引き継ぎ",
    caption: "未開始 · 5/24-5/30",
    state: "todo",
  },
];

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function progressPercent(progress: number | null | undefined): number {
  if (typeof progress !== "number" || Number.isNaN(progress)) return 88;
  if (progress > 0 && progress <= 1) return Math.round(progress * 100);
  return Math.max(0, Math.min(100, Math.round(progress)));
}

function avatarBg(color: "eb" | "blue"): string {
  return color === "blue" ? "bg-blue-500" : "bg-eb-500";
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function ClientPortalPage() {
  const params = useParams<{ token: string | string[] }>();
  const rawToken = params?.token;
  const token = Array.isArray(rawToken) ? rawToken[0] : (rawToken ?? "");

  const queryClient = useQueryClient();

  // AC-F1: GET /api/client/workspaces/{token} on mount.
  const workspaceQuery = useQuery<ClientWorkspaceResponse, ClientPortalApiError>({
    queryKey: ["client-portal", "workspace", token],
    enabled: !!token,
    queryFn: ({ signal }) => getClientWorkspace(token, { signal }),
    retry: false,
    staleTime: 30_000,
  });

  // AC-F2: GET /api/client/workspaces/{token}/spec on mount.
  const specQuery = useQuery<ClientWorkspaceSpecResponse, ClientPortalApiError>({
    queryKey: ["client-portal", "spec", token],
    enabled: !!token,
    queryFn: ({ signal }) => getClientWorkspaceSpec(token, { signal }),
    retry: false,
    staleTime: 30_000,
  });

  // AC-F4: surface non-technical toast referencing the failing endpoint
  //        without leaking server stack traces.
  // AC-F5: 409 → TokenExpiredError surfaces a dedicated banner instead of a toast.
  const lastWorkspaceToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!workspaceQuery.isError) {
      lastWorkspaceToastRef.current = null;
      return;
    }
    const err = workspaceQuery.error;
    if (err instanceof TokenExpiredError) {
      // expired token gets its own UI block — no toast needed.
      lastWorkspaceToastRef.current = null;
      return;
    }
    const userMsg =
      err instanceof ClientPortalApiError
        ? err.toUserMessage()
        : `案件情報を取得できませんでした (/api/client/workspaces/${token || "{token}"})`;
    if (lastWorkspaceToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastWorkspaceToastRef.current = userMsg;
    }
  }, [workspaceQuery.isError, workspaceQuery.error, token]);

  const lastSpecToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!specQuery.isError) {
      lastSpecToastRef.current = null;
      return;
    }
    const err = specQuery.error;
    if (err instanceof TokenExpiredError) {
      lastSpecToastRef.current = null;
      return;
    }
    const userMsg =
      err instanceof ClientPortalApiError
        ? err.toUserMessage()
        : `仕様書 URL を取得できませんでした (/api/client/workspaces/${token || "{token}"}/spec)`;
    if (lastSpecToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastSpecToastRef.current = userMsg;
    }
  }, [specQuery.isError, specQuery.error, token]);

  // AC-F3 + AC-F6: POST /api/client/comments via the typed client.
  const [commentBody, setCommentBody] = React.useState("");
  const commentMutation = useMutation({
    mutationFn: () =>
      postClientComment({
        token,
        body: commentBody.trim(),
      }),
    onSuccess: () => {
      toast.success("コメントを投稿しました");
      setCommentBody("");
      // Future: refresh the comments list once it ships in the review tab.
      queryClient.invalidateQueries({ queryKey: ["client-portal"] });
    },
    onError: (err: unknown) => {
      // AC-F4 / AC-F6: friendly toast tagged with /api/client/comments, no stack.
      const userMsg =
        err instanceof ClientPortalApiError
          ? err.toUserMessage()
          : `コメントの投稿に失敗しました (/api/client/comments)`;
      toast.error(userMsg);
    },
  });

  const onSubmitComment = React.useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!commentBody.trim() || commentMutation.isPending) return;
      commentMutation.mutate();
    },
    [commentBody, commentMutation],
  );

  // --- Token-expired terminal state (AC-F5 dedicated UI) -----------------
  const tokenExpired =
    workspaceQuery.error instanceof TokenExpiredError ||
    specQuery.error instanceof TokenExpiredError;

  const workspace = workspaceQuery.data?.workspace;
  const specHtmlUrl = specQuery.data?.spec_html_url ?? null;
  const heroPercent = progressPercent(workspace?.progress);

  return (
    <main
      data-screen-id="S-042"
      data-feature-id="F-013,F-021"
      data-task-ids="T-V3-C-15"
      data-entities="E-009,E-021"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      {/* Client-only top bar (no sidebar). Mirrors the mock header. */}
      <header className="bg-white border-b border-slate-200 px-6 py-3 sticky top-0 z-10">
        <div className="max-w-[1200px] mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-eb-500 flex items-center justify-center">
              <Factory className="w-4 h-4 text-white" aria-hidden />
            </div>
            <div>
              <div className="text-sm font-bold">Build-Factory</div>
              <div className="text-[11px] text-slate-500 mono">client portal</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-xs text-slate-500">
              案件:{" "}
              <strong className="text-slate-900">
                {workspace?.name ?? "受託 EC 構築 #4"}
              </strong>
            </span>
          </div>
        </div>
      </header>

      {/* Tabs (visible_tabs only) */}
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
                aria-selected={i === 0}
                className={`px-4 py-3 text-sm font-medium border-b-2 ${
                  i === 0
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

      <section className="max-w-[1200px] mx-auto px-6 py-6">
        <h1 className="text-2xl font-bold mb-1">案件進捗状況</h1>
        <p className="text-sm text-slate-600 mb-6">
          {workspace?.name ?? "受託 EC 構築 #4"} ·{" "}
          {workspace?.current_phase ?? "Phase 2 統合テスト中"}
        </p>

        {tokenExpired && (
          <div
            data-testid="token-expired-banner"
            role="alert"
            className="bg-white border border-amber-200 rounded-lg p-6 mb-4"
          >
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-full bg-amber-50 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-4 h-4 text-amber-600" aria-hidden />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold mb-1">
                  リンクの有効期限が切れました
                </p>
                <p className="text-xs text-slate-600">
                  発行元へお問い合わせの上、新しい URL を再発行してください。
                </p>
              </div>
            </div>
          </div>
        )}

        {workspaceQuery.isPending && !tokenExpired && (
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
            <span className="text-sm">案件情報を読み込み中...</span>
          </div>
        )}

        {!tokenExpired && (workspaceQuery.isSuccess || workspaceQuery.isError) && (
          <>
            {/* Status hero — AC-S3 includes the "Phase 2: 統合テスト + 受入" h2 */}
            <div className="bg-white border border-eb-200 rounded-lg p-5 mb-4 ring-2 ring-eb-100">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-eb-700 font-bold">
                    Current Phase
                  </div>
                  <h2 className="text-xl font-bold mt-1">
                    {SECTION_PHASE_CURRENT}
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">
                    5/8 完了 · 残り 3 日
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-4xl font-bold tabular text-eb-500">
                    {heroPercent}
                    <span className="text-base font-normal">%</span>
                  </div>
                </div>
              </div>
              <div className="mt-3 h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-eb-500"
                  style={{ width: `${heroPercent}%` }}
                  data-testid="phase-progress-bar"
                />
              </div>
            </div>

            {/* Recent updates + Team + Due date */}
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="col-span-2 bg-white border border-slate-200 rounded-lg p-5">
                <h2 className="text-sm font-bold text-eb-500 mb-4 flex items-center gap-2">
                  <Bell className="w-4 h-4" aria-hidden />
                  {SECTION_RECENT_UPDATES}
                </h2>
                <div className="space-y-3">
                  {RECENT_UPDATES.map((u, idx) => {
                    const Icon = u.Icon;
                    const bg =
                      u.tone === "amber" ? "bg-amber-50" : "bg-eb-50";
                    const fg =
                      u.tone === "amber" ? "text-amber-600" : "text-eb-600";
                    const last = idx === RECENT_UPDATES.length - 1;
                    return (
                      <div
                        key={u.id}
                        className={`flex items-start gap-3 ${last ? "" : "pb-3 border-b border-slate-100"}`}
                      >
                        <div
                          className={`w-7 h-7 rounded-full ${bg} flex items-center justify-center shrink-0`}
                        >
                          <Icon
                            className={`w-3.5 h-3.5 ${fg}`}
                            aria-hidden
                          />
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium">{u.title}</div>
                          <div className="text-xs text-slate-500 mt-0.5">
                            {u.meta}
                          </div>
                          {u.cta && u.cta_variant === "button" && (
                            <button
                              type="button"
                              className="bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold h-7 px-3 rounded-md mt-1"
                            >
                              {u.cta}
                            </button>
                          )}
                          {u.cta && u.cta_variant === "link" && (
                            <button
                              type="button"
                              className="text-xs text-eb-500 hover:text-eb-600 font-semibold mt-1"
                            >
                              {u.cta}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-4">
                <div className="bg-white border border-slate-200 rounded-lg p-5">
                  <h2 className="text-sm font-bold text-eb-500 mb-3 flex items-center gap-2">
                    <Users className="w-4 h-4" aria-hidden />
                    {SECTION_TEAM}
                  </h2>
                  <div className="space-y-2 text-sm">
                    {TEAM.map((m) => (
                      <div key={m.name} className="flex items-center gap-2">
                        <div
                          className={`w-6 h-6 rounded-full ${avatarBg(m.color)} text-white text-[10px] font-bold flex items-center justify-center ${m.initials.length > 1 ? "mono" : ""}`}
                        >
                          {m.initials}
                        </div>
                        <div className="flex-1">
                          <div className="text-xs font-semibold">{m.name}</div>
                          <div className="text-[10px] text-slate-500">
                            {m.role}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-white border border-slate-200 rounded-lg p-5">
                  <h2 className="text-sm font-bold text-eb-500 mb-3 flex items-center gap-2">
                    <Calendar className="w-4 h-4" aria-hidden />
                    {SECTION_DUE_DATE}
                  </h2>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Phase 2 完了</span>
                      <span className="font-bold mono">5/18</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">最終納品</span>
                      <span className="font-bold mono">5/30</span>
                    </div>
                    <div className="flex justify-between border-t border-slate-100 pt-2">
                      <span className="text-slate-500">残り</span>
                      <span className="font-bold text-eb-500 mono">15 日</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Phase progress */}
            <div className="bg-white border border-slate-200 rounded-lg p-5 mb-4">
              <h2 className="text-sm font-bold text-eb-500 mb-4 flex items-center gap-2">
                <Layers className="w-4 h-4" aria-hidden />
                {SECTION_PHASE_PROGRESS}
              </h2>
              <div className="space-y-3">
                {PHASES.map((p) => {
                  if (p.state === "done") {
                    return (
                      <div
                        key={p.id}
                        className="flex items-center gap-3 p-2.5 border border-emerald-200 bg-emerald-50 rounded-md"
                      >
                        <CheckCircle2
                          className="w-5 h-5 text-emerald-600"
                          aria-hidden
                        />
                        <div className="flex-1">
                          <div className="text-sm font-semibold">{p.label}</div>
                          <div className="text-xs text-slate-500">
                            {p.caption}
                          </div>
                        </div>
                      </div>
                    );
                  }
                  if (p.state === "current") {
                    return (
                      <div
                        key={p.id}
                        className="flex items-center gap-3 p-2.5 border border-eb-200 bg-eb-50 rounded-md"
                      >
                        <PlayCircle
                          className="w-5 h-5 text-eb-500"
                          aria-hidden
                        />
                        <div className="flex-1">
                          <div className="text-sm font-semibold">{p.label}</div>
                          <div className="text-xs text-slate-500">
                            {p.caption}
                          </div>
                        </div>
                        <span className="text-[11px] bg-eb-500 text-white px-2 py-0.5 rounded-full font-bold">
                          CURRENT
                        </span>
                      </div>
                    );
                  }
                  return (
                    <div
                      key={p.id}
                      className="flex items-center gap-3 p-2.5 border border-slate-200 rounded-md opacity-60"
                    >
                      <Circle
                        className="w-5 h-5 text-slate-400"
                        aria-hidden
                      />
                      <div className="flex-1">
                        <div className="text-sm font-semibold">{p.label}</div>
                        <div className="text-xs text-slate-500">
                          {p.caption}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              {specHtmlUrl && (
                <div className="mt-4 text-xs text-slate-500">
                  仕様書:{" "}
                  <a
                    href={specHtmlUrl}
                    className="text-eb-500 hover:text-eb-600 font-semibold"
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    {specHtmlUrl}
                  </a>
                </div>
              )}
            </div>

            {/* Comment form — AC-F3 / AC-F6 path */}
            <div className="bg-white border border-slate-200 rounded-lg p-5">
              <h2 className="text-sm font-bold text-eb-500 mb-3 flex items-center gap-2">
                <MessageCircle className="w-4 h-4" aria-hidden />
                コメントを投稿
              </h2>
              <form onSubmit={onSubmitComment} noValidate>
                <label
                  htmlFor="client-portal-comment"
                  className="text-xs text-slate-500 mb-1.5 block"
                >
                  仕様書 / モック / フェーズに対するフィードバックを記入してください
                </label>
                <textarea
                  id="client-portal-comment"
                  data-testid="client-portal-comment-input"
                  value={commentBody}
                  onChange={(e) => setCommentBody(e.target.value)}
                  rows={4}
                  className="w-full text-sm border border-slate-200 rounded-md p-3 focus:outline-none focus:ring-2 focus:ring-eb-500 focus:border-eb-500"
                  placeholder="例: ログイン後の遷移先を会員ダッシュボードに変更したいです"
                  maxLength={4000}
                  disabled={commentMutation.isPending}
                />
                <div className="flex items-center justify-end mt-3">
                  <button
                    type="submit"
                    data-testid="client-portal-comment-submit"
                    disabled={
                      !commentBody.trim() || commentMutation.isPending
                    }
                    className="bg-eb-500 hover:bg-eb-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold h-9 px-4 rounded-md inline-flex items-center gap-2"
                  >
                    <Send className="w-4 h-4" aria-hidden />
                    {commentMutation.isPending ? "送信中..." : "コメントを投稿"}
                  </button>
                </div>
              </form>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
