"use client";

import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { useState } from "react";

type ChartKind = "bar" | "line" | "pie";

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6"];

export function ChartView({ data, onChange }: Props) {
  const initialKind = (data.kind as ChartKind) || "bar";
  const [kind, setKind] = useState<ChartKind>(initialKind);
  const rows = Array.isArray(data.rows) ? (data.rows as Record<string, unknown>[]) : [];
  const xKey = (data.x as string) || (rows[0] ? Object.keys(rows[0])[0] : "name");
  const yKeys = Array.isArray(data.y) ? (data.y as string[]) : (
    rows[0] ? Object.keys(rows[0]).filter((k) => k !== xKey) : []
  );

  const setKindAndPersist = (k: ChartKind) => {
    setKind(k);
    onChange?.({ ...data, kind: k });
  };

  if (rows.length === 0) {
    return <div className="text-sm text-gray-500">データがありません</div>;
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-1">
        {(["bar", "line", "pie"] as ChartKind[]).map((k) => (
          <button
            key={k}
            onClick={() => setKindAndPersist(k)}
            className={`rounded px-3 py-1 text-xs ${
              kind === k ? "bg-blue-500 text-white" : "bg-gray-100 hover:bg-gray-200"
            }`}
          >
            {k}
          </button>
        ))}
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          {kind === "bar" ? (
            <BarChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey} />
              <YAxis />
              <Tooltip />
              <Legend />
              {yKeys.map((k, i) => (
                <Bar key={k} dataKey={k} fill={COLORS[i % COLORS.length]} />
              ))}
            </BarChart>
          ) : kind === "line" ? (
            <LineChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey} />
              <YAxis />
              <Tooltip />
              <Legend />
              {yKeys.map((k, i) => (
                <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]} />
              ))}
            </LineChart>
          ) : (
            <PieChart>
              <Tooltip />
              <Legend />
              <Pie
                data={rows}
                dataKey={yKeys[0] || "value"}
                nameKey={xKey}
                outerRadius={100}
                label
              >
                {rows.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
