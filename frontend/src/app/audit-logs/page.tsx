// T-018-02: audit_log_viewer UI (検索 + before/after diff + CSV/JSON export)
//
// AC マッピング:
//   AC-1 UBIQUITOUS: feature F-018 として audit_logs 一覧 + 検索 + 詳細 diff
//   AC-2 EVENT-DRIVEN: 検索クエリ変更で /api/audit-logs に GET / export trigger
//   AC-3 STATE-DRIVEN: RLS 経由 (workspace_id 紐付け) + read-only view
//   AC-4 UNWANTED: invalid filter / unauthorized → 4xx 表示

"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Download, FileText, ChevronRight, AlertTriangle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

type AuditLog = {
  id: number;
  workspace_id?: number;
  event_type: string;
  actor_id?: string;
  detail: Record<string, unknown>;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  created_at: string;
};

export default function AuditLogViewerPage() {
  const [query, setQuery] = useState("");
  const [eventType, setEventType] = useState("");
  const [selected, setSelected] = useState<AuditLog | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: logs = [] } = useQuery<AuditLog[]>({
    queryKey: ["audit-logs", query, eventType],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (query) params.set("q", query);
      if (eventType) params.set("event_type", eventType);
      const r = await fetch(`${API}/api/audit-logs?${params}`);
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail?.message ?? `fetch failed (${r.status})`);
      }
      setErrorMessage(null);
      return r.json();
    },
  });

  const exportTo = async (fmt: "csv" | "json") => {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (eventType) params.set("event_type", eventType);
    params.set("format", fmt);
    const r = await fetch(`${API}/api/audit-logs/export?${params}`);
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      setErrorMessage(body?.detail?.message ?? `export failed (${r.status})`);
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-logs.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-4 flex items-center gap-2 text-eb-500">
        <FileText className="w-6 h-6" /> 監査ログ
      </h1>

      {errorMessage && (
        <div className="mb-4 p-3 bg-red-100 border border-red-300 text-red-700 rounded flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {errorMessage}
        </div>
      )}

      <div className="mb-4 flex gap-2 items-center">
        <div className="flex-1 flex gap-2 items-center border rounded p-2">
          <Search className="w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search logs..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="flex-1 focus:outline-none"
          />
        </div>
        <select
          value={eventType}
          onChange={e => setEventType(e.target.value)}
          className="p-2 border rounded focus:border-eb-500"
        >
          <option value="">All events</option>
          <option value="schema_change">schema_change</option>
          <option value="auth.login">auth.login</option>
          <option value="m27.handoff">m27.handoff</option>
          <option value="memory.context_built">memory.context_built</option>
        </select>
        <button
          onClick={() => exportTo("csv")}
          className="px-3 py-2 border rounded flex items-center gap-1 hover:border-eb-500"
        >
          <Download className="w-4 h-4" /> CSV
        </button>
        <button
          onClick={() => exportTo("json")}
          className="px-3 py-2 border rounded flex items-center gap-1 hover:border-eb-500"
        >
          <Download className="w-4 h-4" /> JSON
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 space-y-1 max-h-[70vh] overflow-y-auto">
          {logs.map(l => (
            <button
              key={l.id}
              onClick={() => setSelected(l)}
              className={`w-full text-left p-2 border rounded hover:border-eb-500 ${selected?.id === l.id ? 'border-eb-500 bg-eb-50' : ''}`}
            >
              <div className="flex justify-between items-center text-xs">
                <span className="font-mono">{l.created_at}</span>
                <ChevronRight className="w-3 h-3" />
              </div>
              <div className="font-medium text-sm">{l.event_type}</div>
              <div className="text-xs text-gray-500">actor: {l.actor_id ?? "system"}</div>
            </button>
          ))}
        </div>

        {selected && (
          <div className="border rounded p-4 sticky top-4 max-h-[70vh] overflow-y-auto">
            <h2 className="font-bold mb-2">{selected.event_type}</h2>
            <div className="text-xs text-gray-500 mb-3">{selected.created_at}</div>
            <h3 className="font-medium text-sm mt-2">Before</h3>
            <pre className="text-xs bg-red-50 p-2 rounded overflow-auto">
              {JSON.stringify(selected.before ?? {}, null, 2)}
            </pre>
            <h3 className="font-medium text-sm mt-2">After</h3>
            <pre className="text-xs bg-eb-50 p-2 rounded overflow-auto">
              {JSON.stringify(selected.after ?? {}, null, 2)}
            </pre>
            <h3 className="font-medium text-sm mt-2">Detail</h3>
            <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto">
              {JSON.stringify(selected.detail, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
