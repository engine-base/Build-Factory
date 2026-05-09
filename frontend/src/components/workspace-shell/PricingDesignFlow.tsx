"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchPricingState, fetchPricingAggregatedView,
  startPricingStep, replyPricing, completePricingStep,
  pricingDownloadUrl,
  type PricingState, type AggregatedView, type StepState, type ChatMsg,
} from "@/lib/pricing-api";
import {
  Send, Play, Check, Lock, Loader2, FileText, FileCode2, FileJson,
  CheckCircle2, Circle, CircleDot, MessageSquare, Sparkles,
} from "lucide-react";
import { PricingRichTabContent, PricingRichStyles } from "./PricingRichDemo";

interface Props {
  workspaceId: number;
  demoMode?: boolean;
}

const TAB_NUMBER: Record<string, number> = {
  cost_estimate: 1, market_research: 2, value_calc: 3, recommended_range: 4,
};

/**
 * Phase 3 価格設計 IDE 風タブ UI
 * - 3 STEP / 4 タブ / 統合チャット
 * - 直接編集なし・AI チャット駆動
 */
export function PricingDesignFlow({ workspaceId, demoMode = false }: Props) {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<string>("cost");
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [highlightItems, setHighlightItems] = useState<Set<string>>(new Set());

  const { data: liveState, isLoading: liveLoading, error: liveErr } = useQuery<PricingState>({
    queryKey: ["pricing-state", workspaceId],
    queryFn: () => fetchPricingState(workspaceId),
    enabled: !!workspaceId && !demoMode,
  });

  const { data: liveAgg } = useQuery<AggregatedView>({
    queryKey: ["pricing-aggregated", workspaceId],
    queryFn: () => fetchPricingAggregatedView(workspaceId),
    enabled: !!workspaceId && !demoMode,
    refetchInterval: 5000,
  });

  const state = demoMode ? DEMO_STATE : liveState;
  const agg = demoMode ? DEMO_AGGREGATED : liveAgg;
  const isLoading = demoMode ? false : liveLoading;
  const error = demoMode ? null : liveErr;

  const steps = state?.steps ?? [];
  const tabs = agg?.tabs ?? [];

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
    mutationFn: (step: number) => startPricingStep(workspaceId, step),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pricing-state", workspaceId] }),
  });

  const replyMut = useMutation({
    mutationFn: ({ step, message }: { step: number; message: string }) =>
      replyPricing(workspaceId, step, message),
    onSuccess: (data, vars) => {
      const added = new Set<string>();
      for (const op of data.patch ?? []) {
        if (op.operation !== "remove") {
          for (const it of (op.items ?? [])) added.add(`${vars.step}:${op.section_key}:${it}`);
        }
      }
      setHighlightItems(added);
      setTimeout(() => setHighlightItems(new Set()), 2000);
      qc.invalidateQueries({ queryKey: ["pricing-state", workspaceId] });
      qc.invalidateQueries({ queryKey: ["pricing-aggregated", workspaceId] });
    },
  });

  const completeMut = useMutation({
    mutationFn: (step: number) => completePricingStep(workspaceId, step),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["pricing-state", workspaceId] });
      qc.invalidateQueries({ queryKey: ["pricing-aggregated", workspaceId] });
      if (data.next_step) setActiveStep(data.next_step);
    },
  });

  if (isLoading) return <div style={{ padding: 40, color: "var(--bf-text-3)" }}>価格設計状態を読み込み中…</div>;
  if (error || !state) {
    return (
      <div style={{
        padding: "var(--bf-space-6)", background: "var(--bf-danger-bg)",
        border: "1px solid var(--bf-danger)", borderRadius: "var(--bf-radius-lg)",
        color: "var(--bf-danger)", fontSize: 13,
      }}>
        価格設計 API に接続できません。バックエンドの起動を確認してください。
      </div>
    );
  }

  return (
    <>
      <PricingRichStyles />
      <style>{`
        @keyframes bf-fadein { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
        .bf-tab-fadein { animation: bf-fadein 250ms ease-out; }
        .bf-highlight { background: var(--bf-success-bg) !important; transition: background 1500ms ease-out; }
        .bf-tab-row { scrollbar-width: none; -ms-overflow-style: none; }
        .bf-tab-row::-webkit-scrollbar { display: none; height: 0; width: 0; }

        .bf-rd { font-feature-settings: "palt"; }
        .bf-rd .rd-section-card {
          background: var(--bf-bg-elev); border: 1px solid var(--bf-border);
          border-radius: 8px; padding: 28px 32px; margin-bottom: 16px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .bf-rd .rd-section-header {
          display: flex; align-items: center; gap: 12px;
          margin-bottom: 20px; padding-bottom: 14px;
          border-bottom: 1px solid var(--bf-divider);
        }
        .bf-rd .rd-section-num {
          width: 28px; height: 28px; flex-shrink: 0;
          background: var(--bf-primary); color: #fff; border-radius: 4px;
          display: flex; align-items: center; justify-content: center;
          font-size: 12px; font-weight: 700;
        }
        .bf-rd .rd-section-title { font-size: 16px; font-weight: 700; color: var(--bf-primary); }
        .bf-rd .rd-section-step-tag {
          margin-left: auto; font-size: 10.5px; font-weight: 600;
          color: var(--bf-text-4); padding: 3px 9px; border-radius: 999px;
          background: var(--bf-bg); border: 1px solid var(--bf-divider);
        }
        .bf-rd .rd-subsection { margin-bottom: 22px; }
        .bf-rd .rd-subsection:last-child { margin-bottom: 0; }
        .bf-rd .rd-subsection-title {
          font-size: 13px; font-weight: 700; color: var(--bf-text-1);
          margin-bottom: 10px; padding-left: 10px;
          border-left: 3px solid var(--bf-primary);
        }
        .bf-rd .rd-bullets { list-style: none; padding: 0; margin: 0; }
        .bf-rd .rd-bullets li {
          display: flex; align-items: flex-start; gap: 8px;
          padding: 8px 12px; font-size: 13px; line-height: 1.6;
          color: var(--bf-text-2); border-bottom: 1px solid var(--bf-divider);
        }
        .bf-rd .rd-bullets li::before {
          content: ""; flex-shrink: 0; width: 6px; height: 6px;
          border-radius: 50%; background: var(--bf-primary); margin-top: 9px;
        }
        .bf-rd .rd-bullets li:last-child { border-bottom: none; }

        /* 3 軸試算カード */
        .bf-rd .pr-axis-grid {
          display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 14px;
        }
        .bf-rd .pr-axis-card {
          background: var(--bf-bg); border: 1px solid var(--bf-divider);
          border-radius: 8px; padding: 16px; border-left: 4px solid var(--bf-primary);
        }
        .bf-rd .pr-axis-card.cost { border-left-color: #2563eb; }
        .bf-rd .pr-axis-card.value { border-left-color: #7c3aed; }
        .bf-rd .pr-axis-card.competitor { border-left-color: #f97316; }
        .bf-rd .pr-axis-label {
          font-size: 10.5px; font-weight: 700; letter-spacing: 0.06em;
          text-transform: uppercase; color: var(--bf-text-4); margin-bottom: 6px;
        }
        .bf-rd .pr-axis-amount { font-size: 22px; font-weight: 800; color: var(--bf-primary); margin-bottom: 6px; }
        .bf-rd .pr-axis-sub { font-size: 11.5px; color: var(--bf-text-3); }

        .bf-rd .pr-table-wrap {
          overflow-x: auto; border-radius: 6px; border: 1px solid var(--bf-divider);
        }
        .bf-rd table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
        .bf-rd thead th {
          background: var(--bf-primary); color: #fff; font-weight: 600;
          padding: 9px 12px; text-align: left; font-size: 12px;
        }
        .bf-rd tbody td {
          padding: 8px 12px; border-top: 1px solid var(--bf-divider);
          color: var(--bf-text-2);
        }
      `}</style>

      <div style={{
        display: "grid",
        gridTemplateColumns: "240px 1fr 380px",
        gap: "var(--bf-space-5)",
        height: "calc(100vh - var(--bf-header-h) - 200px)",
      }}>
        <StepProgress steps={steps} activeStep={activeStep} onSelect={setActiveStep}
          onStart={(s) => startMut.mutate(s)} isStarting={startMut.isPending} />
        <CenterTabs workspaceId={workspaceId} tabs={tabs} activeTab={activeTab}
          onTabChange={setActiveTab} highlightItems={highlightItems} activeStep={activeStep}
          onComplete={(s) => completeMut.mutate(s)} isCompleting={completeMut.isPending}
          steps={steps} demoMode={demoMode} />
        <ChatPanel history={fullHistory} activeStep={activeStep ?? 1}
          onSubmit={(msg) => activeStep != null && replyMut.mutate({ step: activeStep, message: msg })}
          isReplying={replyMut.isPending} />
      </div>
    </>
  );
}

/* ───── 左: STEP プログレス ───── */
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
      }}>
        Phase 3 / 価格設計
      </div>
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
              textAlign: "left", cursor: "pointer", transition: "background 150ms",
            }}
          >
            <Icon className="w-4 h-4 mt-0.5" style={{ color, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 12, fontWeight: 600, color: "var(--bf-text-1)",
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>
                STEP {s.step} {s.title}
              </div>
              <div style={{ fontSize: 10.5, color: "var(--bf-text-3)", marginTop: 2 }}>
                {s.status === "confirmed" ? "確定" : s.status === "draft" ? "進行中" : "未着手"}
              </div>
              {isActive && s.status === "not_started" && (
                <button
                  onClick={(e) => { e.stopPropagation(); onStart(s.step); }}
                  disabled={isStarting}
                  style={{
                    marginTop: 8, padding: "4px 10px",
                    background: "var(--bf-primary)", color: "#fff", border: "none",
                    borderRadius: "var(--bf-radius-md)", fontSize: 11, fontWeight: 600,
                    cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4,
                  }}
                >
                  {isStarting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                  開始
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ───── 中央: IDE タブ ───── */
function CenterTabs({
  workspaceId, tabs, activeTab, onTabChange, highlightItems,
  activeStep, onComplete, isCompleting, steps, demoMode,
}: {
  workspaceId: number;
  tabs: AggregatedView["tabs"];
  activeTab: string;
  onTabChange: (k: string) => void;
  highlightItems: Set<string>;
  activeStep: number | null;
  onComplete: (s: number) => void;
  isCompleting: boolean;
  steps: StepState[];
  demoMode?: boolean;
}) {
  const current = tabs.find((t) => t.key === activeTab) ?? tabs[0];
  const activeStepObj = steps.find((s) => s.step === activeStep);
  const canComplete = activeStepObj?.status === "draft";

  return (
    <div style={{
      background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
      borderRadius: "var(--bf-radius-lg)", display: "flex",
      flexDirection: "column", overflow: "hidden",
    }}>
      <div style={{
        display: "flex", borderBottom: "1px solid var(--bf-divider)",
        background: "var(--bf-bg)", flexShrink: 0, minWidth: 0,
      }}>
        <div className="bf-tab-row" style={{ flex: 1, display: "flex", overflowX: "auto", minWidth: 0 }}>
          {tabs.map((t) => {
            const isActive = t.key === activeTab;
            return (
              <button key={t.key}
                onClick={() => !t.locked && onTabChange(t.key)}
                disabled={t.locked}
                style={{
                  padding: "10px 14px",
                  background: isActive ? "var(--bf-bg-elev)" : "transparent",
                  border: "none", borderRight: "1px solid var(--bf-divider)",
                  borderBottom: isActive ? "2px solid var(--bf-primary)" : "2px solid transparent",
                  fontSize: 12, fontWeight: isActive ? 700 : 500,
                  color: t.locked ? "var(--bf-text-4)" : isActive ? "var(--bf-primary)" : "var(--bf-text-2)",
                  cursor: t.locked ? "not-allowed" : "pointer",
                  whiteSpace: "nowrap", display: "inline-flex",
                  alignItems: "center", gap: 6,
                  opacity: t.locked ? 0.5 : 1, flexShrink: 0,
                }}
                title={t.locked ? "対応する STEP の完了後に解放されます" : ""}
              >
                {t.locked && <Lock className="w-3 h-3" />}
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {current && (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          gap: 8, padding: "8px 14px", background: "var(--bf-bg-elev)",
          borderBottom: "1px solid var(--bf-divider)", flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--bf-text-1)" }}>{current.label}</span>
            {current.source_steps?.length > 0 && (
              <span style={{
                fontSize: 10.5, color: "var(--bf-text-4)", background: "var(--bf-bg)",
                border: "1px solid var(--bf-divider)", padding: "1px 6px",
                borderRadius: 999, fontWeight: 500,
              }}>
                STEP {current.source_steps.join(", ")}
              </span>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
            <span style={{ fontSize: 10.5, color: "var(--bf-text-4)", marginRight: 4 }}>ダウンロード</span>
            <DownloadButton tab={current.key} fmt="html" workspaceId={workspaceId} icon={<FileCode2 className="w-3.5 h-3.5" />} label="HTML" />
            <DownloadButton tab={current.key} fmt="md" workspaceId={workspaceId} icon={<FileText className="w-3.5 h-3.5" />} label="MD" />
            <DownloadButton tab={current.key} fmt="json" workspaceId={workspaceId} icon={<FileJson className="w-3.5 h-3.5" />} label="JSON" />
          </div>
        </div>
      )}

      <div className="bf-tab-fadein bf-rd pr-rd" style={{ flex: 1, overflowY: "auto", padding: "var(--bf-space-5)", background: "var(--bf-bg)" }}>
        {!current ? (
          <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>タブが見つかりません。</div>
        ) : demoMode ? (
          /* デモモード: モック準拠のリッチビュー */
          <PricingRichTabContent tabKey={current.key} />
        ) : current.sections.length === 0 ? (
          <div style={{ padding: "var(--bf-space-8) 0", textAlign: "center", color: "var(--bf-text-3)", fontSize: 13 }}>
            <MessageSquare className="w-8 h-8 mx-auto mb-3" style={{ color: "var(--bf-text-4)" }} />
            このタブの内容は、対応する STEP を進めると表示されます。
          </div>
        ) : (
          <div className="rd-section-card">
            <div className="rd-section-header">
              <div className="rd-section-num">{TAB_NUMBER[current.key] ?? "·"}</div>
              <div className="rd-section-title">{current.label}</div>
              {current.source_steps?.length > 0 && (
                <span className="rd-section-step-tag">STEP {current.source_steps.join(", ")}</span>
              )}
            </div>
            {current.sections.map((sec) => (
              <div key={`${sec.source_step}-${sec.key}`} className="rd-subsection">
                <div className="rd-subsection-title">{sec.label}</div>
                <ul className="rd-bullets">
                  {sec.items.map((it, i) => {
                    const k = `${sec.source_step}:${sec.key}:${it}`;
                    const isNew = highlightItems.has(k);
                    return (
                      <li key={`${i}-${it}`} className={isNew ? "bf-highlight" : ""}
                        style={{ animation: isNew ? "bf-fadein 250ms ease-out" : undefined }}>
                        <span style={{ whiteSpace: "pre-wrap" }}>{it}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>

      {canComplete && activeStep != null && (
        <div style={{
          padding: "12px 16px", borderTop: "1px solid var(--bf-divider)",
          background: "var(--bf-bg)", display: "flex",
          justifyContent: "flex-end", flexShrink: 0,
        }}>
          <button disabled={isCompleting} onClick={() => onComplete(activeStep)}
            style={{
              height: 32, padding: "0 14px",
              background: "var(--bf-success)", color: "#fff", border: "none",
              borderRadius: "var(--bf-radius-md)", fontSize: 12.5, fontWeight: 600,
              cursor: "pointer", display: "inline-flex",
              alignItems: "center", gap: 6, opacity: isCompleting ? 0.6 : 1,
            }}>
            {isCompleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            STEP {activeStep} を完了
          </button>
        </div>
      )}
    </div>
  );
}

function DownloadButton({ tab, fmt, workspaceId, icon, label }: {
  tab: string; fmt: "html" | "md" | "json"; workspaceId: number;
  icon: React.ReactNode; label: string;
}) {
  return (
    <a href={pricingDownloadUrl(workspaceId, tab, fmt)} download
      style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "5px 8px", fontSize: 11, fontWeight: 600,
        color: "var(--bf-text-3)", background: "transparent",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-md)",
        textDecoration: "none", transition: "all 150ms",
      }}
      title={`${label} をダウンロード`}>
      {icon}{label}
    </a>
  );
}

/* ───── 右: 統合チャット ───── */
function ChatPanel({ history, activeStep, onSubmit, isReplying }: {
  history: ChatMsg[]; activeStep: number;
  onSubmit: (msg: string) => void; isReplying: boolean;
}) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [history.length]);

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
        background: "var(--bf-bg)", display: "flex",
        alignItems: "center", gap: 8,
      }}>
        <Sparkles className="w-4 h-4" style={{ color: "var(--bf-primary)" }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--bf-text-1)" }}>
          PM AI 社員 (価格設計)
        </span>
        <span style={{ fontSize: 11, color: "var(--bf-text-4)", marginLeft: "auto" }}>
          STEP {activeStep}
        </span>
      </div>

      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "var(--bf-space-4)" }}>
        {renderItems.length === 0 && (
          <div style={{ color: "var(--bf-text-3)", fontSize: 12, textAlign: "center", padding: 24 }}>
            STEP を開始すると、PM AI 社員がここで質問してきます。
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
                }}>
                  STEP {it.data}
                </div>
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
              }}>
                {m.content}
              </div>
            </div>
          );
        })}
        {isReplying && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--bf-text-3)", fontSize: 11.5, padding: "6px 4px" }}>
            <Loader2 className="w-3.5 h-3.5 animate-spin" />AI が考え中…
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          const v = input.trim();
          if (!v || isReplying) return;
          onSubmit(v);
          setInput("");
        }}
        style={{
          padding: "10px 12px", borderTop: "1px solid var(--bf-divider)",
          background: "var(--bf-bg)", display: "flex",
          gap: 6, flexShrink: 0,
        }}
      >
        <input value={input} onChange={(e) => setInput(e.target.value)}
          placeholder={`STEP ${activeStep} の回答や質問を入力…`}
          disabled={isReplying}
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
            cursor: "pointer", display: "inline-flex",
            alignItems: "center", gap: 4,
            opacity: isReplying || !input.trim() ? 0.5 : 1,
          }}>
          <Send className="w-3.5 h-3.5" />
        </button>
      </form>
    </div>
  );
}

/* ═══════════════════════════════════════
 * DEMO (?demo=1)
 * ═══════════════════════════════════════ */
const DEMO_STATE: PricingState = {
  workspace_id: 1, phase: "pricing",
  steps: [
    {
      step: 1, title: "原価試算",
      description: "要件定義から機能別工数を算出し、人件費・ツール・外注を積み上げる",
      status: "confirmed", artifact_id: "demo-1",
      center: { step: 1, sections: [
        { key: "cost_features", label: "機能別工数試算", items: [
          "[F001] 認証・会員管理 (eKYC 連携): 6 人日 (登録/ログイン/管理者承認)",
          "[F002] 商品カタログ・検索: 8 人日 (一覧/絞り込み/全文検索/ページネーション)",
          "[F003] 商品詳細・レコメンド: 5 人日 (詳細 UI + 好み連動レコメンド)",
          "[F004] カート・購入・決済 (Stripe): 7 人日 (カート/Checkout/Webhook/二重課金防止)",
          "[F005] サブスクリプション (定期便): 10 人日 (Stripe Subscription + スキップ/解約)",
          "[F006] BtoB 申込・与信 (Paid 連携): 8 人日 (申込フォーム + 書類 + 与信フロー)",
          "[F007] BtoB 専用ダッシュボード: 6 人日 (一括発注 + 専用価格)",
          "[F008] 顧客マイページ: 5 人日 (注文履歴/好み登録/定期便管理)",
          "[F009] 管理: 商品・在庫 (Shippinno 同期): 8 人日 (CRUD + 1 時間バッチ + 安全在庫アラート)",
          "[F010] 管理: 受注・出荷: 5 人日 (ステータス管理 + CSV エクスポート)",
          "[F011] 管理: 顧客・与信審査: 4 人日",
          "[F012-014] メール配信 / レビュー / クーポン: 計 6 人日",
          "[共通] 設計・テスト・デプロイ・ドキュメント: 12 人日",
          "合計: 90 人日",
        ]},
        { key: "cost_personnel", label: "人件費試算", items: [
          "高本 (PM + 設計 + 主要実装): 60 人日 × 1.2 万円/日 = 72 万円",
          "AI 社員稼働費 (Claude/OpenAI 等): 90 人日 × 0.3 万円/日 = 27 万円",
          "ジュニア外注 (実装サポート): 30 人日 × 0.8 万円/日 = 24 万円",
          "人件費合計: 123 万円",
        ]},
        { key: "cost_tools", label: "ツール・インフラ費", items: [
          "開発期間 (4 か月) のツール費: Vercel/Supabase/Stripe テスト/SendGrid テスト = 6 万円",
          "本番初年度: Vercel Pro + Supabase Pro = 月 6,500 円 × 12 か月 = 7.8 万円 (運用フェーズ)",
          "ツール費合計 (構築期): 6 万円",
        ]},
        { key: "cost_outsource", label: "外注費", items: [
          "デザイン (UI/ロゴ含む): 25 万円",
          "BASE データ移行スクリプト (専門外注): 12 万円",
          "外注費合計: 37 万円",
        ]},
        { key: "cost_total", label: "合計コスト (下限)", items: [
          "人件費 123 万 + ツール 6 万 + 外注 37 万 = 166 万円",
          "粗利率 30% 確保で案件下限 = 166 万 ÷ 0.7 = 約 237 万円",
          "粗利率 40% 確保で = 166 万 ÷ 0.6 = 約 277 万円",
        ]},
      ]},
      history: [
        { id: 1, role: "ai", content: "STEP 1 の原価試算を開始します。要件定義から 14 機能を読み取り、機能別工数を初期試算しました。F001 認証は 6 人日と見積もっていますが、eKYC 連携は経験がありますか?ない場合は +2 人日見ておきましょう。", step: 1 },
        { id: 2, role: "user", content: "eKYC は経験あります。今回は不要です。", step: 1 },
      ],
    },
    {
      step: 2, title: "市場相場・価値試算",
      description: "競合相場と顧客 ROI から中央値・上限を算出",
      status: "confirmed", artifact_id: "demo-2",
      center: { step: 2, sections: [
        { key: "market_competitors", label: "競合相場 (類似案件)", items: [
          "中堅 Web 制作会社の食品 EC + BtoB 連携案件: 350-600 万円 (平均 450 万)",
          "Shopify Plus 構築会社: 250-400 万円 (機能制限ありで対応外)",
          "受注に強いフルスタックフリーランス: 180-350 万円 (品質バラツキ大)",
          "AI 駆動受託 (Build-Factory ポジション): 国内事例少 → 推定 200-400 万円",
        ]},
        { key: "market_position", label: "自社ポジション", items: [
          "強み: 1-2 か月の短納期・AI 社員による反復速度・テンプレ化された運用",
          "弱み: 大型ブランディング・複雑カスタマイズ案件の実績不足",
          "推定ポジション: 中堅 Web 制作の 65-75% 価格帯で同等品質を提供",
          "競合中央値: 350 万円 → 自社ポジション 230-260 万円が市場相場",
        ]},
        { key: "value_roi", label: "顧客 ROI 試算", items: [
          "現状機会損失 (BtoB 取りこぼし 月 5-10 件 × 平均 5 万): 25-50 万/月",
          "サブスクリプション運用工数削減 (月 30 時間 × 3,000 円): 9 万/月",
          "在庫管理自動化 (廃棄ロス + 機会損失 月 8 万): 8 万/月",
          "合計月次効果: 42-67 万円/月 → 年間 504-804 万円",
          "投資回収期間: 構築 250 万なら 5-6 か月で回収可能",
        ]},
        { key: "value_ceiling", label: "価値ベースの価格上限", items: [
          "1 年回収を許容する場合: 年間効果の 70% = 350-560 万円",
          "6 か月回収を求める場合: 半年効果 = 250-400 万円",
          "顧客予算 (中小食品 EC の年間 IT 投資 300-500 万) の 70-80% = 210-400 万円",
          "価値上限: 350 万円 (1 年回収・予算 70%)",
        ]},
      ]},
      history: [],
    },
    {
      step: 3, title: "推奨レンジ・採用案",
      description: "3 軸を統合 + PM とすり合わせて採用見積を確定",
      status: "draft", artifact_id: "demo-3",
      center: { step: 3, sections: [
        { key: "range_summary", label: "3 軸サマリー (下限・中央・上限)", items: [
          "コスト下限 (粗利 40%): 277 万円",
          "競合中央: 自社ポジション 230-260 万円 / 業界平均 350 万円",
          "価値上限 (1 年回収): 350 万円",
          "推奨レンジ: 280-350 万円 (粗利 40% 以上 + 競合中央 + 価値上限内)",
        ]},
        { key: "recommended_amount", label: "推奨見積金額", items: [
          "推奨採用案: 320 万円 (税抜)",
          "粗利率: (320-166) / 320 = 48% (利益 154 万円)",
          "競合相対: 中堅 Web 制作の 71% (350 万 × 0.71)",
          "顧客 ROI: 6.4 か月で回収 (月 50 万効果想定)",
        ]},
        { key: "rationale", label: "採用根拠", items: [
          "コスト下限 (粗利 40% 確保) と競合中央の中間値で着地",
          "顧客の 6 か月以内回収条件を満たす (短期 ROI で稟議が通りやすい)",
          "AI 速度感の優位を価格に転嫁 (中堅 Web 制作より 30% 安価)",
          "値引き余地: 290 万まで下げても粗利 30% 確保可能 (営業ネゴ用バッファ)",
        ]},
        { key: "next_steps", label: "見積書フェーズへの引き継ぎ事項", items: [
          "見積書記載: 構築費 320 万円 (税抜) + 月額保守 月 5 万円",
          "オプション: SEO 月 3 万 / 広告運用 月 5 万 / 追加開発 1 時間 1.5 万",
          "支払条件: 着手金 30% / 中間 30% / 検収後 40%",
          "値引き戦略: 290 万まで OK・それ以下は要相談",
        ]},
      ]},
      history: [],
    },
  ],
};

const DEMO_AGGREGATED: AggregatedView = {
  workspace_id: 1,
  tabs: [
    { key: "cost_estimate", label: "原価試算", locked: false, source_steps: [1],
      sections: [
        { key: "cost_features", label: "機能別工数試算", source_step: 1, items: DEMO_STATE.steps[0].center.sections[0].items },
        { key: "cost_personnel", label: "人件費試算", source_step: 1, items: DEMO_STATE.steps[0].center.sections[1].items },
        { key: "cost_tools", label: "ツール・インフラ費", source_step: 1, items: DEMO_STATE.steps[0].center.sections[2].items },
        { key: "cost_outsource", label: "外注費", source_step: 1, items: DEMO_STATE.steps[0].center.sections[3].items },
        { key: "cost_total", label: "合計コスト (下限)", source_step: 1, items: DEMO_STATE.steps[0].center.sections[4].items },
      ]},
    { key: "market_research", label: "市場相場", locked: false, source_steps: [2],
      sections: [
        { key: "market_competitors", label: "競合相場 (類似案件)", source_step: 2, items: DEMO_STATE.steps[1].center.sections[0].items },
        { key: "market_position", label: "自社ポジション", source_step: 2, items: DEMO_STATE.steps[1].center.sections[1].items },
      ]},
    { key: "value_calc", label: "価値試算", locked: false, source_steps: [2],
      sections: [
        { key: "value_roi", label: "顧客 ROI 試算", source_step: 2, items: DEMO_STATE.steps[1].center.sections[2].items },
        { key: "value_ceiling", label: "価値ベースの価格上限", source_step: 2, items: DEMO_STATE.steps[1].center.sections[3].items },
      ]},
    { key: "recommended_range", label: "推奨レンジ・採用案", locked: false, source_steps: [3],
      sections: [
        { key: "range_summary", label: "3 軸サマリー (下限・中央・上限)", source_step: 3, items: DEMO_STATE.steps[2].center.sections[0].items },
        { key: "recommended_amount", label: "推奨見積金額", source_step: 3, items: DEMO_STATE.steps[2].center.sections[1].items },
        { key: "rationale", label: "採用根拠", source_step: 3, items: DEMO_STATE.steps[2].center.sections[2].items },
        { key: "next_steps", label: "見積書フェーズへの引き継ぎ事項", source_step: 3, items: DEMO_STATE.steps[2].center.sections[3].items },
      ]},
  ],
};
