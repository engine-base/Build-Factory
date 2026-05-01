"use client";

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

export function TableView({ data, onChange }: Props) {
  const columns = Array.isArray(data.columns) ? (data.columns as string[]) : [];
  const rows = Array.isArray(data.rows) ? (data.rows as string[][]) : [];

  const updateCell = (r: number, c: number, val: string) => {
    const next = rows.map((row, ri) =>
      ri === r ? row.map((cell, ci) => (ci === c ? val : cell)) : row,
    );
    onChange?.({ ...data, rows: next });
  };

  const addRow = () => {
    const empty = columns.map(() => "");
    onChange?.({ ...data, rows: [...rows, empty] });
  };

  const removeRow = (r: number) => {
    onChange?.({ ...data, rows: rows.filter((_, ri) => ri !== r) });
  };

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              {columns.map((c, i) => (
                <th key={i} className="border px-2 py-1 text-left font-semibold">
                  {c}
                </th>
              ))}
              <th className="border px-2 py-1 w-10"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className="group hover:bg-gray-50">
                {row.map((cell, ci) => (
                  <td key={ci} className="border px-1">
                    <input
                      value={cell}
                      onChange={(e) => updateCell(ri, ci, e.target.value)}
                      className="w-full bg-transparent px-1 py-1 outline-none focus:bg-yellow-50"
                    />
                  </td>
                ))}
                <td className="border text-center">
                  <button
                    onClick={() => removeRow(ri)}
                    className="invisible text-xs text-red-500 group-hover:visible"
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        onClick={addRow}
        className="rounded border border-dashed px-3 py-1 text-sm text-gray-600 hover:bg-gray-50"
      >
        + 行を追加
      </button>
    </div>
  );
}
