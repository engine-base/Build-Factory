"use client";

interface Metric {
  label: string;
  value: number | string;
  unit?: string;
  delta?: number;
  trend?: "up" | "down" | "flat";
}

interface Props {
  data: Record<string, unknown>;
}

export function KpiCardView({ data }: Props) {
  const metrics = Array.isArray(data.metrics) ? (data.metrics as Metric[]) : [];
  if (metrics.length === 0 && (data.label || data.value)) {
    metrics.push(data as unknown as Metric);
  }

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
      {metrics.map((m, i) => (
        <div key={i} className="rounded-lg border bg-white p-4">
          <div className="text-xs uppercase tracking-wide text-gray-500">
            {m.label}
          </div>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-2xl font-bold">
              {typeof m.value === "number" ? m.value.toLocaleString() : m.value}
            </span>
            {m.unit && <span className="text-sm text-gray-500">{m.unit}</span>}
          </div>
          {typeof m.delta === "number" && (
            <div
              className={`mt-1 text-xs ${
                m.delta > 0
                  ? "text-green-600"
                  : m.delta < 0
                  ? "text-red-600"
                  : "text-gray-500"
              }`}
            >
              {m.delta > 0 ? "▲" : m.delta < 0 ? "▼" : "─"}{" "}
              {Math.abs(m.delta).toLocaleString()}
            </div>
          )}
        </div>
      ))}
      {metrics.length === 0 && (
        <div className="text-sm text-gray-500">
          KPI データが空です
        </div>
      )}
    </div>
  );
}
