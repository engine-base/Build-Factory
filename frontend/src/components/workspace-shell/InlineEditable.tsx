"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Pencil } from "lucide-react";

/**
 * InlineEditable — Notion 風セル/行クリック編集コンポーネント
 *
 * 仕様:
 *  - 通常表示: hover で淡いプライマリ枠が出てクリック可能なことを示す
 *  - クリック: contentEditable に切替、テキストフォーカス
 *  - blur or Cmd+S: onSave を呼ぶ → 親が保存処理
 *  - 改行は単行モードでは無効、複数行モードでは Enter 改行
 *
 * 編集セルの粒度: id (string) で一意識別。useEditableStore でローカル/リモート保存
 */
export function InlineEditable({
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
  /** true: span 表示 / false: div ブロック表示 */
  inline?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const ref = useRef<HTMLDivElement | HTMLSpanElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    if (editing && ref.current) {
      ref.current.focus();
      // カーソルを末尾へ
      const range = document.createRange();
      const sel = window.getSelection();
      range.selectNodeContents(ref.current);
      range.collapse(false);
      sel?.removeAllRanges();
      sel?.addRange(range);
    }
  }, [editing]);

  const commit = useCallback(() => {
    const next = (ref.current?.innerText ?? draft).replace(/ /g, " ").trim();
    setEditing(false);
    if (next !== value) onSave(next);
  }, [draft, value, onSave]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setEditing(false);
      if (ref.current) ref.current.innerText = value;
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      commit();
      return;
    }
    if (!multiline && e.key === "Enter") {
      e.preventDefault();
      commit();
      return;
    }
  };

  const Tag = (inline ? "span" : "div") as "span" | "div";

  // 多行 / 単行で表示モードを切替
  // - inline=true → span (親が <p> や <td> でも安全)
  // - inline=false かつ multiline → block (改行を視覚化、クリック領域を全行カバー)
  // - inline=false かつ単行 → inline-block
  const displayKind: "inline" | "block" | "inline-block" =
    inline ? "inline" : multiline ? "block" : "inline-block";

  if (editing) {
    return (
      <Tag
        ref={ref as any}
        className={className}
        contentEditable
        suppressContentEditableWarning
        onBlur={commit}
        onKeyDown={handleKeyDown}
        style={{
          ...style,
          display: displayKind === "inline" ? "inline" : displayKind,
          outline: "2px solid var(--bf-primary)",
          outlineOffset: 1,
          background: "var(--bf-bg)",
          borderRadius: 4,
          padding: inline ? "0 2px" : "4px 6px",
          minHeight: inline ? undefined : 24,
          whiteSpace: multiline ? "pre-wrap" : "nowrap",
          wordBreak: "break-word",
          cursor: "text",
        }}
      >
        {value}
      </Tag>
    );
  }

  const empty = !value || value.trim() === "";
  return (
    <Tag
      className={`bf-editable bf-editable-${displayKind} ${className ?? ""}`}
      onClick={(e) => { e.stopPropagation(); setEditing(true); }}
      title="クリックして編集 (Esc 取消・Cmd/Ctrl+S 保存)"
      style={{
        ...style,
        display: displayKind === "inline" ? "inline" : displayKind,
        cursor: "pointer",
        borderRadius: 4,
        padding: inline ? "0 2px" : "2px 4px",
        color: empty ? "var(--bf-text-4)" : undefined,
        whiteSpace: multiline ? "pre-wrap" : undefined,
        wordBreak: "break-word",
        position: "relative",
        width: displayKind === "block" ? "100%" : undefined,
        minHeight: displayKind === "block" ? "1.6em" : undefined,
      }}
    >
      {empty ? placeholder : value}
    </Tag>
  );
}

/**
 * グローバル CSS — 一度だけ <head> に埋め込む。
 * page.tsx で <BfEditableStyles /> を呼ぶ。
 */
export function BfEditableStyles() {
  return (
    <style>{`
      .bf-editable {
        transition: background 120ms, box-shadow 120ms;
        max-width: 100%;
      }
      .bf-editable-block { display: block; }
      .bf-editable-inline-block { display: inline-block; }
      .bf-editable-inline { display: inline; }
      .bf-editable:hover {
        background: var(--bf-primary-bg);
        box-shadow: inset 0 0 0 1px var(--bf-primary);
      }
    `}</style>
  );
}
