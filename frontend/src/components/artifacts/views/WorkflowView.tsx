"use client";

interface Step {
  id: string;
  title: string;
  status?: "pending" | "active" | "done" | "skipped" | "failed";
  note?: string;
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

const STATUS_STYLE: Record<string, string> = {
  pending:  "bg-gray-100 text-gray-600 border-gray-300",
  active:   "bg-blue-100 text-blue-800 border-blue-400",
  done:     "bg-green-100 text-green-800 border-green-400",
  skipped:  "bg-gray-50 text-gray-400 border-gray-200 line-through",
  failed:   "bg-red-100 text-red-700 border-red-400",
};

export function WorkflowView({ data, onChange }: Props) {
  const steps = Array.isArray(data.steps) ? (data.steps as Step[]) : [];

  const cycleStatus = (i: number) => {
    const order: Step["status"][] = ["pending", "active", "done", "skipped", "failed"];
    const cur = steps[i].status || "pending";
    const next = order[(order.indexOf(cur) + 1) % order.length];
    const updated = steps.map((s, idx) => idx === i ? { ...s, status: next } : s);
    onChange?.({ ...data, steps: updated });
  };

  if (steps.length === 0) {
    return <div className="text-sm text-gray-500">ステップがありません</div>;
  }

  return (
    <div className="flex flex-col gap-2">
      {steps.map((s, i) => (
        <div key={s.id || i} className="flex items-start gap-3">
          <div className="flex flex-col items-center">
            <div
              className={`flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border text-xs font-bold ${STATUS_STYLE[s.status || "pending"]}`}
              onClick={() => cycleStatus(i)}
              title="クリックで状態変更"
            >
              {i + 1}
            </div>
            {i < steps.length - 1 && (
              <div className="h-6 w-px bg-gray-300" />
            )}
          </div>
          <div className="flex-1 pb-2">
            <div
              className={`rounded border px-3 py-2 ${STATUS_STYLE[s.status || "pending"]}`}
            >
              <div className="text-sm font-medium">{s.title}</div>
              {s.note && <div className="mt-0.5 text-[11px] opacity-80">{s.note}</div>}
            </div>
          </div>
        </div>
      ))}
      <p className="text-[10px] text-gray-500">番号バッジをクリックで pending → active → done → skipped → failed</p>
    </div>
  );
}
