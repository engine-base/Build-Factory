"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Workflow, Play, CheckCircle, XCircle, Clock, ChevronRight, Loader, ShuffleIcon } from "lucide-react";

const API = "http://localhost:8001";

type WorkflowRun = {
  id: number;
  user_request: string;
  status: string;
  steps_completed: number;
  steps_total: number;
  approval_id: number | null;
  started_at: string;
  completed_at: string | null;
};

type Step = {
  id: number;
  step_number: number;
  skill_name: string;
  input: string;
  output: string;
  status: string;
  parallel_group: string | null;
  duration_sec: number | null;
};

type Detail = { run: WorkflowRun & { plan_json: string; final_output: string }; steps: Step[] };

const STATUS_BADGE: Record<string, { label: string; bg: string; color: string; Icon: any }> = {
  running:   { label: "実行中", bg: "#DBEAFE", color: "#1E40AF", Icon: Loader },
  completed: { label: "完了",   bg: "#DCFCE7", color: "#16A34A", Icon: CheckCircle },
  failed:    { label: "失敗",   bg: "#FEE2E2", color: "#DC2626", Icon: XCircle },
  planning:  { label: "計画中", bg: "#FEF9C3", color: "#D97706", Icon: Clock },
};

export default function WorkflowsPage() {
  const [request, setRequest] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data: workflows = [], refetch } = useQuery<WorkflowRun[]>({
    queryKey: ["workflows"],
    queryFn: () => fetch(`${API}/api/workflows`).then(r => r.json()),
    refetchInterval: 5000,
  });

  const { data: detail } = useQuery<Detail>({
    queryKey: ["workflow", selectedId],
    queryFn: () => fetch(`${API}/api/workflows/${selectedId}`).then(r => r.json()),
    enabled: !!selectedId,
    refetchInterval: 3000,
  });

  const run = useMutation({
    mutationFn: () => fetch(`${API}/api/workflows/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request }),
    }).then(r => r.json()),
    onSuccess: (data) => {
      if (data?.workflow_id) setSelectedId(data.workflow_id);
      refetch();
      setRequest("");
    },
  });

  return (
    <div className="p-8 max-w-6xl">
      <h1 className="text-2xl font-bold mb-2" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>マルチエージェント実行</h1>
      <p className="text-sm mb-6" style={{ color: "var(--eb-neutral)" }}>
        複雑な依頼を秘書が複数のAI社員に分解して並列実行します
      </p>

      {/* 実行フォーム */}
      <div className="rounded-xl p-4 mb-6 bg-white" style={{ border: "1px solid var(--eb-border)", boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
        <textarea
          value={request}
          onChange={e => setRequest(e.target.value)}
          placeholder="例: ○○社向けの提案書を作って（市場調査・競合分析・価格設計を含めて）"
          rows={2}
          className="w-full p-3 rounded text-sm resize-none mb-2"
          style={{ border: "1px solid var(--eb-border)", outline: "none", fontFamily: "var(--font-noto-sans-jp)" }} />
        <div className="flex justify-end">
          <button onClick={() => run.mutate()} disabled={!request.trim() || run.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-semibold text-white disabled:opacity-50"
            style={{ background: "var(--eb-primary)", fontFamily: "var(--font-inter)" }}>
            {run.isPending ? <Loader className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {run.isPending ? "実行中..." : "ワークフロー実行"}
          </button>
        </div>
      </div>

      <div className="flex gap-4">
        {/* 左: 履歴 */}
        <div className="w-72 shrink-0 space-y-2">
          <p className="text-xs font-bold mb-2" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
            実行履歴
          </p>
          {workflows.length === 0 ? (
            <div className="text-sm text-center py-8" style={{ color: "var(--eb-neutral)" }}>
              <Workflow className="w-8 h-8 mx-auto mb-2 opacity-30" />
              履歴なし
            </div>
          ) : (
            workflows.map(w => {
              const conf = STATUS_BADGE[w.status] ?? STATUS_BADGE.running;
              const Icon = conf.Icon;
              return (
                <button key={w.id} onClick={() => setSelectedId(w.id)}
                  className="w-full text-left p-3 rounded-lg transition-colors bg-white"
                  style={{
                    border: `1px solid ${selectedId === w.id ? "var(--eb-primary)" : "var(--eb-border)"}`,
                    background: selectedId === w.id ? "var(--eb-primary-container)" : "#fff"
                  }}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-semibold"
                      style={{ background: conf.bg, color: conf.color, fontFamily: "var(--font-inter)" }}>
                      <Icon className={`w-2.5 h-2.5 ${w.status === "running" ? "animate-spin" : ""}`} />
                      {conf.label}
                    </span>
                    <span className="text-[10px]" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                      {w.steps_completed}/{w.steps_total}
                    </span>
                  </div>
                  <p className="text-xs font-medium line-clamp-2" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                    {w.user_request}
                  </p>
                  <p className="text-[10px] mt-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                    {new Date(w.started_at).toLocaleString("ja-JP")}
                  </p>
                </button>
              );
            })
          )}
        </div>

        {/* 右: 詳細 */}
        <div className="flex-1 min-w-0 rounded-xl p-6 bg-white" style={{ border: "1px solid var(--eb-border)", minHeight: 400 }}>
          {detail?.run ? (
            <>
              <h2 className="text-base font-bold mb-1" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                依頼: {detail.run.user_request}
              </h2>
              <p className="text-[11px] mb-4" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                {detail.run.started_at} → {detail.run.completed_at || "実行中..."}
              </p>

              {/* ステップ表示 */}
              <div className="space-y-2 mb-6">
                <p className="text-xs font-bold" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                  実行ステップ
                </p>
                {detail.steps.map(s => {
                  const conf = STATUS_BADGE[s.status] ?? STATUS_BADGE.running;
                  return (
                    <div key={s.id} className="rounded-lg p-3"
                      style={{ background: "var(--eb-surface-variant)", border: "1px solid var(--eb-border)" }}>
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                          style={{ background: "#fff", color: "var(--eb-primary)", fontFamily: "var(--font-inter)" }}>
                          STEP {s.step_number}
                        </span>
                        <span className="text-xs font-semibold" style={{ fontFamily: "var(--font-inter)" }}>
                          {s.skill_name}
                        </span>
                        {s.parallel_group && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded inline-flex items-center gap-1"
                            style={{ background: "#FEF3C7", color: "#92400E", fontFamily: "var(--font-inter)" }}>
                            <ShuffleIcon className="w-3 h-3" aria-label="parallel" /> {s.parallel_group}
                          </span>
                        )}
                        <span className="text-[10px] px-1.5 py-0.5 rounded ml-auto"
                          style={{ background: conf.bg, color: conf.color, fontFamily: "var(--font-inter)" }}>
                          {conf.label}{s.duration_sec ? ` ${s.duration_sec}秒` : ""}
                        </span>
                      </div>
                      {s.output && (
                        <details className="text-[11px]">
                          <summary className="cursor-pointer" style={{ color: "var(--eb-neutral)" }}>出力を表示</summary>
                          <pre className="mt-2 p-2 rounded bg-white whitespace-pre-wrap max-h-32 overflow-auto"
                            style={{ fontFamily: "var(--font-inter)", color: "#374151" }}>
                            {s.output.slice(0, 800)}
                          </pre>
                        </details>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* 最終出力 */}
              {detail.run.final_output && (
                <div>
                  <p className="text-xs font-bold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                    最終アウトプット
                  </p>
                  <pre className="text-xs p-3 rounded whitespace-pre-wrap max-h-60 overflow-auto"
                    style={{ background: "var(--eb-primary-container)", color: "var(--eb-on-primary-container)",
                             fontFamily: "var(--font-noto-sans-jp)", lineHeight: 1.6 }}>
                    {detail.run.final_output.slice(0, 3000)}
                  </pre>
                  {detail.run.approval_id && (
                    <p className="text-xs mt-2" style={{ color: "var(--eb-neutral)" }}>
                      → 承認キュー #{detail.run.approval_id}
                    </p>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="h-full flex flex-col items-center justify-center py-16">
              <Workflow className="w-10 h-10 mb-3 opacity-30" />
              <p className="text-sm" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
                ワークフローを選択してください
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
