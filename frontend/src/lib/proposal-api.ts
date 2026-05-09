/** 提案書 (Phase 4) API クライアント */
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export interface CenterSection { key: string; label: string; items: string[]; }
export interface CenterState { step: number; sections: CenterSection[]; free_sections?: CenterSection[]; edited_by_pm?: boolean; }
export interface ChatMsg { id: number; role: "ai" | "user" | "system"; content: string; metadata?: Record<string, any>; created_at?: string; step?: number; }
export interface StepState { step: number; title: string; description: string; status: "not_started" | "draft" | "confirmed"; artifact_id: string | null; center: CenterState; history: ChatMsg[]; }
export interface ProposalState { workspace_id: number; phase: "proposal"; steps: StepState[]; }

export interface ChapterSection { key: string; label: string; items: string[]; source_step: number; }
export interface AggregatedView {
  workspace_id: number;
  chapters: Array<{ key: string; label: string; locked: boolean; source_steps: number[]; sections: ChapterSection[]; }>;
}

export async function fetchProposalState(workspaceId: number): Promise<ProposalState> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/proposal/state`);
  return r.json();
}
export async function fetchProposalAggregatedView(workspaceId: number): Promise<AggregatedView> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/proposal/aggregated-view`);
  return r.json();
}
export async function startProposalStep(workspaceId: number, step: number) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/proposal/start-step`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step }),
  });
  return r.json();
}
export async function replyProposal(workspaceId: number, step: number, message: string) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/proposal/reply`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step, message }),
  });
  return r.json();
}
export async function completeProposalStep(workspaceId: number, step: number) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/proposal/complete-step`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step }),
  });
  return r.json();
}
export function proposalDownloadUrl(workspaceId: number, chapter: string, fmt: "html" | "md" | "json"): string {
  return `${BASE}/api/workspaces/${workspaceId}/proposal/download/${chapter}.${fmt}`;
}
