"use client";

import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import type { Block, PartialBlock } from "@blocknote/core";

interface Props {
  initialContent?: PartialBlock[];
  onChange?: (blocks: Block[]) => void;
  editable?: boolean;
}

/**
 * Notion 風 リッチエディタ (BlockNote MIT)
 * 議事録 / 要件定義書 / 仕様書 / 成果物の編集に使用。
 */
export function MinutesEditor({ initialContent, onChange, editable = true }: Props) {
  const editor = useCreateBlockNote({
    initialContent: initialContent ?? defaultContent(),
  });

  return (
    <div className="bf-minutes-editor">
      <BlockNoteView
        editor={editor}
        editable={editable}
        theme="light"
        onChange={() => {
          if (onChange) onChange(editor.document);
        }}
      />
      <style jsx global>{`
        .bf-minutes-editor .bn-editor {
          font-family: "Inter", "Noto Sans JP", sans-serif;
          padding: 0;
          background: transparent;
        }
        .bf-minutes-editor .bn-default-styles h1 { font-size: 24px; font-weight: 700; letter-spacing: -0.01em; }
        .bf-minutes-editor .bn-default-styles h2 { font-size: 18px; font-weight: 700; }
        .bf-minutes-editor .bn-default-styles h3 { font-size: 16px; font-weight: 600; }
        .bf-minutes-editor .bn-default-styles p,
        .bf-minutes-editor .bn-default-styles li { font-size: 13.5px; line-height: 1.7; color: var(--bf-text-1); }
      `}</style>
    </div>
  );
}

function defaultContent(): PartialBlock[] {
  return [
    {
      type: "heading",
      props: { level: 1 },
      content: "要件定義レビュー MTG",
    },
    {
      type: "paragraph",
      content: [{ type: "text", text: "5月3日 (土) 14:00 〜 15:00 / Online (Google Meet) / 参加: 山田 太郎、高本 まさと、PM AI、設計 AI", styles: { italic: true } }],
    },
    {
      type: "heading",
      props: { level: 2 },
      content: "1. アジェンダ",
    },
    {
      type: "bulletListItem",
      content: "要件定義書 v1.0 のクライアントレビュー",
    },
    {
      type: "bulletListItem",
      content: "機能要件の優先順位調整",
    },
    {
      type: "bulletListItem",
      content: "非機能要件 (セキュリティ・パフォーマンス) の確認",
    },
    {
      type: "bulletListItem",
      content: "次フェーズ (アーキ + デザイン) のスケジュール",
    },
    {
      type: "heading",
      props: { level: 2 },
      content: "2. 主な決定事項",
    },
    {
      type: "bulletListItem",
      content: [{ type: "text", text: "認証機能を Must に格上げ ", styles: { bold: true } }, { type: "text", text: "— 当初 Should だったが、運用初日から必要との認識で変更", styles: {} }],
    },
    {
      type: "bulletListItem",
      content: [{ type: "text", text: "レポート機能を v1 スコープから外す ", styles: { bold: true } }, { type: "text", text: "— 設計が複雑化するため Phase 2 に", styles: {} }],
    },
    {
      type: "bulletListItem",
      content: [{ type: "text", text: "既存 DB との連携を新規追加 ", styles: { bold: true } }, { type: "text", text: "— 山田様より「移行コスト最小化のため必須」", styles: {} }],
    },
    {
      type: "heading",
      props: { level: 2 },
      content: "3. アクションアイテム",
    },
    {
      type: "checkListItem",
      content: "既存 DB のスキーマ詳細を山田様より受領 (5/8)",
    },
    {
      type: "checkListItem",
      props: { checked: true },
      content: "要件定義書を v2.0 に更新",
    },
    {
      type: "checkListItem",
      content: "アーキ設計に既存 DB 連携を組み込み (5/8)",
    },
    {
      type: "heading",
      props: { level: 2 },
      content: "4. 議論ハイライト",
    },
    {
      type: "paragraph",
      content: [{ type: "text", text: "山田様: ", styles: { bold: true } }, { type: "text", text: "「既存の社内システムが Oracle で動いているので、データ移行よりも参照連携の方が現実的。リードオンリーで良いから繋がせてほしい。」", styles: {} }],
    },
    {
      type: "paragraph",
      content: [{ type: "text", text: "高本: ", styles: { bold: true } }, { type: "text", text: "「分かりました。読み取り専用 API として実装します。Oracle 側のスキーマを後で共有いただければ設計 AI で仕様化します。」", styles: {} }],
    },
  ];
}
