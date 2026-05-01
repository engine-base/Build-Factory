"use client";

import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import { Bot, CheckSquare, Calendar, Clock } from "lucide-react";

const API = "http://localhost:8001";

export default function BriefingPage() {
  const { data: briefingText = "", isLoading } = useQuery({
    queryKey: ["briefing-latest"],
    queryFn: () => fetch(`${API}/api/briefing/latest`).then(r => r.text()),
    refetchInterval: 60000,
  });

  const { data: pending = [] } = useQuery({
    queryKey: ["approval-pending"],
    queryFn: () => fetch(`${API}/api/approval?status=pending`).then(r => r.json()),
    refetchInterval: 15000,
  });

  const { data: employees = [] } = useQuery({
    queryKey: ["ai-employees"],
    queryFn: () => fetch(`${API}/api/ai-employees/status`).then(r => r.json()),
    refetchInterval: 10000,
  });

  const { data: schedules = [] } = useQuery({
    queryKey: ["schedules"],
    queryFn: () => fetch(`${API}/api/schedule`).then(r => r.json()),
  });

  const activeEmployees = employees.filter((e: any) => e.computed_status !== "idle");
  const todaySchedules = schedules.filter((s: any) => s.is_active && s.frequency === "daily");

  const kpis = [
    { label: "承認待ち", value: Array.isArray(pending) ? pending.length : 0, color: "var(--eb-primary)", icon: CheckSquare },
    { label: "AI社員稼働", value: `${activeEmployees.length}/${employees.length}`, color: "var(--eb-success)", icon: Bot },
    { label: "今日のタスク", value: todaySchedules.length, color: "var(--eb-tertiary)", icon: Calendar },
  ];

  const handleRunBriefing = async () => {
    await fetch(`${API}/api/briefing/run`, { method: "POST" });
    setTimeout(() => window.location.reload(), 35000);
  };

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
            今日のブリーフィング
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--eb-neutral)" }}>
            {new Date().toLocaleDateString("ja-JP", { year: "numeric", month: "long", day: "numeric", weekday: "long" })}
          </p>
        </div>
        <button
          onClick={handleRunBriefing}
          className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-semibold text-white transition-opacity hover:opacity-85"
          style={{ background: "var(--eb-primary)", fontFamily: "var(--font-inter)" }}
        >
          <Clock className="w-4 h-4" />
          今すぐ生成
        </button>
      </div>

      {/* KPI カード */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {kpis.map(({ label, value, color, icon: Icon }) => (
          <div key={label}
            className="rounded-lg p-5"
            style={{ background: "#fff", border: "1px solid var(--eb-border)", boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}
          >
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                {label}
              </p>
              <Icon className="w-4 h-4" style={{ color }} />
            </div>
            <p className="text-3xl font-bold" style={{ color, fontFamily: "var(--font-inter)" }}>{value}</p>
          </div>
        ))}
      </div>

      {/* ブリーフィング本文 */}
      <div
        className="rounded-xl p-8"
        style={{ background: "var(--eb-primary-container)", color: "var(--eb-on-primary-container)" }}
      >
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--eb-neutral)" }}>
            <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
            読み込み中...
          </div>
        ) : briefingText && briefingText !== "本日のブリーフィングはまだ生成されていません" ? (
          <div className="prose prose-sm max-w-none" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
            <ReactMarkdown>{briefingText}</ReactMarkdown>
          </div>
        ) : (
          <div className="text-center py-8">
            <Bot className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p className="text-sm font-medium mb-1">ブリーフィングがまだ生成されていません</p>
            <p className="text-xs opacity-60">「今すぐ生成」ボタンを押すか、毎朝8時に自動生成されます</p>
          </div>
        )}
      </div>
    </div>
  );
}
