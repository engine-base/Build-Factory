/** 見積書 (Phase 5) API クライアント */
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export interface CenterSection { key: string; label: string; items: string[]; }
export interface CenterState { step: number; sections: CenterSection[]; free_sections?: CenterSection[]; edited_by_pm?: boolean; }
export interface ChatMsg { id: number; role: "ai" | "user" | "system"; content: string; metadata?: Record<string, any>; created_at?: string; step?: number; }
export interface StepState { step: number; title: string; description: string; status: "not_started" | "draft" | "confirmed"; artifact_id: string | null; center: CenterState; history: ChatMsg[]; }
export interface EstimateState { workspace_id: number; phase: "estimate"; steps: StepState[]; }

export interface AggregatedTabSection { key: string; label: string; items: string[]; source_step: number; }
export interface AggregatedView {
  workspace_id: number;
  tabs: Array<{ key: string; label: string; locked: boolean; source_steps: number[]; sections: AggregatedTabSection[]; }>;
}

export async function fetchEstimateState(workspaceId: number): Promise<EstimateState> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/estimate/state`);
  return r.json();
}
export async function fetchEstimateAggregatedView(workspaceId: number): Promise<AggregatedView> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/estimate/aggregated-view`);
  return r.json();
}
export async function startEstimateStep(workspaceId: number, step: number) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/estimate/start-step`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step }),
  });
  return r.json();
}
export async function replyEstimate(workspaceId: number, step: number, message: string) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/estimate/reply`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step, message }),
  });
  return r.json();
}
export async function completeEstimateStep(workspaceId: number, step: number) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/estimate/complete-step`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step }),
  });
  return r.json();
}
export function estimateDownloadUrl(workspaceId: number, tab: string, fmt: "html" | "md" | "json"): string {
  return `${BASE}/api/workspaces/${workspaceId}/estimate/download/${tab}.${fmt}`;
}
