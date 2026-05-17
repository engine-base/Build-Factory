/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-57-3 / S-027 — タスク Kanban filter & search screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the new screen test harness; they are
 *       installed by the Wave 2 frontend test setup ticket (T-V3-C-TEST-01).
 *       Once installed, tsc strict mode picks them up automatically. Mirrors
 *       the pattern used by S-008 / S-033 / S-048 specs in this directory.
 *
 * Covers (mapped to T-V3-C-57-3 acceptance_criteria):
 *   structural.AC-S1 -> "sticky FilterBar above accordion with 4 inputs"
 *   structural.AC-S2 -> "active-filter badge count + 'Clear filters' button"
 *   functional.AC-F1 -> "250ms debounce + URL search params mirror"
 *   functional.AC-F2 -> "empty state per accordion section + Reset CTA"
 *   functional.AC-F3 -> "truncate text search at 200 chars / no API beyond 200"
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
  cleanup,
  act,
  renderHook,
  waitFor,
} from "@testing-library/react";

import TaskKanbanPage from "@/app/(app)/task/kanban/page";
import {
  KanbanFilterBar,
  EMPTY_KANBAN_FILTER,
  KANBAN_SEARCH_MAX_LEN,
  KANBAN_FILTER_DEBOUNCE_MS,
  countActiveFilters,
  filterStateFromSearchParams,
  filterStateToSearchParams,
  truncateQuery,
} from "@/app/(app)/task/kanban/filter";
import { useKanbanFilter } from "@/app/(app)/task/kanban/use-kanban-filter";

// --- shared fixtures ------------------------------------------------------

const FEATURE_OPTIONS = [
  { value: "F-001", label: "認証" },
  { value: "F-004", label: "メンバー" },
  { value: "F-007", label: "タスク" },
];
const ASSIGNEE_OPTIONS = [
  { value: "devon", label: "devon" },
  { value: "quinn", label: "quinn" },
];

beforeEach(() => {
  try {
    window.history.replaceState(null, "", "/task/kanban");
  } catch {
    /* jsdom only */
  }
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

// =========================================================================
//  Page-level rendering (AC-S1, AC-S2 — full integration through hook)
// =========================================================================

describe("T-V3-C-57-3 S-027 タスク Kanban filter & search — page", () => {
  it("AC-S1: page mounts with data-screen-id='S-027' + sticky FilterBar 4 inputs", () => {
    render(<TaskKanbanPage />);
    const root = document.querySelector("[data-screen-id='S-027']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-007");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-57-3");

    // The 4 input surfaces (text query + 3 multi-selects) must exist.
    expect(screen.getByTestId("kanban-filter-bar")).toBeTruthy();
    expect(screen.getByTestId("kanban-filter-query")).toBeTruthy();
    expect(screen.getByTestId("kanban-filter-feature")).toBeTruthy();
    expect(screen.getByTestId("kanban-filter-status")).toBeTruthy();
    expect(screen.getByTestId("kanban-filter-assignee")).toBeTruthy();
  });

  it("AC-S2: at least one active filter surfaces badge + 'Clear filters' button", () => {
    render(<TaskKanbanPage />);

    // No filters active → no badge / no clear button.
    expect(document.querySelector("[data-testid='kanban-filter-active-count']")).toBeNull();
    expect(document.querySelector("[data-testid='kanban-filter-clear']")).toBeNull();

    // Type a query → badge appears with count == 1.
    const input = screen.getByTestId("kanban-filter-query");
    fireEvent.change(input, { target: { value: "auth" } });

    const badge = screen.getByTestId("kanban-filter-active-count");
    expect(badge).toBeTruthy();
    expect(badge.textContent || "").toContain("1");
    expect(screen.getByTestId("kanban-filter-clear")).toBeTruthy();

    // Click Clear filters → badge gone.
    fireEvent.click(screen.getByTestId("kanban-filter-clear"));
    expect(document.querySelector("[data-testid='kanban-filter-active-count']")).toBeNull();
  });
});

// =========================================================================
//  FilterBar pure component (AC-S1, AC-S2, AC-F3)
// =========================================================================

describe("T-V3-C-57-3 KanbanFilterBar — controlled component", () => {
  it("AC-F3: input maxLength + truncateQuery cap at KANBAN_SEARCH_MAX_LEN", () => {
    const onChange = vi.fn();
    render(
      <KanbanFilterBar
        featureOptions={FEATURE_OPTIONS}
        assigneeOptions={ASSIGNEE_OPTIONS}
        value={EMPTY_KANBAN_FILTER}
        onChange={onChange}
      />,
    );
    const input = screen.getByTestId("kanban-filter-query") as HTMLInputElement;
    expect(input.maxLength).toBe(KANBAN_SEARCH_MAX_LEN);

    // Simulate an attempt to set a value longer than the cap: the onChange
    // payload must be truncated to KANBAN_SEARCH_MAX_LEN.
    const tooLong = "a".repeat(KANBAN_SEARCH_MAX_LEN + 50);
    fireEvent.change(input, { target: { value: tooLong } });
    const last = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(last.query.length).toBe(KANBAN_SEARCH_MAX_LEN);

    // And the pure helper behaves the same.
    expect(truncateQuery(tooLong).length).toBe(KANBAN_SEARCH_MAX_LEN);
    expect(truncateQuery("ok").length).toBe(2);
  });

  it("AC-S2: countActiveFilters counts distinct populated inputs", () => {
    expect(countActiveFilters(EMPTY_KANBAN_FILTER)).toBe(0);
    expect(
      countActiveFilters({
        features: ["F-001"],
        statuses: [],
        assignees: [],
        query: "",
      }),
    ).toBe(1);
    expect(
      countActiveFilters({
        features: ["F-001"],
        statuses: ["todo"],
        assignees: ["devon"],
        query: "auth",
      }),
    ).toBe(4);
    // Whitespace-only query does not count.
    expect(
      countActiveFilters({
        features: [],
        statuses: [],
        assignees: [],
        query: "   ",
      }),
    ).toBe(0);
  });

  it("AC-S1: feature chip toggle calls onChange with toggled featureId", () => {
    const onChange = vi.fn();
    render(
      <KanbanFilterBar
        featureOptions={FEATURE_OPTIONS}
        assigneeOptions={ASSIGNEE_OPTIONS}
        value={EMPTY_KANBAN_FILTER}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("kanban-filter-feature-F-001"));
    expect(onChange).toHaveBeenCalledWith({
      ...EMPTY_KANBAN_FILTER,
      features: ["F-001"],
    });
  });
});

// =========================================================================
//  Hook (AC-F1, AC-F3)
// =========================================================================

describe("T-V3-C-57-3 useKanbanFilter — debounce + URL sync", () => {
  it("AC-F1: debouncedState updates only after KANBAN_FILTER_DEBOUNCE_MS", () => {
    const { result } = renderHook(() =>
      useKanbanFilter({ syncUrl: false }),
    );
    act(() => {
      result.current.setQuery("a");
    });
    // Same tick: state changed, debouncedState NOT yet.
    expect(result.current.state.query).toBe("a");
    expect(result.current.debouncedState.query).toBe("");

    // Advance just under the debounce window — still no commit.
    act(() => {
      vi.advanceTimersByTime(KANBAN_FILTER_DEBOUNCE_MS - 1);
    });
    expect(result.current.debouncedState.query).toBe("");

    // Cross the threshold → commit.
    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(result.current.debouncedState.query).toBe("a");
  });

  it("AC-F1: URL search params mirror committed state (replaceState)", () => {
    const { result } = renderHook(() => useKanbanFilter({ syncUrl: true }));
    act(() => {
      result.current.toggleFeature("F-007");
      result.current.toggleStatus("todo");
      result.current.setQuery("kanban");
    });
    act(() => {
      vi.advanceTimersByTime(KANBAN_FILTER_DEBOUNCE_MS + 5);
    });
    const sp = new URLSearchParams(window.location.search);
    expect(sp.get("feature")).toBe("F-007");
    expect(sp.get("status")).toBe("todo");
    expect(sp.get("q")).toBe("kanban");
  });

  it("AC-F3: setQuery truncates to KANBAN_SEARCH_MAX_LEN; debounce never fires with longer payload", () => {
    const { result } = renderHook(() => useKanbanFilter({ syncUrl: false }));
    act(() => {
      result.current.setQuery("x".repeat(KANBAN_SEARCH_MAX_LEN + 100));
    });
    expect(result.current.state.query.length).toBe(KANBAN_SEARCH_MAX_LEN);
    act(() => {
      vi.advanceTimersByTime(KANBAN_FILTER_DEBOUNCE_MS + 5);
    });
    expect(result.current.debouncedState.query.length).toBe(
      KANBAN_SEARCH_MAX_LEN,
    );
  });
});

// =========================================================================
//  URL serde round-trip + Empty state (AC-F1, AC-F2)
// =========================================================================

describe("T-V3-C-57-3 URL serde + empty state", () => {
  it("AC-F1: filterStateToSearchParams + filterStateFromSearchParams round-trip", () => {
    const original = {
      features: ["F-001", "F-007"],
      statuses: ["todo", "review"],
      assignees: ["devon"],
      query: "rls migration",
    };
    const sp = filterStateToSearchParams(original);
    const back = filterStateFromSearchParams(sp);
    expect(back.features).toEqual(original.features);
    expect(back.statuses).toEqual(original.statuses);
    expect(back.assignees).toEqual(original.assignees);
    expect(back.query).toBe(original.query);
  });

  it("AC-F1: filterStateFromSearchParams drops unknown status values", () => {
    const sp = new URLSearchParams("status=todo,bogus,review");
    const back = filterStateFromSearchParams(sp);
    expect(back.statuses).toEqual(["todo", "review"]);
  });

  it("AC-F2: empty state surfaces + Reset CTA clears filter via real page", async () => {
    render(<TaskKanbanPage />);
    // Narrow to a value that matches no feature label / id.
    fireEvent.change(screen.getByTestId("kanban-filter-query"), {
      target: { value: "no-such-feature-zzz" },
    });
    await waitFor(() => {
      expect(screen.getByTestId("kanban-filter-empty")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("kanban-filter-reset"));
    // After reset, empty state vanishes (placeholder list is non-empty).
    await waitFor(() => {
      expect(
        document.querySelector("[data-testid='kanban-filter-empty']"),
      ).toBeNull();
    });
  });
});
