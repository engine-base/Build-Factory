/**
 * 要件定義 (Phase 2) API クライアント
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

export interface RequirementsState {
  workspace_id: number;
  phase: "requirements";
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
    key: string;       // overview | users | features | functional | nonfunctional | screens | data | integrations | legal | risks | unresolved | history
    label: string;
    locked: boolean;   // 該当 STEP がまだ完了していない
    source_steps: number[];
    sections: AggregatedTabSection[];
  }>;
}

export async function fetchRequirementsState(workspaceId: number): Promise<RequirementsState> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/requirements/state`);
  return r.json();
}

export async function fetchAggregatedView(workspaceId: number): Promise<AggregatedView> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/requirements/aggregated-view`);
  return r.json();
}

export async function startRequirementsStep(workspaceId: number, step: number) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/requirements/start-step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step }),
  });
  return r.json();
}

export async function replyRequirements(workspaceId: number, step: number, message: string) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/requirements/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step, message }),
  });
  return r.json();
}

export async function completeRequirementsStep(workspaceId: number, step: number) {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/requirements/complete-step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step }),
  });
  return r.json();
}

export async function patchRequirementsCenter(workspaceId: number, step: number, center: CenterState): Promise<void> {
  await fetch(`${BASE}/api/workspaces/${workspaceId}/requirements/center?step=${step}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ center, edited_by_pm: true }),
  });
}

export function downloadUrl(workspaceId: number, tab: string, fmt: "html" | "md" | "json"): string {
  return `${BASE}/api/workspaces/${workspaceId}/requirements/download/${tab}.${fmt}`;
}
