/**
 * T-V3-C-57-2 / S-027 — Kanban move typed API client.
 *
 * Canonical implementation. The ticket-mandated path
 * `frontend/lib/api/kanban-move.ts` re-exports this module so both the
 * `work_package_boundary.editable` paths and the canonical `src/` location
 * resolve to the same TypeScript surface.
 *
 * Endpoints (per docs/functional-breakdown/2026-05-16_v3/features.json#F-007):
 *   - PATCH /api/tasks/{task_id}              — within-feature status change
 *   - POST  /api/tasks/{task_id}/play         — kick off execution (409 if blocked)
 *
 * Auth: callers are responsible for cookie / Bearer attachment (handled by
 * the upstream typed fetch helper in `frontend/src/lib/api.ts`).
 */

export type KanbanColumn = "todo" | "in_progress" | "review" | "done";

/**
 * Maps Kanban column ids (the four ticket-mandated columns from
 * CLAUDE.md §5.5) to the backend Task.status enum values.
 */
export const KANBAN_STATUS_BY_COLUMN: Record<KanbanColumn, string> = {
  todo: "pending",
  in_progress: "in_progress",
  review: "review_needed",
  done: "completed",
};

export type MoveTaskRequest = {
  task_id: string;
  feature_id: string;
  from_column: KanbanColumn;
  to_column: KanbanColumn;
};

export type MoveTaskResponse = {
  task_id: string;
  status: string;
  updated_at: string;
};

export class KanbanMoveError extends Error {
  status: number;
  endpoint: string;
  code?: string;
  constructor(message: string, status: number, endpoint: string, code?: string) {
    super(message);
    this.name = "KanbanMoveError";
    this.status = status;
    this.endpoint = endpoint;
    this.code = code;
  }
}

async function parseDetail(res: Response): Promise<{ code?: string; message?: string }> {
  try {
    const body = (await res.json()) as { detail?: { code?: string; message?: string } };
    return body.detail ?? {};
  } catch {
    return {};
  }
}

/**
 * AC-F1 / AC-F2 — PATCH /api/tasks/{id} with the new status.
 * Returns the canonical `MoveTaskResponse` on 2xx; throws
 * `KanbanMoveError` on any 4xx/5xx (caller reverts optimistic state and
 * shows a toast).
 */
export async function moveTask(req: MoveTaskRequest): Promise<MoveTaskResponse> {
  const endpoint = `/api/tasks/${encodeURIComponent(req.task_id)}`;
  const newStatus = KANBAN_STATUS_BY_COLUMN[req.to_column];
  const res = await fetch(endpoint, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: newStatus }),
  });
  if (!res.ok) {
    const detail = await parseDetail(res);
    throw new KanbanMoveError(
      detail.message ?? `kanban move failed (${endpoint})`,
      res.status,
      endpoint,
      detail.code,
    );
  }
  return (await res.json()) as MoveTaskResponse;
}

/**
 * AC-F3 — POST /api/tasks/{id}/play. The backend returns 409 when the
 * task has unsatisfied dependencies; the hook surfaces this inline and
 * does NOT advance the card status.
 */
export async function playTask(taskId: string): Promise<MoveTaskResponse> {
  const endpoint = `/api/tasks/${encodeURIComponent(taskId)}/play`;
  const res = await fetch(endpoint, { method: "POST" });
  if (!res.ok) {
    const detail = await parseDetail(res);
    throw new KanbanMoveError(
      detail.message ?? `kanban play failed (${endpoint})`,
      res.status,
      endpoint,
      detail.code,
    );
  }
  return (await res.json()) as MoveTaskResponse;
}
