"use client";

/**
 * T-V3-C-10 / S-010: 通知 Inbox page (Vertical Slice / UI).
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/account/S-010-notifications-inbox.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-010
 * @feature-id F-018
 * @task-ids T-V3-C-10,T-V3-SCR-02
 * @entities E-042
 * @phase Phase 1B
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-10.md):
 *   structural.AC-S1 (data-screen-id="S-010") — root element.
 *   structural.AC-S2 (h1 "通知 Inbox(<n> 未読)") — screens.json[S-010].h1_text.
 *   functional.AC-F1 (GET /api/notifications via typed client)
 *     — `listNotifications()` called on mount.
 *   functional.AC-F2 (POST /api/notifications/{id}/read via typed client)
 *     — `markNotificationRead(id)` on "既読にする" button click.
 *   functional.AC-F3 (POST /api/notifications/read-all via typed client)
 *     — `markAllNotificationsRead()` on "全て既読にする" button click.
 *   functional.AC-F4 (4xx/5xx -> non-technical toast referencing endpoint)
 *     — `toast.error(err.toUserMessage())`, never embeds stack trace.
 *   functional.AC-F5 (unread item -> contributes to unread_count)
 *     — backend (T-V3-B-25). UI surfaces `unread_count` in the h1.
 *   functional.AC-F6 (read-all w/o category -> mark every unread as read)
 *     — payload omits `category` when no tab filter is active.
 */

import * as React from "react";
import { toast } from "sonner";
import {
  AlertTriangle,
  Bell,
  CheckCheck,
  CheckCircle2,
  GitPullRequest,
  Loader2,
  Mic,
  Rocket,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  NotificationsApiError,
  type Notification,
} from "@/api/notifications";

// --------------------------------------------------------------------------
// Local view-model
// --------------------------------------------------------------------------

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; items: Notification[]; unread_count: number }
  | { kind: "error"; endpoint: string; userMessage: string };

type CategoryFilter = "all" | "unread" | "task" | "red_line" | "pr" | "delivery";

const FILTER_TABS: { id: CategoryFilter; label: string }[] = [
  { id: "all", label: "全て" },
  { id: "unread", label: "未読" },
  { id: "task", label: "タスク" },
  { id: "red_line", label: "赤線" },
  { id: "pr", label: "PR" },
  { id: "delivery", label: "納品" },
];

/**
 * Map a notification's `event_type` (or `priority`) to a Lucide icon.
 * Keeps the icon palette aligned with the S-010 mock (no emojis).
 */
function pickIcon(n: Notification): { Icon: LucideIcon; tone: string } {
  const t = (n.event_type ?? "").toLowerCase();
  if (n.priority === "critical" || t.includes("red") || t.includes("alert")) {
    return { Icon: AlertTriangle, tone: "red" };
  }
  if (t.includes("task")) return { Icon: CheckCircle2, tone: "eb" };
  if (t.includes("pr") || t.includes("review")) {
    return { Icon: GitPullRequest, tone: "blue" };
  }
  if (t.includes("swarm") || t.includes("delivery")) {
    return { Icon: Rocket, tone: "eb" };
  }
  if (t.includes("hearing") || t.includes("voice")) {
    return { Icon: Mic, tone: "eb" };
  }
  if (t.includes("budget") || t.includes("cost")) {
    return { Icon: Wallet, tone: "amber" };
  }
  return { Icon: Bell, tone: "slate" };
}

function iconWrapperClass(tone: string): string {
  switch (tone) {
    case "red":
      return "bg-red-100 text-red-600";
    case "eb":
      return "bg-eb-100 text-eb-600";
    case "blue":
      return "bg-blue-50 text-blue-600";
    case "amber":
      return "bg-amber-50 text-amber-600";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

function categoryMatches(n: Notification, filter: CategoryFilter): boolean {
  if (filter === "all") return true;
  if (filter === "unread") return !n.is_read;
  const t = (n.event_type ?? "").toLowerCase();
  switch (filter) {
    case "task":
      return t.includes("task");
    case "red_line":
      return t.includes("red") || t.includes("alert");
    case "pr":
      return t.includes("pr") || t.includes("review");
    case "delivery":
      return t.includes("delivery") || t.includes("deploy");
  }
}

/** Resolve the bearer token in a way safe for SSR / private-mode browsers. */
function readAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("bf.access_token");
  } catch {
    return null;
  }
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function InboxPage() {
  const [state, setState] = React.useState<LoadState>({ kind: "loading" });
  const [filter, setFilter] = React.useState<CategoryFilter>("all");

  const reload = React.useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await listNotifications(
        {},
        { signal, authToken: readAuthToken() },
      );
      setState({
        kind: "ready",
        items: data.items,
        unread_count: data.unread_count,
      });
    } catch (err: unknown) {
      if ((err as { name?: string })?.name === "AbortError") return;
      if (err instanceof NotificationsApiError) {
        const msg = err.toUserMessage();
        setState({ kind: "error", endpoint: err.endpoint, userMessage: msg });
        toast.error(msg);
        return;
      }
      const fallback = "通知の取得に失敗しました (/api/notifications)";
      setState({
        kind: "error",
        endpoint: "/api/notifications",
        userMessage: fallback,
      });
      toast.error(fallback);
    }
  }, []);

  React.useEffect(() => {
    const ctl = new AbortController();
    void reload(ctl.signal);
    return () => ctl.abort();
  }, [reload]);

  const handleMarkOne = React.useCallback(
    async (id: number) => {
      try {
        await markNotificationRead(id, { authToken: readAuthToken() });
        setState((prev) => {
          if (prev.kind !== "ready") return prev;
          const items = prev.items.map((n) =>
            n.id === id
              ? { ...n, is_read: true, read_at: new Date().toISOString() }
              : n,
          );
          const unread_count = items.filter((n) => !n.is_read).length;
          return { ...prev, items, unread_count };
        });
      } catch (err: unknown) {
        if (err instanceof NotificationsApiError) {
          toast.error(err.toUserMessage());
          return;
        }
        toast.error(
          `通知の既読化に失敗しました (/api/notifications/${id}/read)`,
        );
      }
    },
    [],
  );

  const handleMarkAll = React.useCallback(async () => {
    try {
      // AC-F6: no category filter -> mark ALL unread as read.
      await markAllNotificationsRead({}, { authToken: readAuthToken() });
      setState((prev) => {
        if (prev.kind !== "ready") return prev;
        const items = prev.items.map((n) =>
          n.is_read
            ? n
            : { ...n, is_read: true, read_at: new Date().toISOString() },
        );
        return { ...prev, items, unread_count: 0 };
      });
      toast.success("全ての通知を既読にしました");
    } catch (err: unknown) {
      if (err instanceof NotificationsApiError) {
        toast.error(err.toUserMessage());
        return;
      }
      toast.error("一括既読化に失敗しました (/api/notifications/read-all)");
    }
  }, []);

  const items = state.kind === "ready" ? state.items : [];
  const unreadCount = state.kind === "ready" ? state.unread_count : 0;
  const visibleItems = React.useMemo(
    () => items.filter((n) => categoryMatches(n, filter)),
    [items, filter],
  );
  const unreadVisible = visibleItems.filter((n) => !n.is_read);
  const readVisible = visibleItems.filter((n) => n.is_read);

  return (
    <div
      data-screen-id="S-010"
      data-feature-id="F-018"
      data-task-ids="T-V3-C-10,T-V3-SCR-02"
      data-entities="E-042"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <main className="max-w-[900px] mx-auto px-6 py-8">
        <div className="flex items-end justify-between mb-6 gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              通知 Inbox
              <span className="text-sm text-slate-500 font-normal">
                ({unreadCount} 未読)
              </span>
            </h1>
            <p className="text-sm text-slate-600 mt-1">
              タスク・赤線・PR レビュー等のリアルタイム通知
            </p>
          </div>
          <button
            type="button"
            onClick={handleMarkAll}
            disabled={state.kind !== "ready" || unreadCount === 0}
            className="border border-slate-200 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed text-sm h-9 px-4 rounded-md inline-flex items-center gap-2 transition-colors"
            aria-label="全て既読にする"
          >
            <CheckCheck className="w-4 h-4" aria-hidden />
            全て既読にする
          </button>
        </div>

        {/* Filter tabs */}
        <div
          role="tablist"
          aria-label="通知フィルタ"
          className="border-b border-slate-200 flex gap-0 mb-4 overflow-x-auto"
        >
          {FILTER_TABS.map((tab) => {
            const active = tab.id === filter;
            return (
              <button
                key={tab.id}
                role="tab"
                type="button"
                aria-selected={active}
                onClick={() => setFilter(tab.id)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                  active
                    ? "border-eb-500 text-slate-900"
                    : "border-transparent text-slate-500 hover:text-slate-900"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        {state.kind === "loading" && <LoadingBlock />}
        {state.kind === "error" && (
          <ErrorBlock
            endpoint={state.endpoint}
            userMessage={state.userMessage}
            onRetry={() => {
              setState({ kind: "loading" });
              void reload();
            }}
          />
        )}

        {state.kind === "ready" && visibleItems.length === 0 && (
          <EmptyBlock />
        )}

        {state.kind === "ready" && visibleItems.length > 0 && (
          <section aria-label="通知一覧" className="space-y-2">
            {unreadVisible.map((n) => (
              <NotificationRow
                key={n.id}
                notification={n}
                onMarkRead={() => handleMarkOne(n.id)}
              />
            ))}

            {readVisible.length > 0 && (
              <>
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold pt-4 pb-1 px-1">
                  既読
                </div>
                {readVisible.map((n) => (
                  <NotificationRow
                    key={n.id}
                    notification={n}
                    onMarkRead={() => handleMarkOne(n.id)}
                  />
                ))}
              </>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

// --------------------------------------------------------------------------
// Sub-components
// --------------------------------------------------------------------------

function LoadingBlock() {
  return (
    <div
      data-state="loading"
      role="status"
      aria-live="polite"
      className="flex items-center justify-center py-16 text-slate-500 gap-2"
    >
      <Loader2 className="w-5 h-5 animate-spin text-eb-500" aria-hidden />
      <span className="text-sm">通知を読み込み中...</span>
    </div>
  );
}

function EmptyBlock() {
  return (
    <div
      data-state="empty"
      className="flex flex-col items-center justify-center py-16 text-slate-500"
    >
      <Bell className="w-8 h-8 text-slate-300 mb-2" aria-hidden />
      <p className="text-sm">該当する通知はありません</p>
    </div>
  );
}

function ErrorBlock({
  endpoint,
  userMessage,
  onRetry,
}: {
  endpoint: string;
  userMessage: string;
  onRetry: () => void;
}) {
  return (
    <div
      data-state="error"
      role="alert"
      className="bg-white border border-red-200 rounded-lg p-6"
    >
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-full bg-red-50 flex items-center justify-center shrink-0">
          <AlertTriangle className="w-4 h-4 text-red-600" aria-hidden />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold mb-1">通知を取得できません</p>
          <p className="text-xs text-slate-600 mb-3">{userMessage}</p>
          <p className="text-[11px] text-slate-500 font-mono mb-3">
            endpoint: {endpoint}
          </p>
          <button
            type="button"
            onClick={onRetry}
            className="bg-eb-500 hover:bg-eb-600 text-white text-xs font-semibold h-8 px-4 rounded transition-colors"
          >
            再試行
          </button>
        </div>
      </div>
    </div>
  );
}

function NotificationRow({
  notification,
  onMarkRead,
}: {
  notification: Notification;
  onMarkRead: () => void;
}) {
  const { Icon, tone } = pickIcon(notification);
  const wrapperBg =
    !notification.is_read && tone === "red"
      ? "bg-red-50 border-red-200"
      : !notification.is_read
        ? "bg-white border-slate-200"
        : "bg-white border-slate-200 opacity-70";

  return (
    <article
      data-notification-id={notification.id}
      data-unread={!notification.is_read}
      className={`border rounded-lg p-4 flex items-start gap-3 ${wrapperBg}`}
    >
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${iconWrapperClass(tone)}`}
      >
        <Icon className="w-4 h-4" aria-hidden />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2 mb-1">
          <span className="text-sm font-semibold truncate">
            {notification.title}
          </span>
          {notification.created_at && (
            <time
              className="text-[11px] text-slate-500 font-mono whitespace-nowrap"
              dateTime={notification.created_at}
            >
              {notification.created_at}
            </time>
          )}
        </div>
        {notification.body && (
          <p className="text-xs text-slate-600">{notification.body}</p>
        )}
        {!notification.is_read && (
          <div className="flex items-center gap-2 mt-2">
            {notification.link_url && (
              <a
                href={notification.link_url}
                className="bg-eb-500 hover:bg-eb-600 text-white text-xs font-semibold h-7 px-3 rounded inline-flex items-center"
              >
                詳細を開く
              </a>
            )}
            <button
              type="button"
              onClick={onMarkRead}
              className="text-xs text-slate-500 hover:text-slate-900"
            >
              既読にする
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
