"use client";

import { useEffect, useRef, useState } from "react";

let mermaidPromise: Promise<any> | null = null;
function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then(m => {
      m.default.initialize({
        startOnLoad: false,
        theme: "default",
        fontFamily: "var(--font-noto-sans-jp), system-ui, sans-serif",
      });
      return m.default;
    });
  }
  return mermaidPromise;
}

export function MermaidBlock({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = await loadMermaid();
        const id = `mmd-${Math.random().toString(36).slice(2, 8)}`;
        const { svg } = await mermaid.render(id, code);
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || String(e));
      }
    })();
    return () => { cancelled = true; };
  }, [code]);

  if (error) {
    return (
      <div className="my-2 p-3 rounded-lg text-xs"
        style={{ background: "#FEE2E2", color: "#991B1B" }}>
        Mermaid描画エラー: {error}
        <pre className="mt-2 overflow-x-auto">{code}</pre>
      </div>
    );
  }
  return (
    <div ref={ref} className="my-3 p-3 rounded-lg overflow-x-auto"
      style={{ background: "#fafafa", border: "1px solid var(--eb-border)" }} />
  );
}
