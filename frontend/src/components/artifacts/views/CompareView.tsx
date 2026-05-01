"use client";

interface CompareItem {
  name: string;
  values: Record<string, string | number | boolean>;
  highlight?: boolean;
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

export function CompareView({ data, onChange }: Props) {
  const items = Array.isArray(data.items) ? (data.items as CompareItem[]) : [];
  const criteria = Array.isArray(data.criteria) ? (data.criteria as string[]) : (
    items[0] ? Object.keys(items[0].values || {}) : []
  );

  if (items.length === 0) {
    return <div className="text-sm text-gray-500">比較対象がありません</div>;
  }

  const toggleHighlight = (i: number) => {
    const next = items.map((it, idx) => idx === i ? { ...it, highlight: !it.highlight } : it);
    onChange?.({ ...data, items: next });
  };

  const renderCell = (v: unknown) => {
    if (typeof v === "boolean") return v ? "✓" : "—";
    if (v === null || v === undefined) return "—";
    return String(v);
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50">
            <th className="border px-3 py-2 text-left">項目</th>
            {items.map((it, i) => (
              <th
                key={i}
                onClick={() => toggleHighlight(i)}
                className={`cursor-pointer border px-3 py-2 text-left ${
                  it.highlight ? "bg-yellow-100" : ""
                }`}
                title="クリックで強調"
              >
                {it.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {criteria.map((c) => (
            <tr key={c}>
              <td className="border px-3 py-2 font-medium">{c}</td>
              {items.map((it, i) => (
                <td
                  key={i}
                  className={`border px-3 py-2 ${it.highlight ? "bg-yellow-50" : ""}`}
                >
                  {renderCell(it.values?.[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[10px] text-gray-500">列ヘッダクリックで強調 ON/OFF</p>
    </div>
  );
}
