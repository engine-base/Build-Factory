"use client";

/**
 * S-014 / T-021-04: Workspace メンバー & 権限マトリクス UI (REFACTOR)
 *
 * 対応モック: docs/mocks/2026-05-09_v1/workspace/S-014-workspace-members.html
 * 対応 backend (PR #24 で実装済):
 *   - GET /api/workspaces/{id}/members
 *   - GET /api/workspaces/permissions/matrix
 *   - POST /api/workspaces/{id}/members
 *   - PATCH /api/workspaces/{id}/members/{user_id}  (actor_user_id 必須)
 *   - DELETE /api/workspaces/{id}/members/{user_id}?actor_user_id=
 *
 * 仕様遵守:
 *   - 6 ロール (owner / ws_admin / contributor / viewer / client / monitor)
 *   - 30 permission matrix を backend が正本として提供 (T-021-01)
 *   - self-strip / owner protection: backend 409 をそのまま表示 (T-021-05)
 *   - ENGINE BASE green (bg-eb-500) を主色 (CLAUDE.md §5.2)
 *   - Lucide のみ・絵文字禁止 (CLAUDE.md §5.1)
 */

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  UserPlus, Trash2, Check, AlertTriangle, Loader2, X,
  ShieldCheck, Eye, Hammer, UserCog, Briefcase, Activity,
  Mail, Copy, Link as LinkIcon,
} from "lucide-react";
import {
  fetchWorkspaceMembers, fetchPermissionMatrix,
  updateMemberRole, removeMember, addMember,
  type RoleKey, type WorkspaceMember,
} from "@/lib/workspace-api";
import { Workspace, fetchWorkspace, createInvitation } from "@/lib/workspaces";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { WorkspaceShell } from "@/components/workspace-shell";

// TODO(auth): セッション統合後に動的取得
const ACTOR_USER_ID = "masato";

const ROLE_KEYS: RoleKey[] = ["owner", "ws_admin", "contributor", "viewer", "client", "monitor"];

const ROLE_META: Record<RoleKey, { label: string; icon: typeof ShieldCheck; tone: string; initial: string }> = {
  owner:       { label: "Owner",       icon: ShieldCheck, tone: "bg-eb-500 text-white",   initial: "M" },
  ws_admin:    { label: "Admin",       icon: UserCog,     tone: "bg-blue-500 text-white", initial: "A" },
  contributor: { label: "Contributor", icon: Hammer,      tone: "bg-amber-500 text-white",initial: "C" },
  viewer:      { label: "Viewer",      icon: Eye,         tone: "bg-slate-500 text-white",initial: "V" },
  client:      { label: "Client",      icon: Briefcase,   tone: "bg-purple-500 text-white",initial: "K" },
  monitor:     { label: "Monitor",     icon: Activity,    tone: "bg-slate-400 text-white",initial: "O" },
};

// S-014 mock の代表 7 列。本実装は backend matrix を joining。
const SUMMARY_COLUMNS = [
  { key: "view_phase_X",              label: "ヒアリング" },
  { key: "edit_spec",                 label: "仕様書" },
  { key: "create_tasks",              label: "タスク作成" },
  { key: "run_session",               label: "実行" },
  { key: "approve_red_line",          label: "承認" },
  { key: "manage_workspace_settings", label: "設定" },
  { key: "delete_artifacts",          label: "削除" },
];

export default function MembersPage() {
  const params = useParams();
  const id = Number(params?.id);
  const qc = useQueryClient();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [newUserId, setNewUserId] = useState("");
  const [newRole, setNewRole] = useState<RoleKey>("contributor");

  // T-004-03/04: 招待リンク発行
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<RoleKey>("contributor");
  const [inviteExpires, setInviteExpires] = useState(7);
  const [inviteResult, setInviteResult] = useState<{ url: string; expires_at: string } | null>(null);
  const [inviting, setInviting] = useState(false);

  useEffect(() => {
    if (!id) return;
    fetchWorkspace(id).then(setWorkspace).catch(() => setWorkspace(null));
  }, [id]);

  const membersQ = useQuery<WorkspaceMember[]>({
    queryKey: ["ws-members", id],
    queryFn: () => fetchWorkspaceMembers(id),
    enabled: id > 0,
  });

  const matrixQ = useQuery({
    queryKey: ["permission-matrix"],
    queryFn: fetchPermissionMatrix,
  });

  const roleMut = useMutation({
    mutationFn: async (vars: { userId: string; newRole: RoleKey }) => {
      const res = await updateMemberRole({
        workspaceId: id, userId: vars.userId,
        actorUserId: ACTOR_USER_ID, newRole: vars.newRole,
      });
      if (!res.ok) throw new Error(res.error || "role update failed");
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ws-members", id] }),
    onError: (e: Error) => setErrorMsg(formatBackendError(e.message)),
  });

  const removeMut = useMutation({
    mutationFn: async (userId: string) => {
      const res = await removeMember({ workspaceId: id, userId, actorUserId: ACTOR_USER_ID });
      if (!res.ok) throw new Error(res.error || "remove failed");
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ws-members", id] }),
    onError: (e: Error) => setErrorMsg(formatBackendError(e.message)),
  });

  const addMut = useMutation({
    mutationFn: async () => {
      const res = await addMember({
        workspaceId: id, userId: newUserId, role: newRole, invitedBy: ACTOR_USER_ID,
      });
      if (!res.ok) throw new Error(res.error || "add failed");
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ws-members", id] });
      setNewUserId(""); setShowAdd(false);
    },
    onError: (e: Error) => setErrorMsg(formatBackendError(e.message)),
  });

  const matrix = matrixQ.data?.matrix ?? {};
  const permCount = matrixQ.data?.permission_keys.length ?? 30;

  if (!workspace) {
    return (
      <div className="p-6 flex items-center gap-2 text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> ワークスペースを読み込み中…
      </div>
    );
  }

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      active="members"
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: "メンバー / 権限" },
      ]}
    >
      <div className="space-y-4 max-w-[1200px]">
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <h1 className="text-xl font-bold text-slate-900">案件メンバー / 権限マトリクス</h1>
            <div className="text-xs text-slate-500 mt-1">
              backend `services/roles.py` の 6 ロール × {permCount} permission を正本としています (T-021-01)。
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 rounded font-bold"
              onClick={() => { setShowInvite((s) => !s); setShowAdd(false); setInviteResult(null); }}
            >
              <Mail className="w-3.5 h-3.5" /> 招待リンク発行
            </button>
            <button
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs bg-eb-500 hover:bg-eb-600 text-white rounded font-bold"
              onClick={() => { setShowAdd((s) => !s); setShowInvite(false); }}
            >
              <UserPlus className="w-3.5 h-3.5" /> メンバー追加
            </button>
          </div>
        </div>

        {errorMsg && (
          <div className="flex items-start gap-2 px-4 py-3 bg-rose-50 border border-rose-200 text-rose-700 rounded">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <div className="text-sm flex-1">{errorMsg}</div>
            <button className="text-rose-500 hover:text-rose-700" onClick={() => setErrorMsg(null)}>
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {showInvite && (
          <div className="px-4 py-3 bg-eb-50 border border-eb-100 rounded space-y-3">
            <div className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
              <LinkIcon className="w-3.5 h-3.5" /> 招待リンクを発行する
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Input
                type="email"
                className="min-w-[220px] max-w-[280px]"
                placeholder="招待先メールアドレス"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
              />
              <select
                className="px-3 py-1.5 text-sm border border-slate-300 rounded bg-white"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as RoleKey)}
              >
                {ROLE_KEYS.map((r) => (
                  <option key={r} value={r}>{ROLE_META[r].label}</option>
                ))}
              </select>
              <select
                className="px-3 py-1.5 text-sm border border-slate-300 rounded bg-white"
                value={inviteExpires}
                onChange={(e) => setInviteExpires(Number(e.target.value))}
              >
                <option value={1}>1 日</option>
                <option value={7}>7 日</option>
                <option value={14}>14 日</option>
                <option value={30}>30 日</option>
              </select>
              <button
                className="px-3 py-1.5 text-xs bg-eb-500 hover:bg-eb-600 text-white rounded font-bold disabled:opacity-50"
                disabled={!inviteEmail || inviting}
                onClick={async () => {
                  setInviting(true);
                  setInviteResult(null);
                  try {
                    const r = await createInvitation(id, {
                      email: inviteEmail,
                      role: inviteRole,
                      expires_in_days: inviteExpires,
                    });
                    if (r && (r as any).invitation_url) {
                      setInviteResult({
                        url: (r as any).invitation_url,
                        expires_at: (r as any).expires_at,
                      });
                    } else {
                      setErrorMsg("招待リンク発行に失敗しました");
                    }
                  } catch {
                    setErrorMsg("招待リンク発行に失敗しました");
                  } finally {
                    setInviting(false);
                  }
                }}
              >
                {inviting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "発行"}
              </button>
              <button
                className="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700"
                onClick={() => { setShowInvite(false); setInviteResult(null); }}
              >
                キャンセル
              </button>
            </div>
            {inviteResult && (
              <div className="px-3 py-2 bg-white border border-eb-200 rounded text-xs space-y-1.5">
                <div className="text-slate-500">
                  招待リンク (期限: {new Date(inviteResult.expires_at).toLocaleString("ja-JP")}):
                </div>
                <div className="flex items-center gap-2">
                  <Input
                    readOnly
                    className="flex-1 font-mono text-xs"
                    value={inviteResult.url}
                    onFocus={(e) => e.target.select()}
                  />
                  <button
                    className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-slate-100 hover:bg-slate-200 rounded"
                    onClick={() => navigator.clipboard?.writeText(inviteResult.url)}
                  >
                    <Copy className="w-3 h-3" /> コピー
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {showAdd && (
          <div className="px-4 py-3 bg-eb-50 border border-eb-100 rounded flex items-center gap-2 flex-wrap">
            <Input
              className="min-w-[180px] max-w-[220px]"
              placeholder="user_id (例: hanako)"
              value={newUserId}
              onChange={(e) => setNewUserId(e.target.value)}
            />
            <select
              className="px-3 py-1.5 text-sm border border-slate-300 rounded bg-white"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as RoleKey)}
            >
              {ROLE_KEYS.map((r) => (
                <option key={r} value={r}>{ROLE_META[r].label}</option>
              ))}
            </select>
            <button
              className="px-3 py-1.5 text-xs bg-eb-500 hover:bg-eb-600 text-white rounded font-bold disabled:opacity-50"
              disabled={!newUserId || addMut.isPending}
              onClick={() => addMut.mutate()}
            >
              {addMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "追加"}
            </button>
            <button
              className="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700"
              onClick={() => setShowAdd(false)}
            >
              キャンセル
            </button>
          </div>
        )}

        <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-[10px] tracking-wider text-slate-500 font-bold">
                <tr>
                  <th className="text-left px-5 py-2 sticky left-0 bg-slate-50 z-10">メンバー</th>
                  <th className="text-left px-2 py-2">ロール</th>
                  {SUMMARY_COLUMNS.map((c) => (
                    <th key={c.key} className="px-2 py-2 text-center whitespace-nowrap">{c.label}</th>
                  ))}
                  <th className="px-2 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {membersQ.isLoading && (
                  <tr>
                    <td colSpan={SUMMARY_COLUMNS.length + 3} className="px-5 py-6 text-center text-slate-400">
                      <Loader2 className="w-4 h-4 inline-block animate-spin mr-2" /> 読み込み中…
                    </td>
                  </tr>
                )}
                {!membersQ.isLoading && (!membersQ.data || membersQ.data.length === 0) && (
                  <tr>
                    <td colSpan={SUMMARY_COLUMNS.length + 3} className="px-5 py-6 text-center text-slate-400">
                      メンバーがいません。「メンバー追加」から追加できます。
                    </td>
                  </tr>
                )}
                {membersQ.data?.map((m) => (
                  <MemberRow
                    key={m.user_id}
                    member={m}
                    matrix={matrix}
                    onRoleChange={(role) => roleMut.mutate({ userId: m.user_id, newRole: role })}
                    onRemove={() => {
                      if (confirm(`${m.user_id} を削除しますか?`)) removeMut.mutate(m.user_id);
                    }}
                    saving={roleMut.isPending && roleMut.variables?.userId === m.user_id}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="bg-white border border-slate-200 rounded-lg p-5">
          <h2 className="text-sm font-bold mb-2">ロール定義</h2>
          <p className="text-xs text-slate-500 mb-3">
            上の表は代表 7 列のサマリ。完全 30 permission は `services/roles.py PERMISSION_MATRIX` が正本。
            「configurable」「limited_*」は backend で role 単位で False (safe-by-default)。
          </p>
          <div className="flex flex-wrap gap-2">
            {ROLE_KEYS.map((r) => {
              const M = ROLE_META[r];
              const Icon = M.icon;
              return (
                <span
                  key={r}
                  className={`inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-bold ${M.tone}`}
                >
                  <Icon className="w-3 h-3" /> {M.label}
                </span>
              );
            })}
          </div>
        </section>

        <div className="text-[11px] text-slate-400 font-mono text-right">
          S-014 workspace_members · F-021 · T-021-04 · actor={ACTOR_USER_ID}
        </div>
      </div>
    </WorkspaceShell>
  );
}

function MemberRow({
  member, matrix, onRoleChange, onRemove, saving,
}: {
  member: WorkspaceMember;
  matrix: Record<string, Record<string, boolean | string>>;
  onRoleChange: (r: RoleKey) => void;
  onRemove: () => void;
  saving: boolean;
}) {
  const raw = member.role || "viewer";
  const role: RoleKey = (raw === "admin" ? "ws_admin" : raw) as RoleKey;
  const meta = ROLE_META[role] ?? ROLE_META.viewer;
  const initial = (member.user_id?.[0] ?? "?").toUpperCase();

  return (
    <tr className="hover:bg-slate-50">
      <td className="px-5 py-3 sticky left-0 bg-white z-10">
        <div className="flex items-center gap-2">
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${meta.tone}`}>
            {initial}
          </div>
          <span className="font-medium">{member.user_id}</span>
          {role === "owner" && (
            <span className="text-[9px] uppercase tracking-wider text-eb-700 bg-eb-50 px-1 py-0.5 rounded">owner</span>
          )}
        </div>
      </td>
      <td className="px-2 py-2">
        <select
          className="w-32 h-8 text-xs px-2 border border-slate-300 rounded bg-white disabled:opacity-50"
          value={role}
          onChange={(e) => onRoleChange(e.target.value as RoleKey)}
          disabled={saving}
        >
          {ROLE_KEYS.map((r) => (
            <option key={r} value={r}>{ROLE_META[r].label}</option>
          ))}
        </select>
      </td>
      {SUMMARY_COLUMNS.map((col) => {
        const v = matrix[col.key]?.[role];
        return <td key={col.key} className="px-2 py-2 text-center">{renderCell(v)}</td>;
      })}
      <td className="px-2 py-2 text-right">
        <button
          className="text-slate-400 hover:text-rose-600 disabled:opacity-30"
          onClick={onRemove}
          title="削除"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </td>
    </tr>
  );
}

function renderCell(v: boolean | string | undefined) {
  if (v === true)  return <Check className="w-4 h-4 text-emerald-600 mx-auto" />;
  if (v === false || v === undefined) return <span className="text-slate-300">×</span>;
  return (
    <span className="text-[10px] text-amber-600 font-bold uppercase">
      {String(v).replace(/_/g, " ")}
    </span>
  );
}

function formatBackendError(raw: string): string {
  if (raw.includes("self_strip_blocked")) return "自分自身のロール変更・削除はブロックされました (T-021-05)。";
  if (raw.includes("owner_protected"))    return "最後の owner は降格・削除できません (T-021-05)。";
  if (raw.includes("unknown permission")) return "不明な permission key が含まれています (T-021-02)。";
  return raw;
}
