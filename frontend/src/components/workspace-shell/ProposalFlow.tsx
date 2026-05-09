"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchProposalState, fetchProposalAggregatedView,
  startProposalStep, replyProposal, completeProposalStep,
  proposalDownloadUrl,
  type ProposalState, type AggregatedView, type StepState, type ChatMsg,
} from "@/lib/proposal-api";
import {
  Send, Play, Check, Loader2, FileText, FileCode2, FileJson,
  CheckCircle2, Circle, CircleDot, MessageSquare, Sparkles, ChevronRight,
} from "lucide-react";

interface Props {
  workspaceId: number;
  demoMode?: boolean;
}

const CHAPTER_NUMBER: Record<string, number> = {
  cover: 1, executive_summary: 2, problem: 3, solution: 4,
  roi: 5, scope: 6, schedule: 7, risk_team: 8,
};

/**
 * Phase 4 提案書: スクロール 1 本 + TOC ジャンプ
 * - 5 STEP 構成
 * - 中央 = 上から下への 8 章スクロール
 * - 中間出力なし (完成形のみ表示)
 */
export function ProposalFlow({ workspaceId, demoMode = false }: Props) {
  const qc = useQueryClient();
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [activeChapter, setActiveChapter] = useState<string>("cover");

  const { data: liveState, isLoading: liveLoading, error: liveErr } = useQuery<ProposalState>({
    queryKey: ["proposal-state", workspaceId],
    queryFn: () => fetchProposalState(workspaceId),
    enabled: !!workspaceId && !demoMode,
  });
  const { data: liveAgg } = useQuery<AggregatedView>({
    queryKey: ["proposal-aggregated", workspaceId],
    queryFn: () => fetchProposalAggregatedView(workspaceId),
    enabled: !!workspaceId && !demoMode,
    refetchInterval: 5000,
  });

  const state = demoMode ? DEMO_STATE : liveState;
  const agg = demoMode ? DEMO_AGGREGATED : liveAgg;
  const isLoading = demoMode ? false : liveLoading;
  const error = demoMode ? null : liveErr;

  const steps = state?.steps ?? [];
  const chapters = agg?.chapters ?? [];

  useEffect(() => {
    if (steps.length === 0 || activeStep != null) return;
    const inProg = steps.find((s) => s.status === "draft");
    const next = inProg ?? steps.find((s) => s.status === "not_started");
    setActiveStep(next?.step ?? steps[0]?.step ?? 1);
  }, [steps, activeStep]);

  const fullHistory = useMemo<ChatMsg[]>(() => {
    const out: ChatMsg[] = [];
    for (const s of steps) for (const m of s.history ?? []) out.push({ ...m, step: s.step });
    return out.sort((a, b) => (a.id ?? 0) - (b.id ?? 0));
  }, [steps]);

  const startMut = useMutation({
    mutationFn: (step: number) => startProposalStep(workspaceId, step),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["proposal-state", workspaceId] }),
  });
  const replyMut = useMutation({
    mutationFn: ({ step, message }: { step: number; message: string }) => replyProposal(workspaceId, step, message),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["proposal-state", workspaceId] });
      qc.invalidateQueries({ queryKey: ["proposal-aggregated", workspaceId] });
    },
  });
  const completeMut = useMutation({
    mutationFn: (step: number) => completeProposalStep(workspaceId, step),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["proposal-state", workspaceId] });
      qc.invalidateQueries({ queryKey: ["proposal-aggregated", workspaceId] });
      if (data.next_step) setActiveStep(data.next_step);
    },
  });

  // scroll-spy
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const handler = () => {
      const sections = root.querySelectorAll<HTMLElement>("[data-chapter-key]");
      const top = root.scrollTop + 80;
      let cur = activeChapter;
      for (const sec of Array.from(sections)) {
        if (sec.offsetTop <= top) cur = sec.dataset.chapterKey ?? cur;
      }
      if (cur !== activeChapter) setActiveChapter(cur);
    };
    root.addEventListener("scroll", handler, { passive: true });
    return () => root.removeEventListener("scroll", handler);
  }, [activeChapter, chapters.length]);

  const jumpTo = (key: string) => {
    const root = scrollRef.current;
    if (!root) return;
    const el = root.querySelector<HTMLElement>(`[data-chapter-key="${key}"]`);
    if (el) root.scrollTo({ top: el.offsetTop - 8, behavior: "smooth" });
  };

  if (isLoading) return <div style={{ padding: 40, color: "var(--bf-text-3)" }}>提案書を読み込み中…</div>;
  if (error || !state) {
    return <div style={{
      padding: 24, background: "var(--bf-danger-bg)", border: "1px solid var(--bf-danger)",
      borderRadius: "var(--bf-radius-lg)", color: "var(--bf-danger)", fontSize: 13,
    }}>提案書 API に接続できません。</div>;
  }

  return (
    <>
      <style>{`
        @keyframes bf-fadein { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
        .pp-doc { font-feature-settings: "palt"; }
        .pp-toc {
          position: sticky; top: 0; z-index: 10;
          background: var(--bf-bg-elev);
          border-bottom: 1px solid var(--bf-divider);
          padding: 10px 16px;
          display: flex; gap: 4px; overflow-x: auto;
          scrollbar-width: none;
        }
        .pp-toc::-webkit-scrollbar { display: none; }
        .pp-toc-item {
          display: inline-flex; align-items: center; gap: 6px;
          padding: 6px 10px; font-size: 11.5px; font-weight: 600;
          color: var(--bf-text-3); background: transparent;
          border: 1px solid transparent; border-radius: 999px;
          cursor: pointer; white-space: nowrap; transition: all 150ms;
          font-family: inherit;
        }
        .pp-toc-item:hover { background: var(--bf-primary-bg); color: var(--bf-primary); }
        .pp-toc-item.active {
          background: var(--bf-primary); color: #fff; border-color: var(--bf-primary);
        }
        .pp-toc-item .num {
          display: inline-flex; align-items: center; justify-content: center;
          width: 16px; height: 16px; font-size: 10px; font-weight: 700;
          background: rgba(0,0,0,0.06); border-radius: 50%;
        }
        .pp-toc-item.active .num { background: rgba(255,255,255,0.3); }
        .pp-toc-item.locked { color: var(--bf-text-4); cursor: not-allowed; opacity: 0.5; }

        .pp-chapter {
          background: #fff;
          border: 1px solid var(--bf-divider);
          border-radius: 12px;
          padding: 36px 40px;
          margin-bottom: 16px;
          scroll-margin-top: 60px;
        }
        .pp-chapter-head {
          display: flex; align-items: center; gap: 14px;
          margin-bottom: 24px; padding-bottom: 16px;
          border-bottom: 2px solid var(--bf-primary-bg);
        }
        .pp-chapter-num {
          width: 40px; height: 40px; flex-shrink: 0;
          background: linear-gradient(135deg, var(--bf-primary) 0%, #1A5FE0 100%);
          color: #fff; border-radius: 10px;
          display: flex; align-items: center; justify-content: center;
          font-size: 16px; font-weight: 800;
          box-shadow: 0 2px 6px rgba(0,76,217,0.2);
        }
        .pp-chapter-title {
          font-size: 22px; font-weight: 800; color: var(--bf-primary);
          letter-spacing: -0.01em;
        }
        .pp-chapter-step-tag {
          margin-left: auto;
          font-size: 10.5px; color: var(--bf-text-4);
          background: var(--bf-bg); border: 1px solid var(--bf-divider);
          padding: 2px 9px; border-radius: 999px; font-weight: 600;
        }
        .pp-sub-title {
          font-size: 13px; font-weight: 700; color: var(--bf-text-2);
          margin: 18px 0 10px; padding-left: 10px;
          border-left: 3px solid var(--bf-primary);
        }
        .pp-para {
          font-size: 14px; line-height: 1.85;
          color: var(--bf-text-2);
          margin-bottom: 12px;
          white-space: pre-wrap;
        }
        .pp-para:last-child { margin-bottom: 0; }
        .pp-empty {
          padding: 24px;
          color: var(--bf-text-4);
          font-size: 13px;
          text-align: center;
          background: var(--bf-bg);
          border: 1px dashed var(--bf-divider);
          border-radius: 8px;
        }

        .pp-chapter-foot {
          display: flex; justify-content: flex-end; gap: 4px;
          margin-top: 18px; padding-top: 14px;
          border-top: 1px solid var(--bf-divider);
        }
      `}</style>

      <div style={{
        display: "grid",
        gridTemplateColumns: "240px 1fr 380px",
        gap: "var(--bf-space-5)",
        height: "calc(100vh - var(--bf-header-h) - 200px)",
      }}>
        {/* Left STEP プログレス */}
        <StepProgress steps={steps} activeStep={activeStep} onSelect={setActiveStep}
          onStart={(s) => startMut.mutate(s)} isStarting={startMut.isPending} />

        {/* Center: スクロール 1 本 */}
        <div style={{
          background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
          borderRadius: "var(--bf-radius-lg)", display: "flex",
          flexDirection: "column", overflow: "hidden",
        }}>
          {/* Action bar */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            gap: 8, padding: "10px 16px", background: "var(--bf-bg-elev)",
            borderBottom: "1px solid var(--bf-divider)", flexShrink: 0,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <FileText className="w-4 h-4" style={{ color: "var(--bf-primary)" }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: "var(--bf-text-1)" }}>提案書ドラフト</span>
              <span style={{
                fontSize: 10.5, color: "var(--bf-text-4)", background: "var(--bf-bg)",
                border: "1px solid var(--bf-divider)", padding: "1px 6px",
                borderRadius: 999, fontWeight: 500,
              }}>8 章</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontSize: 10.5, color: "var(--bf-text-4)", marginRight: 4 }}>全章一括 DL</span>
              <DownloadButton chapter="all" fmt="html" workspaceId={workspaceId} icon={<FileCode2 className="w-3.5 h-3.5" />} label="HTML" />
              <DownloadButton chapter="all" fmt="md" workspaceId={workspaceId} icon={<FileText className="w-3.5 h-3.5" />} label="MD" />
              <DownloadButton chapter="all" fmt="json" workspaceId={workspaceId} icon={<FileJson className="w-3.5 h-3.5" />} label="JSON" />
            </div>
          </div>

          {/* TOC */}
          <div className="pp-toc">
            {chapters.map((ch) => {
              const num = CHAPTER_NUMBER[ch.key] ?? "·";
              const isActive = ch.key === activeChapter;
              return (
                <button key={ch.key}
                  className={`pp-toc-item ${isActive ? "active" : ""} ${ch.locked ? "locked" : ""}`}
                  onClick={() => !ch.locked && jumpTo(ch.key)}
                  disabled={ch.locked}>
                  <span className="num">{num}</span>{ch.label}
                </button>
              );
            })}
          </div>

          {/* Doc body */}
          <div ref={scrollRef} className="pp-doc" style={{
            flex: 1, overflowY: "auto", padding: "16px 20px",
            background: "var(--bf-bg)",
          }}>
            {chapters.length === 0 ? (
              <div style={{ padding: 40, textAlign: "center", color: "var(--bf-text-3)", fontSize: 13 }}>
                STEP を開始すると、提案書ドラフトが章ごとに埋まっていきます。
              </div>
            ) : chapters.map((ch) => (
              <section key={ch.key} className="pp-chapter" data-chapter-key={ch.key}>
                <div className="pp-chapter-head">
                  <div className="pp-chapter-num">{CHAPTER_NUMBER[ch.key] ?? "·"}</div>
                  <div className="pp-chapter-title">{ch.label}</div>
                  {ch.source_steps?.length > 0 && (
                    <span className="pp-chapter-step-tag">STEP {ch.source_steps.join(", ")}</span>
                  )}
                </div>
                {(ch.sections ?? []).every((sec) => (sec.items ?? []).length === 0) ? (
                  <div className="pp-empty">この章はまだ AI と対話して埋めていない状態です。STEP を進めると追記されます。</div>
                ) : ch.sections.map((sec) => (
                  <div key={sec.key}>
                    {ch.sections.length > 1 && <div className="pp-sub-title">{sec.label}</div>}
                    {(sec.items ?? []).map((it, i) => (
                      <p key={i} className="pp-para">{it}</p>
                    ))}
                  </div>
                ))}
                <div className="pp-chapter-foot">
                  <DownloadButton chapter={ch.key} fmt="html" workspaceId={workspaceId} icon={<FileCode2 className="w-3.5 h-3.5" />} label="HTML" />
                  <DownloadButton chapter={ch.key} fmt="md" workspaceId={workspaceId} icon={<FileText className="w-3.5 h-3.5" />} label="MD" />
                  <DownloadButton chapter={ch.key} fmt="json" workspaceId={workspaceId} icon={<FileJson className="w-3.5 h-3.5" />} label="JSON" />
                </div>
              </section>
            ))}
          </div>

          {/* Complete bar */}
          {(() => {
            const activeStepObj = steps.find((s) => s.step === activeStep);
            if (!activeStepObj || activeStepObj.status !== "draft") return null;
            return (
              <div style={{
                padding: "12px 16px", borderTop: "1px solid var(--bf-divider)",
                background: "var(--bf-bg-elev)", display: "flex",
                justifyContent: "flex-end", flexShrink: 0,
              }}>
                <button disabled={completeMut.isPending} onClick={() => completeMut.mutate(activeStep!)}
                  style={{
                    height: 32, padding: "0 14px",
                    background: "var(--bf-success)", color: "#fff", border: "none",
                    borderRadius: "var(--bf-radius-md)", fontSize: 12.5, fontWeight: 600,
                    cursor: "pointer", display: "inline-flex",
                    alignItems: "center", gap: 6, opacity: completeMut.isPending ? 0.6 : 1,
                  }}>
                  {completeMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                  STEP {activeStep} を完了
                </button>
              </div>
            );
          })()}
        </div>

        {/* Right: チャット */}
        <ChatPanel history={fullHistory} activeStep={activeStep ?? 1}
          onSubmit={(msg) => activeStep != null && replyMut.mutate({ step: activeStep, message: msg })}
          isReplying={replyMut.isPending} />
      </div>
    </>
  );
}

/* ─── 左 STEP ─── */
function StepProgress({ steps, activeStep, onSelect, onStart, isStarting }: {
  steps: StepState[]; activeStep: number | null;
  onSelect: (s: number) => void; onStart: (s: number) => void; isStarting: boolean;
}) {
  return (
    <div style={{
      background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
      borderRadius: "var(--bf-radius-lg)", padding: "var(--bf-space-4)", overflowY: "auto",
    }}>
      <div style={{
        fontSize: 11, fontWeight: 700, color: "var(--bf-text-4)",
        letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 12,
      }}>Phase 4 / 提案書</div>
      {steps.map((s) => {
        const isActive = activeStep === s.step;
        const Icon = s.status === "confirmed" ? CheckCircle2 : isActive ? CircleDot : Circle;
        const color = s.status === "confirmed" ? "var(--bf-success)" : isActive ? "var(--bf-primary)" : "var(--bf-text-4)";
        return (
          <div key={s.step} role="button" tabIndex={0}
            onClick={() => onSelect(s.step)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(s.step); } }}
            style={{
              display: "flex", alignItems: "flex-start", gap: 10,
              width: "100%", padding: "10px 12px", marginBottom: 4,
              background: isActive ? "var(--bf-primary-bg)" : "transparent",
              border: "none", borderRadius: "var(--bf-radius-md)",
              cursor: "pointer", transition: "background 150ms",
            }}>
            <Icon className="w-4 h-4 mt-0.5" style={{ color, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 12, fontWeight: 600, color: "var(--bf-text-1)",
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>STEP {s.step} {s.title}</div>
              <div style={{ fontSize: 10.5, color: "var(--bf-text-3)", marginTop: 2 }}>
                {s.status === "confirmed" ? "確定" : s.status === "draft" ? "進行中" : "未着手"}
              </div>
              {isActive && s.status === "not_started" && (
                <button onClick={(e) => { e.stopPropagation(); onStart(s.step); }} disabled={isStarting}
                  style={{
                    marginTop: 8, padding: "4px 10px",
                    background: "var(--bf-primary)", color: "#fff", border: "none",
                    borderRadius: "var(--bf-radius-md)", fontSize: 11, fontWeight: 600,
                    cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4,
                  }}>
                  {isStarting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}開始
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DownloadButton({ chapter, fmt, workspaceId, icon, label }: {
  chapter: string; fmt: "html" | "md" | "json"; workspaceId: number;
  icon: React.ReactNode; label: string;
}) {
  return (
    <a href={proposalDownloadUrl(workspaceId, chapter, fmt)} download
      style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "5px 8px", fontSize: 11, fontWeight: 600,
        color: "var(--bf-text-3)", background: "transparent",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-md)",
        textDecoration: "none", transition: "all 150ms",
      }} title={`${label} をダウンロード`}>
      {icon}{label}
    </a>
  );
}

/* ─── 右 チャット ─── */
function ChatPanel({ history, activeStep, onSubmit, isReplying }: {
  history: ChatMsg[]; activeStep: number;
  onSubmit: (msg: string) => void; isReplying: boolean;
}) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [history.length]);

  const renderItems = useMemo(() => {
    const items: Array<{ type: "divider" | "msg"; data: any; key: string }> = [];
    let prevStep: number | null = null;
    for (const m of history) {
      if (m.step !== prevStep) {
        items.push({ type: "divider", data: m.step, key: `div-${m.step}-${m.id}` });
        prevStep = m.step ?? null;
      }
      items.push({ type: "msg", data: m, key: `m-${m.id}` });
    }
    return items;
  }, [history]);

  return (
    <div style={{
      background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
      borderRadius: "var(--bf-radius-lg)", display: "flex",
      flexDirection: "column", overflow: "hidden",
    }}>
      <div style={{
        padding: "10px 14px", borderBottom: "1px solid var(--bf-divider)",
        background: "var(--bf-bg)", display: "flex", alignItems: "center", gap: 8,
      }}>
        <Sparkles className="w-4 h-4" style={{ color: "var(--bf-primary)" }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--bf-text-1)" }}>PM AI 社員 (提案書)</span>
        <span style={{ fontSize: 11, color: "var(--bf-text-4)", marginLeft: "auto" }}>STEP {activeStep}</span>
      </div>
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "var(--bf-space-4)" }}>
        {renderItems.length === 0 && (
          <div style={{ color: "var(--bf-text-3)", fontSize: 12, textAlign: "center", padding: 24 }}>
            STEP を開始すると、PM AI 社員が章ごとに埋めていきます。
          </div>
        )}
        {renderItems.map((it) => {
          if (it.type === "divider") {
            return (
              <div key={it.key} style={{ display: "flex", alignItems: "center", gap: 8, margin: "16px 0 12px" }}>
                <div style={{ flex: 1, height: 1, background: "var(--bf-divider)" }} />
                <div style={{
                  fontSize: 10.5, fontWeight: 700, color: "var(--bf-text-4)",
                  letterSpacing: "0.08em", textTransform: "uppercase",
                  padding: "2px 8px", background: "var(--bf-bg-elev)",
                  border: "1px solid var(--bf-border)", borderRadius: 999,
                }}>STEP {it.data}</div>
                <div style={{ flex: 1, height: 1, background: "var(--bf-divider)" }} />
              </div>
            );
          }
          const m: ChatMsg = it.data;
          if (m.role === "system") return null;
          const isAi = m.role === "ai";
          return (
            <div key={it.key} style={{
              display: "flex", flexDirection: "column",
              alignItems: isAi ? "flex-start" : "flex-end", marginBottom: 10,
            }}>
              <div style={{
                maxWidth: "85%", padding: "8px 12px",
                background: isAi ? "var(--bf-bg)" : "var(--bf-primary)",
                color: isAi ? "var(--bf-text-1)" : "#fff",
                borderRadius: "var(--bf-radius-md)",
                border: isAi ? "1px solid var(--bf-divider)" : "none",
                fontSize: 12.5, lineHeight: 1.55, whiteSpace: "pre-wrap",
              }}>{m.content}</div>
            </div>
          );
        })}
        {isReplying && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--bf-text-3)", fontSize: 11.5, padding: "6px 4px" }}>
            <Loader2 className="w-3.5 h-3.5 animate-spin" />AI が考え中…
          </div>
        )}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); const v = input.trim(); if (!v || isReplying) return; onSubmit(v); setInput(""); }}
        style={{
          padding: "10px 12px", borderTop: "1px solid var(--bf-divider)",
          background: "var(--bf-bg)", display: "flex", gap: 6, flexShrink: 0,
        }}>
        <input value={input} onChange={(e) => setInput(e.target.value)}
          placeholder={`STEP ${activeStep} の回答や質問を入力…`} disabled={isReplying}
          style={{
            flex: 1, height: 32, padding: "0 10px",
            background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
            borderRadius: "var(--bf-radius-md)", fontSize: 12.5, color: "var(--bf-text-1)",
          }} />
        <button type="submit" disabled={isReplying || !input.trim()}
          style={{
            height: 32, padding: "0 12px",
            background: "var(--bf-primary)", color: "#fff", border: "none",
            borderRadius: "var(--bf-radius-md)", fontSize: 12, fontWeight: 600,
            cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4,
            opacity: isReplying || !input.trim() ? 0.5 : 1,
          }}><Send className="w-3.5 h-3.5" /></button>
      </form>
    </div>
  );
}

/* ═══════════════════════════════════════
 * DEMO データ (?demo=1)
 * ═══════════════════════════════════════ */
const DEMO_STATE: ProposalState = {
  workspace_id: 1, phase: "proposal",
  steps: [
    { step: 1, title: "起点整理・トーン確認", description: "前フェーズ引き継ぎ + 骨格", status: "confirmed", artifact_id: "demo-1",
      center: { step: 1, sections: [
        { key: "cover", label: "カバー", items: [
          "案件名: 自家焙煎コーヒー豆 EC サイト構築 (BtoC + BtoB 統合)",
          "クライアント: 株式会社○○珈琲 / 担当: 田中様",
          "サービス種別: フルコード開発 (Build-Factory AI 駆動)",
          "提案日: 2026 年 5 月 8 日",
        ]},
        { key: "executive_summary", label: "エグゼクティブサマリー", items: [
          "現状: BASE で運営中の EC が定期便と BtoB 卸に対応しきれず、月 5-10 件の機会損失と運用工数増大が発生。",
          "提案: Stripe Subscription による定期便基盤 + Paid 連携の BtoB 与信フロー + Shippinno 在庫同期を 4 か月で構築。月商 300 万円・継続率 80% を 6 か月で達成。",
          "投資対効果: 320 万円の構築投資に対し、月 50 万円の効果想定で 6.4 か月で回収。",
        ]},
        { key: "tone", label: "提案書のトーン", items: [
          "対象読者: 経営判断層 (代表) + 運用責任者",
          "トーン: 信頼感重視・ROI を数字で示す・専門用語は最小限",
        ]},
        { key: "achievements", label: "実績情報", items: [
          "[統計] 開発実績 30+ 件 / 平均納期 1.8 か月 / 顧客満足度 4.7",
          "[事例 1] 食品 EC: 月商 200→500 万円・継続率 35→78% (6 か月)",
          "[事例 2] BtoB 卸サイト: 申込数 8→52 件/月 (3 か月)",
          "[事例 3] サブスク EC: 解約率 18→6% (機能改善のみで)",
        ]},
      ]},
      history: [
        { id: 1, role: "ai", content: "STEP 1 を始めます。前フェーズの情報を踏まえて提案書の骨格を作りました。トーンは経営判断層向けで ROI を数字で示す方向で良いですか?", step: 1 },
        { id: 2, role: "user", content: "それで OK です。経営層が動きやすい数字を出してください。", step: 1 },
      ],
    },
    { step: 2, title: "課題深掘り・ソリューション設計", description: "問題深掘り + ROI", status: "confirmed", artifact_id: "demo-2",
      center: { step: 2, sections: [
        { key: "problem", label: "課題の深掘り", items: [
          "BASE には定期便機能がなく、現状はスプレッドシート + 手動配送指示で運用されている。顧客 30 名超で運用が破綻し、当日対応できないスキップ要望から解約が連鎖発生している。",
          "BtoB 価格表示・請求書払い・与信機能が存在しないため、飲食店からの問い合わせを月 5-10 件取りこぼしている。1 件あたり平均年商 60 万円とすると、年間 360-720 万円の機会損失。",
          "顧客の好み (焙煎度・抽出方法) を記録できないため、クロスセルの精度が低く、平均購入単価 2,800 円で頭打ちになっている。",
        ]},
        { key: "solution", label: "提案ソリューション", items: [
          "Next.js 16 + Supabase + Stripe Subscription を中核とする受注・サブスクリプション基盤を構築。",
          "Paid 連携で BtoB 与信フローを自動化し、Shippinno 在庫同期で運用工数を削減。",
          "好み登録 → レコメンド連動でクロスセル機会を最大化。",
        ]},
        { key: "tech_stack", label: "実装アプローチ・技術スタック", items: [
          "Frontend: Next.js 16 (App Router) / React / TypeScript",
          "Backend: Hono on Node.js / TypeScript",
          "Database: PostgreSQL 16 (Supabase)",
          "Payment: Stripe Subscription (BtoC) / Paid (BtoB 請求書払い)",
          "Logistics: Shippinno (在庫同期 + 配送)",
        ]},
        { key: "roi", label: "ROI・効果", items: [
          "月次効果 (想定): BtoB 機会回復 25-50 万円 + 運用工数削減 9 万円 + 在庫管理自動化 8 万円 = 月 42-67 万円",
          "年間効果: 504-804 万円",
          "投資回収: 構築費 320 万円に対し 6.4 か月で回収完了",
        ]},
      ]},
      history: [],
    },
    { step: 3, title: "スコープ・フェーズ・スケジュール", description: "範囲・計画・費用", status: "confirmed", artifact_id: "demo-3",
      center: { step: 3, sections: [
        { key: "scope_in", label: "スコープ (含むもの)", items: [
          "商品カタログ・検索・好み連動レコメンド",
          "カート・購入・Stripe Checkout 決済",
          "サブスクリプション (定期便・スキップ/変更/解約)",
          "BtoB 申込・与信 (Paid 連携)・専用ダッシュボード",
          "顧客マイページ (注文履歴・好み登録・定期便管理)",
          "管理画面 (商品/在庫/受注/顧客/レポート)",
          "Shippinno 在庫同期 (1 時間バッチ)",
          "メール通知 (12 種) + ステップ配信 (3/7/30 日)",
          "BASE データ移行 (商品 80 点・顧客 1,200 件)",
        ]},
        { key: "scope_out", label: "スコープ (含まないもの・将来対応)", items: [
          "実店舗 POS 連携 (将来 Phase 2 で対応可能)",
          "海外配送・国際決済",
          "B2B EDI 連携",
          "ロイヤリティポイントシステム",
          "AI レコメンドの自社学習モデル",
        ]},
        { key: "phases", label: "フェーズ設計", items: [
          "Phase 1 (今回): 中核機能・Stripe・Shippinno 連携・BASE 移行",
          "Phase 2 (将来): ロイヤリティポイント・実店舗 POS 連携",
          "Phase 3 (将来): AI レコメンドモデル・海外展開",
        ]},
        { key: "schedule", label: "スケジュール", items: [
          "5 月: 要件確定・設計",
          "6 月: 基盤・商品・カート",
          "7 月: 定期便・BtoB・管理画面",
          "8 月前半: Shippinno 連携・テスト",
          "8 月後半: BASE 移行・受け入れテスト",
          "9 月初週: 本番リリース",
        ]},
        { key: "cost", label: "費用概算", items: [
          "構築費: 320 万円 (税抜)",
          "月額保守: 5 万円 (基本プラン)",
          "オプション: SEO 月 3 万 / 広告運用 月 5 万",
          "支払条件: 着手金 30% / 中間 30% / 検収後 40%",
        ]},
      ]},
      history: [],
    },
    { step: 4, title: "リスク・前提・体制", description: "リスク + 前提 + 体制", status: "draft", artifact_id: "demo-4",
      center: { step: 4, sections: [
        { key: "risks", label: "リスクと対応策", items: [
          "[技術] Shippinno API レート制限 (1分100req): キュー処理 + 指数バックオフで吸収",
          "[運用] 倉庫スタッフが管理画面に不慣れ: リリース 2 週間前に研修 + 動画マニュアル",
          "[要件] BtoB 与信ロジック未確定: 6 月 15 日までに業務側で基準確定",
          "[スケジュール] 9 月リリース前提でデザイン未着手: 6 月中にデザイン完了",
        ]},
        { key: "assumptions", label: "提案前提・クライアント協力事項", items: [
          "BASE データのエクスポート CSV は 6 月初週に提供",
          "Stripe / Paid アカウントの取得・KYC は貴社で実施",
          "デザインのフィードバック期間は 1 サイクル 3 営業日以内",
          "本番リリース前の受け入れテストに 1 週間確保",
        ]},
        { key: "team", label: "開発体制", items: [
          "PM: 株式会社 ENGINE BASE 高本聖斗",
          "AI 社員: PM AI / 設計 AI / 実装 AI / 品質 AI / DevOps AI",
          "デザイン: 外注 (パートナー)",
          "クライアント側: 代表 1 名 + 運用責任者 1 名 (週次定例)",
        ]},
        { key: "security", label: "セキュリティ・コンプライアンス", items: [
          "個人情報のアクセスログを 3 年保管 (改正個情法準拠)",
          "決済情報は Stripe トークン化のみ (PCI DSS SAQ-A 範囲)",
          "管理画面は 2FA 必須 + IP 制限",
          "改正特商法 2022 の解約導線 (1 クリック解約) 対応",
        ]},
      ]},
      history: [],
    },
    { step: 5, title: "最終ドラフト確定 + 出力", description: "全章整合性確認 + 出力", status: "not_started", artifact_id: null,
      center: { step: 5, sections: [{ key: "summary", label: "提案書サマリー", items: [] }] }, history: [],
    },
  ],
};

const DEMO_AGGREGATED: AggregatedView = {
  workspace_id: 1,
  chapters: [
    { key: "cover", label: "カバー", locked: false, source_steps: [1],
      sections: [{ key: "cover", label: "カバー", source_step: 1, items: DEMO_STATE.steps[0].center.sections[0].items }] },
    { key: "executive_summary", label: "エグゼクティブサマリー", locked: false, source_steps: [1],
      sections: [
        { key: "executive_summary", label: "エグゼクティブサマリー", source_step: 1, items: DEMO_STATE.steps[0].center.sections[1].items },
        { key: "tone", label: "提案書のトーン", source_step: 1, items: DEMO_STATE.steps[0].center.sections[2].items },
        { key: "achievements", label: "実績情報", source_step: 1, items: DEMO_STATE.steps[0].center.sections[3].items },
      ]},
    { key: "problem", label: "課題の深掘り", locked: false, source_steps: [2],
      sections: [{ key: "problem", label: "課題の深掘り", source_step: 2, items: DEMO_STATE.steps[1].center.sections[0].items }] },
    { key: "solution", label: "提案ソリューション", locked: false, source_steps: [2],
      sections: [
        { key: "solution", label: "提案ソリューション", source_step: 2, items: DEMO_STATE.steps[1].center.sections[1].items },
        { key: "tech_stack", label: "実装アプローチ・技術スタック", source_step: 2, items: DEMO_STATE.steps[1].center.sections[2].items },
      ]},
    { key: "roi", label: "ROI・効果", locked: false, source_steps: [2],
      sections: [{ key: "roi", label: "ROI・効果", source_step: 2, items: DEMO_STATE.steps[1].center.sections[3].items }] },
    { key: "scope", label: "スコープ・フェーズ", locked: false, source_steps: [3],
      sections: [
        { key: "scope_in", label: "含むもの", source_step: 3, items: DEMO_STATE.steps[2].center.sections[0].items },
        { key: "scope_out", label: "含まないもの・将来対応", source_step: 3, items: DEMO_STATE.steps[2].center.sections[1].items },
        { key: "phases", label: "フェーズ設計", source_step: 3, items: DEMO_STATE.steps[2].center.sections[2].items },
      ]},
    { key: "schedule", label: "スケジュール・費用", locked: false, source_steps: [3],
      sections: [
        { key: "schedule", label: "スケジュール", source_step: 3, items: DEMO_STATE.steps[2].center.sections[3].items },
        { key: "cost", label: "費用概算", source_step: 3, items: DEMO_STATE.steps[2].center.sections[4].items },
      ]},
    { key: "risk_team", label: "リスク・前提・体制", locked: false, source_steps: [4],
      sections: [
        { key: "risks", label: "リスクと対応策", source_step: 4, items: DEMO_STATE.steps[3].center.sections[0].items },
        { key: "assumptions", label: "前提・クライアント協力事項", source_step: 4, items: DEMO_STATE.steps[3].center.sections[1].items },
        { key: "team", label: "開発体制", source_step: 4, items: DEMO_STATE.steps[3].center.sections[2].items },
        { key: "security", label: "セキュリティ・コンプライアンス", source_step: 4, items: DEMO_STATE.steps[3].center.sections[3].items },
      ]},
  ],
};
