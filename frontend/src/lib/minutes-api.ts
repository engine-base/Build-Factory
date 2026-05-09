/**
 * 議事録 (Minutes) API クライアント
 * artifacts テーブルに type="minutes" として保存。
 * data: { blocks: BlockNote の document JSON, meta: 日付/参加者/タグ }
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export interface MinutesMeta {
  date?: string;
  participants?: string[];
  duration?: string;
  category?: "client" | "internal";
  tags?: string[];
}

export interface MinutesArtifact {
  id: string;
  title: string;
  data: {
    blocks?: any[];
    meta?: MinutesMeta;
  };
  category_tags?: string[];
  created_at: string;
  updated_at: string;
  workspace_id?: number;
}

export async function listMinutes(workspaceId: number): Promise<MinutesArtifact[]> {
  const r = await fetch(`${BASE}/api/artifacts?type=minutes&workspace_id=${workspaceId}&limit=100`);
  if (!r.ok) return [];
  const data = await r.json();
  return data.artifacts ?? [];
}

export async function getMinutes(artifactId: string): Promise<MinutesArtifact | null> {
  const r = await fetch(`${BASE}/api/artifacts/${artifactId}`);
  if (!r.ok) return null;
  return r.json();
}

export async function createMinutes(args: {
  workspaceId: number;
  title: string;
  blocks?: any[];
  meta?: MinutesMeta;
}): Promise<MinutesArtifact | null> {
  const r = await fetch(`${BASE}/api/artifacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: "minutes",
      title: args.title,
      data: { blocks: args.blocks ?? [], meta: args.meta ?? {} },
      category_tags: ["minutes", args.meta?.category ?? "client"],
      workspace_id: args.workspaceId,
    }),
  });
  if (!r.ok) {
    console.warn("[minutes] create failed", r.status);
    return null;
  }
  return r.json();
}

export async function updateMinutes(args: {
  artifactId: string;
  blocks?: any[];
  title?: string;
  meta?: MinutesMeta;
  note?: string;
}): Promise<boolean> {
  const body: any = {};
  const dataPatch: any = {};
  if (args.blocks !== undefined) dataPatch.blocks = args.blocks;
  if (args.meta    !== undefined) dataPatch.meta = args.meta;
  if (Object.keys(dataPatch).length > 0) body.data_patch = dataPatch;
  if (args.title) body.title = args.title;
  if (args.note)  body.note  = args.note;

  const r = await fetch(`${BASE}/api/artifacts/${args.artifactId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.ok;
}

export async function deleteMinutes(artifactId: string): Promise<boolean> {
  const r = await fetch(`${BASE}/api/artifacts/${artifactId}`, { method: "DELETE" });
  return r.ok;
}
