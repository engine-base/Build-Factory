/**
 * T-021-04 / T-023-01 / T-023-02 backend API client.
 *
 * - workspaces/{ws}/members + roles (T-021-04)
 * - profile (T-023-01) — Phase 1 では account_settings に統合済みのため、本ファイルでは
 *   表示専用の最小 endpoint をラップ
 * - oauth (T-023-02 part 1)
 * - encrypted_store (T-023-02 part 2) — backend に直接 endpoint は無いため OAuth と
 *   workspace credentials を統合して扱う
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

// ──────────────────────────────────────────
// Permissions (T-021-04)
// ──────────────────────────────────────────

export type RoleKey =
  | "owner"
  | "ws_admin"
  | "contributor"
  | "viewer"
  | "client"
  | "monitor";

export interface WorkspaceMember {
  user_id: string;
  role: string;
  custom_permissions?: Record<string, unknown>;
  invited_by?: string;
  joined_at?: string;
}

export interface PermissionMatrix {
  /** permission_key → { role_key: allowed (bool | "configurable" | "limited_*") } */
  matrix: Record<string, Record<string, boolean | string>>;
  permission_keys: string[];
  roles: RoleKey[];
}

/** workspace のメンバー一覧を取得。 */
export async function fetchWorkspaceMembers(workspaceId: number): Promise<WorkspaceMember[]> {
  const res = await fetch(`${BASE}/api/workspaces/${workspaceId}/members`);
  if (!res.ok) return [];
  const body = await res.json();
  return Array.isArray(body) ? body : (body.members ?? []);
}

/** role / permission の matrix を取得 (T-021-01 で定義された 6 ロール × 30 perm)。 */
export async function fetchPermissionMatrix(): Promise<PermissionMatrix> {
  const res = await fetch(`${BASE}/api/workspaces/permissions/matrix`);
  if (!res.ok) {
    return {
      matrix: {},
      permission_keys: [],
      roles: ["owner", "ws_admin", "contributor", "viewer", "client", "monitor"],
    };
  }
  return res.json();
}

export async function updateMemberRole(params: {
  workspaceId: number;
  userId: string;
  actorUserId: string;
  newRole: RoleKey;
}): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${BASE}/api/workspaces/${params.workspaceId}/members/${params.userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor_user_id: params.actorUserId, role: params.newRole }),
  });
  if (!res.ok) {
    const detail = await res.text();
    return { ok: false, error: detail };
  }
  return { ok: true };
}

export async function removeMember(params: {
  workspaceId: number;
  userId: string;
  actorUserId: string;
}): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(
    `${BASE}/api/workspaces/${params.workspaceId}/members/${params.userId}?actor_user_id=${encodeURIComponent(params.actorUserId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) return { ok: false, error: await res.text() };
  return { ok: true };
}

export async function addMember(params: {
  workspaceId: number;
  userId: string;
  role: RoleKey;
  invitedBy?: string;
}): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${BASE}/api/workspaces/${params.workspaceId}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: params.userId, role: params.role, invited_by: params.invitedBy,
    }),
  });
  if (!res.ok) return { ok: false, error: await res.text() };
  return { ok: true };
}

// ──────────────────────────────────────────
// OAuth (T-023-02)
// ──────────────────────────────────────────

export type OAuthProvider = "slack" | "github" | "anthropic";

// ──────────────────────────────────────────
// Profile (T-023-01) — backend bf_profile router
// ──────────────────────────────────────────

export interface BfProfile {
  user_id: string;
  display_name: string | null;
  role_text: string | null;
  bio: string | null;
  theme: "light" | "dark" | "system";
  avatar_url: string | null;
  updated_at: string | null;
}

export async function fetchProfile(userId: string): Promise<BfProfile> {
  const res = await fetch(`${BASE}/api/bf-profile?user_id=${encodeURIComponent(userId)}`);
  if (!res.ok) {
    return {
      user_id: userId, display_name: userId,
      role_text: null, bio: null, theme: "light",
      avatar_url: null, updated_at: null,
    };
  }
  return res.json();
}

export async function patchProfile(
  userId: string,
  patch: Partial<Omit<BfProfile, "user_id" | "updated_at">>,
): Promise<BfProfile | null> {
  const res = await fetch(`${BASE}/api/bf-profile?user_id=${encodeURIComponent(userId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchOAuthProviders(): Promise<OAuthProvider[]> {
  const res = await fetch(`${BASE}/api/oauth/providers`);
  if (!res.ok) return [];
  const body = await res.json();
  return body.providers ?? [];
}

export async function fetchOAuthStatus(
  provider: OAuthProvider, ownerId: string,
): Promise<{ connected: boolean }> {
  const res = await fetch(
    `${BASE}/api/oauth/${provider}/status?owner_id=${encodeURIComponent(ownerId)}`,
  );
  if (!res.ok) return { connected: false };
  return res.json();
}

export async function startOAuthAuthorize(
  provider: OAuthProvider, redirectUri: string,
): Promise<{ authorize_url: string; state: string } | null> {
  const res = await fetch(
    `${BASE}/api/oauth/${provider}/authorize?redirect_uri=${encodeURIComponent(redirectUri)}`,
  );
  if (!res.ok) return null;
  return res.json();
}

export async function disconnectOAuth(
  provider: OAuthProvider, ownerId: string,
): Promise<boolean> {
  const res = await fetch(
    `${BASE}/api/oauth/${provider}?owner_id=${encodeURIComponent(ownerId)}`,
    { method: "DELETE" },
  );
  return res.ok;
}

// ──────────────────────────────────────────
// Clone opt-in + GDPR deletion (T-023-05 connector for profile page)
// ──────────────────────────────────────────

export async function fetchCloneOptin(userId: string): Promise<boolean> {
  const res = await fetch(`${BASE}/api/user/clone-optin?user_id=${encodeURIComponent(userId)}`);
  if (!res.ok) return false;
  return (await res.json()).opted_in === true;
}

export async function setCloneOptin(userId: string, optedIn: boolean): Promise<boolean> {
  const res = await fetch(`${BASE}/api/user/clone-optin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, opted_in: optedIn }),
  });
  return res.ok;
}

export async function requestUserDeletion(userId: string, reason?: string): Promise<{
  ok: boolean; request_id?: number; execute_after?: string;
}> {
  const res = await fetch(`${BASE}/api/user/deletion`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, reason }),
  });
  if (!res.ok) return { ok: false };
  return await res.json();
}
