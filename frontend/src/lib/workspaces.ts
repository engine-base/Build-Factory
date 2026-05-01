/**
 * workspaces.ts — Account / Workspace API クライアント
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export interface Account {
  id: number;
  name: string;
  type: "company" | "individual";
  plan: string;
  owner_user_id: string;
  billing_email: string | null;
  is_active: number;
  created_at: string;
  member_role?: string;
}

export interface Workspace {
  id: number;
  account_id: number;
  name: string;
  description: string | null;
  status: "active" | "archived" | "paused";
  project_meta: string;
  client_visibility: string;
  design_system_ref: string | null;
  created_at: string;
  updated_at: string;
  member_role?: string;
}

export interface WorkspaceMember {
  id: number;
  workspace_id: number;
  user_id: string;
  role: string;
  custom_permissions: string;
  invited_by: string | null;
  created_at: string;
}

// ── Accounts ─────────────────────────────────

export async function fetchAccounts(userId = "masato"): Promise<Account[]> {
  const r = await fetch(`${BASE}/api/accounts?user_id=${userId}`);
  return (await r.json()).accounts;
}

export async function fetchAccount(id: number): Promise<Account> {
  const r = await fetch(`${BASE}/api/accounts/${id}`);
  return r.json();
}

// ── Workspaces ───────────────────────────────

export async function fetchWorkspacesByAccount(
  accountId: number, includeArchived = false,
): Promise<Workspace[]> {
  const r = await fetch(
    `${BASE}/api/workspaces?account_id=${accountId}&include_archived=${includeArchived}`,
  );
  return (await r.json()).workspaces;
}

export async function fetchWorkspacesForUser(userId = "masato"): Promise<Workspace[]> {
  const r = await fetch(`${BASE}/api/workspaces?user_id=${userId}`);
  return (await r.json()).workspaces;
}

export async function fetchWorkspace(id: number): Promise<Workspace> {
  const r = await fetch(`${BASE}/api/workspaces/${id}`);
  return r.json();
}

export async function createWorkspace(body: {
  account_id: number;
  name: string;
  description?: string;
  project_meta?: Record<string, unknown>;
  creator_user_id?: string;
}): Promise<Workspace> {
  const r = await fetch(`${BASE}/api/workspaces`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

export async function updateWorkspace(
  id: number,
  patch: Partial<Pick<Workspace, "name" | "description" | "status" | "design_system_ref">>,
): Promise<Workspace> {
  const r = await fetch(`${BASE}/api/workspaces/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return r.json();
}

export async function archiveWorkspace(id: number): Promise<Workspace> {
  const r = await fetch(`${BASE}/api/workspaces/${id}`, { method: "DELETE" });
  return r.json();
}

// ── Members ──────────────────────────────────

export async function fetchMembers(workspaceId: number): Promise<WorkspaceMember[]> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/members`);
  return (await r.json()).members;
}

export async function addMember(
  workspaceId: number,
  body: { user_id: string; role: string; invited_by?: string },
): Promise<WorkspaceMember> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

export async function updateMemberRole(
  workspaceId: number, userId: string, role: string,
): Promise<WorkspaceMember> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/members/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  return r.json();
}

export async function removeMember(workspaceId: number, userId: string): Promise<void> {
  await fetch(`${BASE}/api/workspaces/${workspaceId}/members/${userId}`, {
    method: "DELETE",
  });
}

// ── Invitations ──────────────────────────────

export async function createInvitation(
  workspaceId: number,
  body: { email: string; role?: string; expires_in_days?: number },
): Promise<{ token: string; invitation_url: string; expires_at: string }> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/invitations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, invited_by: "masato" }),
  });
  return r.json();
}
