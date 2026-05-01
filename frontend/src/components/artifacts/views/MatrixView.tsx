"use client";

import { useState } from "react";

interface MatrixItem {
  id: string;
  text: string;
  quadrant: "q1" | "q2" | "q3" | "q4";
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

export function MatrixView({ data, onChange }: Props) {
  const items = Array.isArray(data.items) ? (data.items as MatrixItem[]) : [];
  const labels = (data.labels as Record<string, string>) || {
    q1: "重要・緊急",
    q2: "重要・非緊急",
    q3: "緊急・非重要",
    q4: "非緊急・非重要",
    xAxis: "緊急度 →",
    yAxis: "重要度 ↑",
  };
  const [drag, setDrag] = useState<string | null>(null);

  const moveTo = (id: string, q: MatrixItem["quadrant"]) => {
    const next = items.map((it) => it.id === id ? { ...it, quadrant: q } : it);
    onChange?.({ ...data, items: next });
  };

  const Quadrant = ({ q, color }: { q: MatrixItem["quadrant"]; color: string }) => (
    <div
      className="relative min-h-[160px] border p-2"
      style={{ background: color }}
      onDragOver={(e) => e.preventDefault()}
      onDrop={() => { if (drag) moveTo(drag, q); setDrag(null); }}
    >
      <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-700">
        {labels[q]}
      </div>
      <div className="mt-2 space-y-1">
        {items.filter((it) => it.quadrant === q).map((it) => (
          <div
            key={it.id}
            draggable
            onDragStart={() => setDrag(it.id)}
            className="cursor-grab rounded bg-white px-2 py-1 text-xs shadow-sm hover:shadow"
          >
            {it.text}
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-px bg-gray-300">
        <Quadrant q="q1" color="#fee2e2" />
        <Quadrant q="q2" color="#dbeafe" />
        <Quadrant q="q3" color="#fef3c7" />
        <Quadrant q="q4" color="#f3f4f6" />
      </div>
      <div className="flex justify-between text-[10px] text-gray-500">
        <span>{labels.yAxis || "重要度 ↑"}</span>
        <span>{labels.xAxis || "緊急度 →"}</span>
      </div>
      <p className="text-[10px] text-gray-500">カードを別の象限にドラッグできます</p>
    </div>
  );
}
