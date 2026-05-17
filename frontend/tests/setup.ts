/**
 * Vitest setup for Build-Factory frontend (T-V3-C-TEST-01).
 *
 * - Wires @testing-library/jest-dom matchers into vitest's expect.
 * - Provides default stubs for next/navigation, next/link, and sonner so
 *   any spec that does not declare its own per-file mock still renders.
 * - Cleans up the DOM and fetch between tests.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import * as React from "react";

// ---------------------------------------------------------------------------
// next/navigation default stub. Individual specs may re-mock to assert calls.
// ---------------------------------------------------------------------------
vi.mock("next/navigation", () => {
  const router = {
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  };
  return {
    useRouter: () => router,
    usePathname: () => "/",
    useSearchParams: () => new URLSearchParams(),
    useParams: () => ({}),
    redirect: vi.fn(),
    notFound: vi.fn(),
  };
});

// ---------------------------------------------------------------------------
// next/link default stub — render the children inline with the href.
// ---------------------------------------------------------------------------
vi.mock("next/link", () => {
  return {
    default: ({
      href,
      children,
      ...rest
    }: {
      href: string;
      children: React.ReactNode;
    } & React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
      React.createElement("a", { href, ...rest }, children),
  };
});

// ---------------------------------------------------------------------------
// sonner toast default stub. Specs that need to assert calls re-mock locally.
// ---------------------------------------------------------------------------
vi.mock("sonner", () => {
  const fn = vi.fn();
  const toast = Object.assign(fn, {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    message: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    promise: vi.fn(),
  });
  return {
    toast,
    Toaster: () => null,
  };
});

// ---------------------------------------------------------------------------
// JSDOM polyfills not provided by default but assumed by Radix UI + shadcn.
// ---------------------------------------------------------------------------
if (typeof window !== "undefined") {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        dispatchEvent: () => false,
      }),
    });
  }
  if (!window.ResizeObserver) {
    class StubResizeObserver {
      observe() {
        /* no-op */
      }
      unobserve() {
        /* no-op */
      }
      disconnect() {
        /* no-op */
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).ResizeObserver = StubResizeObserver;
  }
  if (!window.IntersectionObserver) {
    class StubIntersectionObserver {
      observe() {
        /* no-op */
      }
      unobserve() {
        /* no-op */
      }
      disconnect() {
        /* no-op */
      }
      takeRecords() {
        return [];
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).IntersectionObserver = StubIntersectionObserver;
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = function scrollIntoView() {
      /* no-op */
    };
  }
}

// ---------------------------------------------------------------------------
// Per-test reset hooks.
// ---------------------------------------------------------------------------
const originalFetch = globalThis.fetch;

beforeEach(() => {
  // Ensure each test starts from a known fetch state. Specs that need to
  // stub fetch should reassign `globalThis.fetch`.
  if (originalFetch) {
    globalThis.fetch = originalFetch;
  }
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  if (originalFetch) {
    globalThis.fetch = originalFetch;
  }
});
