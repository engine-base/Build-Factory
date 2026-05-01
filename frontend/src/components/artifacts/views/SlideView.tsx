"use client";

import { useState } from "react";

interface Slide {
  id: string;
  title?: string;
  body?: string;
  layout?: "title" | "content" | "two-col" | "image";
  image?: string;
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

export function SlideView({ data, onChange }: Props) {
  const slides = Array.isArray(data.slides) ? (data.slides as Slide[]) : [];
  const [idx, setIdx] = useState(0);

  if (slides.length === 0) {
    return <div className="text-sm text-gray-500">スライドがありません</div>;
  }

  const cur = slides[Math.min(idx, slides.length - 1)];

  const updateField = (key: keyof Slide, value: string) => {
    const next = slides.map((s, i) => i === idx ? { ...s, [key]: value } : s);
    onChange?.({ ...data, slides: next });
  };

  const addSlide = () => {
    const next: Slide[] = [
      ...slides,
      { id: `s-${Date.now()}`, title: "新しいスライド", body: "", layout: "content" },
    ];
    onChange?.({ ...data, slides: next });
    setIdx(next.length - 1);
  };

  return (
    <div className="space-y-2">
      {/* スライド本体 */}
      <div className="aspect-[16/9] rounded-lg border bg-white p-8 shadow">
        {cur.layout === "title" ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <input
              value={cur.title || ""}
              onChange={(e) => updateField("title", e.target.value)}
              className="w-full bg-transparent text-center text-3xl font-bold outline-none focus:bg-yellow-50"
              placeholder="タイトル"
            />
            <textarea
              value={cur.body || ""}
              onChange={(e) => updateField("body", e.target.value)}
              className="mt-4 w-full bg-transparent text-center text-base outline-none focus:bg-yellow-50"
              placeholder="サブタイトル"
              rows={2}
            />
          </div>
        ) : (
          <div className="flex h-full flex-col">
            <input
              value={cur.title || ""}
              onChange={(e) => updateField("title", e.target.value)}
              className="border-b pb-2 text-xl font-bold outline-none focus:bg-yellow-50"
              placeholder="スライドタイトル"
            />
            <textarea
              value={cur.body || ""}
              onChange={(e) => updateField("body", e.target.value)}
              className="mt-3 flex-1 resize-none bg-transparent text-sm outline-none focus:bg-yellow-50"
              placeholder="本文"
            />
          </div>
        )}
      </div>

      {/* ナビ */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setIdx(Math.max(0, idx - 1))}
          className="rounded px-3 py-1 text-xs hover:bg-gray-100"
          disabled={idx === 0}
        >
          ◀
        </button>
        <span className="text-xs">{idx + 1} / {slides.length}</span>
        <button
          onClick={() => setIdx(Math.min(slides.length - 1, idx + 1))}
          className="rounded px-3 py-1 text-xs hover:bg-gray-100"
          disabled={idx === slides.length - 1}
        >
          ▶
        </button>
        <button
          onClick={addSlide}
          className="ml-auto rounded border border-dashed px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
        >
          + スライド追加
        </button>
      </div>

      {/* サムネイル */}
      <div className="flex gap-1 overflow-x-auto pb-2">
        {slides.map((s, i) => (
          <button
            key={s.id || i}
            onClick={() => setIdx(i)}
            className={`shrink-0 rounded border bg-white px-2 py-1 text-[10px] ${
              i === idx ? "border-blue-500 ring-2 ring-blue-200" : ""
            }`}
            style={{ width: 96 }}
          >
            <div className="font-semibold truncate">{s.title || `Slide ${i + 1}`}</div>
            <div className="truncate text-gray-500">{s.body?.slice(0, 24) || ""}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
