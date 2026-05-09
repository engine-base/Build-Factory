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

async function safeJson<T>(r: Response, fallback: T): Promise<T> {
  if (!r.ok) {
    console.warn(`[workspaces] HTTP ${r.status} ${r.url}`);
    return fallback;
  }
  try {
    return await r.json();
  } catch (e) {
    console.warn("[workspaces] JSON parse failed", e);
    return fallback;
  }
}

// ── Accounts ─────────────────────────────────

export async function fetchAccounts(userId = "masato"): Promise<Account[]> {
  try {
    const r = await fetch(`${BASE}/api/accounts?user_id=${userId}`);
    const data = await safeJson<{ accounts?: Account[] }>(r, {});
    return data.accounts ?? [];
  } catch (e) {
    console.warn("[fetchAccounts] failed", e);
    return [];
  }
}

export async function fetchAccount(id: number): Promise<Account | null> {
  try {
    const r = await fetch(`${BASE}/api/accounts/${id}`);
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

// ── Workspaces ───────────────────────────────

export async function fetchWorkspacesByAccount(
  accountId: number, includeArchived = false,
): Promise<Workspace[]> {
  try {
    const r = await fetch(
      `${BASE}/api/workspaces?account_id=${accountId}&include_archived=${includeArchived}`,
    );
    const data = await safeJson<{ workspaces?: Workspace[] }>(r, {});
    return data.workspaces ?? [];
  } catch {
    return [];
  }
}

export async function fetchWorkspacesForUser(userId = "masato"): Promise<Workspace[]> {
  try {
    const r = await fetch(`${BASE}/api/workspaces?user_id=${userId}`);
    const data = await safeJson<{ workspaces?: Workspace[] }>(r, {});
    return data.workspaces ?? [];
  } catch {
    return [];
  }
}

export async function fetchWorkspace(id: number): Promise<Workspace> {
  const r = await fetch(`${BASE}/api/workspaces/${id}`);
  return r.json();
}

/* ── Workspace summary (project + tasks 統計 + active phases) ─────── */

export interface WorkspaceTaskStats {
  total: number;
  completed: number;
  in_progress: number;
  pending: number;
  blockers: number;
}

export interface ActivePhase {
  id: number;
  title: string;
  skill_name: string;
  status: string;
  child_total: number;
  child_done: number;
}

export interface RecentArtifact {
  id: string;
  type: string;
  title: string;
  category_tags?: string[];
  updated_at: string;
}

export interface WorkspaceSummary {
  workspace: { id: number; name: string; description: string | null; status: string };
  project: { id: number; title: string; status: string } | null;
  task_stats: WorkspaceTaskStats;
  completion_rate: number;
  active_phases: ActivePhase[];
  recent_artifacts: RecentArtifact[];
}

export async function fetchWorkspaceSummary(id: number): Promise<WorkspaceSummary> {
  const r = await fetch(`${BASE}/api/workspaces/${id}/summary`);
  return r.json();
}

export interface WorkspaceTask {
  id: number;
  project_id: number;
  parent_task_id: number | null;
  title: string;
  description: string | null;
  assigned_to: number | null;
  assignee_name: string | null;
  skill_name: string;
  status: string;
  result: string | null;
  level: number;
  created_at: string;
}

export async function fetchWorkspaceTasks(id: number, status?: string): Promise<{ project_id: number; tasks: WorkspaceTask[]; total: number }> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  const r = await fetch(`${BASE}/api/workspaces/${id}/tasks${qs}`);
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
  try {
    const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/members`);
    const data = await safeJson<{ members?: WorkspaceMember[] }>(r, {});
    return data.members ?? [];
  } catch {
    return [];
  }
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
