/**
 * artifacts.ts — Artifact API クライアント + WebSocket
 *
 * Backend (`/api/artifacts/*`) との通信ラッパー。
 * Live 反映は WebSocket で受け取る。
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
const WS_BASE = BASE.replace(/^http/, "ws");

export type ArtifactType =
  | "list" | "table" | "kanban" | "kpi-card" | "markdown"
  | "gantt" | "calendar" | "chart" | "compare" | "workflow"
  | "gallery" | "matrix" | "form" | "slide" | "mindmap";

export interface Artifact {
  id: string;
  type: ArtifactType;
  title: string;
  data: Record<string, unknown>;
  category_tags: string[];
  pinned_by: string[];
  thread_id: number | null;
  employee_id: number | null;
  created_by: string;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface CategorySummary {
  key: string;
  label: string;
  count: number;
}

export interface ArtifactEvent {
  id: number;
  artifact_id: string;
  actor: string;
  action: string;
  diff: Record<string, unknown>;
  note: string;
  ts: string;
}

// ── REST API ─────────────────────────────────

export async function fetchArtifacts(opts: {
  category?: string;
  type?: ArtifactType;
  pinned_only?: boolean;
  thread_id?: number;
  include_archived?: boolean;
  limit?: number;
} = {}): Promise<{ artifacts: Artifact[]; total: number }> {
  const params = new URLSearchParams();
  if (opts.category)         params.set("category", opts.category);
  if (opts.type)             params.set("type", opts.type);
  if (opts.pinned_only)      params.set("pinned_only", "true");
  if (opts.thread_id)        params.set("thread_id", String(opts.thread_id));
  if (opts.include_archived) params.set("include_archived", "true");
  if (opts.limit)            params.set("limit", String(opts.limit));
  const res = await fetch(`${BASE}/api/artifacts?${params.toString()}`);
  return res.json();
}

export async function fetchCategorySummary(): Promise<CategorySummary[]> {
  const res = await fetch(`${BASE}/api/artifacts/categories/summary`);
  const data = await res.json();
  return data.categories;
}

export async function fetchArtifact(id: string): Promise<Artifact> {
  const res = await fetch(`${BASE}/api/artifacts/${id}`);
  return res.json();
}

export async function createArtifact(body: {
  type: ArtifactType;
  title?: string;
  data?: Record<string, unknown>;
  category_tags?: string[];
  thread_id?: number;
  employee_id?: number;
}): Promise<Artifact> {
  const res = await fetch(`${BASE}/api/artifacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

export async function updateArtifact(
  id: string,
  body: {
    title?: string;
    data?: Record<string, unknown>;
    data_patch?: Record<string, unknown>;
    note?: string;
  },
): Promise<Artifact> {
  const res = await fetch(`${BASE}/api/artifacts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

export async function pinArtifact(id: string): Promise<Artifact> {
  const res = await fetch(`${BASE}/api/artifacts/${id}/pin`, { method: "POST" });
  return res.json();
}

export async function unpinArtifact(id: string): Promise<Artifact> {
  const res = await fetch(`${BASE}/api/artifacts/${id}/unpin`, { method: "POST" });
  return res.json();
}

export async function archiveArtifact(id: string): Promise<Artifact> {
  const res = await fetch(`${BASE}/api/artifacts/${id}/archive`, { method: "POST" });
  return res.json();
}

export async function deleteArtifact(id: string): Promise<void> {
  await fetch(`${BASE}/api/artifacts/${id}`, { method: "DELETE" });
}

export async function fetchArtifactEvents(id: string): Promise<ArtifactEvent[]> {
  const res = await fetch(`${BASE}/api/artifacts/${id}/events`);
  const data = await res.json();
  return data.events;
}

export async function exportArtifact(
  id: string,
  format: "pdf" | "xlsx" | "pptx",
  template: string = "minimal",
): Promise<{ ok: boolean; url: string; filename: string; size: number }> {
  const res = await fetch(
    `${BASE}/api/artifacts/${id}/export?format=${format}&template=${template}`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`export failed: ${res.status}`);
  return res.json();
}

export function exportDownloadUrl(relUrl: string): string {
  return `${BASE}${relUrl}`;
}

// ── WebSocket ────────────────────────────────

export interface ArtifactWSEvent {
  event:
    | "connected" | "pong"
    | "artifact.created" | "artifact.updated"
    | "artifact.pinned"  | "artifact.archived"
    | "artifact.deleted";
  artifact?: Artifact;
  artifact_id?: string;
  user_id?: string;
}

export class ArtifactWS {
  private ws: WebSocket | null = null;
  private listeners = new Set<(e: ArtifactWSEvent) => void>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private userId: string = "masato") {}

  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return;
    this.ws = new WebSocket(`${WS_BASE}/api/artifacts/ws?user_id=${this.userId}`);
    this.ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as ArtifactWSEvent;
        this.listeners.forEach((fn) => fn(data));
      } catch { /* ignore */ }
    };
    this.ws.onclose = () => {
      // 自動再接続
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  on(fn: (e: ArtifactWSEvent) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
}
