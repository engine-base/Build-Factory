"use client";

import { useState } from "react";

interface Card {
  id: string;
  text: string;
  meta?: Record<string, unknown>;
}

interface Column {
  id: string;
  title: string;
  cards: Card[];
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

export function KanbanView({ data, onChange }: Props) {
  const columns = Array.isArray(data.columns) ? (data.columns as Column[]) : [];
  const [dragId, setDragId] = useState<string | null>(null);

  const update = (next: Column[]) => onChange?.({ ...data, columns: next });

  const moveCard = (cardId: string, toColId: string) => {
    let card: Card | null = null;
    const cleared = columns.map((c) => ({
      ...c,
      cards: c.cards.filter((card2) => {
        if (card2.id === cardId) {
          card = card2;
          return false;
        }
        return true;
      }),
    }));
    if (!card) return;
    const next = cleared.map((c) =>
      c.id === toColId ? { ...c, cards: [...c.cards, card!] } : c,
    );
    update(next);
  };

  const addCard = (colId: string, text: string) => {
    if (!text.trim()) return;
    const next = columns.map((c) =>
      c.id === colId
        ? {
            ...c,
            cards: [
              ...c.cards,
              { id: `c-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, text: text.trim() },
            ],
          }
        : c,
    );
    update(next);
  };

  const removeCard = (colId: string, cardId: string) => {
    const next = columns.map((c) =>
      c.id === colId ? { ...c, cards: c.cards.filter((cd) => cd.id !== cardId) } : c,
    );
    update(next);
  };

  return (
    <div className="flex gap-3 overflow-x-auto pb-4">
      {columns.map((col) => (
        <ColumnView
          key={col.id}
          column={col}
          onCardDrop={(cardId) => moveCard(cardId, col.id)}
          onCardDragStart={setDragId}
          onAddCard={(text) => addCard(col.id, text)}
          onRemoveCard={(cardId) => removeCard(col.id, cardId)}
        />
      ))}
    </div>
  );
}

function ColumnView({
  column,
  onCardDrop,
  onCardDragStart,
  onAddCard,
  onRemoveCard,
}: {
  column: Column;
  onCardDrop: (cardId: string) => void;
  onCardDragStart: (id: string) => void;
  onAddCard: (text: string) => void;
  onRemoveCard: (cardId: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");

  return (
    <div
      className="flex w-72 shrink-0 flex-col rounded-lg bg-gray-100 p-2"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        const id = e.dataTransfer.getData("text/plain");
        if (id) onCardDrop(id);
      }}
    >
      <div className="flex items-center gap-2 px-2 py-1">
        <span className="font-semibold text-sm">{column.title}</span>
        <span className="rounded bg-gray-200 px-1.5 text-xs text-gray-600">
          {column.cards.length}
        </span>
      </div>
      <div className="flex flex-col gap-2 py-2">
        {column.cards.map((card) => (
          <div
            key={card.id}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData("text/plain", card.id);
              onCardDragStart(card.id);
            }}
            className="group cursor-grab rounded-md bg-white p-2 text-sm shadow-sm hover:shadow-md"
          >
            <div className="flex items-start gap-2">
              <span className="flex-1">{card.text}</span>
              <button
                onClick={() => onRemoveCard(card.id)}
                className="invisible text-xs text-red-500 group-hover:visible"
              >
                ×
              </button>
            </div>
          </div>
        ))}
      </div>
      {adding ? (
        <div className="space-y-1">
          <textarea
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="w-full rounded border p-2 text-sm"
            rows={2}
          />
          <div className="flex gap-2">
            <button
              onClick={() => {
                onAddCard(text);
                setText("");
                setAdding(false);
              }}
              className="rounded bg-blue-500 px-3 py-1 text-sm text-white"
            >
              追加
            </button>
            <button
              onClick={() => {
                setAdding(false);
                setText("");
              }}
              className="rounded px-3 py-1 text-sm text-gray-600"
            >
              キャンセル
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="rounded px-2 py-1 text-left text-sm text-gray-600 hover:bg-gray-200"
        >
          + カード追加
        </button>
      )}
    </div>
  );
}
