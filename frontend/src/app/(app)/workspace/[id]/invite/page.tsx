"use client";

/**
 * T-V3-C-64 / S-015: メンバー招待 page (Vertical Slice / UI).
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/workspace/S-015-workspace-invite.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-015
 * @feature-id F-004
 * @task-ids T-V3-C-64
 * @entities E-043
 * @phase Phase 1
 *
 * Backend contracts (T-V3-B-04 / T-V3-B-05 / T-V3-B-06):
 *   POST   /api/workspaces/{id}/invitations
 *   GET    /api/workspaces/{id}/invitations
 *   DELETE /api/workspaces/{id}/invitations/{token}
 *   PUT    /api/accounts/{id}  (AC-F3 plan upgrade)
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-64.md):
 *   structural.AC-S1 — h1 === "メンバーを招待" (mock h1 逐語コピー).
 *   structural.AC-S2 — section h2 set === {"新規招待", "送信済み招待 (pending)"}.
 *   structural.AC-S3 — Lucide icons only (no emoji glyphs).
 *   functional.AC-F1 — POST /api/workspaces/{id}/invitations on submit; 2xx
 *                      renders into the pending list, 4xx → inline toast + empty state.
 *   functional.AC-F2 — 401 → router.replace("/login") (no workspace-scoped render).
 *   functional.AC-F3 — PUT /api/accounts/{id} for owner plan upgrade emits
 *                      account_updated audit log server-side.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowLeft,
  ChevronRight,
  Copy,
  Eye,
  Link as LinkIcon,
  Loader2,
  Mail,
  RefreshCcw,
  Send,
  Sliders,
  Trash2,
  X,
} from "lucide-react";

import {
  WorkspaceInviteApiError,
  type CreateWorkspaceInvitationRequest,
  type WorkspaceInvitation,
  type WorkspaceInviteRole,
} from "@/api/workspace-invite";
import { useWorkspaceInvite } from "@/hooks/useWorkspaceInvite";

// ---------------------------------------------------------------------------
// Mock-derived screen literals — 逐語コピー from
// docs/mocks/2026-05-15_v3/workspace/S-015-workspace-invite.html
// AC-S1: h1_text === "メンバーを招待"
// AC-S2: section h2 set === {"新規招待", "送信済み招待 (pending)"}
// ---------------------------------------------------------------------------
const S015_H1_TEXT = "メンバーを招待";
const S015_NEW_INVITE_H2 = "新規招待";
const S015_PENDING_H2 = "送信済み招待 (pending)";

const ROLE_OPTIONS: Array<{ value: WorkspaceInviteRole; label: string }> = [
  { value: "contributor", label: "contributor (編集可)" },
  { value: "monitor", label: "monitor (読み取り)" },
  { value: "client", label: "client (限定 view)" },
];

const EXPIRES_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 7, label: "7 日" },
  { value: 3, label: "3 日" },
  { value: 1, label: "24 時間" },
];

const CUSTOM_PERMS = [
  { key: "edit_spec", label: "仕様編集", defaultChecked: true },
  { key: "edit_tasks", label: "タスク編集", defaultChecked: true },
  { key: "approve_red_line", label: "赤線承認", defaultChecked: false },
  { key: "approve_delivery", label: "納品承認", defaultChecked: false },
];

const CLIENT_TABS = [
  { key: "dashboard", label: "dashboard", defaultChecked: true },
  { key: "spec_viewer", label: "spec_viewer", defaultChecked: true },
  { key: "task_kanban", label: "task_kanban", defaultChecked: false },
  { key: "cost", label: "cost", defaultChecked: false },
  { key: "audit_log", label: "audit_log", defaultChecked: false },
  { key: "review", label: "review", defaultChecked: false },
];

function parseEmails(raw: string): string[] {
  return raw
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function formatTimeAgo(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "たった今";
  if (diffMin < 60) return `${diffMin} 分前`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} 時間前`;
  const diffD = Math.floor(diffH / 24);
  return `${diffD} 日前`;
}

function formatRemaining(iso?: string | null): {
  text: string;
  tone: "ok" | "warn" | "expired";
} {
  if (!iso) return { text: "—", tone: "warn" };
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { text: "—", tone: "warn" };
  const diffMs = d.getTime() - Date.now();
  if (diffMs <= 0) return { text: "期限切れ", tone: "expired" };
  const diffH = Math.floor(diffMs / 3_600_000);
  if (diffH < 24) return { text: `残 ${diffH} 時間`, tone: "warn" };
  const diffD = Math.floor(diffH / 24);
  return { text: `残 ${diffD} 日`, tone: diffD <= 1 ? "warn" : "ok" };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function WorkspaceInvitePage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const workspaceId = String(params?.id ?? "");

  // AC-F2 — once we observe a 401 from any endpoint, stop rendering data.
  const [unauthorized, setUnauthorized] = React.useState(false);

  const {
    invitations,
    isLoading,
    isError,
    error,
    refetch,
    createInvitation,
    isCreating,
    revokeInvitation,
    isRevoking,
  } = useWorkspaceInvite({
    workspaceId,
    enabled: !!workspaceId && !unauthorized,
  });

  // Form state — mirrors mock fields exactly (S-015-workspace-invite.html).
  const [emailsRaw, setEmailsRaw] = React.useState("");
  const [role, setRole] = React.useState<WorkspaceInviteRole>("contributor");
  const [expiresDays, setExpiresDays] = React.useState<number>(7);
  const [message, setMessage] = React.useState("");

  // Handle list-query errors. 401 → redirect; other 4xx → toast + empty state.
  React.useEffect(() => {
    if (!isError || !error) return;
    if (error instanceof WorkspaceInviteApiError) {
      if (error.status === 401) {
        setUnauthorized(true);
        router.replace("/login");
        return;
      }
      toast.error(error.toUserMessage());
    }
  }, [isError, error, router]);

  if (unauthorized) {
    // AC-F2: render no workspace-scoped data.
    return (
      <div
        data-screen-id="S-015"
        data-screen-name="workspace_invite"
        data-feature-id="F-004"
        data-task-ids="T-V3-C-64"
        data-entities="E-043"
        data-testid="workspace-invite-unauthorized"
        className="p-6"
      />
    );
  }

  const handleSubmit = async (
    ev: React.FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    ev.preventDefault();
    const emails = parseEmails(emailsRaw);
    if (emails.length === 0) {
      toast.error("メールアドレスを入力してください");
      return;
    }
    let successCount = 0;
    for (const email of emails) {
      const body: CreateWorkspaceInvitationRequest = {
        email,
        role,
        expires_in_days: expiresDays,
        invited_by: "masato",
        message: message || null,
      };
      try {
        await createInvitation(body);
        successCount += 1;
      } catch (err) {
        if (err instanceof WorkspaceInviteApiError) {
          if (err.status === 401) {
            setUnauthorized(true);
            router.replace("/login");
            return;
          }
          toast.error(err.toUserMessage());
        } else if (err instanceof Error) {
          toast.error(err.message);
        } else {
          toast.error("招待処理に失敗しました");
        }
      }
    }
    if (successCount > 0) {
      toast.success(`${successCount} 件の招待を送信しました`);
      setEmailsRaw("");
      setMessage("");
      void refetch();
    }
  };

  const handleRevoke = async (token: string): Promise<void> => {
    if (typeof window !== "undefined") {
      const ok = window.confirm("この招待を取り消しますか?");
      if (!ok) return;
    }
    try {
      await revokeInvitation(token);
      toast.success("招待を取り消しました");
      void refetch();
    } catch (err) {
      if (err instanceof WorkspaceInviteApiError) {
        if (err.status === 401) {
          setUnauthorized(true);
          router.replace("/login");
          return;
        }
        toast.error(err.toUserMessage());
      } else if (err instanceof Error) {
        toast.error(err.message);
      } else {
        toast.error("招待の取り消しに失敗しました");
      }
    }
  };

  const handleCopyUrl = async (token: string): Promise<void> => {
    const url =
      typeof window !== "undefined"
        ? `${window.location.origin}/invitation?token=${encodeURIComponent(token)}`
        : `/invitation?token=${encodeURIComponent(token)}`;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(url);
      }
      toast.success("招待 URL をコピーしました");
    } catch {
      toast.error("URL のコピーに失敗しました");
    }
  };

  const hasInvitations = invitations.length > 0;
  const showEmptyState =
    !isLoading &&
    !hasInvitations &&
    (isError || invitations.length === 0);

  return (
    <div
      data-screen-id="S-015"
      data-screen-name="workspace_invite"
      data-feature-id="F-004"
      data-task-ids="T-V3-C-64"
      data-entities="E-043"
      data-testid="workspace-invite-page"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <main className="max-w-[800px] mx-auto px-6 py-8">
        <nav
          aria-label="breadcrumb"
          className="text-xs text-slate-500 flex items-center gap-1.5 mb-2"
        >
          <a
            href={`/workspaces/${workspaceId}/members`}
            className="hover:text-slate-900 inline-flex items-center gap-1"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            メンバー
          </a>
          <ChevronRight className="w-3 h-3" aria-hidden="true" />
          <span className="text-slate-900 font-medium">招待</span>
        </nav>

        <h1 className="text-2xl font-bold mb-1">{S015_H1_TEXT}</h1>
        <p className="text-sm text-slate-600 mb-6">
          この workspace への参加リンクを発行
        </p>

        <section
          aria-labelledby="new-invite-heading"
          data-testid="workspace-invite-new-section"
          className="bg-white border border-slate-200 rounded-lg p-6 mb-4"
        >
          <h2 id="new-invite-heading" className="text-base font-bold mb-4">
            {S015_NEW_INVITE_H2}
          </h2>
          <form
            data-testid="workspace-invite-form"
            onSubmit={handleSubmit}
            className="space-y-4"
          >
            <div className="space-y-1.5">
              <label
                htmlFor="invite-emails"
                className="text-sm font-medium block"
              >
                メールアドレス <span className="text-red-600">*</span>
              </label>
              <textarea
                id="invite-emails"
                data-testid="workspace-invite-emails"
                required
                className="border border-slate-200 bg-white text-sm px-3 py-2 rounded-md w-full min-h-[60px] font-mono"
                placeholder={"user1@example.com\nuser2@example.com (複数行で一括招待)"}
                value={emailsRaw}
                onChange={(e) => setEmailsRaw(e.target.value)}
              />
              <p className="text-xs text-slate-500">改行区切りで複数アドレス可</p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label htmlFor="invite-role" className="text-sm font-medium block">
                  ロール
                </label>
                <select
                  id="invite-role"
                  data-testid="workspace-invite-role"
                  className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
                  value={role}
                  onChange={(e) => setRole(e.target.value as WorkspaceInviteRole)}
                >
                  {ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <label
                  htmlFor="invite-expires"
                  className="text-sm font-medium block"
                >
                  有効期限
                </label>
                <select
                  id="invite-expires"
                  data-testid="workspace-invite-expires"
                  className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
                  value={expiresDays}
                  onChange={(e) => setExpiresDays(Number(e.target.value))}
                >
                  {EXPIRES_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <details className="border border-slate-200 rounded-md">
              <summary className="cursor-pointer px-3 py-2 text-sm font-medium flex items-center gap-2">
                <Sliders className="w-4 h-4 text-slate-500" />
                Custom 権限テンプレート (任意)
              </summary>
              <div className="p-4 border-t border-slate-200 grid grid-cols-2 gap-2 text-sm">
                {CUSTOM_PERMS.map((perm) => (
                  <label
                    key={perm.key}
                    className="flex items-center gap-2 p-2 border border-slate-200 rounded-md"
                  >
                    <input
                      type="checkbox"
                      defaultChecked={perm.defaultChecked}
                      className="w-4 h-4 accent-eb-500"
                    />
                    <span>{perm.label}</span>
                  </label>
                ))}
              </div>
            </details>

            <details className="border border-slate-200 rounded-md">
              <summary className="cursor-pointer px-3 py-2 text-sm font-medium flex items-center gap-2">
                <Eye className="w-4 h-4 text-slate-500" />
                表示 Tabs (client ロール時)
              </summary>
              <div className="p-4 border-t border-slate-200 grid grid-cols-3 gap-2 text-sm">
                {CLIENT_TABS.map((tab) => (
                  <label key={tab.key} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      defaultChecked={tab.defaultChecked}
                      className="w-4 h-4 accent-eb-500"
                    />
                    <span>{tab.label}</span>
                  </label>
                ))}
              </div>
            </details>

            <div className="space-y-1.5">
              <label
                htmlFor="invite-message"
                className="text-sm font-medium block"
              >
                メッセージ (任意)
              </label>
              <textarea
                id="invite-message"
                data-testid="workspace-invite-message"
                className="border border-slate-200 bg-white text-sm px-3 py-2 rounded-md w-full min-h-[60px]"
                placeholder="招待メールに添える短いメッセージ"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                data-testid="workspace-invite-cancel"
                onClick={() => {
                  setEmailsRaw("");
                  setMessage("");
                }}
                className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-4 rounded-md"
              >
                キャンセル
              </button>
              <button
                type="submit"
                data-testid="workspace-invite-submit"
                disabled={isCreating}
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md flex items-center gap-2 disabled:opacity-60"
              >
                {isCreating ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                招待を送信
              </button>
            </div>
          </form>
        </section>

        <section
          aria-labelledby="pending-invite-heading"
          data-testid="workspace-invite-pending-section"
          className="bg-white border border-slate-200 rounded-lg overflow-hidden"
        >
          <div className="px-5 py-3 border-b border-slate-200">
            <h2 id="pending-invite-heading" className="text-base font-bold">
              {S015_PENDING_H2}
            </h2>
          </div>

          {isLoading && (
            <div
              data-testid="workspace-invite-loading"
              className="px-5 py-8 text-center text-slate-400 flex items-center justify-center gap-2"
            >
              <Loader2 className="w-4 h-4 animate-spin" />
              読み込み中…
            </div>
          )}

          {!isLoading && showEmptyState && (
            <div
              data-testid="workspace-invite-error-empty-state"
              className="px-5 py-8 text-center text-sm text-slate-500"
            >
              <div className="inline-flex items-center gap-2 text-slate-500 mb-2">
                <Mail className="w-4 h-4" />
                送信済みの招待はありません
              </div>
              <div>
                <button
                  type="button"
                  onClick={() => void refetch()}
                  className="text-xs text-eb-500 hover:text-eb-600 inline-flex items-center gap-1"
                >
                  <RefreshCcw className="w-3 h-3" />
                  再読み込み
                </button>
              </div>
            </div>
          )}

          {!isLoading && hasInvitations && (
            <table
              data-testid="workspace-invite-pending-table"
              className="w-full text-sm"
            >
              <thead className="bg-slate-50">
                <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                  <th className="text-left font-bold px-4 py-2">宛先</th>
                  <th className="text-left font-bold px-4 py-2">Role</th>
                  <th className="text-left font-bold px-4 py-2">送信日時</th>
                  <th className="text-left font-bold px-4 py-2">期限</th>
                  <th className="text-right font-bold px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {invitations.map((inv: WorkspaceInvitation) => {
                  const remaining = formatRemaining(inv.expires_at);
                  const toneCls =
                    remaining.tone === "expired"
                      ? "text-red-600"
                      : remaining.tone === "warn"
                        ? "text-amber-600"
                        : "text-emerald-600";
                  return (
                    <tr
                      key={inv.token}
                      data-testid={`workspace-invite-row-${inv.token}`}
                      className="border-t border-slate-100"
                    >
                      <td className="px-4 py-3 font-mono text-xs">{inv.email}</td>
                      <td className="px-4 py-3">
                        <span className="text-[11px] bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full font-medium">
                          {inv.role ?? "contributor"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {formatTimeAgo(inv.invited_at ?? inv.created_at)}
                      </td>
                      <td className={`px-4 py-3 text-xs ${toneCls}`}>
                        {remaining.text}
                      </td>
                      <td className="px-4 py-3 text-right space-x-2">
                        <button
                          type="button"
                          data-testid={`workspace-invite-copy-${inv.token}`}
                          onClick={() => void handleCopyUrl(inv.token)}
                          className="text-xs text-slate-500 hover:text-slate-900 inline-flex items-center gap-1"
                        >
                          <Copy className="w-3 h-3" />
                          URL コピー
                        </button>
                        <button
                          type="button"
                          data-testid={`workspace-invite-revoke-${inv.token}`}
                          onClick={() => void handleRevoke(inv.token)}
                          disabled={isRevoking}
                          className="text-xs text-red-500 hover:text-red-700 inline-flex items-center gap-1 disabled:opacity-50"
                        >
                          <Trash2 className="w-3 h-3" />
                          取消
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>

        <div className="mt-4 text-[11px] text-slate-400 text-right inline-flex items-center gap-1 font-mono justify-end w-full">
          <LinkIcon className="w-3 h-3" />
          S-015 workspace_invite · F-004 · T-V3-C-64
        </div>
      </main>
    </div>
  );
}
