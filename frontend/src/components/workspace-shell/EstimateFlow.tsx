"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchEstimateState, fetchEstimateAggregatedView,
  startEstimateStep, replyEstimate, completeEstimateStep,
  estimateDownloadUrl,
  type EstimateState, type AggregatedView, type StepState, type ChatMsg,
} from "@/lib/estimate-api";
import {
  Send, Play, Check, Lock, Loader2, FileText, FileCode2, FileJson,
  CheckCircle2, Circle, CircleDot, MessageSquare, Sparkles,
} from "lucide-react";

interface Props {
  workspaceId: number;
  demoMode?: boolean;
}

const TAB_NUMBER: Record<string, number> = {
  basic_info: 1, items: 2, summary: 3, terms: 4,
};

/**
 * Phase 5 見積書: 4 タブ + 統合チャット
 */
export function EstimateFlow({ workspaceId, demoMode = false }: Props) {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<string>("basic_info");
  const [activeStep, setActiveStep] = useState<number | null>(null);

  const { data: liveState, isLoading: liveLoading, error: liveErr } = useQuery<EstimateState>({
    queryKey: ["estimate-state", workspaceId],
    queryFn: () => fetchEstimateState(workspaceId),
    enabled: !!workspaceId && !demoMode,
  });
  const { data: liveAgg } = useQuery<AggregatedView>({
    queryKey: ["estimate-aggregated", workspaceId],
    queryFn: () => fetchEstimateAggregatedView(workspaceId),
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
    mutationFn: (step: number) => startEstimateStep(workspaceId, step),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["estimate-state", workspaceId] }),
  });
  const replyMut = useMutation({
    mutationFn: ({ step, message }: { step: number; message: string }) => replyEstimate(workspaceId, step, message),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["estimate-state", workspaceId] });
      qc.invalidateQueries({ queryKey: ["estimate-aggregated", workspaceId] });
    },
  });
  const completeMut = useMutation({
    mutationFn: (step: number) => completeEstimateStep(workspaceId, step),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["estimate-state", workspaceId] });
      qc.invalidateQueries({ queryKey: ["estimate-aggregated", workspaceId] });
      if (data.next_step) setActiveStep(data.next_step);
    },
  });

  if (isLoading) return <div style={{ padding: 40, color: "var(--bf-text-3)" }}>見積書を読み込み中…</div>;
  if (error || !state) {
    return <div style={{
      padding: 24, background: "var(--bf-danger-bg)", border: "1px solid var(--bf-danger)",
      borderRadius: "var(--bf-radius-lg)", color: "var(--bf-danger)", fontSize: 13,
    }}>見積書 API に接続できません。</div>;
  }

  const current = tabs.find((t) => t.key === activeTab) ?? tabs[0];
  const activeStepObj = steps.find((s) => s.step === activeStep);
  const canComplete = activeStepObj?.status === "draft";

  return (
    <>
      <style>{`
        @keyframes bf-fadein { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
        .bf-tab-fadein { animation: bf-fadein 250ms ease-out; }
        .bf-tab-row { scrollbar-width: none; -ms-overflow-style: none; }
        .bf-tab-row::-webkit-scrollbar { display: none; height: 0; width: 0; }

        .es-rd { font-feature-settings: "palt"; }
        .es-rd .es-section-card {
          background: #fff; border: 1px solid var(--bf-border);
          border-radius: 12px; padding: 28px 32px; margin-bottom: 16px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .es-rd .es-section-header {
          display: flex; align-items: center; gap: 12px;
          margin-bottom: 20px; padding-bottom: 14px;
          border-bottom: 1px solid var(--bf-divider);
        }
        .es-rd .es-section-num {
          width: 32px; height: 32px; flex-shrink: 0;
          background: linear-gradient(135deg, var(--bf-primary) 0%, #1A5FE0 100%);
          color: #fff; border-radius: 8px;
          display: flex; align-items: center; justify-content: center;
          font-size: 14px; font-weight: 800;
        }
        .es-rd .es-section-title { font-size: 18px; font-weight: 700; color: var(--bf-primary); }
        .es-rd .es-subsection { margin-bottom: 18px; }
        .es-rd .es-subsection:last-child { margin-bottom: 0; }
        .es-rd .es-subsection-title {
          font-size: 12px; font-weight: 700; color: var(--bf-text-3);
          letter-spacing: 0.06em; text-transform: uppercase;
          margin-bottom: 10px;
        }
        .es-rd .es-bullets { list-style: none; padding: 0; margin: 0; }
        .es-rd .es-bullets li {
          padding: 10px 14px; font-size: 13.5px; line-height: 1.7;
          color: var(--bf-text-1); background: var(--bf-bg);
          border: 1px solid var(--bf-divider); border-radius: 8px;
          margin-bottom: 6px;
          white-space: pre-wrap;
        }
        .es-rd .es-bullets li:last-child { margin-bottom: 0; }
      `}</style>

      <div style={{
        display: "grid",
        gridTemplateColumns: "240px 1fr 380px",
        gap: "var(--bf-space-5)",
        height: "calc(100vh - var(--bf-header-h) - 200px)",
      }}>
        <StepProgress steps={steps} activeStep={activeStep} onSelect={setActiveStep}
          onStart={(s) => startMut.mutate(s)} isStarting={startMut.isPending} />

        <div style={{
          background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
          borderRadius: "var(--bf-radius-lg)", display: "flex",
          flexDirection: "column", overflow: "hidden",
        }}>
          <div style={{
            display: "flex", borderBottom: "1px solid var(--bf-divider)",
            background: "var(--bf-bg)", flexShrink: 0,
          }}>
            <div className="bf-tab-row" style={{ flex: 1, display: "flex", overflowX: "auto", minWidth: 0 }}>
              {tabs.map((t) => {
                const isActive = t.key === activeTab;
                return (
                  <button key={t.key}
                    onClick={() => !t.locked && setActiveTab(t.key)}
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
                      opacity: t.locked ? 0.5 : 1,
                    }}>
                    {t.locked && <Lock className="w-3 h-3" />}{t.label}
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
              <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--bf-text-1)" }}>{current.label}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ fontSize: 10.5, color: "var(--bf-text-4)", marginRight: 4 }}>ダウンロード</span>
                <DLBtn tab={current.key} fmt="html" workspaceId={workspaceId} icon={<FileCode2 className="w-3.5 h-3.5" />} label="HTML" />
                <DLBtn tab={current.key} fmt="md" workspaceId={workspaceId} icon={<FileText className="w-3.5 h-3.5" />} label="MD" />
                <DLBtn tab={current.key} fmt="json" workspaceId={workspaceId} icon={<FileJson className="w-3.5 h-3.5" />} label="JSON" />
              </div>
            </div>
          )}

          <div className="bf-tab-fadein es-rd" style={{ flex: 1, overflowY: "auto", padding: "var(--bf-space-5)", background: "var(--bf-bg)" }}>
            {!current ? (
              <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>タブが見つかりません。</div>
            ) : current.sections.length === 0 || current.sections.every((s) => (s.items ?? []).length === 0) ? (
              <div style={{ padding: 40, textAlign: "center", color: "var(--bf-text-3)", fontSize: 13 }}>
                <MessageSquare className="w-8 h-8 mx-auto mb-3" style={{ color: "var(--bf-text-4)" }} />
                STEP を開始すると、PM AI が見積項目を埋めます。
              </div>
            ) : (
              <div className="es-section-card">
                <div className="es-section-header">
                  <div className="es-section-num">{TAB_NUMBER[current.key] ?? "·"}</div>
                  <div className="es-section-title">{current.label}</div>
                </div>
                {current.sections.map((sec) => (
                  <div key={`${sec.source_step}-${sec.key}`} className="es-subsection">
                    {current.sections.length > 1 && <div className="es-subsection-title">{sec.label}</div>}
                    <ul className="es-bullets">
                      {sec.items.map((it, i) => <li key={i}>{it}</li>)}
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
              <button disabled={completeMut.isPending} onClick={() => completeMut.mutate(activeStep)}
                style={{
                  height: 32, padding: "0 14px",
                  background: "var(--bf-success)", color: "#fff", border: "none",
                  borderRadius: "var(--bf-radius-md)", fontSize: 12.5, fontWeight: 600,
                  cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6,
                  opacity: completeMut.isPending ? 0.6 : 1,
                }}>
                {completeMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                STEP {activeStep} を完了
              </button>
            </div>
          )}
        </div>

        <ChatPanel history={fullHistory} activeStep={activeStep ?? 1}
          onSubmit={(msg) => activeStep != null && replyMut.mutate({ step: activeStep, message: msg })}
          isReplying={replyMut.isPending} />
      </div>
    </>
  );
}

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
      }}>Phase 5 / 見積書</div>
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
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--bf-text-1)" }}>STEP {s.step} {s.title}</div>
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

function DLBtn({ tab, fmt, workspaceId, icon, label }: {
  tab: string; fmt: "html" | "md" | "json"; workspaceId: number;
  icon: React.ReactNode; label: string;
}) {
  return (
    <a href={estimateDownloadUrl(workspaceId, tab, fmt)} download
      style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "5px 8px", fontSize: 11, fontWeight: 600,
        color: "var(--bf-text-3)", background: "transparent",
        border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)",
        textDecoration: "none",
      }}>{icon}{label}</a>
  );
}

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
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--bf-text-1)" }}>PM AI 社員 (見積書)</span>
        <span style={{ fontSize: 11, color: "var(--bf-text-4)", marginLeft: "auto" }}>STEP {activeStep}</span>
      </div>
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "var(--bf-space-4)" }}>
        {renderItems.length === 0 && (
          <div style={{ color: "var(--bf-text-3)", fontSize: 12, textAlign: "center", padding: 24 }}>
            STEP を開始すると、PM AI が見積項目を埋めていきます。
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

/* ═══════════ DEMO ═══════════ */
const DEMO_STATE: EstimateState = {
  workspace_id: 1, phase: "estimate",
  steps: [
    { step: 1, title: "見積項目確認", description: "前フェーズ引き継ぎ + 明細確定", status: "confirmed", artifact_id: "demo-1",
      center: { step: 1, sections: [
        { key: "basic", label: "基本情報", items: [
          "見積番号: EST-20260508-001",
          "発行日: 2026 年 5 月 8 日",
          "有効期限: 2026 年 6 月 7 日",
          "宛先: 株式会社○○珈琲 御中 / 田中 様",
          "件名: 自家焙煎コーヒー豆 EC サイト構築 御見積書",
        ]},
        { key: "items", label: "見積項目", items: [
          "1. 中核機能開発 (商品/カート/決済) / 1 式 / 1,200,000 円 / 1,200,000 円",
          "2. サブスクリプション機能 (定期便) / 1 式 / 600,000 円 / 600,000 円",
          "3. BtoB 機能 (申込・与信・専用ダッシュボード) / 1 式 / 700,000 円 / 700,000 円",
          "4. 管理画面 (商品/在庫/受注/顧客) / 1 式 / 400,000 円 / 400,000 円",
          "5. Shippinno 在庫同期連携 / 1 式 / 200,000 円 / 200,000 円",
          "6. BASE データ移行 / 1 式 / 100,000 円 / 100,000 円",
        ]},
        { key: "summary", label: "金額サマリー", items: [
          "小計: 3,200,000 円",
          "消費税 (10%): 320,000 円",
          "合計: 3,520,000 円 (税込)",
        ]},
        { key: "payment", label: "支払い条件", items: [
          "着手金: 30% (96 万円・税抜) — 契約後 7 日以内",
          "中間金: 30% (96 万円・税抜) — 7 月末",
          "残金: 40% (128 万円・税抜) — 検収完了後 14 日以内",
        ]},
        { key: "bank", label: "振込先", items: [
          "銀行名: 三菱 UFJ 銀行 / 渋谷支店",
          "口座種別: 普通",
          "口座番号: 1234567",
          "口座名義: カ) エンジンベース",
        ]},
        { key: "notes", label: "備考・特記事項", items: [
          "本見積書の有効期限は発行日より 30 日間です。",
          "保証期間: 検収完了後 90 日間 (バグ修正・軽微な改修は無償対応)。",
          "範囲外の追加開発は別途お見積りいたします。",
          "月額保守: 5 万円 (税抜) / 月 — 契約は別途締結。",
        ]},
      ]},
      history: [
        { id: 1, role: "ai", content: "STEP 1 を始めます。価格設計の推奨見積金額 320 万円を基本情報・見積項目に反映しました。支払い条件は 30/30/40 で良いですか?", step: 1 },
        { id: 2, role: "user", content: "それで OK です。検収後 14 日以内で。", step: 1 },
      ],
    },
    { step: 2, title: "最終出力", description: "HTML/MD/JSON 一括出力", status: "not_started", artifact_id: null,
      center: { step: 2, sections: [{ key: "summary_final", label: "出力前最終確認", items: [] }] }, history: [],
    },
  ],
};

const DEMO_AGGREGATED: AggregatedView = {
  workspace_id: 1,
  tabs: [
    { key: "basic_info", label: "基本情報", locked: false, source_steps: [1],
      sections: [{ key: "basic", label: "基本情報", source_step: 1, items: DEMO_STATE.steps[0].center.sections[0].items }] },
    { key: "items", label: "見積項目", locked: false, source_steps: [1],
      sections: [{ key: "items", label: "見積項目", source_step: 1, items: DEMO_STATE.steps[0].center.sections[1].items }] },
    { key: "summary", label: "金額サマリー", locked: false, source_steps: [1],
      sections: [{ key: "summary", label: "金額サマリー", source_step: 1, items: DEMO_STATE.steps[0].center.sections[2].items }] },
    { key: "terms", label: "支払・振込・備考", locked: false, source_steps: [1],
      sections: [
        { key: "payment", label: "支払い条件", source_step: 1, items: DEMO_STATE.steps[0].center.sections[3].items },
        { key: "bank", label: "振込先", source_step: 1, items: DEMO_STATE.steps[0].center.sections[4].items },
        { key: "notes", label: "備考・特記事項", source_step: 1, items: DEMO_STATE.steps[0].center.sections[5].items },
      ]},
  ],
};
