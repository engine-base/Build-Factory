"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";

const API = "http://localhost:8001";

type Log = {
  id: number;
  skill_name: string;
  status: string;
  duration_sec?: number;
  started_at: string;
  finished_at?: string;
  output?: string;
  error_message?: string;
};

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  completed: { label: "完了", color: "#16A34A", bg: "#DCFCE7" },
  failed:    { label: "失敗", color: "#DC2626", bg: "#FEE2E2" },
  running:   { label: "実行中", color: "#004CD9", bg: "#DBEAFE" },
};

export default function LogsPage() {
  const [filter, setFilter] = useState<string>("all");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const PER_PAGE = 20;

  const { data: logs = [], isLoading } = useQuery<Log[]>({
    queryKey: ["logs-all"],
    queryFn: () => fetch(`${API}/api/logs?limit=200`).then(r => r.json()),
    refetchInterval: 15000,
  });

  const filtered = filter === "all" ? logs : logs.filter(l => l.status === filter);
  const total = filtered.length;
  const paginated = filtered.slice(page * PER_PAGE, (page + 1) * PER_PAGE);
  const totalPages = Math.ceil(total / PER_PAGE);

  const counts = {
    all: logs.length,
    completed: logs.filter(l => l.status === "completed").length,
    failed: logs.filter(l => l.status === "failed").length,
    running: logs.filter(l => l.status === "running").length,
  };

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-2xl font-bold mb-6" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>実行ログ</h1>

      {/* Filter */}
      <div className="flex gap-2 mb-6">
        {(["all", "completed", "failed", "running"] as const).map(f => (
          <button key={f} onClick={() => { setFilter(f); setPage(0); }}
            className="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
            style={{
              background: filter === f ? "var(--eb-primary)" : "var(--eb-surface-variant)",
              color: filter === f ? "#fff" : "var(--eb-neutral)",
              fontFamily: "var(--font-inter)"
            }}>
            {f === "all" ? "すべて" : STATUS_CONFIG[f]?.label ?? f}
            <span className="ml-1.5 opacity-70">({counts[f]})</span>
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--eb-neutral)" }}>
          <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          読み込み中...
        </div>
      ) : paginated.length === 0 ? (
        <div className="text-center py-12 text-sm" style={{ color: "var(--eb-neutral)" }}>
          ログがありません
        </div>
      ) : (
        <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--eb-border)" }}>
          <table className="w-full text-xs">
            <thead>
              <tr style={{ background: "var(--eb-surface-variant)" }}>
                {["スキル", "ステータス", "所要時間", "実行開始", ""].map((h, i) => (
                  <th key={i} className="text-left px-4 py-2.5 font-semibold"
                    style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)", letterSpacing: "0.05em" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paginated.map(log => {
                const st = STATUS_CONFIG[log.status] ?? { label: log.status, color: "#6B7280", bg: "#F3F4F6" };
                const isExpanded = expandedId === log.id;
                return (
                  <React.Fragment key={log.id}>
                    <tr style={{ borderTop: "1px solid var(--eb-border)" }}>
                      <td className="px-4 py-3 font-medium" style={{ fontFamily: "var(--font-inter)" }}>{log.skill_name}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold"
                          style={{ background: st.bg, color: st.color, fontFamily: "var(--font-inter)" }}>
                          {st.label}
                        </span>
                      </td>
                      <td className="px-4 py-3" style={{ fontFamily: "var(--font-inter)", color: "var(--eb-neutral)" }}>
                        {log.duration_sec != null ? `${log.duration_sec}秒` : "—"}
                      </td>
                      <td className="px-4 py-3" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                        {log.started_at ? new Date(log.started_at).toLocaleString("ja-JP") : "—"}
                      </td>
                      <td className="px-4 py-3">
                        {(log.output || log.error_message) && (
                          <button onClick={() => setExpandedId(isExpanded ? null : log.id)}
                            className="p-1 rounded transition-opacity hover:opacity-70"
                            style={{ color: "var(--eb-neutral)" }}>
                            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          </button>
                        )}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr style={{ borderTop: "1px solid var(--eb-border)", background: "var(--eb-surface-variant)" }}>
                        <td colSpan={5} className="px-4 py-3">
                          {log.error_message && (
                            <div className="mb-2">
                              <p className="text-[10px] font-bold mb-1" style={{ color: "var(--eb-error)" }}>エラー</p>
                              <pre className="text-[11px] p-2 rounded overflow-auto max-h-32"
                                style={{ background: "#FEE2E2", color: "#991B1B", fontFamily: "var(--font-inter)" }}>
                                {log.error_message}
                              </pre>
                            </div>
                          )}
                          {log.output && (
                            <div>
                              <p className="text-[10px] font-bold mb-1" style={{ color: "var(--eb-neutral)" }}>出力</p>
                              <pre className="text-[11px] p-2 rounded overflow-auto max-h-48"
                                style={{ background: "#fff", color: "#374151", fontFamily: "var(--font-inter)", border: "1px solid var(--eb-border)" }}>
                                {log.output}
                              </pre>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-xs" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
            {total}件中 {page * PER_PAGE + 1}〜{Math.min((page + 1) * PER_PAGE, total)}件を表示
          </span>
          <div className="flex gap-2">
            <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
              className="px-3 py-1.5 rounded-md text-xs font-semibold disabled:opacity-40"
              style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
              前へ
            </button>
            <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
              className="px-3 py-1.5 rounded-md text-xs font-semibold disabled:opacity-40"
              style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
              次へ
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
