"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Play, Pause, Plus, Clock, Zap } from "lucide-react";

const API = "http://localhost:8001";

type Schedule = {
  id: number;
  skill_name: string;
  frequency: string;
  scheduled_time?: string;
  is_active: boolean;
  last_run?: string;
  next_run?: string;
};

type Employee = {
  id: number;
  display_name: string;
  category: string;
  autonomy_level: number;
  computed_status: string;
};

const FREQ_LABEL: Record<string, string> = {
  daily: "毎日",
  weekly: "毎週",
  manual: "手動のみ",
};

export default function SchedulePage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"schedule" | "autonomy">("schedule");
  const [showAdd, setShowAdd] = useState(false);
  const [newSkill, setNewSkill] = useState("");
  const [newFreq, setNewFreq] = useState("daily");
  const [newTime, setNewTime] = useState("09:00");

  const { data: schedules = [] } = useQuery<Schedule[]>({
    queryKey: ["schedules"],
    queryFn: () => fetch(`${API}/api/schedule`).then(r => r.json()),
    refetchInterval: 30000,
  });

  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey: ["ai-employees"],
    queryFn: () => fetch(`${API}/api/ai-employees/status`).then(r => r.json()),
    refetchInterval: 30000,
  });

  const toggleSchedule = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      fetch(`${API}/api/schedule/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active }),
      }).then(r => r.json()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });

  const addSchedule = useMutation({
    mutationFn: () =>
      fetch(`${API}/api/schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill_name: newSkill, frequency: newFreq, scheduled_time: newTime, is_active: true }),
      }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedules"] });
      setShowAdd(false);
      setNewSkill("");
    },
  });

  const updateAutonomy = useMutation({
    mutationFn: ({ id, level }: { id: number; level: number }) =>
      fetch(`${API}/api/ai-employees/${id}/autonomy`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ autonomy_level: level }),
      }).then(r => r.json()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-employees"] }),
  });

  const runNow = useMutation({
    mutationFn: (skillName: string) =>
      fetch(`${API}/api/schedule/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill_name: skillName }),
      }).then(r => r.json()),
  });

  const AUTONOMY_LABELS = ["完全承認制", "重要のみ確認", "自律実行"];

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="text-2xl font-bold mb-6" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>スケジュール管理</h1>

      {/* Tab */}
      <div className="flex gap-1 mb-6 p-1 rounded-lg w-fit" style={{ background: "var(--eb-surface-variant)" }}>
        {(["schedule", "autonomy"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className="px-4 py-1.5 rounded-md text-xs font-semibold transition-colors"
            style={{
              background: tab === t ? "#fff" : "transparent",
              color: tab === t ? "var(--eb-primary)" : "var(--eb-neutral)",
              boxShadow: tab === t ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
              fontFamily: "var(--font-inter)"
            }}>
            {t === "schedule" ? "スケジュール設定" : "自律度設定"}
          </button>
        ))}
      </div>

      {tab === "schedule" && (
        <>
          <div className="rounded-xl overflow-hidden mb-4" style={{ border: "1px solid var(--eb-border)" }}>
            <table className="w-full text-xs">
              <thead>
                <tr style={{ background: "var(--eb-surface-variant)" }}>
                  {["スキル", "頻度", "実行時刻", "最終実行", "状態", "操作"].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 font-semibold"
                      style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)", letterSpacing: "0.05em" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {schedules.map(s => (
                  <tr key={s.id} style={{ borderTop: "1px solid var(--eb-border)" }}>
                    <td className="px-4 py-3 font-medium" style={{ fontFamily: "var(--font-inter)" }}>{s.skill_name}</td>
                    <td className="px-4 py-3" style={{ color: "var(--eb-neutral)" }}>{FREQ_LABEL[s.frequency] ?? s.frequency}</td>
                    <td className="px-4 py-3" style={{ fontFamily: "var(--font-inter)" }}>
                      {s.scheduled_time ?? <span style={{ color: "var(--eb-neutral)" }}>—</span>}
                    </td>
                    <td className="px-4 py-3" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                      {s.last_run ? new Date(s.last_run).toLocaleString("ja-JP", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "未実行"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold"
                        style={{
                          background: s.is_active ? "#DCFCE7" : "var(--eb-surface-variant)",
                          color: s.is_active ? "#16A34A" : "var(--eb-neutral)",
                          fontFamily: "var(--font-inter)"
                        }}>
                        {s.is_active ? "有効" : "無効"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleSchedule.mutate({ id: s.id, is_active: !s.is_active })}
                          className="p-1 rounded transition-opacity hover:opacity-70"
                          style={{ color: s.is_active ? "var(--eb-warning)" : "var(--eb-success)" }}
                          title={s.is_active ? "無効化" : "有効化"}
                        >
                          {s.is_active ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                        </button>
                        <button
                          onClick={() => runNow.mutate(s.skill_name)}
                          className="p-1 rounded transition-opacity hover:opacity-70"
                          style={{ color: "var(--eb-primary)" }}
                          title="今すぐ実行"
                        >
                          <Zap className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button onClick={() => setShowAdd(!showAdd)}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-semibold transition-opacity hover:opacity-80"
            style={{ background: "var(--eb-primary)", color: "#fff", fontFamily: "var(--font-inter)" }}>
            <Plus className="w-4 h-4" />
            スケジュールを追加
          </button>

          {showAdd && (
            <div className="mt-4 p-5 rounded-xl" style={{ border: "1px solid var(--eb-border)", background: "#fff" }}>
              <h3 className="text-sm font-bold mb-4" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>新しいスケジュール</h3>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div>
                  <label className="block text-xs font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>スキル名</label>
                  <input value={newSkill} onChange={e => setNewSkill(e.target.value)} placeholder="例: secretary"
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ border: "1px solid var(--eb-border)", fontFamily: "var(--font-inter)", outline: "none" }} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>頻度</label>
                  <select value={newFreq} onChange={e => setNewFreq(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ border: "1px solid var(--eb-border)", fontFamily: "var(--font-inter)", outline: "none" }}>
                    <option value="daily">毎日</option>
                    <option value="weekly">毎週</option>
                    <option value="manual">手動のみ</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>実行時刻</label>
                  <input type="time" value={newTime} onChange={e => setNewTime(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ border: "1px solid var(--eb-border)", fontFamily: "var(--font-inter)", outline: "none" }} />
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setShowAdd(false)}
                  className="px-4 py-2 rounded-md text-sm font-semibold"
                  style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                  キャンセル
                </button>
                <button onClick={() => addSchedule.mutate()} disabled={!newSkill.trim() || addSchedule.isPending}
                  className="px-4 py-2 rounded-md text-sm font-semibold text-white disabled:opacity-50"
                  style={{ background: "var(--eb-primary)", fontFamily: "var(--font-inter)" }}>
                  {addSchedule.isPending ? "追加中..." : "追加"}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {tab === "autonomy" && (
        <div className="space-y-4">
          <p className="text-sm mb-4" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
            各AI社員の自律度を設定します。自律度が高いほど、承認なしで実行できる範囲が広がります。
          </p>
          {employees.map(emp => (
            <div key={emp.id} className="rounded-xl p-5 bg-white" style={{ border: "1px solid var(--eb-border)", boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="font-semibold text-sm" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{emp.display_name}</p>
                  <p className="text-xs" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>{emp.category}</p>
                </div>
                <span className="text-xs font-bold px-3 py-1 rounded-full"
                  style={{
                    background: emp.autonomy_level === 2 ? "#DCFCE7" : emp.autonomy_level === 1 ? "#FEF9C3" : "#FEE2E2",
                    color: emp.autonomy_level === 2 ? "#16A34A" : emp.autonomy_level === 1 ? "#D97706" : "#DC2626",
                    fontFamily: "var(--font-inter)"
                  }}>
                  {AUTONOMY_LABELS[emp.autonomy_level ?? 0]}
                </span>
              </div>
              <div className="flex gap-2">
                {AUTONOMY_LABELS.map((label, i) => (
                  <button key={i} onClick={() => updateAutonomy.mutate({ id: emp.id, level: i })}
                    className="flex-1 py-2 rounded-lg text-xs font-semibold transition-all"
                    style={{
                      background: emp.autonomy_level === i ? "var(--eb-primary)" : "var(--eb-surface-variant)",
                      color: emp.autonomy_level === i ? "#fff" : "var(--eb-neutral)",
                      fontFamily: "var(--font-inter)"
                    }}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          ))}
          {employees.length === 0 && (
            <div className="text-center py-12 text-sm" style={{ color: "var(--eb-neutral)" }}>
              AI社員が登録されていません
            </div>
          )}
        </div>
      )}
    </div>
  );
}
