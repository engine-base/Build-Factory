"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import type { Block, PartialBlock } from "@blocknote/core";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";

import "@blocknote/core/style.css";
import "@blocknote/mantine/style.css";

/**
 * BlockNoteEditable — 常時 live の BlockNote エディタ
 *
 * 仕様 (徹底版):
 *  - 常に BlockNote が live で表示される (display モードなし・クリック不要)
 *  - Formatting toolbar (選択時の浮上ツールバー): 有効
 *  - Slash menu (/ で blocks 挿入): 有効
 *  - Side menu (ブロックハンドル + D&D + 削除/追加): 有効
 *  - Link toolbar / Table handles / Emoji picker: 有効
 *  - 自動保存: blur (フォーカス外し) + Cmd/Ctrl+S
 *  - 100+ インスタンス対応のため IntersectionObserver で lazy mount
 *  - 表示モードでもエディタが立ち上がる前提だが、画面外は軽量プレースホルダ
 */
export function BlockNoteEditable({
  value,
  id,
  multiline = false,
  placeholder = "クリックして編集",
  onSave,
  className,
  style,
  inline = false,
}: {
  value: string;
  id: string;
  multiline?: boolean;
  placeholder?: string;
  onSave: (next: string) => void;
  className?: string;
  style?: React.CSSProperties;
  inline?: boolean;
}) {
  const [mounted, setMounted] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // ビューポートに入ったら mount (パフォーマンス最適化)
  useEffect(() => {
    if (mounted) return;
    const el = wrapRef.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setMounted(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setMounted(true);
            io.disconnect();
            return;
          }
        }
      },
      { rootMargin: "200px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [mounted]);

  return (
    <div
      ref={wrapRef}
      className={`bf-bn-wrap ${inline ? "bf-bn-inline" : "bf-bn-block"} ${className ?? ""}`}
      style={{
        ...style,
        display: inline ? "inline-block" : "block",
        width: inline ? undefined : "100%",
        minHeight: inline ? "1.6em" : "1.6em",
        position: "relative",
      }}
      data-bn-id={id}
    >
      {mounted ? (
        <LiveEditor
          initialText={value}
          multiline={multiline}
          inline={inline}
          onSave={onSave}
        />
      ) : (
        <ClickToActivatePlaceholder
          value={value}
          placeholder={placeholder}
          inline={inline}
          multiline={multiline}
          onActivate={() => setMounted(true)}
        />
      )}
    </div>
  );
}

/* ──────── Lazy 表示中のプレースホルダ ──────── */
function ClickToActivatePlaceholder({
  value, placeholder, inline, multiline, onActivate,
}: {
  value: string; placeholder: string;
  inline: boolean; multiline: boolean;
  onActivate: () => void;
}) {
  const empty = !value || value.trim() === "";
  const Tag = (inline ? "span" : "div") as "span" | "div";
  return (
    <Tag
      className="bf-bn-placeholder"
      onClick={onActivate}
      onFocus={onActivate}
      tabIndex={0}
      style={{
        display: inline ? "inline" : "block",
        cursor: "text",
        whiteSpace: multiline ? "pre-wrap" : undefined,
        wordBreak: "break-word",
        color: empty ? "var(--bf-text-4)" : "inherit",
        padding: inline ? "0 2px" : "2px 4px",
        borderRadius: 4,
      }}
    >
      {empty ? placeholder : value}
    </Tag>
  );
}

/* ──────── Live BlockNote エディタ本体 ──────── */
function LiveEditor({
  initialText, multiline, inline, onSave,
}: {
  initialText: string;
  multiline: boolean;
  inline: boolean;
  onSave: (next: string) => void;
}) {
  const initialContent: PartialBlock[] = textToBlocks(initialText, multiline);
  const editor = useCreateBlockNote({ initialContent });
  const lastSaved = useRef(initialText);
  const containerRef = useRef<HTMLDivElement>(null);

  const commit = useCallback(() => {
    const text = blocksToText(editor.document);
    if (text !== lastSaved.current) {
      lastSaved.current = text;
      onSave(text);
    }
  }, [editor, onSave]);

  // 外側へ focus が抜けたら commit
  useEffect(() => {
    const handleFocusOut = (e: FocusEvent) => {
      const next = e.relatedTarget as Node | null;
      if (containerRef.current && next && containerRef.current.contains(next)) return;
      setTimeout(() => {
        if (containerRef.current && !containerRef.current.contains(document.activeElement)) {
          commit();
        }
      }, 80);
    };
    const el = containerRef.current;
    if (el) el.addEventListener("focusout", handleFocusOut);
    return () => { if (el) el.removeEventListener("focusout", handleFocusOut); };
  }, [commit]);

  // Cmd/Ctrl+S と (multiline=false 時の) Enter
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      commit();
      return;
    }
    if (!multiline && e.key === "Enter" && !e.shiftKey) {
      // 単行モードでは改行禁止 → そのまま blur で commit
      e.preventDefault();
      (e.currentTarget as HTMLElement).blur();
    }
  };

  return (
    <div
      ref={containerRef}
      className={`bf-bn-live ${inline ? "bf-bn-live-inline" : "bf-bn-live-block"}`}
      onKeyDown={handleKeyDown}
    >
      <BlockNoteView
        editor={editor}
        theme="light"
        formattingToolbar
        slashMenu
        sideMenu={!inline}
        linkToolbar
        tableHandles
        emojiPicker
        filePanel={false}
      />
    </div>
  );
}

/* ════════════════════════════════════════════
 * BlockNoteListEditable — 箇条書き / 番号付き / チェックリストの集合エディタ
 * - 1 つの BlockNote エディタで N 項目をまとめて編集 (Enter で追加・Backspace で削除)
 * - SideMenu (block ハンドル) で並べ替え・削除・追加が可能
 * - 保存時は string[] に変換
 * ════════════════════════════════════════════ */
export function BlockNoteListEditable({
  items,
  id,
  listType = "bullet",
  onSave,
  className,
  style,
}: {
  items: string[];
  id: string;
  listType?: "bullet" | "number" | "check";
  onSave: (next: string[]) => void;
  className?: string;
  style?: React.CSSProperties;
}) {
  const [mounted, setMounted] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (mounted) return;
    const el = wrapRef.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setMounted(true); return;
    }
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) { setMounted(true); io.disconnect(); return; }
      }
    }, { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, [mounted]);

  return (
    <div
      ref={wrapRef}
      className={`bf-bn-list-wrap ${className ?? ""}`}
      style={{ display: "block", width: "100%", minHeight: "1.6em", ...style }}
      data-bn-list-id={id}
    >
      {mounted ? (
        <LiveListEditor items={items} listType={listType} onSave={onSave} />
      ) : (
        <ListPlaceholder items={items} listType={listType} onActivate={() => setMounted(true)} />
      )}
    </div>
  );
}

function ListPlaceholder({
  items, listType, onActivate,
}: {
  items: string[]; listType: "bullet" | "number" | "check";
  onActivate: () => void;
}) {
  const Tag = (listType === "number" ? "ol" : "ul") as "ol" | "ul";
  return (
    <Tag
      onClick={onActivate}
      onFocus={onActivate}
      tabIndex={0}
      style={{ cursor: "text", paddingLeft: 18, margin: 0 }}
    >
      {items.length === 0
        ? <li style={{ color: "var(--bf-text-4)" }}>クリックして項目を追加</li>
        : items.map((it, i) => <li key={i}>{it}</li>)}
    </Tag>
  );
}

function LiveListEditor({
  items, listType, onSave,
}: {
  items: string[]; listType: "bullet" | "number" | "check";
  onSave: (next: string[]) => void;
}) {
  const blockType =
    listType === "number" ? "numberedListItem" :
    listType === "check"  ? "checkListItem"   :
    "bulletListItem";

  const initialContent: PartialBlock[] = items.length === 0
    ? [{ type: blockType as any, content: "" }]
    : items.map((it) => ({ type: blockType as any, content: it }));

  const editor = useCreateBlockNote({ initialContent });
  const lastSaved = useRef(items);
  const containerRef = useRef<HTMLDivElement>(null);

  const commit = useCallback(() => {
    const next = editor.document
      .map((b) => extractText(b))
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    const a = JSON.stringify(next);
    const b = JSON.stringify(lastSaved.current);
    if (a !== b) {
      lastSaved.current = next;
      onSave(next);
    }
  }, [editor, onSave]);

  useEffect(() => {
    const handleFocusOut = (e: FocusEvent) => {
      const next = e.relatedTarget as Node | null;
      if (containerRef.current && next && containerRef.current.contains(next)) return;
      setTimeout(() => {
        if (containerRef.current && !containerRef.current.contains(document.activeElement)) commit();
      }, 80);
    };
    const el = containerRef.current;
    if (el) el.addEventListener("focusout", handleFocusOut);
    return () => { if (el) el.removeEventListener("focusout", handleFocusOut); };
  }, [commit]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
      e.preventDefault(); commit();
    }
  };

  return (
    <div
      ref={containerRef}
      className="bf-bn-live bf-bn-live-block"
      onKeyDown={handleKeyDown}
    >
      <BlockNoteView
        editor={editor}
        theme="light"
        formattingToolbar
        slashMenu
        sideMenu
        linkToolbar
        emojiPicker
        filePanel={false}
      />
    </div>
  );
}

/* ──────── 文字列 ↔ BlockNote 変換 ──────── */

function textToBlocks(text: string, multiline: boolean): PartialBlock[] {
  if (!text) return [{ type: "paragraph", content: "" }];
  if (!multiline) return [{ type: "paragraph", content: text }];
  const lines = text.split("\n");
  return lines.map((line) => ({ type: "paragraph", content: line }));
}

function blocksToText(blocks: Block[]): string {
  const parts: string[] = [];
  for (const b of blocks) {
    parts.push(extractText(b));
  }
  return parts.join("\n").replace(/\n+$/g, "");
}

function extractText(b: Block): string {
  const content: any = b.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((node: any) => {
        if (typeof node === "string") return node;
        if (node?.type === "text") return node.text ?? "";
        if (node?.type === "link") {
          const inner = (node.content || []).map((c: any) => c.text ?? "").join("");
          return inner;
        }
        return "";
      })
      .join("");
  }
  return "";
}

/* ──────── 全体スタイル — BlockNote をセル内に flush 表示 ──────── */
export function BfEditableStyles() {
  return (
    <style>{`
      /* 旧 InlineEditable 互換 hover スタイル (placeholder に hover した時だけ) */
      .bf-bn-placeholder {
        transition: background 120ms, box-shadow 120ms;
        max-width: 100%;
      }
      .bf-bn-placeholder:hover {
        background: var(--bf-primary-bg);
        box-shadow: inset 0 0 0 1px var(--bf-primary);
      }

      /* === BlockNote ライブ表示時のスタイル調整 === */
      .bf-bn-live { width: 100%; background: transparent; }
      .bf-bn-live-inline { display: inline-block; vertical-align: top; min-width: 80px; }
      .bf-bn-live-block { display: block; }

      .bf-bn-live .bn-container,
      .bf-bn-live [data-blocknote-container] {
        background: transparent !important;
      }
      .bf-bn-live .bn-editor {
        padding: 0 !important;
        background: transparent !important;
        font-family: inherit !important;
        color: var(--bf-text-1) !important;
      }
      .bf-bn-live .bn-block-outer {
        margin: 0 !important;
      }
      .bf-bn-live .bn-block {
        padding-inline-start: 0 !important;
      }
      .bf-bn-live .bn-block-content {
        padding: 2px 0 !important;
        font-size: inherit !important;
        line-height: 1.65 !important;
        color: var(--bf-text-1) !important;
        background: transparent !important;
      }
      .bf-bn-live .bn-block-content[data-content-type="paragraph"] { padding: 1px 0 !important; }
      .bf-bn-live .bn-inline-content { font-size: inherit !important; }
      .bf-bn-live p { margin: 0 !important; }

      /* 各 block の hover/active で薄いグレーのみ (白〜白を維持) */
      .bf-bn-live .bn-block-content:hover {
        background: var(--bf-bg) !important;
      }

      /* リスト内のマーカー */
      .bf-bn-live ul, .bf-bn-live ol {
        padding-left: 22px !important;
        margin: 0 !important;
      }
      .bf-bn-live li::marker { color: var(--bf-text-3); }

      /* 編集中の枠線 */
      .bf-bn-live:focus-within {
        outline: 2px solid var(--bf-primary);
        outline-offset: 2px;
        border-radius: 4px;
      }

      /* 行ハンドル (sideMenu) — 全コンテキストで使えるように常時有効 */
      .bf-bn-live .bn-side-menu {
        position: absolute;
        left: -34px !important;
        opacity: 0;
        transition: opacity 120ms;
      }
      .bf-bn-live:hover .bn-side-menu,
      .bf-bn-live:focus-within .bn-side-menu {
        opacity: 1;
      }

      /* テーブルセル内: 左の余白を確保して sideMenu が見えるように */
      td .bf-bn-live { padding-left: 4px; }

      /* 空ブロックのプレースホルダ (BlockNote 標準) のスタイル統一 */
      .bf-bn-live .bn-block-content[data-is-empty-and-focused="true"]::before {
        color: var(--bf-text-4) !important;
        font-style: normal !important;
      }

      /* Mantine ポップオーバー (toolbar 等) を最前面 */
      .mantine-Popover-dropdown,
      .bn-floating-toolbar,
      .bn-suggestion-menu {
        z-index: 9999 !important;
      }

      /* セル背景は親要素 (table tr / persona-body / info-card) の白を継承 */
      td .bf-bn-live, .rd-info-card .bf-bn-live, .rd-persona-body .bf-bn-live,
      .rd-feature-row-value .bf-bn-live, .rd-flow-block .bf-bn-live,
      .rd-unresolved-content .bf-bn-live {
        background: transparent !important;
      }
    `}</style>
  );
}
