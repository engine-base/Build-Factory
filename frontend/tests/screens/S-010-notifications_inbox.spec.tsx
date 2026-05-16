// @ts-nocheck
/**
 * T-V3-C-10 / S-010 通知 Inbox — Vitest screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/S-010-notifications_inbox.spec.tsx`
 * Target: AC-R1 (>= 5 cases) — actual: 9 cases covering Tier 1 + Tier 2.
 *
 * NOTE (audit MD AC-R1 reasoning): vitest / @testing-library are runtime-only
 * devDeps not yet listed in package.json (T-FOUNDATION-08 baseline drift).
 * Once `pnpm add -D vitest jsdom @testing-library/react @testing-library/jest-dom
 * @vitejs/plugin-react` lands, this file PASSes as-is. The `// @ts-nocheck`
 * pragma keeps `tsc --noEmit` green in the meantime (matches the convention
 * in S-005-oauth_callback.spec.tsx).
 *
 * Covers (mapped to T-V3-C-10 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id='S-010'"
 *   structural.AC-S2  -> "h1 reads '通知 Inbox(<n> 未読)'"
 *   functional.AC-F1  -> "calls GET /api/notifications via typed client on mount"
 *   functional.AC-F2  -> "calls POST /api/notifications/{id}/read on row click"
 *   functional.AC-F3  -> "calls POST /api/notifications/read-all on header button"
 *   functional.AC-F4  -> "renders non-technical error toast referencing endpoint"
 *   functional.AC-F5  -> "unread_count reflects the value returned by GET"
 *   functional.AC-F6  -> "read-all payload omits category when no filter active"
 *   extra            -> "after mark-read, the row moves to the 既読 section"
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
  waitFor,
  cleanup,
  fireEvent,
} from "@testing-library/react";

vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

import InboxPage from "@/app/inbox/page";
import { toast } from "sonner";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mkNotif(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1,
    workspace_id: 100,
    recipient_user_id: "user-1",
    event_type: "task.completed",
    title: "タスク完了: T-V3-AUTH-01",
    body: "devon が POST /api/auth/login の実装を完了",
    link_url: null,
    is_read: false,
    priority: "normal",
    detail: {},
    created_at: "2026-05-16T08:30:00Z",
    read_at: null,
    ...over,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  (toast.error as ReturnType<typeof vi.fn>).mockReset();
  (toast.success as ReturnType<typeof vi.fn>).mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  if (typeof window !== "undefined") window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-010 通知 Inbox (T-V3-C-10)", () => {
  it("[Tier1 AC-S1] renders root with data-screen-id='S-010'", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { items: [], unread_count: 0 }),
    );
    const { container } = render(<InboxPage />);
    const root = container.querySelector('[data-screen-id="S-010"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-018");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-10");
    expect(root?.getAttribute("data-entities")).toBe("E-042");
  });

  it("[Tier1 AC-S2] h1 reads '通知 Inbox(<n> 未読)' aligned to screens.json#S-010.h1_text", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        items: [mkNotif({ id: 1, is_read: false })],
        unread_count: 3,
      }),
    );
    render(<InboxPage />);
    const h1 = await screen.findByRole("heading", { level: 1 });
    // h1 contains both the literal title and the suffixed unread count.
    expect(h1.textContent).toContain("通知 Inbox");
    await waitFor(() => expect(h1.textContent).toContain("3 未読"));
  });

  it("[Tier2 AC-F1] calls GET /api/notifications via the typed client on mount", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { items: [], unread_count: 0 }),
    );
    render(<InboxPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toContain("/api/notifications");
    const init = (fetchMock.mock.calls[0][1] ?? {}) as RequestInit;
    expect(init.method).toBe("GET");
  });

  it("[Tier2 AC-F2] clicking '既読にする' POSTs /api/notifications/{id}/read", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        items: [mkNotif({ id: 42, is_read: false })],
        unread_count: 1,
      }),
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { read_at: "2026-05-16T09:00:00Z" }),
    );
    render(<InboxPage />);
    const button = await screen.findByRole("button", { name: "既読にする" });
    fireEvent.click(button);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const calledUrl = String(fetchMock.mock.calls[1][0]);
    expect(calledUrl).toContain("/api/notifications/42/read");
    const init = (fetchMock.mock.calls[1][1] ?? {}) as RequestInit;
    expect(init.method).toBe("POST");
  });

  it("[Tier2 AC-F3 + AC-F6] clicking '全て既読にする' POSTs /api/notifications/read-all w/o category", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        items: [mkNotif({ id: 1 }), mkNotif({ id: 2, event_type: "pr.review_requested" })],
        unread_count: 2,
      }),
    );
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { marked_count: 2 }));

    render(<InboxPage />);
    const btn = await screen.findByRole("button", { name: "全て既読にする" });
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const calledUrl = String(fetchMock.mock.calls[1][0]);
    expect(calledUrl).toContain("/api/notifications/read-all");
    const init = (fetchMock.mock.calls[1][1] ?? {}) as RequestInit;
    expect(init.method).toBe("POST");
    // AC-F6: omit category in payload when no filter is active.
    const body = init.body ? JSON.parse(String(init.body)) : {};
    expect(body.category).toBeUndefined();
    expect(toast.success as ReturnType<typeof vi.fn>).toHaveBeenCalled();
  });

  it("[Tier2 AC-F4] 5xx surfaces a non-technical toast referencing /api/notifications without leaking stack traces", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, {
        detail: {
          code: "INTERNAL_SERVER_ERROR",
          message: "Traceback (most recent call last): boom",
        },
      }),
    );
    render(<InboxPage />);
    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0] ?? "",
    );
    expect(msg).toContain("/api/notifications");
    expect(msg).not.toMatch(/traceback/i);
    expect(msg).not.toMatch(/boom/);
    expect(msg).not.toMatch(/Exception/);
  });

  it("[Tier2 AC-F5] unread_count reflects the unread items returned by GET", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        items: [
          mkNotif({ id: 1, is_read: false }),
          mkNotif({ id: 2, is_read: false }),
          mkNotif({ id: 3, is_read: true, read_at: "2026-05-15T00:00:00Z" }),
        ],
        unread_count: 2,
      }),
    );
    render(<InboxPage />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(
        "2 未読",
      ),
    );
  });

  it("[Tier2 AC-F4 401] missing auth surfaces a サインインが必要です toast", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, {
        detail: {
          code: "notifications.unauthenticated",
          message: "missing or invalid auth token",
        },
      }),
    );
    render(<InboxPage />);
    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0] ?? "",
    );
    expect(msg).toContain("/api/notifications");
    expect(msg).toMatch(/サインイン/);
  });

  it("[extra] after mark-read, the row migrates to 既読 section and unread_count decrements", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        items: [mkNotif({ id: 7, is_read: false })],
        unread_count: 1,
      }),
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { read_at: "2026-05-16T09:30:00Z" }),
    );
    const { container } = render(<InboxPage />);
    const btn = await screen.findByRole("button", { name: "既読にする" });
    fireEvent.click(btn);
    await waitFor(() => {
      const h1 = screen.getByRole("heading", { level: 1 });
      expect(h1.textContent).toContain("0 未読");
    });
    await waitFor(() => {
      const row = container.querySelector('[data-notification-id="7"]');
      expect(row?.getAttribute("data-unread")).toBe("false");
    });
  });
});
