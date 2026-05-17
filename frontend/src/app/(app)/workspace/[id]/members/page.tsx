"use client";

/**
 * T-V3-C-63 / S-014: 案件メンバー (workspace_members) page.
 *
 * Vertical Slice / UI implementation of the screen documented at:
 *   docs/mocks/2026-05-15_v3/workspace/S-014-workspace-members.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-014
 * @feature-id F-004,F-021
 * @task-ids T-V3-C-63
 * @entities E-003,E-001
 * @phase Phase 1
 *
 * Backend contracts (T-V3-B-06 / backend/routers/workspaces.py):
 *   GET    /api/workspaces/{id}/members
 *   PUT    /api/workspaces/{id}/members/{user_id}/role
 *   DELETE /api/workspaces/{id}/members/{user_id}
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-63.md):
 *   structural.AC-S1 — h1 === "案件メンバー" (mock h1 逐語コピー).
 *   structural.AC-S2 — Lucide icons only (no emoji glyphs) per
 *                      design-tokens.md §8.
 *   functional.AC-F1 — GET /api/workspaces/{id}/members on mount; 2xx renders,
 *                      4xx renders inline toast + empty state.
 *   functional.AC-F2 — 401 redirects to /login (S-001); page never renders any
 *                      workspace-scoped data on the unauthenticated branch.
 *   functional.AC-F3 — PUT /api/accounts/{id} (and the role mutation
 *                      /api/workspaces/{id}/members/{user_id}/role) emits the
 *                      account_updated audit log server-side (T-V3-B-06).
 *   functional.AC-F4 — Access is evaluated server-side via OR across role
 *                      default_permissions and member custom_permissions
 *                      (F-021); the page surfaces 403 as a friendly toast and
 *                      does not bypass the server check client-side.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronRight,
  Loader2,
  MoreHorizontal,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";

import {
  WorkspaceMembersApiError,
  workspaceMembersEndpoint,
  type WorkspaceMember,
  type WorkspaceRole,
} from "@/api/workspace-members";
import { useWorkspaceMembers } from "@/hooks/use-workspace-members";

// ---------------------------------------------------------------------------
// Mock-derived literals — 逐語コピー from
// docs/mocks/2026-05-15_v3/workspace/S-014-workspace-members.html.
// AC-S1: h1_text === "案件メンバー"
// ---------------------------------------------------------------------------
const S014_H1_TEXT = "案件メンバー";

const ROLE_OPTIONS: WorkspaceRole[] = [
  "owner",
  "admin",
  "member",
  "viewer",
  "guest",
];

const ROLE_BADGE_CLASS: Record<string, string> = {
  owner: "bg-eb-50 text-eb-700 border-eb-200",
  workspace_admin: "bg-eb-50 text-eb-700 border-eb-200",
  ws_admin: "bg-eb-50 text-eb-700 border-eb-200",
  admin: "bg-blue-50 text-blue-700 border-blue-200",
  contributor: "bg-blue-50 text-blue-700 border-blue-200",
  member: "bg-blue-50 text-blue-700 border-blue-200",
  client: "bg-amber-50 text-amber-700 border-amber-200",
  guest: "bg-amber-50 text-amber-700 border-amber-200",
  viewer: "bg-slate-100 text-slate-700 border-slate-200",
  monitor: "bg-slate-100 text-slate-700 border-slate-200",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resolveAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage?.getItem("bf.access_token") ?? null;
  } catch {
    return null;
  }
}

function roleBadgeClass(role: string): string {
  return (
    ROLE_BADGE_CLASS[role] ?? "bg-slate-100 text-slate-700 border-slate-200"
  );
}

function initial(name: string | null | undefined, fallback: string): string {
  const src = (name || fallback || "?").trim();
  return src.charAt(0).toUpperCase() || "?";
}

function describeError(
  err: unknown,
  fallbackEndpoint: string,
): { kind: "auth" | "error"; message: string } {
  if (err instanceof WorkspaceMembersApiError) {
    if (err.status === 401) {
      return { kind: "auth", message: err.toUserMessage() };
    }
    return { kind: "error", message: err.toUserMessage() };
  }
  return {
    kind: "error",
    message: `通信に失敗しました (${fallbackEndpoint})`,
  };
}

function describePermissions(member: WorkspaceMember): string {
  // visible_tabs may be string (CSV) or array.
  const v = member.visible_tabs;
  if (Array.isArray(v) && v.length > 0) return v.join(", ");
  if (typeof v === "string" && v.trim()) return v;
  return "—";
}

function describeCustomPermissions(member: WorkspaceMember): string {
  const c = member.custom_permissions;
  if (!c) return "—";
  if (typeof c === "string") return c;
  if (typeof c === "object") {
    const trueKeys = Object.entries(c)
      .filter(([, v]) => v === true)
      .map(([k]) => k);
    if (trueKeys.length === 0) return "—";
    return trueKeys.join(", ");
  }
  return "—";
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function WorkspaceMembersPage(): React.JSX.Element {
  const params = useParams();
  const router = useRouter();
  const idParam = params?.id;
  const workspaceId = React.useMemo(() => {
    if (Array.isArray(idParam)) return idParam[0] ?? "";
    return String(idParam ?? "");
  }, [idParam]);

  const authToken = React.useMemo(() => resolveAuthToken(), []);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);
  const [redirectedToLogin, setRedirectedToLogin] = React.useState(false);

  const {
    data,
    isLoading,
    isError,
    error,
    isSuccess,
    refetch,
    updateRole,
    removeMember,
    isUpdatingRole,
    isRemoving,
  } = useWorkspaceMembers({
    workspaceId,
    authToken,
    // AC-F2: do not fire the GET when the workspaceId is missing — but we
    // still want to attempt it for missing token so the server returns 401
    // and we can branch to /login.
    enabled: !!workspaceId,
  });

  const endpoint = React.useMemo(
    () => workspaceMembersEndpoint(workspaceId || "_"),
    [workspaceId],
  );

  // AC-F2: 401 → router.replace("/login"). The early replace guard prevents
  // any workspace-scoped data from rendering.
  React.useEffect(() => {
    if (!isError) return;
    const described = describeError(error, endpoint);
    if (described.kind === "auth" && !redirectedToLogin) {
      setRedirectedToLogin(true);
      router.replace("/login");
      return;
    }
    setErrorMsg(described.message);
  }, [isError, error, endpoint, redirectedToLogin, router]);

  // Clear the inline toast on successful refetch.
  React.useEffect(() => {
    if (isSuccess) setErrorMsg(null);
  }, [isSuccess]);

  const members = data?.members ?? [];

  const handleRoleChange = React.useCallback(
    async (userId: string, newRole: WorkspaceRole) => {
      try {
        await updateRole({ userId, role: newRole });
        setErrorMsg(null);
      } catch (err) {
        const described = describeError(
          err,
          `/api/workspaces/${workspaceId}/members/${userId}/role`,
        );
        if (described.kind === "auth" && !redirectedToLogin) {
          setRedirectedToLogin(true);
          router.replace("/login");
          return;
        }
        setErrorMsg(described.message);
      }
    },
    [updateRole, workspaceId, redirectedToLogin, router],
  );

  const handleRemove = React.useCallback(
    async (userId: string) => {
      try {
        await removeMember({ userId });
        setErrorMsg(null);
      } catch (err) {
        const described = describeError(
          err,
          `/api/workspaces/${workspaceId}/members/${userId}`,
        );
        if (described.kind === "auth" && !redirectedToLogin) {
          setRedirectedToLogin(true);
          router.replace("/login");
          return;
        }
        setErrorMsg(described.message);
      }
    },
    [removeMember, workspaceId, redirectedToLogin, router],
  );

  // AC-F2: while the auth redirect is in flight, render nothing so no
  // workspace-scoped data leaks.
  if (redirectedToLogin) {
    return (
      <main
        data-screen-id="S-014"
        data-feature-id="F-004,F-021"
        data-task-ids="T-V3-C-63"
        data-entities="E-003,E-001"
        data-phase="Phase 1"
        aria-live="polite"
        className="min-h-screen bg-slate-50"
      />
    );
  }

  return (
    <main
      data-screen-id="S-014"
      data-feature-id="F-004,F-021"
      data-task-ids="T-V3-C-63"
      data-entities="E-003,E-001"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <div className="max-w-[1200px] mx-auto px-6 py-8">
        {/* Breadcrumb */}
        <div className="text-xs text-slate-500 flex items-center gap-1.5 mb-2">
          <a
            href={`/workspaces/${workspaceId}`}
            className="hover:text-slate-900 inline-flex items-center gap-1"
          >
            <ArrowLeft className="w-3 h-3" aria-hidden />
            Workspace
          </a>
          <ChevronRight className="w-3 h-3" aria-hidden />
          <span className="text-slate-900 font-medium">メンバー</span>
        </div>

        {/* Header — AC-S1 verbatim h1 text */}
        <div className="flex items-end justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">{S014_H1_TEXT}</h1>
            <p className="text-sm text-slate-600 mt-1">
              この workspace に参加しているメンバー / ロール / カスタム権限
            </p>
          </div>
          <a
            href={`/workspaces/${workspaceId}/invite`}
            data-testid="invite-link"
            className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md inline-flex items-center gap-2"
          >
            <UserPlus className="w-4 h-4" aria-hidden />
            メンバーを招待
          </a>
        </div>

        {/* AC-F1: inline error toast (4xx renders here + empty state below) */}
        {errorMsg && (
          <div
            role="alert"
            aria-live="assertive"
            data-testid="members-error-toast"
            className="mb-4 flex items-start gap-2 px-4 py-3 bg-rose-50 border border-rose-200 text-rose-700 rounded"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
            <div className="text-sm flex-1">{errorMsg}</div>
            <button
              type="button"
              className="text-rose-500 hover:text-rose-700 text-xs underline"
              onClick={() => {
                setErrorMsg(null);
                void refetch();
              }}
            >
              再試行
            </button>
          </div>
        )}

        {/* Members table */}
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          {isLoading ? (
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
                  <th className="text-left font-bold px-4 py-2">
                    Custom 権限
                  </th>
                  <th className="text-left font-bold px-4 py-2">表示 Tabs</th>
                  <th className="text-left font-bold px-4 py-2">最終 active</th>
                  <th className="text-right font-bold px-4 py-2"></th>
                </tr>
              </thead>
              <tbody data-testid="members-table-body">
                {members.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-10 text-center text-sm text-slate-500"
                      data-testid="members-empty-state"
                    >
                      <Users
                        className="w-5 h-5 inline mr-2 text-slate-400"
                        aria-hidden
                      />
                      {errorMsg
                        ? "メンバーを取得できませんでした"
                        : "メンバーが登録されていません"}
                    </td>
                  </tr>
                )}
                {members.map((m) => (
                  <MemberRow
                    key={m.user_id}
                    member={m}
                    onRoleChange={(role) => handleRoleChange(m.user_id, role)}
                    onRemove={() => handleRemove(m.user_id)}
                    saving={isUpdatingRole}
                    removing={isRemoving}
                  />
                ))}
              </tbody>
            </table>
          )}
          <div className="px-4 py-3 border-t border-slate-100 text-xs text-slate-500">
            {members.length} 件 · {endpoint}
          </div>
        </div>
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Member row — role select + delete button.
// ---------------------------------------------------------------------------

function MemberRow({
  member,
  onRoleChange,
  onRemove,
  saving,
  removing,
}: {
  member: WorkspaceMember;
  onRoleChange: (role: WorkspaceRole) => void;
  onRemove: () => void;
  saving: boolean;
  removing: boolean;
}): React.JSX.Element {
  const display = member.display_name || member.email || member.user_id;
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-eb-500 text-white text-xs font-bold flex items-center justify-center">
            {initial(member.display_name, member.user_id)}
          </div>
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
        <label className="sr-only" htmlFor={`role-${member.user_id}`}>
          ロール
        </label>
        <select
          id={`role-${member.user_id}`}
          data-testid={`role-select-${member.user_id}`}
          aria-label={`${display} のロール`}
          value={
            ROLE_OPTIONS.includes(member.role as WorkspaceRole)
              ? (member.role as WorkspaceRole)
              : (member.role as string)
          }
          disabled={saving}
          onChange={(e) => onRoleChange(e.target.value as WorkspaceRole)}
          className={`text-[11px] border px-2 py-0.5 rounded-full font-medium bg-white ${roleBadgeClass(
            String(member.role),
          )}`}
        >
          {ROLE_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
          {!ROLE_OPTIONS.includes(member.role as WorkspaceRole) && (
            <option value={String(member.role)}>{String(member.role)}</option>
          )}
        </select>
      </td>
      <td className="px-4 py-3 text-xs text-slate-700">
        {describeCustomPermissions(member)}
      </td>
      <td className="px-4 py-3 text-xs text-slate-500">
        {describePermissions(member)}
      </td>
      <td className="px-4 py-3 text-xs text-slate-500 font-mono">
        {member.last_active_at ?? "—"}
      </td>
      <td className="px-4 py-3 text-right">
        <button
          type="button"
          data-testid={`remove-member-${member.user_id}`}
          aria-label={`${display} を削除`}
          disabled={removing}
          onClick={onRemove}
          className="text-slate-400 hover:text-red-600 inline-flex items-center justify-center w-6 h-6 rounded hover:bg-red-50 disabled:opacity-50"
        >
          <Trash2 className="w-4 h-4" aria-hidden />
          <span className="sr-only">削除</span>
          <MoreHorizontal className="w-0 h-0" aria-hidden />
        </button>
      </td>
    </tr>
  );
}
