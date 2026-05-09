/**
 * ヒアリング API クライアント
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

export interface HearingState {
  workspace_id: number;
  phase: "hearing";
  steps: StepState[];
}

export async function fetchHearingState(workspaceId: number): Promise<HearingState> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/hearing/state`);
  return r.json();
}

export async function startStep(workspaceId: number, step: number): Promise<{
  artifact: any;
  center: CenterState;
  ai_message: string | null;
  ai_message_id?: number;
  history?: ChatMsg[];
  ready_to_complete?: boolean;
}> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/hearing/start-step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step }),
  });
  return r.json();
}

export async function replyHearing(workspaceId: number, step: number, message: string): Promise<{
  artifact: any;
  center: CenterState;
  ai_message: string;
  ai_message_id: number;
  patch: any[];
  ready_to_complete: boolean;
}> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/hearing/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step, message }),
  });
  return r.json();
}

export async function completeStep(workspaceId: number, step: number): Promise<{
  artifact: any;
  center: CenterState;
  next_step: number | null;
  next_artifact: any;
}> {
  const r = await fetch(`${BASE}/api/workspaces/${workspaceId}/hearing/complete-step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step }),
  });
  return r.json();
}

export async function patchCenter(workspaceId: number, step: number, center: CenterState): Promise<void> {
  await fetch(`${BASE}/api/workspaces/${workspaceId}/hearing/center?step=${step}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ center, edited_by_pm: true }),
  });
}
