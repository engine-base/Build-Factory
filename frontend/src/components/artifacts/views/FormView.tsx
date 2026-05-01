"use client";

import { useState, useEffect } from "react";

interface Field {
  id: string;
  type: "text" | "textarea" | "number" | "date" | "select" | "checkbox";
  label: string;
  options?: string[];
  required?: boolean;
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

export function FormView({ data, onChange }: Props) {
  const fields = Array.isArray(data.fields) ? (data.fields as Field[]) : [];
  const initial = (data.values as Record<string, unknown>) || {};
  const [values, setValues] = useState<Record<string, unknown>>(initial);

  useEffect(() => {
    setValues(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(initial)]);

  const set = (id: string, v: unknown) => {
    const next = { ...values, [id]: v };
    setValues(next);
    onChange?.({ ...data, values: next });
  };

  if (fields.length === 0) {
    return <div className="text-sm text-gray-500">フィールドがありません</div>;
  }

  return (
    <form className="space-y-3" onSubmit={(e) => e.preventDefault()}>
      {fields.map((f) => (
        <div key={f.id}>
          <label className="block text-xs font-semibold text-gray-700">
            {f.label}{f.required && <span className="text-red-500"> *</span>}
          </label>
          {f.type === "textarea" ? (
            <textarea
              value={String(values[f.id] ?? "")}
              onChange={(e) => set(f.id, e.target.value)}
              className="mt-1 w-full rounded border px-2 py-1 text-sm"
              rows={3}
            />
          ) : f.type === "select" ? (
            <select
              value={String(values[f.id] ?? "")}
              onChange={(e) => set(f.id, e.target.value)}
              className="mt-1 w-full rounded border px-2 py-1 text-sm"
            >
              <option value="">--</option>
              {(f.options || []).map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          ) : f.type === "checkbox" ? (
            <input
              type="checkbox"
              checked={!!values[f.id]}
              onChange={(e) => set(f.id, e.target.checked)}
              className="mt-1 h-4 w-4"
            />
          ) : (
            <input
              type={f.type}
              value={String(values[f.id] ?? "")}
              onChange={(e) => set(f.id, f.type === "number" ? parseFloat(e.target.value) : e.target.value)}
              className="mt-1 w-full rounded border px-2 py-1 text-sm"
            />
          )}
        </div>
      ))}
    </form>
  );
}
