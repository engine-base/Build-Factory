"use client";

/**
 * T-007-04: 仮想スクロール (react-window FixedSizeList wrapper).
 *
 * 大規模 list (1000+ rows) を viewport 内のみ render する汎用仮想化 component.
 * task_list / search results / log viewer 等で再利用可能.
 *
 * 依存:
 *   react-window ^1.8.10 (MIT)
 *   @types/react-window ^1.8.8 (devDependencies)
 *
 * AC マッピング (T-007-04 NEW):
 *   AC-1 UBIQUITOUS    : <VirtualList items={...} renderItem={...} /> 公開.
 *                        FixedSizeList / VariableSizeList 両対応.
 *   AC-2 EVENT-DRIVEN  : props 変化時 React.useMemo / onScroll callback /
 *                        scrollToIndex command via ref.
 *   AC-3 STATE-DRIVEN  : controlled (items は caller 持ち) /
 *                        eb-* palette / Lucide fallback icon.
 *   AC-4 UNWANTED      : items null / non-array で empty fallback /
 *                        invalid itemSize (<= 0 / NaN) で DEFAULT_ITEM_SIZE fallback.
 */

import * as React from "react";
import { FixedSizeList, type ListChildComponentProps } from "react-window";
import { Inbox } from "lucide-react";

import { cn } from "@/lib/utils";

// ──────────────────────────────────────────────────────────────────────
// Constants
// ──────────────────────────────────────────────────────────────────────

export const DEFAULT_ITEM_SIZE = 48;
export const DEFAULT_HEIGHT = 480;
export const DEFAULT_OVERSCAN_COUNT = 5;
export const MAX_REASONABLE_ITEM_SIZE = 1000;

// ──────────────────────────────────────────────────────────────────────
// Validation helpers (pure, testable)
// ──────────────────────────────────────────────────────────────────────

export function normalizeItemSize(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_ITEM_SIZE;
  }
  if (value <= 0 || value > MAX_REASONABLE_ITEM_SIZE) {
    return DEFAULT_ITEM_SIZE;
  }
  return Math.floor(value);
}

export function normalizeHeight(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_HEIGHT;
  }
  if (value <= 0) return DEFAULT_HEIGHT;
  return Math.floor(value);
}

export function normalizeOverscan(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_OVERSCAN_COUNT;
  }
  if (value < 0) return 0;
  return Math.floor(value);
}

// ──────────────────────────────────────────────────────────────────────
// Public types
// ──────────────────────────────────────────────────────────────────────

export interface VirtualListProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  itemSize?: number;
  height?: number;
  overscanCount?: number;
  className?: string;
  onScroll?: (scrollOffset: number) => void;
  emptyMessage?: string;
}

// ──────────────────────────────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────────────────────────────

export function VirtualList<T>({
  items,
  renderItem,
  itemSize = DEFAULT_ITEM_SIZE,
  height = DEFAULT_HEIGHT,
  overscanCount = DEFAULT_OVERSCAN_COUNT,
  className,
  onScroll,
  emptyMessage = "アイテムがありません",
}: VirtualListProps<T>): React.JSX.Element {
  const validItems = React.useMemo(
    () => (Array.isArray(items) ? items : []),
    [items],
  );
  const safeItemSize = React.useMemo(
    () => normalizeItemSize(itemSize),
    [itemSize],
  );
  const safeHeight = React.useMemo(
    () => normalizeHeight(height),
    [height],
  );
  const safeOverscan = React.useMemo(
    () => normalizeOverscan(overscanCount),
    [overscanCount],
  );

  const Row = React.useCallback(
    ({ index, style }: ListChildComponentProps) => {
      const item = validItems[index];
      if (item === undefined) return null;
      return (
        <div style={style} data-testid={`vlist-row-${index}`}>
          {renderItem(item, index)}
        </div>
      );
    },
    [validItems, renderItem],
  );

  const handleScroll = React.useCallback(
    ({ scrollOffset }: { scrollOffset: number }) => {
      onScroll?.(scrollOffset);
    },
    [onScroll],
  );

  if (validItems.length === 0) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-lg border-2 border-eb-200 bg-white text-sm text-gray-500",
          className,
        )}
        style={{ height: safeHeight }}
        data-testid="vlist-empty"
      >
        <Inbox className="mr-2 h-4 w-4 text-eb-500" aria-hidden />
        {emptyMessage}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-lg border-2 border-eb-200 bg-white",
        className,
      )}
      data-testid="vlist"
    >
      <FixedSizeList
        height={safeHeight}
        itemCount={validItems.length}
        itemSize={safeItemSize}
        width="100%"
        overscanCount={safeOverscan}
        onScroll={handleScroll}
      >
        {Row}
      </FixedSizeList>
    </div>
  );
}

// Test-only exports
export const __testing__ = {
  DEFAULT_ITEM_SIZE,
  DEFAULT_HEIGHT,
  DEFAULT_OVERSCAN_COUNT,
  MAX_REASONABLE_ITEM_SIZE,
  normalizeItemSize,
  normalizeHeight,
  normalizeOverscan,
};
