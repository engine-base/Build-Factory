"use client";

import { useState } from "react";

interface Item {
  text: string;
  done?: boolean;
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

export function ListView({ data, onChange }: Props) {
  const items = Array.isArray(data.items) ? (data.items as Item[]) : [];
  const [newText, setNewText] = useState("");

  const update = (next: Item[]) => onChange?.({ ...data, items: next });

  const toggle = (i: number) => {
    const next = items.map((it, idx) =>
      idx === i ? { ...it, done: !it.done } : it,
    );
    update(next);
  };

  const remove = (i: number) => {
    update(items.filter((_, idx) => idx !== i));
  };

  const add = () => {
    if (!newText.trim()) return;
    update([...items, { text: newText.trim(), done: false }]);
    setNewText("");
  };

  const editText = (i: number, text: string) => {
    const next = items.map((it, idx) => (idx === i ? { ...it, text } : it));
    update(next);
  };

  return (
    <div className="space-y-2">
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li
            key={i}
            className="group flex items-center gap-2 rounded px-2 py-1.5 hover:bg-gray-50"
          >
            <input
              type="checkbox"
              checked={!!it.done}
              onChange={() => toggle(i)}
              className="h-4 w-4"
            />
            <input
              value={it.text}
              onChange={(e) => editText(i, e.target.value)}
              className={`flex-1 bg-transparent text-sm outline-none ${
                it.done ? "text-gray-400 line-through" : ""
              }`}
            />
            <button
              onClick={() => remove(i)}
              className="invisible text-xs text-red-500 group-hover:visible"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <div className="flex gap-2 border-t pt-2">
        <input
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="新しい項目を追加…"
          className="flex-1 rounded border px-2 py-1 text-sm"
        />
        <button
          onClick={add}
          className="rounded bg-blue-500 px-3 py-1 text-sm text-white hover:bg-blue-600"
        >
          追加
        </button>
      </div>
    </div>
  );
}
