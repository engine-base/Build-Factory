/**
 * 価格設計 (Phase 3) API クライアント
 */
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export interface CenterSection {
  key: string;
  label: string;
  items: string[];
}

export interface CenterState {
  step: number;
  sections: CenterSection[];
  free_sections?: CenterSection[];
  edited_by_pm?: boolean;
}

export interface ChatMsg {
  id: number;
  role: "ai" | "user" | "system";
  content: string;
  metadata?: Record<string, any>;
  created_at?: string;
  step?: number;
}

export interface StepState {
  step: number;
  title: string;
  description: string;
  status: "not_started" | "draft" | "confirmed";
  artifact_id: string | null;
  center: CenterState;
  history: ChatMsg[];
}

export interface PricingState {
  workspace_id: number;
  phase: "pricing";
  steps: StepState[];
}

export interface AggregatedTabSection {
  key: string;
  label: string;
  items: string[];
  source_step: number;
}

export interface AggregatedView {
  workspace_id: number;
  tabs: Array<{
    key: string;
    label: string;
    locked: boolean;
    source_steps: number[];
    sections: AggregatedTabSection[];
  }>;
}

export async function fetchPricingState(workspaceId: number): Promise<PricingState> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/pricing/state`);
  return r.json();
}

export async function fetchPricingAggregatedView(workspaceId: number): Promise<AggregatedView> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/pricing/aggregated-view`);
  return r.json();
}

export async function startPricingStep(workspaceId: number, step: number) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/pricing/start-step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step }),
  });
  return r.json();
}

export async function replyPricing(workspaceId: number, step: number, message: string) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/pricing/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step, message }),
  });
  return r.json();
}

export async function completePricingStep(workspaceId: number, step: number) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/pricing/complete-step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step }),
  });
  return r.json();
}

export function pricingDownloadUrl(workspaceId: number, tab: string, fmt: "html" | "md" | "json"): string {
  return `${BASE}/api/workspaces/${workspaceId}/pricing/download/${tab}.${fmt}`;
}
