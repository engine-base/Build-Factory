"use client";

interface Task {
  id: string;
  name: string;
  start: string; // YYYY-MM-DD
  end: string;
  progress?: number; // 0-100
  color?: string;
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

function dayDiff(a: string, b: string): number {
  const da = new Date(a).getTime();
  const db = new Date(b).getTime();
  return Math.round((db - da) / (24 * 3600 * 1000));
}

function fmt(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function GanttView({ data, onChange }: Props) {
  const tasks = Array.isArray(data.tasks) ? (data.tasks as Task[]) : [];
  if (tasks.length === 0) {
    return <div className="text-sm text-gray-500">タスクがありません</div>;
  }

  const minStart = tasks.reduce(
    (m, t) => (t.start < m ? t.start : m), tasks[0].start,
  );
  const maxEnd = tasks.reduce(
    (m, t) => (t.end > m ? t.end : m), tasks[0].end,
  );
  const totalDays = Math.max(1, dayDiff(minStart, maxEnd) + 1);
  const dayPx = Math.max(20, Math.min(40, 800 / totalDays));

  // 日付ヘッダ
  const dates: string[] = [];
  for (let i = 0; i < totalDays; i++) {
    const d = new Date(minStart);
    d.setDate(d.getDate() + i);
    dates.push(fmt(d));
  }

  const setProgress = (i: number, progress: number) => {
    const next = tasks.map((t, idx) =>
      idx === i ? { ...t, progress: Math.max(0, Math.min(100, progress)) } : t,
    );
    onChange?.({ ...data, tasks: next });
  };

  return (
    <div className="overflow-x-auto">
      <div className="min-w-fit">
        {/* 日付ヘッダ */}
        <div className="flex border-b text-[10px] text-gray-500">
          <div className="w-40 shrink-0 border-r px-2 py-1">タスク</div>
          {dates.map((d) => (
            <div
              key={d}
              style={{ width: dayPx }}
              className="shrink-0 border-r px-1 py-1 text-center"
            >
              {d.slice(5)}
            </div>
          ))}
        </div>
        {/* タスク行 */}
        {tasks.map((t, i) => {
          const offset = dayDiff(minStart, t.start);
          const span = Math.max(1, dayDiff(t.start, t.end) + 1);
          return (
            <div key={t.id || i} className="flex items-center border-b py-1">
              <div className="w-40 shrink-0 truncate border-r px-2 text-xs" title={t.name}>
                {t.name}
              </div>
              <div className="relative flex-1" style={{ width: totalDays * dayPx }}>
                <div
                  className="absolute h-5 rounded shadow-sm"
                  style={{
                    left: offset * dayPx,
                    width: span * dayPx - 4,
                    background: t.color || "#3b82f6",
                    top: 2,
                  }}
                  title={`${t.start} → ${t.end}`}
                >
                  {typeof t.progress === "number" && (
                    <div
                      className="h-full rounded bg-white/30"
                      style={{ width: `${t.progress}%` }}
                    />
                  )}
                  <div className="absolute inset-0 flex items-center justify-center px-2 text-[10px] text-white">
                    {t.name}
                    {typeof t.progress === "number" && (
                      <span className="ml-2 opacity-80">{t.progress}%</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="ml-2 shrink-0">
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={t.progress ?? 0}
                  onChange={(e) => setProgress(i, parseInt(e.target.value || "0", 10))}
                  className="w-14 rounded border px-1 text-xs"
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
