/** template-builder API クライアント */
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export interface ChatMsg {
  id: number;
  role: "ai" | "user" | "system";
  content: string;
  metadata?: Record<string, any>;
  created_at?: string;
  step?: number;
}

export interface CenterSection { key: string; label: string; items: string[]; }
export interface CenterState { step: number; sections: CenterSection[]; free_sections?: CenterSection[]; }

export interface BuilderStepState {
  step: number;
  title: string;
  description: string;
  status: "not_started" | "draft" | "confirmed";
  center: CenterState;
  history: ChatMsg[];
}

export interface BuilderState {
  account_id: number;
  phase: "template_builder";
  steps: BuilderStepState[];
  template_config: Record<string, any>;
}

export async function fetchBuilderState(accountId: number): Promise<BuilderState> {
  const r = await fetch(`${BASE}/api/accounts/${accountId}/template-builder/state`);
  return r.json();
}

export async function startBuilderStep(accountId: number, step: number) {
  const r = await fetch(`${BASE}/api/accounts/${accountId}/template-builder/start-step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step }),
  });
  return r.json();
}

export async function replyBuilder(accountId: number, step: number, message: string) {
  const r = await fetch(`${BASE}/api/accounts/${accountId}/template-builder/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step, message }),
  });
  return r.json();
}

export async function completeBuilderStep(accountId: number, step: number) {
  const r = await fetch(`${BASE}/api/accounts/${accountId}/template-builder/complete-step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step }),
  });
  return r.json();
}
