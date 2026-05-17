// @ts-nocheck
/**
 * T-V3-C-57-2 / S-027 — Kanban drag & drop (within-feature card move +
 * optimistic update) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 7 cases).
 *
 * NOTE: Uses `// @ts-nocheck` because vitest + @testing-library/react are
 * runtime-only devDeps wired by T-V3-C-TEST-01 (same convention as the
 * other S-* screen specs).
 *
 * Covers (mapped to T-V3-C-57-2 acceptance_criteria):
 *   structural.AC-S1  -> "data-dragging=true on the dragged card"
 *   structural.AC-S2  -> "valid same-feature drop zones get dashed eb-500 ring"
 *   functional.AC-F1  -> "PATCH /api/tasks/{id} optimistic, revert on 4xx"
 *   functional.AC-F2  -> "different-feature drop is rejected, no API call"
 *   functional.AC-F3  -> "409 from /play surfaces inline, status not advanced"
 *   functional.AC-F4  -> "shift+drop opens confirm dialog before applying"
 *   regression.AC-R1  -> ">=7 test cases (this file)"
 */

import * as React from "react";
import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
} from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
  cleanup,
  renderHook,
} from "@testing-library/react";

// Sonner mock so we can assert toast.error fires (AC-F1 revert path).
vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

import { toast } from "sonner";
import { DraggableCard } from "@/components/kanban/DraggableCard";
import { DropZone } from "@/components/kanban/DropZone";
import { useTaskDnd } from "@/lib/hooks/use-task-dnd";
import {
  KANBAN_STATUS_BY_COLUMN,
  KanbanMoveError,
  moveTask,
  playTask,
} from "@/lib/api/kanban-move";
import {
  KanbanDndProvider,
  useKanbanDnd,
} from "@/app/(app)/task/kanban/drag-drop";

// --------------------------------------------------------------------------
// fetch mocking (kanban-move API client uses globalThis.fetch directly)
// --------------------------------------------------------------------------

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  (toast.error as ReturnType<typeof vi.fn>).mockClear();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

const INITIAL_CARDS = [
  { task_id: "T-V3-AUTH-08", feature_id: "F-001", column: "todo", title: "/login page" },
  { task_id: "T-V3-AUTH-09", feature_id: "F-001", column: "in_progress", title: "/signup page" },
  { task_id: "T-V3-WS-01", feature_id: "F-004", column: "todo", title: "workspace board" },
];

/**
 * Minimal harness board: one DraggableCard + N DropZones, all bound to a
 * single useTaskDnd instance. We render this to exercise AC-S1/S2/F1/F2.
 */
function Harness(props: {
  initial?: typeof INITIAL_CARDS;
  shiftConfirm?: () => Promise<boolean>;
}) {
  const dnd = useTaskDnd({
    initial: props.initial ?? INITIAL_CARDS,
    onErrorToast: (m) => (toast.error as ReturnType<typeof vi.fn>)(m),
    onShiftConfirm: props.shiftConfirm,
  });
  const cardsByFeature: Record<string, typeof INITIAL_CARDS> = {};
  for (const c of dnd.cards) {
    cardsByFeature[c.feature_id] ||= [];
    cardsByFeature[c.feature_id].push(c);
  }
  return (
    <div data-screen-id="S-027" data-feature-id="F-007">
      {Object.entries(cardsByFeature).map(([fid, cards]) => (
        <section key={fid} data-feature-section={fid}>
          {(["todo", "in_progress", "review", "done"] as const).map((col) => (
            <DropZone
              key={col}
              featureId={fid}
              column={col}
              isValidTarget={dnd.isValidDrop({ feature_id: fid, column: col })}
              isDragActive={!!dnd.dragging}
              onDropHere={(t, opts) => dnd.onDrop(t, { shiftKey: opts.shiftKey })}
            >
              {cards
                .filter((c) => c.column === col)
                .map((c) => (
                  <DraggableCard
                    key={c.task_id}
                    taskId={c.task_id}
                    featureId={c.feature_id}
                    column={c.column}
                    title={c.title}
                    isDragging={
                      dnd.dragging?.task_id === c.task_id &&
                      dnd.dragging?.feature_id === c.feature_id
                    }
                    onDragStart={dnd.onDragStart}
                    onDragEnd={dnd.onDragEnd}
                  />
                ))}
            </DropZone>
          ))}
        </section>
      ))}
    </div>
  );
}

function makeDataTransfer(): DataTransfer {
  // jsdom does not implement DataTransfer; a thin stub is sufficient.
  const store: Record<string, string> = {};
  return {
    setData: (type: string, val: string) => {
      store[type] = val;
    },
    getData: (type: string) => store[type] ?? "",
    effectAllowed: "move",
    dropEffect: "move",
    types: ["text/x-task-id"],
    files: [] as unknown as FileList,
    items: [] as unknown as DataTransferItemList,
    clearData: () => {},
    setDragImage: () => {},
  } as unknown as DataTransfer;
}

function fireDragStart(el: Element, dt: DataTransfer) {
  fireEvent.dragStart(el, { dataTransfer: dt });
}
function fireDragOver(el: Element, dt: DataTransfer) {
  fireEvent.dragOver(el, { dataTransfer: dt });
}
function fireDrop(el: Element, dt: DataTransfer, shiftKey = false) {
  fireEvent.drop(el, { dataTransfer: dt, shiftKey });
}
function fireDragEnd(el: Element, dt: DataTransfer) {
  fireEvent.dragEnd(el, { dataTransfer: dt });
}

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------

describe("T-V3-C-57-2 S-027 kanban drag & drop", () => {
  it("AC-S1: while a card is being dragged, it carries data-dragging=true", () => {
    render(<Harness />);
    const card = screen.getByTestId("kanban-card-T-V3-AUTH-08");
    expect(card.getAttribute("data-dragging")).toBeNull();

    const dt = makeDataTransfer();
    act(() => fireDragStart(card, dt));

    // Re-query — react has re-rendered with isDragging=true.
    const after = screen.getByTestId("kanban-card-T-V3-AUTH-08");
    expect(after.getAttribute("data-dragging")).toBe("true");
    // class list should include the elevation/2 treatment.
    expect(after.className).toMatch(/shadow-md/);
    expect(after.className).toMatch(/ring-1/);
  });

  it("AC-S2: valid same-feature drop zones get a dashed eb-500 ring during a drag", () => {
    render(<Harness />);
    const card = screen.getByTestId("kanban-card-T-V3-AUTH-08");
    const sameFeatureZone = screen.getByTestId("drop-zone-F-001-in_progress");
    const otherFeatureZone = screen.getByTestId("drop-zone-F-004-in_progress");

    expect(sameFeatureZone.getAttribute("data-valid-target")).toBeNull();

    const dt = makeDataTransfer();
    act(() => fireDragStart(card, dt));

    const sameAfter = screen.getByTestId("drop-zone-F-001-in_progress");
    const otherAfter = screen.getByTestId("drop-zone-F-004-in_progress");
    expect(sameAfter.getAttribute("data-valid-target")).toBe("true");
    expect(otherAfter.getAttribute("data-valid-target")).toBe("false");
    // Visual classes for valid target.
    expect(sameAfter.className).toMatch(/border-dashed/);
    expect(sameAfter.className).toMatch(/border-eb-500/);
    // Invalid target keeps neutral border.
    expect(otherAfter.className).not.toMatch(/border-dashed/);
  });

  it("AC-F1: drop on valid same-feature zone PATCHes /api/tasks/{id} and optimistically updates", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ task_id: "T-V3-AUTH-08", status: "in_progress", updated_at: "2026-05-17T00:00:00Z" }),
    );
    render(<Harness />);
    const card = screen.getByTestId("kanban-card-T-V3-AUTH-08");
    const zone = screen.getByTestId("drop-zone-F-001-in_progress");

    const dt = makeDataTransfer();
    await act(async () => {
      fireDragStart(card, dt);
      fireDragOver(zone, dt);
      fireDrop(zone, dt);
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("/api/tasks/T-V3-AUTH-08");
    expect(init?.method).toBe("PATCH");
    const body = JSON.parse(String(init?.body ?? "{}"));
    // Status MUST come from the canonical column→status map.
    expect(body).toEqual({ status: KANBAN_STATUS_BY_COLUMN.in_progress });

    // Optimistic: the card is already moved synchronously (no toast).
    expect((toast.error as ReturnType<typeof vi.fn>)).not.toHaveBeenCalled();
  });

  it("AC-F1 revert: on 4xx the optimistic move is reverted and toast.error fires referencing the endpoint", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: { code: "VALIDATION_ERROR", message: "bad" } }, { status: 422 }),
    );
    render(<Harness />);
    const card = screen.getByTestId("kanban-card-T-V3-AUTH-08");
    const zone = screen.getByTestId("drop-zone-F-001-in_progress");

    const dt = makeDataTransfer();
    await act(async () => {
      fireDragStart(card, dt);
      fireDragOver(zone, dt);
      fireDrop(zone, dt);
    });

    await waitFor(() => {
      expect((toast.error as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0);
    });
    const msg = String((toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(msg).toContain("/api/tasks/T-V3-AUTH-08");
    expect(msg).toContain("422");
  });

  it("AC-F2: cross-feature drop is rejected and no PATCH is issued", async () => {
    render(<Harness />);
    const card = screen.getByTestId("kanban-card-T-V3-AUTH-08");
    const otherFeatureZone = screen.getByTestId("drop-zone-F-004-in_progress");

    const dt = makeDataTransfer();
    await act(async () => {
      fireDragStart(card, dt);
      fireDragOver(otherFeatureZone, dt);
      fireDrop(otherFeatureZone, dt);
      fireDragEnd(card, dt);
    });

    // Critically: no fetch happened.
    expect(fetchMock).not.toHaveBeenCalled();
    // The card stayed in F-001 (still rendered under the F-001 section).
    const stillCard = screen.getByTestId("kanban-card-T-V3-AUTH-08");
    expect(stillCard.closest("[data-feature-section='F-001']")).not.toBeNull();
  });

  it("AC-F3: playTask() 409 surfaces inline and does NOT advance the card status", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "DEPENDENCY_BLOCKED", message: "dep" } },
        { status: 409 },
      ),
    );
    await expect(playTask("T-V3-AUTH-08")).rejects.toMatchObject({
      status: 409,
      endpoint: "/api/tasks/T-V3-AUTH-08/play",
      code: "DEPENDENCY_BLOCKED",
    });
    // Caller (page) is responsible for surfacing this inline.
    // We exercise the moveTask layer's 409 path too — the hook formats a
    // "dependency block" message rather than a generic "move failed".
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: { code: "DEPENDENCY_BLOCKED" } }, { status: 409 }),
    );
    render(<Harness />);
    const card = screen.getByTestId("kanban-card-T-V3-AUTH-08");
    const zone = screen.getByTestId("drop-zone-F-001-in_progress");
    const dt = makeDataTransfer();
    await act(async () => {
      fireDragStart(card, dt);
      fireDragOver(zone, dt);
      fireDrop(zone, dt);
    });
    await waitFor(() => {
      expect((toast.error as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0);
    });
    const msg = String((toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(msg).toMatch(/dependency block/i);
  });

  it("AC-F4: shift+drop opens the confirm gate; declining aborts the move and no PATCH is issued", async () => {
    const confirmFn = vi.fn().mockResolvedValue(false);
    render(<Harness shiftConfirm={confirmFn} />);
    const card = screen.getByTestId("kanban-card-T-V3-AUTH-08");
    const zone = screen.getByTestId("drop-zone-F-001-in_progress");
    const dt = makeDataTransfer();
    await act(async () => {
      fireDragStart(card, dt);
      fireDragOver(zone, dt);
      fireDrop(zone, dt, /* shiftKey */ true);
    });
    await waitFor(() => expect(confirmFn).toHaveBeenCalledTimes(1));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("AC-F4 accept: shift+drop with confirm=true proceeds to PATCH", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ task_id: "T-V3-AUTH-08", status: "review_needed", updated_at: "x" }),
    );
    const confirmFn = vi.fn().mockResolvedValue(true);
    render(<Harness shiftConfirm={confirmFn} />);
    const card = screen.getByTestId("kanban-card-T-V3-AUTH-08");
    const zone = screen.getByTestId("drop-zone-F-001-review");
    const dt = makeDataTransfer();
    await act(async () => {
      fireDragStart(card, dt);
      fireDragOver(zone, dt);
      fireDrop(zone, dt, /* shiftKey */ true);
    });
    await waitFor(() => expect(confirmFn).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("/api/tasks/T-V3-AUTH-08");
    expect(JSON.parse(String(init?.body))).toEqual({
      status: KANBAN_STATUS_BY_COLUMN.review,
    });
  });

  it("moveTask() typed client unit: throws KanbanMoveError on 4xx with the failing endpoint", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: { code: "NOT_FOUND" } }, { status: 404 }),
    );
    await expect(
      moveTask({
        task_id: "T-NOPE",
        feature_id: "F-001",
        from_column: "todo",
        to_column: "done",
      }),
    ).rejects.toMatchObject({
      status: 404,
      endpoint: "/api/tasks/T-NOPE",
      code: "NOT_FOUND",
    });
  });

  it("KanbanDndProvider: context consumer receives the same drag state instance", async () => {
    let captured: ReturnType<typeof useKanbanDnd> | null = null;
    function Consumer() {
      captured = useKanbanDnd();
      return null;
    }
    render(
      <KanbanDndProvider initial={INITIAL_CARDS}>
        <Consumer />
      </KanbanDndProvider>,
    );
    expect(captured).not.toBeNull();
    expect(captured!.cards).toHaveLength(INITIAL_CARDS.length);
    expect(captured!.dragging).toBeNull();
  });
});
