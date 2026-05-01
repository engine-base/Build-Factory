"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/atom-one-dark.css";
import { MermaidBlock } from "./MermaidBlock";

/**
 * MarkdownView — チャットアシスタント返答の本文を綺麗に描画する。
 * テーブル / リスト / 見出し / コードブロック / リンク / 引用 を自動整形。
 */
export function MarkdownView({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={{
        h1: ({ children }) => (
          <h1 className="text-base font-bold mt-3 mb-2"
            style={{ color: "#1f2937", fontFamily: "var(--font-noto-sans-jp)" }}>{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-sm font-bold mt-3 mb-1.5 pb-1"
            style={{
              color: "#1f2937",
              borderBottom: "1px solid var(--eb-border)",
              fontFamily: "var(--font-noto-sans-jp)",
            }}>{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-sm font-bold mt-2 mb-1 flex items-center gap-1.5"
            style={{ color: "var(--eb-primary)", fontFamily: "var(--font-noto-sans-jp)" }}>
            <span style={{
              width: 3, height: 14, background: "var(--eb-primary)",
              borderRadius: 2, display: "inline-block",
            }} />
            {children}
          </h3>
        ),
        h4: ({ children }) => (
          <h4 className="text-xs font-bold mt-2 mb-1"
            style={{ color: "#374151" }}>{children}</h4>
        ),
        p: ({ children }) => (
          <p className="my-1.5 leading-relaxed">{children}</p>
        ),
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer"
            className="underline"
            style={{ color: "var(--eb-primary)" }}>{children}</a>
        ),
        ul: ({ children }) => (
          <ul className="list-disc pl-5 my-1.5 space-y-0.5"
            style={{ marginLeft: 4 }}>{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal pl-5 my-1.5 space-y-0.5"
            style={{ marginLeft: 4 }}>{children}</ol>
        ),
        li: ({ children }) => (
          <li className="leading-relaxed">{children}</li>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-4 pl-3 my-2 italic"
            style={{
              borderColor: "var(--eb-primary)",
              background: "var(--eb-surface-variant)",
              padding: "8px 12px",
              borderRadius: 4,
              color: "#4b5563",
            }}>{children}</blockquote>
        ),
        hr: () => (
          <hr className="my-3" style={{ border: "none", borderTop: "1px solid var(--eb-border)" }} />
        ),
        table: ({ children }) => (
          <div className="my-3 overflow-x-auto rounded-lg" style={{ border: "1px solid var(--eb-border)" }}>
            <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead style={{ background: "var(--eb-surface-variant)" }}>{children}</thead>
        ),
        th: ({ children }) => (
          <th className="text-left px-3 py-2 font-bold"
            style={{
              color: "#374151", borderBottom: "1px solid var(--eb-border)",
              fontFamily: "var(--font-noto-sans-jp)",
            }}>{children}</th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-2"
            style={{ borderBottom: "1px solid var(--eb-border)", verticalAlign: "top" }}>{children}</td>
        ),
        tr: ({ children }) => <tr>{children}</tr>,
        code: ({ inline, className, children }: any) => {
          if (inline) {
            return (
              <code className="px-1.5 py-0.5 rounded text-[0.85em]"
                style={{
                  background: "var(--eb-surface-variant)",
                  fontFamily: "var(--font-mono, ui-monospace, monospace)",
                  color: "#a83232",
                }}>{children}</code>
            );
          }
          // mermaid → SVG レンダリング
          const lang = (className || "").replace("language-", "").trim();
          const codeText = String(children).replace(/\n$/, "");
          if (lang === "mermaid") {
            return <MermaidBlock code={codeText} />;
          }
          return (
            <pre className="my-2 p-3 rounded-lg overflow-x-auto text-xs"
              style={{
                background: "#282c34", color: "#abb2bf",
                fontFamily: "var(--font-mono, ui-monospace, monospace)",
              }}>
              <code className={className}>{children}</code>
            </pre>
          );
        },
        pre: ({ children }: any) => <>{children}</>,
        strong: ({ children }) => (
          <strong className="font-bold" style={{ color: "#111827" }}>{children}</strong>
        ),
        em: ({ children }) => <em className="italic">{children}</em>,
      }}
    >{children}</ReactMarkdown>
  );
}
