"use client";

/**
 * T-024-01: グローバル Cmd+K (Ctrl+K) modal.
 *
 * cmdk + shadcn/ui Dialog 連携で OS 横断ショートカット modal を提供.
 * ENGINE BASE green (eb-500) + Lucide icons 厳守.
 *
 * AC マッピング (T-024-01 NEW):
 *   AC-1 UBIQUITOUS    : <CommandKModal items={...} onSelect={...} /> を公開.
 *                        既存 cmdk dep を活用 (REUSE).
 *   AC-2 EVENT-DRIVEN  : Cmd+K / Ctrl+K で open / Escape で close /
 *                        item 選択で onSelect callback.
 *   AC-3 STATE-DRIVEN  : ARIA role="dialog" / focus trap /
 *                        eb-* palette only / Lucide icons only.
 *   AC-4 UNWANTED      : items 空 / null で graceful (空 modal) / global keyboard
 *                        binding は modal close 後に detach しない (stable).
 */

import * as React from "react";
import { Search } from "lucide-react";

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

/** Single Cmd+K item shape. */
export interface CommandKItem {
  /** Stable unique id. */
  id: string;
  /** Display label (search target). */
  label: string;
  /** Optional secondary text. */
  hint?: string;
  /** Group name (sections in the modal). */
  group?: string;
  /** Optional Lucide icon name (rendered separately by caller). */
  iconName?: string;
  /** Action when selected. */
  onSelect?: () => void;
  /** Disabled state. */
  disabled?: boolean;
}

export interface CommandKModalProps {
  items: CommandKItem[];
  /** Called when an item is selected (in addition to item.onSelect). */
  onSelect?: (item: CommandKItem) => void;
  /** Override placeholder text. */
  placeholder?: string;
  /** Empty state message. */
  emptyMessage?: string;
  /** Disable global Cmd+K binding (test 用). */
  disableGlobalShortcut?: boolean;
  /** Controlled open state (test 用). */
  open?: boolean;
  /** Controlled onOpenChange. */
  onOpenChange?: (open: boolean) => void;
  /** className for outer DialogContent. */
  className?: string;
}

/** Detect Cmd+K (macOS) or Ctrl+K (others). */
function isCommandKEvent(e: KeyboardEvent): boolean {
  if (e.key !== "k" && e.key !== "K") return false;
  // macOS = metaKey, others = ctrlKey
  return e.metaKey || e.ctrlKey;
}

/** Group items by `group` field; stable order. */
function groupItems(items: CommandKItem[]): Map<string, CommandKItem[]> {
  const map = new Map<string, CommandKItem[]>();
  for (const it of items) {
    const g = (it.group ?? "Other").trim() || "Other";
    if (!map.has(g)) map.set(g, []);
    map.get(g)!.push(it);
  }
  return map;
}

export function CommandKModal({
  items,
  onSelect,
  placeholder = "Search commands...",
  emptyMessage = "No results.",
  disableGlobalShortcut = false,
  open: controlledOpen,
  onOpenChange,
  className,
}: CommandKModalProps): React.JSX.Element {
  const [internalOpen, setInternalOpen] = React.useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;

  const setOpen = React.useCallback(
    (next: boolean) => {
      if (isControlled) {
        onOpenChange?.(next);
      } else {
        setInternalOpen(next);
        onOpenChange?.(next);
      }
    },
    [isControlled, onOpenChange],
  );

  // Global Cmd+K / Ctrl+K binding
  React.useEffect(() => {
    if (disableGlobalShortcut) return;
    if (typeof window === "undefined") return;

    const handler = (e: KeyboardEvent) => {
      if (isCommandKEvent(e)) {
        e.preventDefault();
        setOpen(!open);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [disableGlobalShortcut, open, setOpen]);

  const validItems = React.useMemo(
    () => (Array.isArray(items) ? items : []),
    [items],
  );
  const groups = React.useMemo(() => groupItems(validItems), [validItems]);

  const handleSelect = React.useCallback(
    (item: CommandKItem) => {
      if (item.disabled) return;
      item.onSelect?.();
      onSelect?.(item);
      setOpen(false);
    },
    [onSelect, setOpen],
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        className={cn(
          "overflow-hidden p-0 border-2 border-eb-500 sm:max-w-[640px]",
          className,
        )}
        data-testid="cmdk-modal"
        role="dialog"
        aria-label="Command palette"
      >
        <Command>
          <CommandInput placeholder={placeholder} />
          <CommandList>
            {validItems.length === 0 ? (
              <CommandEmpty>{emptyMessage}</CommandEmpty>
            ) : (
              <>
                {Array.from(groups.entries()).map(([groupName, groupItems_], idx) => (
                  <React.Fragment key={groupName}>
                    {idx > 0 && <CommandSeparator />}
                    <CommandGroup heading={groupName}>
                      {groupItems_.map((item) => (
                        <CommandItem
                          key={item.id}
                          value={`${item.label} ${item.hint ?? ""}`}
                          onSelect={() => handleSelect(item)}
                          disabled={item.disabled}
                          data-testid={`cmdk-item-${item.id}`}
                        >
                          <Search
                            className="mr-2 h-4 w-4 text-eb-500"
                            aria-hidden
                          />
                          <span>{item.label}</span>
                          {item.hint && (
                            <span className="ml-2 text-xs text-gray-500">
                              {item.hint}
                            </span>
                          )}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </React.Fragment>
                ))}
              </>
            )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}

// Test-only exports
export const __testing__ = {
  isCommandKEvent,
  groupItems,
};
