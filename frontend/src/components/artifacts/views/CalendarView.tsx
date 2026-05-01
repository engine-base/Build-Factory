"use client";

import { useState } from "react";

interface Event {
  id: string;
  title: string;
  date: string; // YYYY-MM-DD
  color?: string;
  note?: string;
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

function startOfMonth(year: number, month: number): Date {
  return new Date(year, month, 1);
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function fmt(y: number, m: number, d: number): string {
  return `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export function CalendarView({ data, onChange }: Props) {
  const events = Array.isArray(data.events) ? (data.events as Event[]) : [];
  const initial = (data.cursor as string) || (events[0]?.date ?? new Date().toISOString().slice(0, 10));
  const initialDate = new Date(initial);
  const [year, setYear] = useState(initialDate.getFullYear());
  const [month, setMonth] = useState(initialDate.getMonth());

  const first = startOfMonth(year, month).getDay();
  const total = daysInMonth(year, month);
  const cells: (number | null)[] = [
    ...Array(first).fill(null),
    ...Array.from({ length: total }, (_, i) => i + 1),
  ];

  const eventsByDay: Record<string, Event[]> = {};
  for (const ev of events) {
    eventsByDay[ev.date] ??= [];
    eventsByDay[ev.date].push(ev);
  }

  const addEvent = (date: string) => {
    const title = prompt("予定のタイトル");
    if (!title) return;
    const next: Event[] = [
      ...events,
      { id: `e-${Date.now()}`, title, date, color: "#3b82f6" },
    ];
    onChange?.({ ...data, events: next });
  };

  const removeEvent = (id: string) => {
    onChange?.({ ...data, events: events.filter((e) => e.id !== id) });
  };

  const move = (delta: number) => {
    let m = month + delta;
    let y = year;
    if (m < 0) { m = 11; y -= 1; }
    if (m > 11) { m = 0; y += 1; }
    setYear(y); setMonth(m);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <button onClick={() => move(-1)} className="rounded px-2 py-1 text-sm hover:bg-gray-100">◀</button>
        <span className="font-semibold text-sm">{year} 年 {month + 1} 月</span>
        <button onClick={() => move(1)} className="rounded px-2 py-1 text-sm hover:bg-gray-100">▶</button>
      </div>
      <div className="grid grid-cols-7 text-[10px] text-gray-500">
        {["日","月","火","水","木","金","土"].map((d) => (
          <div key={d} className="px-1 py-1 text-center">{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-px bg-gray-200">
        {cells.map((d, i) => {
          if (d === null) return <div key={i} className="bg-gray-50 min-h-[60px]" />;
          const date = fmt(year, month, d);
          const evs = eventsByDay[date] || [];
          return (
            <div
              key={i}
              className="bg-white p-1 min-h-[80px] cursor-pointer hover:bg-blue-50 group"
              onClick={() => addEvent(date)}
            >
              <div className="text-[10px] font-medium text-gray-700">{d}</div>
              <div className="space-y-0.5 mt-0.5">
                {evs.map((ev) => (
                  <div
                    key={ev.id}
                    className="group/ev flex items-center gap-1 rounded px-1 py-0.5 text-[10px] text-white truncate"
                    style={{ background: ev.color || "#3b82f6" }}
                    onClick={(e) => { e.stopPropagation(); }}
                  >
                    <span className="flex-1 truncate">{ev.title}</span>
                    <button
                      onClick={(e) => { e.stopPropagation(); removeEvent(ev.id); }}
                      className="hidden group-hover/ev:inline text-white/80 hover:text-white"
                    >×</button>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-gray-500">セルをクリックで予定追加・予定にホバーで × で削除</p>
    </div>
  );
}
