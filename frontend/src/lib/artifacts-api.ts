/**
 * Artifact API クライアント (workspace 用 横串)
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export interface Artifact {
  id: string;
  type: string;
  title: string;
  data: any;
  category_tags?: string[];
  created_at: string;
  updated_at: string;
  workspace_id?: number;
  is_archived?: boolean;
}

export async function listWorkspaceArtifacts(
  workspaceId: number,
  opts?: { type?: string; limit?: number; includeArchived?: boolean },
): Promise<Artifact[]> {
  const qs = new URLSearchParams();
  qs.set("workspace_id", String(workspaceId));
  if (opts?.type) qs.set("type", opts.type);
  qs.set("limit", String(opts?.limit ?? 100));
  if (opts?.includeArchived) qs.set("include_archived", "true");
  const r = await fetch(`${BASE}/api/artifacts?${qs.toString()}`);
  if (!r.ok) return [];
  const data = await r.json();
  return data.artifacts ?? [];
}
