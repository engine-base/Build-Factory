"use client";

/**
 * T-V3-C-08 / S-008: メンバー管理 (Account members) page.
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/account/S-008-account-members.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-008
 * @feature-id F-004,F-021
 * @task-ids T-V3-C-08
 * @entities E-001,E-002,E-043
 * @phase Phase 1B
 *
 * Embedded dialog (Gate #8):
 *   S-051 confirm_delete (typed-name confirmation) — see ConfirmDeleteDialog
 *   block below; its root carries data-screen-id="S-051" so the
 *   lint-mock-impl-diff Gate #8 indexes it next to the dedicated mock
 *   docs/mocks/2026-05-15_v3/dialog/S-051-confirm-delete.html.
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-08.md):
 *   structural.AC-S1 (data-screen-id="S-008")                          — root <main> element.
 *   structural.AC-S2 (h1 text "メンバー管理")                          — <h1> below.
 *   functional.AC-F1 (GET /api/accounts/{id}/members typed call)       — membersQuery.
 *   functional.AC-F2 (POST /api/accounts/{id}/invitations typed call)  — inviteMutation.
 *   functional.AC-F3 (DELETE /api/accounts/{id}/members/{user_id})     — removeMutation.
 *   functional.AC-F4 (4xx/5xx -> non-technical endpoint toast)         — surfaceError().
 *   functional.AC-F5 (429 cap 20 / hour / account preserved)           — AccountsApiError.status === 429.
 *   functional.AC-F6 (destructive -> S-051 typed-name confirm dialog)  — ConfirmDeleteDialog.
 */

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle,
  ChevronRight,
  Loader2,
  Mail,
  MoreHorizontal,
  Search,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AccountsApiError,
  accountInvitationsEndpoint,
  accountMemberDetailEndpoint,
  accountMembersEndpoint,
  inviteAccountMember,
  listAccountMembers,
  removeAccountMember,
  type AccountMember,
  type InviteAccountMemberRequest,
} from "@/api/accounts";

// --------------------------------------------------------------------------
// Constants
// --------------------------------------------------------------------------

const DEFAULT_ACCOUNT_ID =
  "00000000-0000-0000-0000-000000000000"; // resolved client-side via localStorage.bf.account_id

const ROLE_OPTIONS: InviteAccountMemberRequest["role"][] = [
  "admin",
  "member",
  "viewer",
  "guest",
];

const STATUS_LABELS: Record<string, string> = {
  active: "active",
  pending: "pending",
  invited: "pending",
};

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function resolveAccountId(): string {
  if (typeof window === "undefined") return DEFAULT_ACCOUNT_ID;
  try {
    const stored = window.localStorage?.getItem("bf.account_id");
    if (stored) return stored;
  } catch {
    // ignore — fall back to default UUID.
  }
  return DEFAULT_ACCOUNT_ID;
}

function resolveAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage?.getItem("bf.access_token") ?? null;
  } catch {
    return null;
  }
}

/**
 * AC-F4: surface a non-technical, endpoint-tagged toast without leaking server
 * stack traces. AC-F5: when 429, surface the rate-limit message verbatim.
 */
function surfaceError(err: unknown, fallbackEndpoint: string): void {
  if (err instanceof AccountsApiError) {
    toast.error(err.toUserMessage());
    return;
  }
  toast.error(`通信に失敗しました (${fallbackEndpoint})`);
}

function roleBadgeClass(role: string): string {
  const r = role.toLowerCase();
  if (r === "account_owner" || r === "owner") {
    return "bg-eb-50 text-eb-700 border-eb-200";
  }
  if (r === "workspace_admin" || r === "admin") {
    return "bg-blue-50 text-blue-700 border-blue-200";
  }
  if (r === "monitor" || r === "viewer") {
    return "bg-slate-100 text-slate-700 border-slate-200";
  }
  if (r === "guest") {
    return "bg-amber-50 text-amber-700 border-amber-200";
  }
  return "bg-slate-100 text-slate-700 border-slate-200";
}

function statusBadgeClass(status: string): string {
  if (status === "active") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (status === "pending" || status === "invited") {
    return "bg-amber-50 text-amber-700 border-amber-200";
  }
  return "bg-slate-100 text-slate-700 border-slate-200";
}

function initial(name: string | undefined, email: string | undefined): string {
  const src = (name || email || "?").trim();
  return src.charAt(0).toUpperCase() || "?";
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function AccountMembersPage() {
  const queryClient = useQueryClient();
  const accountId = React.useMemo(() => resolveAccountId(), []);
  const authToken = React.useMemo(() => resolveAuthToken(), []);

  // --- list state -----------------------------------------------------------
  const [filterQuery, setFilterQuery] = React.useState("");
  const [filterRole, setFilterRole] = React.useState("all");
  const [filterStatus, setFilterStatus] = React.useState("all");

  // --- invite dialog state --------------------------------------------------
  const [inviteOpen, setInviteOpen] = React.useState(false);
  const [inviteEmail, setInviteEmail] = React.useState("");
  const [inviteRole, setInviteRole] =
    React.useState<InviteAccountMemberRequest["role"]>("member");

  // --- delete dialog state (S-051) ------------------------------------------
  const [removalTarget, setRemovalTarget] = React.useState<AccountMember | null>(
    null,
  );
  const [confirmTypedName, setConfirmTypedName] = React.useState("");

  // AC-F1: GET /api/accounts/{id}/members via typed client.
  const membersQuery = useQuery({
    queryKey: ["account-members", accountId],
    queryFn: ({ signal }) =>
      listAccountMembers(accountId, { signal, authToken }),
    retry: false,
    staleTime: 30_000,
  });

  // Surface fetch errors (AC-F4) without leaking stack traces.
  const lastFetchToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!membersQuery.isError) {
      lastFetchToastRef.current = null;
      return;
    }
    const err = membersQuery.error;
    const msg =
      err instanceof AccountsApiError
        ? err.toUserMessage()
        : `メンバー一覧を取得できませんでした (${accountMembersEndpoint(accountId)})`;
    if (lastFetchToastRef.current !== msg) {
      toast.error(msg);
      lastFetchToastRef.current = msg;
    }
  }, [membersQuery.isError, membersQuery.error, accountId]);

  // AC-F2 + AC-F5: POST /api/accounts/{id}/invitations.
  const inviteMutation = useMutation({
    mutationFn: (req: InviteAccountMemberRequest) =>
      inviteAccountMember(accountId, req, { authToken }),
    onSuccess: () => {
      toast.success("招待メールを送信しました");
      setInviteOpen(false);
      setInviteEmail("");
      setInviteRole("member");
      void queryClient.invalidateQueries({
        queryKey: ["account-members", accountId],
      });
    },
    onError: (err) =>
      surfaceError(err, accountInvitationsEndpoint(accountId)),
  });

  // AC-F3: DELETE /api/accounts/{id}/members/{user_id}.
  const removeMutation = useMutation({
    mutationFn: (member: AccountMember) =>
      removeAccountMember(accountId, member.user_id, { authToken }),
    onSuccess: () => {
      toast.success("メンバーを削除しました");
      setRemovalTarget(null);
      setConfirmTypedName("");
      void queryClient.invalidateQueries({
        queryKey: ["account-members", accountId],
      });
    },
    onError: (err) => {
      const endpoint = removalTarget
        ? accountMemberDetailEndpoint(accountId, removalTarget.user_id)
        : "/api/accounts/{id}/members/{user_id}";
      surfaceError(err, endpoint);
    },
  });

  const members = membersQuery.data?.members ?? [];

  const roleDistribution = React.useMemo(() => {
    const dist = { total: 0, owner: 0, admin: 0, monitor: 0 };
    for (const m of members) {
      dist.total += 1;
      const r = m.role.toLowerCase();
      if (r === "account_owner" || r === "owner") dist.owner += 1;
      else if (r === "workspace_admin" || r === "admin") dist.admin += 1;
      else if (r === "monitor" || r === "viewer") dist.monitor += 1;
    }
    return dist;
  }, [members]);

  const filteredMembers = React.useMemo(() => {
    const q = filterQuery.trim().toLowerCase();
    return members.filter((m) => {
      if (q) {
        const hay = `${m.display_name ?? ""} ${m.email ?? ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (filterRole !== "all" && m.role !== filterRole) return false;
      if (filterStatus !== "all") {
        const status = STATUS_LABELS[m.status ?? "active"] ?? m.status ?? "active";
        if (status !== filterStatus) return false;
      }
      return true;
    });
  }, [members, filterQuery, filterRole, filterStatus]);

  // ------------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------------
  return (
    <main
      data-screen-id="S-008"
      data-feature-id="F-004,F-021"
      data-task-ids="T-V3-C-08"
      data-entities="E-001,E-002,E-043"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <div className="max-w-[1200px] mx-auto px-6 py-8">
        {/* Breadcrumb */}
        <div className="text-xs text-slate-500 flex items-center gap-1.5 mb-2">
          <span className="hover:text-slate-900">Account</span>
          <ChevronRight className="w-3 h-3" aria-hidden />
          <span className="text-slate-900 font-medium">メンバー管理</span>
        </div>

        {/* Header */}
        <div className="flex items-end justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">メンバー管理</h1>
            <p className="text-sm text-slate-600 mt-1">
              アカウント全体のメンバー一覧とロール
            </p>
          </div>
          <Button
            data-testid="invite-open"
            onClick={() => setInviteOpen(true)}
            className="bg-eb-500 hover:bg-eb-600 text-white"
          >
            <UserPlus className="w-4 h-4 mr-1.5" aria-hidden />
            メンバーを招待
          </Button>
        </div>

        {/* Role distribution */}
        <div className="grid grid-cols-4 gap-3 mb-6">
          <StatCard label="Total" value={roleDistribution.total} unit="人" />
          <StatCard
            label="Account Owner"
            value={roleDistribution.owner}
            unit="最大 1 人"
            tone="eb"
          />
          <StatCard
            label="Workspace Admin"
            value={roleDistribution.admin}
            unit="人"
            tone="blue"
          />
          <StatCard
            label="Monitor"
            value={roleDistribution.monitor}
            unit="読み取り専用"
            tone="slate"
          />
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 mb-4">
          <div className="flex-1 relative">
            <Search
              className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              aria-hidden
            />
            <Input
              type="search"
              placeholder="メンバー検索..."
              aria-label="メンバー検索"
              className="pl-9"
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
            />
          </div>
          <select
            aria-label="全ロール"
            className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md"
            value={filterRole}
            onChange={(e) => setFilterRole(e.target.value)}
          >
            <option value="all">全ロール</option>
            <option value="account_owner">account_owner</option>
            <option value="workspace_admin">workspace_admin</option>
            <option value="monitor">monitor</option>
          </select>
          <select
            aria-label="全ステータス"
            className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="all">全ステータス</option>
            <option value="active">active</option>
            <option value="pending">pending</option>
          </select>
        </div>

        {/* Members table */}
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          {membersQuery.isLoading ? (
            <div className="p-12 text-center text-slate-500 text-sm">
              <Loader2
                className="w-5 h-5 inline mr-2 animate-spin"
                aria-hidden
              />
              読み込み中…
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                  <th className="text-left font-bold px-4 py-2">メンバー</th>
                  <th className="text-left font-bold px-4 py-2">Role</th>
                  <th className="text-left font-bold px-4 py-2">所属 Workspace</th>
                  <th className="text-left font-bold px-4 py-2">最終ログイン</th>
                  <th className="text-left font-bold px-4 py-2">Status</th>
                  <th className="text-right font-bold px-4 py-2"></th>
                </tr>
              </thead>
              <tbody data-testid="members-table-body">
                {filteredMembers.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-10 text-center text-sm text-slate-500"
                    >
                      <Users
                        className="w-5 h-5 inline mr-2 text-slate-400"
                        aria-hidden
                      />
                      該当するメンバーはいません
                    </td>
                  </tr>
                )}
                {filteredMembers.map((m) => (
                  <MemberRow
                    key={m.user_id}
                    member={m}
                    onRemoveClick={() => {
                      setRemovalTarget(m);
                      setConfirmTypedName("");
                    }}
                  />
                ))}
              </tbody>
            </table>
          )}
          <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>
              {filteredMembers.length} / {members.length} 件表示
            </span>
          </div>
        </div>
      </div>

      {/* ─── Invite Dialog (mock S-051 同居ではなく独立 modal — invitation flow) ─── */}
      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>メンバーを招待</DialogTitle>
            <DialogDescription>
              招待メールが送信されます。同一アカウント宛は 1 時間 20 回まで。
            </DialogDescription>
          </DialogHeader>
          <form
            data-testid="invite-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!inviteEmail || inviteMutation.isPending) return;
              inviteMutation.mutate({
                email: inviteEmail,
                role: inviteRole,
              });
            }}
            className="space-y-4"
            noValidate
          >
            <div className="space-y-1.5">
              <label
                htmlFor="invite-email"
                className="text-sm font-medium block"
              >
                メールアドレス
              </label>
              <Input
                id="invite-email"
                type="email"
                placeholder="member@example.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="invite-role" className="text-sm font-medium block">
                ロール
              </label>
              <select
                id="invite-role"
                value={inviteRole}
                onChange={(e) =>
                  setInviteRole(
                    e.target.value as InviteAccountMemberRequest["role"],
                  )
                }
                className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setInviteOpen(false)}
              >
                キャンセル
              </Button>
              <Button
                type="submit"
                data-testid="invite-submit"
                disabled={!inviteEmail || inviteMutation.isPending}
                className="bg-eb-500 hover:bg-eb-600 text-white"
              >
                {inviteMutation.isPending ? (
                  <>
                    <Loader2
                      className="w-3.5 h-3.5 inline mr-1.5 animate-spin"
                      aria-hidden
                    />
                    送信中…
                  </>
                ) : (
                  "招待を送信"
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ─── S-051 Confirm-Delete Dialog (typed-name confirmation) ─── */}
      <ConfirmDeleteDialog
        target={removalTarget}
        typedName={confirmTypedName}
        onTypedNameChange={setConfirmTypedName}
        onCancel={() => {
          setRemovalTarget(null);
          setConfirmTypedName("");
        }}
        onConfirm={() => {
          if (removalTarget) removeMutation.mutate(removalTarget);
        }}
        isPending={removeMutation.isPending}
      />
    </main>
  );
}

// --------------------------------------------------------------------------
// Sub-components
// --------------------------------------------------------------------------

function StatCard({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: number;
  unit: string;
  tone?: "eb" | "blue" | "slate";
}) {
  const valueColor =
    tone === "eb"
      ? "text-eb-500"
      : tone === "blue"
        ? "text-blue-600"
        : tone === "slate"
          ? "text-slate-700"
          : "text-slate-900";
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">
        {label}
      </div>
      <div className={`text-2xl font-bold tabular-nums ${valueColor}`}>
        {value}
      </div>
      <div className="text-xs text-slate-500 mt-1">{unit}</div>
    </div>
  );
}

function MemberRow({
  member,
  onRemoveClick,
}: {
  member: AccountMember;
  onRemoveClick: () => void;
}) {
  const status = STATUS_LABELS[member.status ?? "active"] ?? member.status ?? "active";
  const isPending = status === "pending";
  const display = member.display_name || member.email || member.user_id;
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          {isPending ? (
            <div className="w-8 h-8 rounded-full bg-amber-100 text-amber-700 text-xs font-bold flex items-center justify-center">
              <Mail className="w-3.5 h-3.5" aria-hidden />
            </div>
          ) : (
            <div className="w-8 h-8 rounded-full bg-eb-500 text-white text-xs font-bold flex items-center justify-center">
              {initial(member.display_name, member.email)}
            </div>
          )}
          <div>
            <div className="text-sm font-medium">{display}</div>
            {member.email && (
              <div className="text-xs text-slate-500 font-mono">
                {member.email}
              </div>
            )}
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <span
          className={`text-[11px] border px-2 py-0.5 rounded-full font-medium ${roleBadgeClass(member.role)}`}
        >
          {member.role}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-slate-500">
        {member.workspace_names?.length
          ? member.workspace_names.join(", ")
          : "—"}
      </td>
      <td className="px-4 py-3 text-xs text-slate-500 font-mono">
        {member.last_login_at ?? "—"}
      </td>
      <td className="px-4 py-3">
        <span
          className={`text-[11px] border px-2 py-0.5 rounded-full font-medium ${statusBadgeClass(status)}`}
        >
          {status}
        </span>
      </td>
      <td className="px-4 py-3 text-right">
        <button
          type="button"
          aria-label={`${display} のメニュー`}
          data-testid={`remove-open-${member.user_id}`}
          onClick={onRemoveClick}
          className="text-slate-400 hover:text-red-600 inline-flex items-center justify-center w-6 h-6 rounded hover:bg-red-50"
        >
          <Trash2 className="w-4 h-4" aria-hidden />
          <span className="sr-only">削除</span>
          <MoreHorizontal className="w-0 h-0" aria-hidden />
        </button>
      </td>
    </tr>
  );
}

/**
 * AC-F6 (S-051 confirm_delete pattern): typed-name confirmation required
 * before the destructive DELETE call. The dialog root carries
 * `data-screen-id="S-051"` so the Gate #8 lint-mock-impl-diff indexes both
 * S-008 and S-051 from this single file.
 */
function ConfirmDeleteDialog({
  target,
  typedName,
  onTypedNameChange,
  onCancel,
  onConfirm,
  isPending,
}: {
  target: AccountMember | null;
  typedName: string;
  onTypedNameChange: (v: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
  isPending: boolean;
}) {
  const isOpen = !!target;
  const requiredName = target?.display_name || target?.email || "";
  const matches = typedName.trim() === requiredName.trim() && !!requiredName;

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
    >
      <DialogContent
        data-screen-id="S-051"
        data-feature-id="F-004"
        data-task-ids="T-V3-C-08"
      >
        <DialogHeader>
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5 text-red-600" aria-hidden />
            </div>
            <div className="space-y-1.5">
              <DialogTitle>メンバーを削除しますか?</DialogTitle>
              <DialogDescription>
                この操作は元に戻せません。
                <strong className="font-semibold text-slate-900">
                  {requiredName || "メンバー"}
                </strong>{" "}
                のアカウントへのアクセスが取り消されます。
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="space-y-1.5">
          <label
            htmlFor="confirm-typed-name"
            className="text-sm font-medium block"
          >
            確認: メンバー名 / メール を入力
          </label>
          <Input
            id="confirm-typed-name"
            data-testid="confirm-typed-name"
            placeholder={requiredName}
            value={typedName}
            onChange={(e) => onTypedNameChange(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
            キャンセル
          </Button>
          <Button
            type="button"
            data-testid="confirm-delete-submit"
            disabled={!matches || isPending}
            onClick={onConfirm}
            className="bg-red-600 hover:bg-red-700 text-white disabled:opacity-50"
          >
            {isPending ? (
              <>
                <Loader2
                  className="w-3.5 h-3.5 inline mr-1.5 animate-spin"
                  aria-hidden
                />
                削除中…
              </>
            ) : (
              "削除する"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
