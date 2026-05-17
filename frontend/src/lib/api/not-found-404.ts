/**
 * T-V3-C-53 / S-044 — typed API client for the 404 Not Found page.
 *
 * S-044 is a static system page (mock `bf-related-apis` = "N/A (static page)"),
 * so there is *no* workspace-scoped data fetch. This module nonetheless exists
 * so the Vertical Slice retains the canonical four-file shape mandated by
 * `tickets-group-c-ui-part2.json#T-V3-C-53.files_changed`:
 *
 *   frontend/src/lib/api/not-found-404.ts          ← this file (canonical)
 *   frontend/lib/api/not-found-404.ts              ← re-export alias
 *
 * Public surface:
 *   - `NOT_FOUND_KNOWN_ROUTES` — the curated catalogue of routes suggested to a
 *     visitor who has landed on a 404. Keep in sync with the navigation
 *     skeleton in `frontend/src/app/layout.tsx`. Acts as a typed contract so
 *     unit tests can assert the suggestion list without scraping the DOM.
 *   - `getKnownRoutes()` — pure helper returning the catalogue. Wrapping the
 *     constant in a function lets the hook layer swap to a backend-driven
 *     manifest later (e.g. workspace-specific routes) without touching the
 *     page component.
 *   - `NotFoundApiError` — uniform error wrapper, present to match the
 *     four-file pattern used by sibling tasks (T-V3-C-50 .. T-V3-C-56) so the
 *     hook can surface a non-technical toast if a future GET call is added.
 */

export interface KnownRoute {
  /** Path the visitor will be sent to when the suggestion is clicked. */
  readonly href: string;
  /** User-visible Japanese label rendered inside the suggestion list. */
  readonly label: string;
  /**
   * Short description rendered as supporting text in the suggestion card.
   * Helps the visitor confirm the route before clicking.
   */
  readonly description: string;
  /**
   * Lucide-react icon name (PascalCase) rendered next to the label.
   * The page imports the icon component lazily; storing the name as a string
   * keeps this module dependency-free for non-UI consumers (tests, etc.).
   */
  readonly icon: "Home" | "LayoutDashboard" | "FolderKanban" | "Search" | "HelpCircle";
}

/**
 * Curated catalogue of routes suggested to a 404 visitor. Order is
 * significant — the first entry is the primary CTA in the page header.
 *
 * The mock (S-044) renders just two CTAs ("前のページへ戻る" and
 * "ダッシュボードへ"); the additional entries fulfil the user-facing
 * requirement that S-044 also exposes a "known routes" suggestion list.
 */
export const NOT_FOUND_KNOWN_ROUTES: readonly KnownRoute[] = Object.freeze([
  Object.freeze({
    href: "/",
    label: "ダッシュボード",
    description: "今月の売上 / パイプライン / タスクサマリー",
    icon: "LayoutDashboard",
  }),
  Object.freeze({
    href: "/workspaces",
    label: "ワークスペース一覧",
    description: "進行中の案件と AI 社員の稼働状況",
    icon: "FolderKanban",
  }),
  Object.freeze({
    href: "/tasks",
    label: "タスク",
    description: "Kanban — Todo / In Progress / Review / Done",
    icon: "Home",
  }),
  Object.freeze({
    href: "/audit-logs",
    label: "監査ログ",
    description: "誰が・いつ・何を変更したかの記録",
    icon: "HelpCircle",
  }),
]) as readonly KnownRoute[];

/** Returns the curated 404-page suggestion list (pure / side-effect free). */
export function getKnownRoutes(): readonly KnownRoute[] {
  return NOT_FOUND_KNOWN_ROUTES;
}

/**
 * Lightweight error wrapper kept for parity with the sibling Vertical Slice
 * API clients (T-V3-C-50 .. T-V3-C-56). Unused by the current static-page
 * implementation but exported so the hook layer can throw a uniformly typed
 * error if a backend call is added in the future.
 */
export class NotFoundApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly endpoint: string,
  ) {
    super(message);
    this.name = "NotFoundApiError";
  }

  /** Renders a user-safe, non-technical message for toast display. */
  toUserMessage(): string {
    return `読み込みに失敗しました (${this.endpoint})`;
  }
}
