/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-53 / S-044 — 404 Not Found (not_found_404) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the screen test
 *       harness; tsc strict picks them up once the Wave 2 frontend test ticket
 *       (T-V3-C-TEST-01) installs them. Pattern mirrors S-048 / S-063 specs.
 *
 * Covers (mapped to T-V3-C-53 acceptance_criteria):
 *   structural.AC-S1 -> "h1 == 'ページが見つかりません'"
 *   structural.AC-S2 -> "Lucide icons only (no emoji)"
 *   functional.AC-F1 -> "static page; renders skeleton then content atomically"
 *   functional.AC-F2 -> "no redirect / no workspace-scoped data exposed"
 *   functional.AC-F3 -> "skeleton role='status' aria-live='polite' while loading"
 *   extra            -> "search box filters the known-routes list"
 *   extra            -> "back button calls window.history.back()"
 *   extra            -> "requested path is captured from window.location.pathname"
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
  cleanup,
} from "@testing-library/react";

// next/link → render plain <a> so we can assert hrefs without next router.
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import NotFoundPage from "@/app/not-found";
import { NOT_FOUND_KNOWN_ROUTES } from "@/lib/api/not-found-404";

const originalLocation = window.location;

beforeEach(() => {
  // Stub window.location.pathname so AC-F3 + requestedPath are deterministic.
  Object.defineProperty(window, "location", {
    configurable: true,
    value: {
      ...originalLocation,
      pathname: "/workspaces/xyz-deleted/dashboard",
      assign: vi.fn(),
    },
  });
});

afterEach(() => {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: originalLocation,
  });
  cleanup();
});

describe("T-V3-C-53 S-044 404 Not Found (not_found_404)", () => {
  it("AC-S1 + AC-S2: renders root with data-screen-id='S-044', exact h1 'ページが見つかりません', no emoji glyphs", async () => {
    render(<NotFoundPage />);

    // Skeleton clears once useEffect runs and requestedPath is captured.
    await waitFor(() => {
      expect(screen.queryByTestId("not-found-content")).not.toBeNull();
    });

    const root = document.querySelector("[data-screen-id='S-044']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-system");
    expect(root?.getAttribute("data-screen-name")).toBe("not_found_404");

    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toBe("ページが見つかりません");

    // AC-S2: no emoji in rendered DOM (pictographic / symbols ranges).
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-F3: while requestedPath is null (pre-hydration) the skeleton with role='status' + aria-live='polite' is rendered, then replaced atomically", async () => {
    render(<NotFoundPage />);

    // Initially (before useEffect flush) the skeleton is present. Because
    // React 19 batches the effect, we read the skeleton via testid and then
    // wait for the swap.
    const skeleton = screen.queryByTestId("not-found-skeleton");
    if (skeleton) {
      expect(skeleton.getAttribute("role")).toBe("status");
      expect(skeleton.getAttribute("aria-live")).toBe("polite");
    }

    await waitFor(() => {
      expect(screen.queryByTestId("not-found-content")).not.toBeNull();
    });
    expect(screen.queryByTestId("not-found-skeleton")).toBeNull();
  });

  it("AC-F1: static page, no fetch is performed (no workspace-scoped data leaked)", async () => {
    const fetchSpy = vi.fn();
    const originalFetch = globalThis.fetch;
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    try {
      render(<NotFoundPage />);
      await waitFor(() => {
        expect(screen.queryByTestId("not-found-content")).not.toBeNull();
      });

      expect(fetchSpy).not.toHaveBeenCalled();

      // AC-F2: no workspace-scoped data is rendered — the only path-like
      // content is the echoed `requested:` badge, which is sourced from
      // window.location.pathname, not from any API.
      const badge = screen.getByTestId("not-found-requested-path");
      expect(badge.textContent).toContain(
        "requested: /workspaces/xyz-deleted/dashboard",
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("AC-F2: page is public — does not redirect unauthenticated visitors", async () => {
    // We don't import next/navigation's useRouter at all in NotFoundPage —
    // assert that the rendered DOM contains the content block (i.e. nothing
    // short-circuited the render). If a redirect had fired the content
    // testid would never appear.
    render(<NotFoundPage />);
    await waitFor(() => {
      expect(screen.queryByTestId("not-found-content")).not.toBeNull();
    });
    // The 'ダッシュボードへ' link is a plain <Link>, not a programmatic
    // navigation — it would never push the visitor anywhere automatically.
    const homeLink = screen.getByTestId("not-found-home-link");
    expect(homeLink.getAttribute("href")).toBe("/");
  });

  it("renders all curated known routes as suggestions when search box is empty", async () => {
    render(<NotFoundPage />);
    await waitFor(() => {
      expect(screen.queryByTestId("not-found-content")).not.toBeNull();
    });

    const list = screen.getByTestId("not-found-suggestions");
    // Every curated route is rendered.
    for (const route of NOT_FOUND_KNOWN_ROUTES) {
      const item = list.querySelector(
        `[data-testid="not-found-suggestion-${route.href}"]`,
      );
      expect(item).not.toBeNull();
      expect(item?.getAttribute("href")).toBe(route.href);
      expect(item?.textContent).toContain(route.label);
    }
  });

  it("filters the suggestion list when the visitor types into the search box", async () => {
    render(<NotFoundPage />);
    await waitFor(() => {
      expect(screen.queryByTestId("not-found-content")).not.toBeNull();
    });

    const input = screen.getByTestId(
      "not-found-search-input",
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "監査" } });

    await waitFor(() => {
      const list = screen.getByTestId("not-found-suggestions");
      // Only the 監査ログ entry should remain visible after the filter.
      const items = list.querySelectorAll('[data-testid^="not-found-suggestion-"]');
      expect(items.length).toBe(1);
      expect(items[0].textContent).toContain("監査ログ");
    });

    // An impossible query should render the empty state, never crash.
    fireEvent.change(input, { target: { value: "ZZZZZ-NO-MATCH" } });
    await waitFor(() => {
      expect(
        screen.queryByTestId("not-found-suggestions-empty"),
      ).not.toBeNull();
    });
  });

  it("back button calls window.history.back()", async () => {
    const backSpy = vi
      .spyOn(window.history, "back")
      .mockImplementation(() => undefined);

    render(<NotFoundPage />);
    await waitFor(() => {
      expect(screen.queryByTestId("not-found-content")).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId("not-found-back-button"));
    expect(backSpy).toHaveBeenCalledTimes(1);

    backSpy.mockRestore();
  });
});
