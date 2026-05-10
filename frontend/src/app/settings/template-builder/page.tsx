"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Send, Play, Check, Loader2, CheckCircle2, Circle, CircleDot,
  Sparkles, Wand2, Eye, ArrowRight, CheckIcon, StarIcon,
} from "lucide-react";
import {
  fetchBuilderState, startBuilderStep, replyBuilder, completeBuilderStep,
  type BuilderState, type ChatMsg, type BuilderStepState,
} from "@/lib/template-builder-api";

const ACCOUNT_ID = 1;

export default function TemplateBuilderPage() {
  const qc = useQueryClient();
  const [activeStep, setActiveStep] = useState<number | null>(null);

  const { data: state, isLoading } = useQuery<BuilderState>({
    queryKey: ["template-builder-state", ACCOUNT_ID],
    queryFn: () => fetchBuilderState(ACCOUNT_ID),
    refetchInterval: 8000,
  });

  const steps = state?.steps ?? [];

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
    mutationFn: (step: number) => startBuilderStep(ACCOUNT_ID, step),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["template-builder-state", ACCOUNT_ID] }),
  });
  const replyMut = useMutation({
    mutationFn: ({ step, message }: { step: number; message: string }) =>
      replyBuilder(ACCOUNT_ID, step, message),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["template-builder-state", ACCOUNT_ID] }),
  });
  const completeMut = useMutation({
    mutationFn: (step: number) => completeBuilderStep(ACCOUNT_ID, step),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["template-builder-state", ACCOUNT_ID] });
      if (data.next_step) setActiveStep(data.next_step);
    },
  });

  if (isLoading || !state) {
    return <div style={{ padding: 40, color: "var(--bf-text-3)" }}>
      <Loader2 className="w-5 h-5 inline mr-2 animate-spin" />読み込み中…
    </div>;
  }

  return (
    <div style={{ padding: "var(--bf-space-6)", height: "100vh", overflow: "hidden", display: "flex", flexDirection: "column" }}>
      {/* ヘッダー */}
      <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10,
          background: "linear-gradient(135deg, var(--bf-primary) 0%, #1A5FE0 100%)",
          color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 4px 12px rgba(0,76,217,0.2)",
        }}>
          <Wand2 className="w-5 h-5" />
        </div>
        <div style={{ flex: 1 }}>
          <h1 style={{ fontSize: 20, fontWeight: 800, color: "var(--bf-text-1)" }}>テンプレートビルダー</h1>
          <p style={{ fontSize: 12, color: "var(--bf-text-3)" }}>
            AI と対話で自社専用の提案書テンプレートを設計します。完了後、提案書/見積書フェーズで自動的にこのテンプレが使われます。
          </p>
        </div>
        <a
          href="/settings/account"
          style={{ fontSize: 12, color: "var(--bf-primary)", textDecoration: "none", padding: "6px 12px", border: "1px solid var(--bf-primary)", borderRadius: 6, fontWeight: 600 }}
        >会社設定へ ↗</a>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "240px 1fr 380px",
        gap: 16,
        flex: 1, minHeight: 0,
      }}>
        {/* 左: STEP プログレス */}
        <StepProgress
          steps={steps}
          activeStep={activeStep}
          onSelect={setActiveStep}
          onStart={(s) => startMut.mutate(s)}
          isStarting={startMut.isPending}
        />

        {/* 中央: 中央エリア (累積セクション) */}
        <CenterPanel
          steps={steps}
          activeStep={activeStep}
          template_config={state.template_config}
          onComplete={(s) => completeMut.mutate(s)}
          isCompleting={completeMut.isPending}
        />

        {/* 右: チャット */}
        <ChatPanel
          history={fullHistory}
          activeStep={activeStep ?? 1}
          onSubmit={(msg) => activeStep != null && replyMut.mutate({ step: activeStep, message: msg })}
          isReplying={replyMut.isPending}
        />
      </div>
    </div>
  );
}

/* ─── 左: STEP ─── */
function StepProgress({ steps, activeStep, onSelect, onStart, isStarting }: {
  steps: BuilderStepState[]; activeStep: number | null;
  onSelect: (s: number) => void; onStart: (s: number) => void; isStarting: boolean;
}) {
  return (
    <div style={{
      background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
      borderRadius: "var(--bf-radius-lg)", padding: 14, overflowY: "auto",
    }}>
      <div style={{
        fontSize: 10.5, fontWeight: 700, color: "var(--bf-text-4)",
        letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 12,
      }}>Phase 0 / テンプレ設計</div>
      {steps.map((s) => {
        const isActive = activeStep === s.step;
        const Icon = s.status === "confirmed" ? CheckCircle2 : isActive ? CircleDot : Circle;
        const color = s.status === "confirmed" ? "var(--bf-success)" : isActive ? "var(--bf-primary)" : "var(--bf-text-4)";
        return (
          <div key={s.step} role="button" tabIndex={0}
            onClick={() => onSelect(s.step)}
            onKeyDown={(e) => { if (e.key === "Enter") onSelect(s.step); }}
            style={{
              display: "flex", alignItems: "flex-start", gap: 10,
              padding: "10px 12px", marginBottom: 4,
              background: isActive ? "var(--bf-primary-bg)" : "transparent",
              border: "none", borderRadius: 8, cursor: "pointer",
            }}
          >
            <Icon className="w-4 h-4 mt-0.5" style={{ color, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--bf-text-1)" }}>
                STEP {s.step} {s.title}
              </div>
              <div style={{ fontSize: 10.5, color: "var(--bf-text-3)", marginTop: 2 }}>
                {s.status === "confirmed" ? "確定" : s.status === "draft" ? "進行中" : "未着手"}
              </div>
              {isActive && s.status === "not_started" && (
                <button onClick={(e) => { e.stopPropagation(); onStart(s.step); }} disabled={isStarting}
                  style={{
                    marginTop: 8, padding: "4px 10px",
                    background: "var(--bf-primary)", color: "#fff", border: "none",
                    borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: "pointer",
                    display: "inline-flex", alignItems: "center", gap: 4,
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

/* ─── 中央: 構築中の template_config プレビュー ─── */
function CenterPanel({
  steps, activeStep, template_config, onComplete, isCompleting,
}: {
  steps: BuilderStepState[];
  activeStep: number | null;
  template_config: Record<string, any>;
  onComplete: (s: number) => void;
  isCompleting: boolean;
}) {
  const activeStepObj = steps.find((s) => s.step === activeStep);
  const canComplete = activeStepObj?.status === "draft";

  return (
    <div style={{
      background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
      borderRadius: "var(--bf-radius-lg)", display: "flex",
      flexDirection: "column", overflow: "hidden",
    }}>
      <div style={{
        padding: "12px 16px", background: "var(--bf-bg)",
        borderBottom: "1px solid var(--bf-divider)",
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <Eye className="w-4 h-4" style={{ color: "var(--bf-primary)" }} />
        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--bf-text-1)" }}>
          構築中のテンプレート設計
        </span>
        {activeStepObj && (
          <span style={{
            marginLeft: "auto", fontSize: 10.5, color: "var(--bf-text-4)",
            background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
            padding: "2px 8px", borderRadius: 999, fontWeight: 600,
          }}>STEP {activeStepObj.step}: {activeStepObj.title}</span>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
        {steps.map((s) => {
          const sections = s.center?.sections ?? [];
          const hasContent = sections.some((sec) => (sec.items ?? []).length > 0);
          if (!hasContent && s.status === "not_started") return null;
          return (
            <div key={s.step} style={{
              marginBottom: 18, padding: 16,
              background: s.status === "confirmed" ? "rgba(22,163,74,0.04)" : "var(--bf-bg)",
              border: `1px solid ${s.status === "confirmed" ? "rgba(22,163,74,0.2)" : "var(--bf-divider)"}`,
              borderRadius: 10,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <span style={{
                  width: 22, height: 22, borderRadius: 6,
                  background: s.status === "confirmed" ? "var(--bf-success)" : "var(--bf-primary)",
                  color: "#fff", fontSize: 11, fontWeight: 800,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>{s.step}</span>
                <span style={{ fontSize: 13.5, fontWeight: 700, color: "var(--bf-text-1)" }}>{s.title}</span>
                {s.status === "confirmed" && (
                  <span style={{
                    marginLeft: "auto", fontSize: 10, fontWeight: 700,
                    color: "var(--bf-success)", background: "rgba(22,163,74,0.1)",
                    padding: "2px 8px", borderRadius: 999,
                    display: "inline-flex", alignItems: "center", gap: 4,
                  }}><CheckIcon className="w-3 h-3" aria-label="confirmed" /> 確定</span>
                )}
              </div>
              {sections.map((sec) => sec.items.length > 0 && (
                <div key={sec.key} style={{ marginBottom: 10 }}>
                  <div style={{
                    fontSize: 11, fontWeight: 700, color: "var(--bf-text-3)",
                    letterSpacing: "0.05em", marginBottom: 6,
                  }}>{sec.label}</div>
                  <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                    {sec.items.map((it, i) => (
                      <li key={i} style={{
                        padding: "6px 10px", fontSize: 12.5, color: "var(--bf-text-2)",
                        background: "var(--bf-bg-elev)", border: "1px solid var(--bf-divider)",
                        borderRadius: 6, marginBottom: 4,
                        whiteSpace: "pre-wrap",
                      }}>{it}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          );
        })}

        {/* 全 STEP で何も埋まっていない時の空状態 */}
        {steps.every((s) => !(s.center?.sections ?? []).some((sec) => (sec.items ?? []).length > 0)) && (
          <div style={{ padding: 40, textAlign: "center", color: "var(--bf-text-3)", fontSize: 13 }}>
            <Sparkles className="w-8 h-8 mx-auto mb-3" style={{ color: "var(--bf-text-4)" }} />
            左から STEP 1 を「開始」すると、AI が業種・読者像を確認して<br />テンプレ構成を提案します。
          </div>
        )}

        {/* 最終 template_config プレビュー */}
        {Object.keys(template_config || {}).filter((k) => !k.startsWith("_")).length > 0 && (
          <div style={{
            marginTop: 24, padding: 16, background: "var(--bf-primary-bg)",
            border: "1px solid var(--bf-primary)", borderRadius: 10,
          }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: "var(--bf-primary)", letterSpacing: "0.06em", marginBottom: 8, display: "inline-flex", alignItems: "center", gap: 4 }}>
              <StarIcon className="w-3 h-3" aria-label="confirmed template" /> 確定済みテンプレ構成 (template_config)
            </div>
            <pre style={{
              fontSize: 11, lineHeight: 1.55, color: "var(--bf-text-2)",
              background: "var(--bf-bg-elev)", padding: 10, borderRadius: 6,
              overflow: "auto", maxHeight: 200,
              fontFamily: "'SF Mono', 'Courier New', monospace",
            }}>
              {JSON.stringify(
                Object.fromEntries(Object.entries(template_config).filter(([k]) => !k.startsWith("_"))),
                null, 2
              )}
            </pre>
          </div>
        )}
      </div>

      {canComplete && activeStep != null && (
        <div style={{
          padding: "12px 16px", borderTop: "1px solid var(--bf-divider)",
          background: "var(--bf-bg)", display: "flex", justifyContent: "flex-end",
        }}>
          <button disabled={isCompleting} onClick={() => onComplete(activeStep)}
            style={{
              height: 34, padding: "0 16px",
              background: "var(--bf-success)", color: "#fff", border: "none",
              borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: "pointer",
              display: "inline-flex", alignItems: "center", gap: 6,
              opacity: isCompleting ? 0.6 : 1,
            }}>
            {isCompleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            STEP {activeStep} を完了
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}

/* ─── 右: チャット ─── */
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
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--bf-text-1)" }}>テンプレ AI ビルダー</span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--bf-text-4)" }}>STEP {activeStep}</span>
      </div>
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: 14 }}>
        {renderItems.length === 0 && (
          <div style={{ color: "var(--bf-text-3)", fontSize: 12, textAlign: "center", padding: 24, lineHeight: 1.7 }}>
            STEP を開始すると、AI が業種・読者・実績見せ方などを確認して<br />
            最適なテンプレ構成を提案します。
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
                borderRadius: 10,
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
          background: "var(--bf-bg)", display: "flex", gap: 6,
        }}>
        <input value={input} onChange={(e) => setInput(e.target.value)}
          placeholder={`STEP ${activeStep} の回答を入力…`} disabled={isReplying}
          style={{
            flex: 1, height: 32, padding: "0 10px",
            background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
            borderRadius: 6, fontSize: 12.5, color: "var(--bf-text-1)",
          }} />
        <button type="submit" disabled={isReplying || !input.trim()}
          style={{
            height: 32, padding: "0 12px",
            background: "var(--bf-primary)", color: "#fff", border: "none",
            borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
            display: "inline-flex", alignItems: "center", gap: 4,
            opacity: isReplying || !input.trim() ? 0.5 : 1,
          }}><Send className="w-3.5 h-3.5" /></button>
      </form>
    </div>
  );
}
