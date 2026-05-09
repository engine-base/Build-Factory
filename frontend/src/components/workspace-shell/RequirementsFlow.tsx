"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchRequirementsState,
  fetchAggregatedView,
  startRequirementsStep,
  replyRequirements,
  completeRequirementsStep,
  downloadUrl,
  type RequirementsState,
  type AggregatedView,
  type StepState,
  type ChatMsg,
} from "@/lib/requirements-api";
import {
  Send, Play, Check, Lock, Loader2, Download, FileText, FileCode2, FileJson,
  CheckCircle2, Circle, CircleDot, MessageSquare, X, Sparkles,
} from "lucide-react";
import { RichTabContent } from "./RequirementsRichDemo";

interface Props {
  workspaceId: number;
  /** ?demo=1 で全タブダミーデータ表示モード */
  demoMode?: boolean;
}

/* ───── タブ番号マップ (HTML テンプレートと同じ) ───── */
const TAB_NUMBER: Record<string, number> = {
  overview: 1,
  users: 2,
  features: 3,
  functional: 4,
  nonfunctional: 5,
  screens: 6,
  data: 7,
  integrations: 8,
  legal: 9,
  risks: 10,
  infra_cost: 11,
  unresolved: 12,
  scope: 13,
  history: 14,
};

/**
 * Phase 2 要件定義 IDE 風タブ UI (モック)
 *
 * レイアウト (3 カラム):
 *   ┌ 左: STEP プログレス ─┬ 中央: IDE タブ + 内容 ─┬ 右: 統合チャット ┐
 *
 * 仕様:
 *   - STEP 完了に応じてタブが順次活性化 (Q1=c)
 *   - チャットは全 STEP 通して 1 本 (一人の AI 社員)
 *   - STEP 1 開始時にヒアリング引き継ぎモーダル
 *   - タブヘッダー右端に HTML/MD/JSON ダウンロードボタン
 *   - 新規追加項目はフェード+ハイライト
 */
export function RequirementsFlow({ workspaceId, demoMode = false }: Props) {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [showHearingIntro, setShowHearingIntro] = useState(false);
  const [highlightItems, setHighlightItems] = useState<Set<string>>(new Set());

  const { data: liveState, isLoading: liveLoading, error: liveErr } = useQuery<RequirementsState>({
    queryKey: ["requirements-state", workspaceId],
    queryFn: () => fetchRequirementsState(workspaceId),
    enabled: !!workspaceId && !demoMode,
  });

  const { data: liveAgg } = useQuery<AggregatedView>({
    queryKey: ["requirements-aggregated", workspaceId],
    queryFn: () => fetchAggregatedView(workspaceId),
    enabled: !!workspaceId && !demoMode,
    refetchInterval: 5000,
  });

  const state = demoMode ? DEMO_STATE : liveState;
  const agg = demoMode ? DEMO_AGGREGATED : liveAgg;
  const isLoading = demoMode ? false : liveLoading;
  const error = demoMode ? null : liveErr;

  const steps = state?.steps ?? [];
  const tabs = agg?.tabs ?? [];

  // 初回 active step 決定
  useEffect(() => {
    if (steps.length === 0 || activeStep != null) return;
    const inProg = steps.find((s) => s.status === "draft");
    const next = inProg ?? steps.find((s) => s.status === "not_started");
    setActiveStep(next?.step ?? steps[0]?.step ?? 1);

    // STEP 1 がまだ未着手 → ヒアリング引き継ぎモーダルを開く
    const step1 = steps.find((s) => s.step === 1);
    if (step1 && step1.status === "not_started") {
      setShowHearingIntro(true);
    }
  }, [steps, activeStep]);

  // 統合履歴 (全 STEP の chat を時系列で並べる)
  const fullHistory = useMemo<ChatMsg[]>(() => {
    const out: ChatMsg[] = [];
    for (const s of steps) {
      for (const m of s.history ?? []) {
        out.push({ ...m, step: s.step });
      }
    }
    return out.sort((a, b) => (a.id ?? 0) - (b.id ?? 0));
  }, [steps]);

  const startMut = useMutation({
    mutationFn: (step: number) => startRequirementsStep(workspaceId, step),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["requirements-state", workspaceId] }),
  });

  const replyMut = useMutation({
    mutationFn: ({ step, message }: { step: number; message: string }) =>
      replyRequirements(workspaceId, step, message),
    onSuccess: (data, vars) => {
      const added = new Set<string>();
      for (const op of data.patch ?? []) {
        if (op.operation !== "remove") {
          for (const it of (op.items ?? [])) {
            added.add(`${vars.step}:${op.section_key}:${it}`);
          }
        }
      }
      setHighlightItems(added);
      setTimeout(() => setHighlightItems(new Set()), 2000);
      qc.invalidateQueries({ queryKey: ["requirements-state", workspaceId] });
      qc.invalidateQueries({ queryKey: ["requirements-aggregated", workspaceId] });
    },
  });

  const completeMut = useMutation({
    mutationFn: (step: number) => completeRequirementsStep(workspaceId, step),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["requirements-state", workspaceId] });
      qc.invalidateQueries({ queryKey: ["requirements-aggregated", workspaceId] });
      if (data.next_step) setActiveStep(data.next_step);
    },
  });

  if (isLoading) {
    return <div style={{ padding: 40, color: "var(--bf-text-3)" }}>要件定義状態を読み込み中…</div>;
  }
  if (error || !state) {
    return (
      <div
        style={{
          padding: "var(--bf-space-6)",
          background: "var(--bf-danger-bg)",
          border: "1px solid var(--bf-danger)",
          borderRadius: "var(--bf-radius-lg)",
          color: "var(--bf-danger)",
          fontSize: 13,
        }}
      >
        要件定義 API に接続できません。バックエンドの起動を確認してください。
      </div>
    );
  }

  return (
    <>
      <style>{`
        @keyframes bf-fadein {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .bf-tab-fadein { animation: bf-fadein 250ms ease-out; }
        .bf-highlight {
          background: var(--bf-success-bg) !important;
          transition: background 1500ms ease-out;
        }

        /* タブ行のスクロールバー非表示 */
        .bf-tab-row { scrollbar-width: none; -ms-overflow-style: none; }
        .bf-tab-row::-webkit-scrollbar { display: none; height: 0; width: 0; }

        /* === Requirements Document Template Styles (faithful clone, BF primary) === */
        .bf-rd { font-feature-settings: "palt"; }
        .bf-rd p, .bf-rd .rd-p { font-size: 13px; color: var(--bf-text-2); line-height: 1.75; margin-bottom: 10px; }
        .bf-rd p:last-child, .bf-rd .rd-p:last-child { margin-bottom: 0; }
        .bf-rd ul, .bf-rd ol { padding-left: 18px; font-size: 12.5px; color: var(--bf-text-2); line-height: 1.7; }
        .bf-rd li { margin-bottom: 4px; }
        .bf-rd li:last-child { margin-bottom: 0; }
        .bf-rd strong { color: var(--bf-text-1); font-weight: 700; }

        .bf-rd .rd-section-card {
          background: var(--bf-bg-elev);
          border: 1px solid var(--bf-border);
          border-radius: 8px;
          padding: 28px 32px;
          margin-bottom: 16px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .bf-rd .rd-section-header {
          display: flex; align-items: center; gap: 12px;
          margin-bottom: 20px; padding-bottom: 14px;
          border-bottom: 1px solid var(--bf-divider);
        }
        .bf-rd .rd-section-num {
          width: 28px; height: 28px; flex-shrink: 0;
          background: var(--bf-primary); color: #fff;
          border-radius: 4px;
          display: flex; align-items: center; justify-content: center;
          font-size: 12px; font-weight: 700;
        }
        .bf-rd .rd-section-title {
          font-size: 16px; font-weight: 700; color: var(--bf-primary);
        }
        .bf-rd .rd-section-step-tag {
          margin-left: auto; font-size: 10.5px; font-weight: 600;
          color: var(--bf-text-4); padding: 3px 9px; border-radius: 999px;
          background: var(--bf-bg); border: 1px solid var(--bf-divider);
        }

        .bf-rd .rd-subsection { margin-bottom: 22px; }
        .bf-rd .rd-subsection:last-child { margin-bottom: 0; }
        .bf-rd .rd-subsection-title {
          font-size: 13px; font-weight: 700; color: var(--bf-text-1);
          margin-bottom: 10px;
          padding-left: 10px;
          border-left: 3px solid var(--bf-primary);
        }

        /* table */
        .bf-rd .rd-table-wrap {
          overflow-x: auto;
          border-radius: 6px;
          border: 1px solid var(--bf-divider);
        }
        .bf-rd table {
          width: 100%; border-collapse: collapse; font-size: 12.5px;
        }
        .bf-rd thead th {
          background: var(--bf-primary); color: #fff; font-weight: 600;
          padding: 9px 12px; text-align: left; font-size: 12px;
        }
        .bf-rd tbody td {
          padding: 8px 12px; border-top: 1px solid var(--bf-divider);
          vertical-align: top; color: var(--bf-text-2);
        }
        .bf-rd tbody tr:nth-child(even) td { background: var(--bf-bg); }
        .bf-rd tbody tr:hover td { background: var(--bf-primary-bg); }

        /* info-grid */
        .bf-rd .rd-info-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 12px; margin-bottom: 16px;
        }
        .bf-rd .rd-info-card {
          background: var(--bf-bg); border: 1px solid var(--bf-divider);
          border-radius: 6px; padding: 12px 14px;
        }
        .bf-rd .rd-info-card-label {
          font-size: 10px; font-weight: 600; color: var(--bf-text-4);
          letter-spacing: 0.06em; text-transform: uppercase;
          margin-bottom: 4px;
        }
        .bf-rd .rd-info-card-value {
          font-size: 13px; color: var(--bf-text-1); font-weight: 500;
        }

        /* persona */
        .bf-rd .rd-persona-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
          gap: 12px;
        }
        .bf-rd .rd-persona-card {
          border: 1px solid var(--bf-divider);
          border-radius: 8px; overflow: hidden;
          background: var(--bf-bg);
        }
        .bf-rd .rd-persona-header {
          background: var(--bf-primary); padding: 10px 14px;
          display: flex; align-items: center; gap: 8px;
        }
        .bf-rd .rd-persona-icon { font-size: 16px; }
        .bf-rd .rd-persona-title { font-size: 12px; font-weight: 700; color: #fff; }
        .bf-rd .rd-persona-body { padding: 12px 14px; }
        .bf-rd .rd-persona-row { margin-bottom: 8px; font-size: 12px; }
        .bf-rd .rd-persona-row:last-child { margin-bottom: 0; }
        .bf-rd .rd-persona-row-label {
          font-size: 10px; font-weight: 600;
          color: var(--bf-text-4); margin-bottom: 2px;
        }
        .bf-rd .rd-persona-row-value { color: var(--bf-text-2); line-height: 1.55; }

        /* feature-block */
        .bf-rd .rd-feature-block {
          border: 1px solid var(--bf-divider); border-radius: 8px;
          overflow: hidden; margin-bottom: 16px; background: var(--bf-bg);
        }
        .bf-rd .rd-feature-block:last-child { margin-bottom: 0; }
        .bf-rd .rd-feature-header {
          display: flex; align-items: center; gap: 10px;
          padding: 12px 16px; background: var(--bf-bg-elev);
          border-bottom: 1px solid var(--bf-divider);
        }
        .bf-rd .rd-feature-id {
          font-size: 11px; font-weight: 700; color: var(--bf-primary);
          background: var(--bf-primary-bg); padding: 2px 8px;
          border-radius: 4px; font-family: 'SF Mono','Courier New',monospace;
        }
        .bf-rd .rd-feature-name { font-size: 14px; font-weight: 700; color: var(--bf-primary); }
        .bf-rd .rd-feature-phase {
          margin-left: auto; font-size: 10px; font-weight: 600;
          padding: 2px 8px; border-radius: 10px;
        }
        .bf-rd .rd-feature-phase.p1 {
          background: var(--bf-primary-bg); color: var(--bf-primary);
          border: 1px solid var(--bf-primary);
        }
        .bf-rd .rd-feature-phase.p2 {
          background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;
        }
        .bf-rd .rd-feature-phase.urgent {
          background: #fef2f2; color: #991b1b; border: 1px solid #fecaca;
        }
        .bf-rd .rd-feature-row {
          display: grid; grid-template-columns: 100px 1fr;
          border-bottom: 1px solid var(--bf-divider);
        }
        .bf-rd .rd-feature-row:last-child { border-bottom: none; }
        .bf-rd .rd-feature-row-label {
          padding: 10px 14px; font-size: 11px; font-weight: 600;
          color: var(--bf-text-3); background: var(--bf-bg-elev);
          border-right: 1px solid var(--bf-divider);
        }
        .bf-rd .rd-feature-row-value {
          padding: 10px 14px; font-size: 12.5px;
          color: var(--bf-text-2); line-height: 1.7;
        }
        .bf-rd .rd-feature-row-value ul { margin: 0; padding-left: 16px; }

        /* badges */
        .bf-rd .rd-badge {
          display: inline-block; font-size: 10px; font-weight: 600;
          padding: 2px 8px; border-radius: 4px;
        }
        .bf-rd .rd-badge-must { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .bf-rd .rd-badge-should { background: var(--bf-primary-bg); color: var(--bf-primary); border: 1px solid var(--bf-primary); }
        .bf-rd .rd-badge-p1 { background: var(--bf-primary-bg); color: var(--bf-primary); border: 1px solid var(--bf-primary); }
        .bf-rd .rd-badge-p2 { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
        .bf-rd .rd-badge-confirmed { background: #ecfdf5; color: #166534; border: 1px solid #86efac; }
        .bf-rd .rd-badge-hypothesis { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
        .bf-rd .rd-badge-urgent { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }

        /* code */
        .bf-rd .rd-code {
          font-family: 'SF Mono','Courier New',monospace;
          font-size: 11.5px; background: var(--bf-bg);
          padding: 1px 5px; border-radius: 3px; color: var(--bf-text-1);
        }

        /* flow-block */
        .bf-rd .rd-flow-block {
          background: var(--bf-bg); border: 1px solid var(--bf-divider);
          border-radius: 6px; padding: 14px 16px; margin-bottom: 12px;
        }
        .bf-rd .rd-flow-block:last-child { margin-bottom: 0; }
        .bf-rd .rd-flow-title {
          font-size: 12px; font-weight: 700; color: var(--bf-primary);
          margin-bottom: 8px;
        }
        .bf-rd .rd-flow-steps { font-size: 12px; color: var(--bf-text-2); }
        .bf-rd .rd-flow-steps ol { padding-left: 18px; }
        .bf-rd .rd-flow-steps li { margin-bottom: 4px; }

        /* unresolved */
        .bf-rd .rd-unresolved-list { display: flex; flex-direction: column; gap: 10px; }
        .bf-rd .rd-unresolved-item {
          display: grid; grid-template-columns: 36px 1fr;
          border: 1px solid var(--bf-divider);
          border-radius: 6px; overflow: hidden;
        }
        .bf-rd .rd-unresolved-priority {
          display: flex; align-items: center; justify-content: center;
          font-size: 10px; font-weight: 700;
        }
        .bf-rd .rd-unresolved-priority.high { background: #fef2f2; color: #991b1b; }
        .bf-rd .rd-unresolved-priority.medium { background: #fff7ed; color: #c2410c; }
        .bf-rd .rd-unresolved-priority.resolved { background: #ecfdf5; color: #166534; }
        .bf-rd .rd-unresolved-content { padding: 10px 14px; }
        .bf-rd .rd-unresolved-topic {
          font-size: 13px; font-weight: 600; color: var(--bf-text-1);
          margin-bottom: 4px;
        }
        .bf-rd .rd-unresolved-impact {
          font-size: 11.5px; color: var(--bf-text-3); margin-bottom: 6px;
        }
        .bf-rd .rd-unresolved-hypothesis {
          font-size: 11px; color: #92400e; background: #fffbeb;
          padding: 3px 8px; border-radius: 4px; display: inline-block;
        }
        .bf-rd .rd-unresolved-confirmed {
          font-size: 11px; color: #166534; background: #ecfdf5;
          padding: 3px 8px; border-radius: 4px; display: inline-block;
        }

        /* cost-grid */
        .bf-rd .rd-cost-grid {
          display: grid; grid-template-columns: repeat(3, 1fr);
          gap: 16px; margin-bottom: 16px;
        }
        .bf-rd .rd-cost-card {
          border: 1px solid var(--bf-divider); border-radius: 8px;
          overflow: hidden; background: var(--bf-bg);
        }
        .bf-rd .rd-cost-card-header {
          padding: 12px 16px; font-size: 12px; font-weight: 700; color: #fff;
        }
        .bf-rd .rd-cost-card-body { padding: 14px 16px; }
        .bf-rd .rd-cost-card-amount {
          font-size: 22px; font-weight: 800; margin-bottom: 4px;
        }
        .bf-rd .rd-cost-card-detail {
          font-size: 11.5px; color: var(--bf-text-2); padding-left: 16px;
        }
        .bf-rd .rd-cost-card-detail li { margin-bottom: 3px; }

        /* notice-warn */
        .bf-rd .rd-notice-warn {
          background: #fffbeb; border: 1px solid #fde68a;
          border-left: 4px solid #f59e0b; border-radius: 6px;
          padding: 12px 16px; font-size: 12px; color: #92400e;
          margin-bottom: 0; display: flex; gap: 8px; align-items: flex-start;
          line-height: 1.6;
        }

        /* scope-grid */
        .bf-rd .rd-scope-grid {
          display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
        }
        .bf-rd .rd-scope-in-label {
          font-size: 11px; font-weight: 700; color: #166534; margin-bottom: 8px;
        }
        .bf-rd .rd-scope-out-label {
          font-size: 11px; font-weight: 700; color: var(--bf-text-3); margin-bottom: 8px;
        }
        .bf-rd .rd-scope-grid ul {
          padding-left: 18px; font-size: 12.5px; color: var(--bf-text-2);
        }
        .bf-rd .rd-scope-grid li { margin-bottom: 4px; }

        /* schedule-bar */
        .bf-rd .rd-schedule-bar {
          display: flex; border-radius: 8px; overflow: hidden;
          height: 56px; margin-bottom: 16px;
        }
        .bf-rd .rd-schedule-phase {
          display: flex; flex-direction: column; align-items: center;
          justify-content: center; font-size: 11px; font-weight: 600;
          color: #fff; flex: 1; padding: 4px;
        }
        .bf-rd .rd-schedule-phase .rd-ph-label {
          font-size: 9px; font-weight: 700; letter-spacing: 0.06em; opacity: 0.85;
        }
        .bf-rd .rd-schedule-phase .rd-ph-name {
          font-size: 11.5px; font-weight: 700; text-align: center; line-height: 1.3;
        }
        .bf-rd .rd-schedule-phase.s-urgent { background: #991b1b; }
        .bf-rd .rd-schedule-phase.s-m1 { background: var(--bf-primary); }
        .bf-rd .rd-schedule-phase.s-m2 { background: #003b9e; flex: 2; }
        .bf-rd .rd-schedule-phase.s-m3 { background: #2e6cd9; }
        .bf-rd .rd-schedule-phase.s-release { background: #00c97a; }

        /* simple bullet list */
        .bf-rd .rd-bullets { list-style: none; padding: 0; margin: 0; }
        .bf-rd .rd-bullets li {
          display: flex; align-items: flex-start; gap: 8px;
          padding: 8px 12px; font-size: 13px; line-height: 1.6;
          color: var(--bf-text-2); border-bottom: 1px solid var(--bf-divider);
        }
        .bf-rd .rd-bullets li::before {
          content: ""; flex-shrink: 0; width: 6px; height: 6px;
          border-radius: 50%; background: var(--bf-primary);
          margin-top: 9px;
        }
        .bf-rd .rd-bullets li:last-child { border-bottom: none; }
      `}</style>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "240px 1fr 380px",
          gap: "var(--bf-space-5)",
          height: "calc(100vh - var(--bf-header-h) - 200px)",
        }}
      >
        {/* ───── 左: STEP プログレス ───── */}
        <StepProgress
          steps={steps}
          activeStep={activeStep}
          onSelect={setActiveStep}
          onStart={(s) => startMut.mutate(s)}
          isStarting={startMut.isPending}
        />

        {/* ───── 中央: IDE タブ ───── */}
        <CenterTabs
          workspaceId={workspaceId}
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          highlightItems={highlightItems}
          activeStep={activeStep}
          onComplete={(s) => completeMut.mutate(s)}
          isCompleting={completeMut.isPending}
          steps={steps}
          demoMode={demoMode}
        />

        {/* ───── 右: 統合チャット ───── */}
        <ChatPanel
          history={fullHistory}
          activeStep={activeStep ?? 1}
          onSubmit={(msg) => activeStep != null && replyMut.mutate({ step: activeStep, message: msg })}
          isReplying={replyMut.isPending}
        />
      </div>

      {/* ───── ヒアリング引き継ぎモーダル ───── */}
      {showHearingIntro && (
        <HearingIntroModal
          workspaceId={workspaceId}
          onApprove={() => {
            setShowHearingIntro(false);
            startMut.mutate(1);
          }}
          onCancel={() => setShowHearingIntro(false)}
        />
      )}
    </>
  );
}

/* ═══════════════════════════════════════
 * 左カラム: STEP プログレスバー
 * ═══════════════════════════════════════ */
function StepProgress({
  steps,
  activeStep,
  onSelect,
  onStart,
  isStarting,
}: {
  steps: StepState[];
  activeStep: number | null;
  onSelect: (s: number) => void;
  onStart: (s: number) => void;
  isStarting: boolean;
}) {
  return (
    <div
      style={{
        background: "var(--bf-bg-elev)",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-lg)",
        padding: "var(--bf-space-4)",
        overflowY: "auto",
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          color: "var(--bf-text-4)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          marginBottom: 12,
        }}
      >
        Phase 2 / 要件定義
      </div>
      {steps.map((s) => {
        const isActive = activeStep === s.step;
        const Icon =
          s.status === "confirmed" ? CheckCircle2 : isActive ? CircleDot : Circle;
        const color =
          s.status === "confirmed"
            ? "var(--bf-success)"
            : isActive
              ? "var(--bf-primary)"
              : "var(--bf-text-4)";
        return (
          <div
            key={s.step}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(s.step)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(s.step); } }}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              width: "100%",
              padding: "10px 12px",
              marginBottom: 4,
              background: isActive ? "var(--bf-primary-bg)" : "transparent",
              border: "none",
              borderRadius: "var(--bf-radius-md)",
              textAlign: "left",
              cursor: "pointer",
              transition: "background 150ms",
            }}
          >
            <Icon className="w-4 h-4 mt-0.5" style={{ color, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--bf-text-1)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
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
                    marginTop: 8,
                    padding: "4px 10px",
                    background: "var(--bf-primary)",
                    color: "#fff",
                    border: "none",
                    borderRadius: "var(--bf-radius-md)",
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  {isStarting ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Play className="w-3 h-3" />
                  )}
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

/* ═══════════════════════════════════════
 * 中央カラム: IDE 風タブ + 内容
 * ═══════════════════════════════════════ */
function CenterTabs({
  workspaceId,
  tabs,
  activeTab,
  onTabChange,
  highlightItems,
  activeStep,
  onComplete,
  isCompleting,
  steps,
  demoMode,
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
    <div
      style={{
        background: "var(--bf-bg-elev)",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-lg)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* タブヘッダー (2 段構成: 上段=タブ scroll, 下段=アクションバー) */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--bf-divider)",
          background: "var(--bf-bg)",
          flexShrink: 0,
          minWidth: 0,
        }}
      >
        <div
          className="bf-tab-row"
          style={{
            flex: 1,
            display: "flex",
            overflowX: "auto",
            minWidth: 0,
          }}
        >
          {tabs.map((t) => {
            const isActive = t.key === activeTab;
            return (
              <button
                key={t.key}
                onClick={() => !t.locked && onTabChange(t.key)}
                disabled={t.locked}
                style={{
                  padding: "10px 14px",
                  background: isActive ? "var(--bf-bg-elev)" : "transparent",
                  border: "none",
                  borderRight: "1px solid var(--bf-divider)",
                  borderBottom: isActive ? "2px solid var(--bf-primary)" : "2px solid transparent",
                  fontSize: 12,
                  fontWeight: isActive ? 700 : 500,
                  color: t.locked
                    ? "var(--bf-text-4)"
                    : isActive
                      ? "var(--bf-primary)"
                      : "var(--bf-text-2)",
                  cursor: t.locked ? "not-allowed" : "pointer",
                  whiteSpace: "nowrap",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  opacity: t.locked ? 0.5 : 1,
                  flexShrink: 0,
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

      {/* アクションバー (下段): 現在のタブ名 + ダウンロードボタン */}
      {current && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
            padding: "8px 14px",
            background: "var(--bf-bg-elev)",
            borderBottom: "1px solid var(--bf-divider)",
            flexShrink: 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
            <span
              style={{
                fontSize: 12.5,
                fontWeight: 700,
                color: "var(--bf-text-1)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {current.label}
            </span>
            {current.source_steps?.length > 0 && (
              <span
                style={{
                  fontSize: 10.5,
                  color: "var(--bf-text-4)",
                  background: "var(--bf-bg)",
                  border: "1px solid var(--bf-divider)",
                  padding: "1px 6px",
                  borderRadius: 999,
                  fontWeight: 500,
                }}
              >
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

      {/* タブ内容 (テンプレートデザイン適用) */}
      <div className="bf-tab-fadein bf-rd" style={{ flex: 1, overflowY: "auto", padding: "var(--bf-space-5)", background: "var(--bf-bg)" }}>
        {!current ? (
          <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>タブが見つかりません。</div>
        ) : demoMode ? (
          /* デモモード: テンプレ完全準拠のリッチビュー */
          <RichTabContent tabKey={current.key} />
        ) : current.sections.length === 0 ? (
          <div
            style={{
              padding: "var(--bf-space-8) 0",
              textAlign: "center",
              color: "var(--bf-text-3)",
              fontSize: 13,
            }}
          >
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
                <SectionItems
                  items={sec.items}
                  sectionKey={sec.key}
                  sourceStep={sec.source_step}
                  highlightItems={highlightItems}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* フッター: STEP 完了ボタン */}
      {canComplete && activeStep != null && (
        <div
          style={{
            padding: "12px 16px",
            borderTop: "1px solid var(--bf-divider)",
            background: "var(--bf-bg)",
            display: "flex",
            justifyContent: "flex-end",
            flexShrink: 0,
          }}
        >
          <button
            disabled={isCompleting}
            onClick={() => onComplete(activeStep)}
            style={{
              height: 32,
              padding: "0 14px",
              background: "var(--bf-success)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--bf-radius-md)",
              fontSize: 12.5,
              fontWeight: 600,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              opacity: isCompleting ? 0.6 : 1,
            }}
          >
            {isCompleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            STEP {activeStep} を完了
          </button>
        </div>
      )}
    </div>
  );
}

/* ───── セクション内アイテム描画 (テンプレ風) ─────
 * "[label] body (出典: url)" / "【仮説】..." / "【要確認】..." / "【ナレッジ参照】..." を解釈
 */
function SectionItems({
  items,
  sectionKey,
  sourceStep,
  highlightItems,
}: {
  items: string[];
  sectionKey: string;
  sourceStep: number;
  highlightItems: Set<string>;
}) {
  if (items.length === 0) {
    return (
      <div style={{ fontSize: 12.5, color: "var(--bf-text-4)", padding: "8px 12px" }}>
        (まだ記入されていません)
      </div>
    );
  }
  return (
    <ul className="rd-bullets">
      {items.map((it, i) => {
        const key = `${sourceStep}:${sectionKey}:${it}`;
        const isNew = highlightItems.has(key);
        const parsed = parseItem(it);
        return (
          <li
            key={`${i}-${it}`}
            className={isNew ? "bf-highlight" : ""}
            style={{ animation: isNew ? "bf-fadein 250ms ease-out" : undefined }}
          >
            <div style={{ flex: 1 }}>
              {parsed.flag === "hyp" && <span className="rd-badge rd-badge-hypothesis" style={{ marginRight: 6 }}>仮説</span>}
              {parsed.flag === "warn" && <span className="rd-badge rd-badge-must" style={{ marginRight: 6 }}>要確認</span>}
              {parsed.flag === "knowledge" && <span className="rd-badge rd-badge-p2" style={{ marginRight: 6 }}>ナレッジ</span>}
              {parsed.label && <span className="rd-badge rd-badge-p1" style={{ marginRight: 6 }}>{parsed.label}</span>}
              <span style={{ whiteSpace: "pre-wrap" }}>{parsed.body}</span>
              {parsed.sourceUrl && (
                <a
                  href={parsed.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ marginLeft: 8, fontSize: 11, color: "var(--bf-text-4)", borderBottom: "1px dotted", textDecoration: "none" }}
                >
                  出典
                </a>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function parseItem(raw: string): {
  flag?: "hyp" | "warn" | "knowledge";
  label?: string;
  body: string;
  sourceUrl?: string;
} {
  let s = raw;
  let flag: "hyp" | "warn" | "knowledge" | undefined;
  if (s.startsWith("【仮説】")) { flag = "hyp"; s = s.slice(4); }
  else if (s.startsWith("【要確認】")) { flag = "warn"; s = s.slice(5); }
  else if (s.startsWith("【ナレッジ参照】")) { flag = "knowledge"; s = s.slice(8); }
  else if (s.startsWith("【自動検出】")) { s = s.slice(6); }
  else if (s.startsWith("【未検出】")) { flag = "warn"; s = s.slice(5); }

  // [label] body
  let label: string | undefined;
  const labelMatch = s.match(/^\[([^\]]+)\]\s*(.*)$/);
  if (labelMatch) {
    label = labelMatch[1];
    s = labelMatch[2];
  }

  // (出典: url) or  出典: url
  let sourceUrl: string | undefined;
  const srcMatch = s.match(/\(?\s*出典[::]\s*(https?:\/\/[^\s)]+)\)?/);
  if (srcMatch) {
    sourceUrl = srcMatch[1];
    s = s.replace(srcMatch[0], "").trim();
  }

  return { flag, label, body: s.trim(), sourceUrl };
}

function DownloadButton({
  tab, fmt, workspaceId, icon, label,
}: {
  tab: string;
  fmt: "html" | "md" | "json";
  workspaceId: number;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <a
      href={downloadUrl(workspaceId, tab, fmt)}
      download
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "5px 8px",
        fontSize: 11,
        fontWeight: 600,
        color: "var(--bf-text-3)",
        background: "transparent",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-md)",
        textDecoration: "none",
        transition: "all 150ms",
      }}
      title={`${label} をダウンロード`}
    >
      {icon}
      {label}
    </a>
  );
}

/* ═══════════════════════════════════════
 * 右カラム: 統合チャット (全 STEP 1 本)
 * ═══════════════════════════════════════ */
function ChatPanel({
  history,
  activeStep,
  onSubmit,
  isReplying,
}: {
  history: ChatMsg[];
  activeStep: number;
  onSubmit: (msg: string) => void;
  isReplying: boolean;
}) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history.length]);

  // STEP 区切りの計算 (前メッセージと step が変わった位置に区切り線)
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
    <div
      style={{
        background: "var(--bf-bg-elev)",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-lg)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* ヘッダー */}
      <div
        style={{
          padding: "10px 14px",
          borderBottom: "1px solid var(--bf-divider)",
          background: "var(--bf-bg)",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <Sparkles className="w-4 h-4" style={{ color: "var(--bf-primary)" }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--bf-text-1)" }}>
          PM AI 社員 (要件定義)
        </span>
        <span style={{ fontSize: 11, color: "var(--bf-text-4)", marginLeft: "auto" }}>
          STEP {activeStep}
        </span>
      </div>

      {/* メッセージリスト */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "var(--bf-space-4)" }}>
        {renderItems.length === 0 && (
          <div style={{ color: "var(--bf-text-3)", fontSize: 12, textAlign: "center", padding: 24 }}>
            STEP を開始すると、PM AI 社員がここで質問してきます。
          </div>
        )}
        {renderItems.map((it) => {
          if (it.type === "divider") {
            return (
              <div
                key={it.key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  margin: "16px 0 12px",
                }}
              >
                <div style={{ flex: 1, height: 1, background: "var(--bf-divider)" }} />
                <div
                  style={{
                    fontSize: 10.5,
                    fontWeight: 700,
                    color: "var(--bf-text-4)",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    padding: "2px 8px",
                    background: "var(--bf-bg-elev)",
                    border: "1px solid var(--bf-border)",
                    borderRadius: 999,
                  }}
                >
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
            <div
              key={it.key}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: isAi ? "flex-start" : "flex-end",
                marginBottom: 10,
              }}
            >
              <div
                style={{
                  maxWidth: "85%",
                  padding: "8px 12px",
                  background: isAi ? "var(--bf-bg)" : "var(--bf-primary)",
                  color: isAi ? "var(--bf-text-1)" : "#fff",
                  borderRadius: "var(--bf-radius-md)",
                  border: isAi ? "1px solid var(--bf-divider)" : "none",
                  fontSize: 12.5,
                  lineHeight: 1.55,
                  whiteSpace: "pre-wrap",
                }}
              >
                {m.content}
              </div>
            </div>
          );
        })}
        {isReplying && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--bf-text-3)", fontSize: 11.5, padding: "6px 4px" }}>
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            AI が考え中…
          </div>
        )}
      </div>

      {/* 入力 */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const v = input.trim();
          if (!v || isReplying) return;
          onSubmit(v);
          setInput("");
        }}
        style={{
          padding: "10px 12px",
          borderTop: "1px solid var(--bf-divider)",
          background: "var(--bf-bg)",
          display: "flex",
          gap: 6,
          flexShrink: 0,
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={`STEP ${activeStep} の回答や質問を入力…`}
          disabled={isReplying}
          style={{
            flex: 1,
            height: 32,
            padding: "0 10px",
            background: "var(--bf-bg-elev)",
            border: "1px solid var(--bf-border)",
            borderRadius: "var(--bf-radius-md)",
            fontSize: 12.5,
            color: "var(--bf-text-1)",
          }}
        />
        <button
          type="submit"
          disabled={isReplying || !input.trim()}
          style={{
            height: 32,
            padding: "0 12px",
            background: "var(--bf-primary)",
            color: "#fff",
            border: "none",
            borderRadius: "var(--bf-radius-md)",
            fontSize: 12,
            fontWeight: 600,
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            opacity: isReplying || !input.trim() ? 0.5 : 1,
          }}
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </form>
    </div>
  );
}

/* ═══════════════════════════════════════
 * ヒアリング引き継ぎモーダル (Q3=c)
 * ═══════════════════════════════════════ */
function HearingIntroModal({
  workspaceId,
  onApprove,
  onCancel,
}: {
  workspaceId: number;
  onApprove: () => void;
  onCancel: () => void;
}) {
  // モック: 実 API があれば fetch するところを今は注意書きだけ
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: "var(--bf-bg-elev)",
          border: "1px solid var(--bf-border)",
          borderRadius: "var(--bf-radius-lg)",
          padding: "var(--bf-space-6)",
          maxWidth: 560,
          width: "100%",
          boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--bf-text-1)" }}>
            ヒアリング結果の引き継ぎ
          </h3>
          <button
            onClick={onCancel}
            style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--bf-text-3)" }}
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <p style={{ fontSize: 13, color: "var(--bf-text-2)", lineHeight: 1.7, marginBottom: 16 }}>
          Phase 1 ヒアリングで集めた情報を STEP 1 の起点として引き継ぎます。
          PM AI 社員が「このように聞きました。これで合っていますか?」と詳細を確認していきます。
        </p>
        <div
          style={{
            background: "var(--bf-bg)",
            border: "1px solid var(--bf-divider)",
            borderRadius: "var(--bf-radius-md)",
            padding: 12,
            fontSize: 12,
            color: "var(--bf-text-3)",
            marginBottom: 16,
          }}
        >
          ヒアリング artifact (Workspace #{workspaceId}) の最新版が STEP 1 開始時に PM AI のコンテキストに自動で渡されます。
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button
            onClick={onCancel}
            style={{
              height: 36,
              padding: "0 14px",
              background: "transparent",
              border: "1px solid var(--bf-border)",
              borderRadius: "var(--bf-radius-md)",
              fontSize: 12.5,
              fontWeight: 600,
              color: "var(--bf-text-2)",
              cursor: "pointer",
            }}
          >
            あとで
          </button>
          <button
            onClick={onApprove}
            style={{
              height: 36,
              padding: "0 16px",
              background: "var(--bf-primary)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--bf-radius-md)",
              fontSize: 12.5,
              fontWeight: 600,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <Play className="w-3.5 h-3.5" />
            STEP 1 を始める
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════
 * DEMO データ (?demo=1 用)
 * 実 API を使わず、ECサイト案件を想定したダミーで全タブ・全 STEP を埋める
 * ═══════════════════════════════════════ */
const DEMO_STATE: RequirementsState = {
  workspace_id: 1,
  phase: "requirements",
  steps: [
    {
      step: 1, title: "初期ヒアリング・目的明確化",
      description: "ヒアリングのブリーフをすり合わせ、要件として正式に整理する起点",
      status: "confirmed", artifact_id: "demo-1",
      center: { step: 1, sections: [
        { key: "overview", label: "プロジェクト概要", items: [
          "自家焙煎コーヒー豆のオンライン販売 EC サイトを新規構築",
          "対象: 個人消費者 (BtoC) + 飲食店向け卸 (BtoB) の 2 ライン",
          "サブスクリプション (定期便) 機能を中核に据える",
        ]},
        { key: "challenges", label: "現状の課題", items: [
          "現在は BASE で運営しており、定期便機能が手動運用で限界",
          "BtoB 向け価格表示・請求書払いに対応できていない",
          "顧客の焙煎度・抽出方法の好みに合わせた商品レコメンドができない",
        ]},
        { key: "kpi", label: "成功の定義・KPI", items: [
          "リリース 6 か月で月商 300 万円達成 (現状 120 万円)",
          "定期便継続率 80% 以上 (3 か月時点)",
          "BtoB アカウント 30 社獲得",
        ]},
        { key: "constraints_initial", label: "背景・制約", items: [
          "予算: 350 万円 (初期構築) + 月額 5 万円以内 (運用)",
          "希望リリース: 2026 年 9 月 (商戦期前)",
          "現行 BASE データ (商品 80 点・顧客 1200 件) の移行必須",
        ]},
      ]},
      history: [
        { id: 1, role: "ai", content: "プロジェクト概要を確認させてください。今回作りたい EC サイトは BtoC のみですか?それとも BtoB も含みますか?", step: 1 },
        { id: 2, role: "user", content: "両方です。BtoC が中心ですが、最近飲食店からの引き合いが増えていて。", step: 1 },
        { id: 3, role: "ai", content: "ありがとうございます。BtoB の取引は (a) サイトから直接申し込み (b) 営業経由のみ、どちらでしょう?", step: 1 },
        { id: 4, role: "user", content: "サイトから申し込み → 与信審査 → 承認後にログインして注文、という流れにしたいです。", step: 1 },
      ],
    },
    {
      step: 2, title: "ターゲット・構造設計",
      description: "ペルソナ・利用シーン・システム全体像・主要機能の大分類",
      status: "confirmed", artifact_id: "demo-2",
      center: { step: 2, sections: [
        { key: "users", label: "ターゲットユーザー (ペルソナ)", items: [
          "[BtoC] 30〜45 歳・在宅勤務中心・月のコーヒー支出 5,000 円以上のこだわり層",
          "[BtoC] 20代後半・カフェ巡りが趣味・SNS 経由での新規購入が多い",
          "[BtoB] 個人経営カフェ・15-30 席規模・週 2-3 回の安定発注を希望",
          "[管理] 自社スタッフ 3 名・受注/在庫/発送を兼任",
        ]},
        { key: "scenes", label: "利用シーン", items: [
          "朝のコーヒータイムにスマホで定期便のスキップ操作",
          "BtoB オーナーが営業終了後 PC から翌週分を一括発注",
          "スタッフが朝一で前日受注を確認 → ピッキング → 発送ラベル印刷",
        ]},
        { key: "system_overview", label: "システム全体像", items: [
          "フロント: Next.js 16 (App Router) + React Server Components",
          "バック: Hono on Node.js (REST + 一部 SSE)",
          "DB: PostgreSQL 16 (Supabase ホスティング)",
          "決済: Stripe (カード) + 請求書払い (BtoB は Paid 連携)",
          "倉庫: Shippinno API で在庫・配送を一元管理",
        ]},
        { key: "features", label: "主要機能一覧 (大分類)", items: [
          "商品カタログ・検索・絞り込み (焙煎度/産地/抽出方法)",
          "カート・購入・決済 (Stripe)",
          "サブスクリプション (定期便: スキップ/変更/解約)",
          "BtoB 申込・与信・専用価格・請求書払い",
          "顧客マイページ (注文履歴・お気に入り・好み登録)",
          "管理画面 (商品・在庫・受注・顧客・分析)",
          "メールマーケティング (ステップ配信)",
        ]},
      ]},
      history: [
        { id: 5, role: "ai", content: "STEP 2 に進みます。BtoC のメインペルソナを 1 つ挙げてください。年齢層・購入動機・コーヒーへの関与度はどう想定していますか?", step: 2 },
      ],
    },
    {
      step: 3, title: "機能要件詳細",
      description: "各機能の入出力・エラーケース・制約を確定",
      status: "confirmed", artifact_id: "demo-3",
      center: { step: 3, sections: [
        { key: "functional", label: "機能要件 (詳細)", items: [
          "[商品検索] 入力: キーワード/焙煎度/産地/価格帯 → 出力: 商品カードリスト (ページネーション 24 件単位)",
          "[商品検索] エラー: 該当 0 件 → レコメンド 6 件を代替表示",
          "[カート] セッションでの匿名カート + ログイン後マージ。在庫切れ商品は赤バッジ表示",
          "[決済] Stripe Checkout (カード)・3D セキュア必須・請求書払いは BtoB 承認済アカウントのみ",
          "[定期便] サイクル: 2/3/4 週から選択。次回配送 7 日前まで変更/スキップ可能",
          "[定期便] 解約は 3 回目の配送以降から可能 (約款に明記)",
          "[BtoB申込] 入力: 屋号・住所・代表者・取引希望月額 → 与信は手動審査・3 営業日以内に結果メール",
          "[マイページ] 好み登録 (焙煎度・抽出方法) を行うと、商品検索結果に 'あなた向け' バッジ表示",
          "[管理:受注] CSV エクスポート (Shippinno 取込形式) + 個別ステータス更新",
          "[管理:在庫] 商品ごとの実在庫 + 引当在庫 + 安全在庫を表示。安全在庫割れでメール通知",
        ]},
      ]},
      history: [
        { id: 6, role: "ai", content: "STEP 3 機能要件詳細です。まず商品検索の入力項目と出力フォーマットを決めましょう。検索条件は何を使いますか?", step: 3 },
      ],
    },
    {
      step: 4, title: "非機能要件・UX・データ構造",
      description: "性能・セキュリティ・可用性・画面・ER 図",
      status: "confirmed", artifact_id: "demo-4",
      center: { step: 4, sections: [
        { key: "nonfunctional", label: "非機能要件", items: [
          "[性能] LCP 2.5s 以内 (3G 回線想定)・API p95 300ms 以内",
          "[セキュリティ] HTTPS 必須・パスワード bcrypt (cost 12)・JWT 有効期限 1 時間",
          "[可用性] 99.5% 稼働率 (月間 3.6 時間以内のダウン)",
          "[拡張性] 商品 5,000 点・月間 10,000 注文まで無改修で対応",
          "[アクセシビリティ] WCAG 2.1 AA 準拠 (色コントラスト/キーボード操作/スクリーンリーダー対応)",
        ]},
        { key: "screens", label: "画面・UX", items: [
          "[一般] トップ / 商品一覧 / 商品詳細 / カート / チェックアウト / 注文完了",
          "[会員] ログイン / 新規登録 / マイページ / 注文履歴 / 定期便管理 / 好み設定",
          "[BtoB] BtoB 申込 / BtoB 専用ダッシュボード / 一括発注 / 請求書一覧",
          "[管理] ログイン / ダッシュボード / 商品管理 / 在庫管理 / 受注管理 / 顧客管理 / レポート",
        ]},
        { key: "data", label: "データ構造", items: [
          "users (id, email, role[customer/btob/admin], password_hash, preferences_jsonb, created_at)",
          "products (id, name, slug, roast_level, origin, price, stock_qty, safety_stock, status)",
          "orders (id, user_id, total, status, payment_method, shipping_addr_jsonb, placed_at)",
          "order_items (id, order_id, product_id, qty, unit_price)",
          "subscriptions (id, user_id, product_id, cycle_weeks, next_ship_date, status)",
          "btob_accounts (id, user_id, company_name, credit_status, monthly_limit_yen, approved_at)",
        ]},
        { key: "integrations", label: "外部連携", items: [
          "Stripe (カード決済 + 顧客 / Subscription オブジェクト管理)",
          "Paid (BtoB 請求書払い・与信)",
          "Shippinno (倉庫・配送・在庫同期)",
          "SendGrid (トランザクションメール + ステップ配信)",
          "Google Analytics 4 (eコマースイベント)",
        ]},
      ]},
      history: [],
    },
    {
      step: 5, title: "法的考慮・コンプライアンス",
      description: "業種・取扱データから適用法令を網羅し、機能要件に反映",
      status: "confirmed", artifact_id: "demo-5",
      center: { step: 5, sections: [
        { key: "legal_domain", label: "業種・取扱データ判定", items: [
          "業種: EC・通販 (食品 BtoC + BtoB) (出典: https://www.no-trouble.caa.go.jp/)",
          "取扱データ: 個人情報 (氏名/住所/電話/メール) + 決済情報 (Stripe 経由・自社非保持) + 嗜好データ",
          "ビジネスモデル: BtoC + BtoB マーケットプレイス的要素なし (自社販売)",
        ]},
        { key: "legal_regulations", label: "適用法令・規制 一覧", items: [
          "[EC] 特定商取引法: 販売者情報・返品条件・送料・引渡し時期の表記義務 (出典: https://www.no-trouble.caa.go.jp/what/mailorder/)",
          "[EC] 景品表示法: 優良誤認・有利誤認の禁止 (二重価格表示の根拠資料 6 か月保管)",
          "[個人情報] 個人情報保護法: 利用目的明示・第三者提供記録・開示請求対応窓口",
          "[食品] 食品表示法: アレルギー特定原材料 8 品目の表示義務 (コーヒーは対象外だがブレンド添加物に注意)",
          "[サブスク] 特定商取引法 改正 (2022): 解約方法を申込画面と同じ手段で提供する義務",
          "[BtoB] 下請法: BtoB 卸取引で取引基本契約・支払サイト 60 日以内厳守",
        ]},
        { key: "legal_features", label: "必要な実装要件 (機能要件への追加)", items: [
          "特定商取引法に基づく表記ページ (フッター固定リンク)",
          "プライバシーポリシー / 利用規約ページ + 新規登録時の同意チェック",
          "定期便: マイページから 1 クリックで解約完了する導線 (改正特商法対応)",
          "Cookie 同意バナー (必須/分析/マーケティングを個別選択可)",
          "個人情報開示請求フォーム (本人確認 + 30 日以内応答)",
          "【要確認】請求書払いで Paid 利用時、加盟店として古物営業法に該当しないか確認",
        ]},
        { key: "legal_nfr", label: "非機能要件への追加", items: [
          "個人情報のアクセスログを 3 年保管",
          "決済情報は Stripe トークン化により自社 DB に保存しない (PCI DSS SAQ-A 範囲)",
          "管理画面アクセスは 2FA 必須 + IP 制限",
        ]},
        { key: "legal_risks", label: "法的リスク・要確認事項", items: [
          "【要確認】定期便の最低継続回数を約款に明記しないと景表法のおとり広告に該当する恐れ",
          "【要確認】BtoB 与信判断を AI 自動化する場合、説明責任の根拠保持が必要",
          "【ナレッジ参照】社内ナレッジ #legal-001 'サブスク EC の解約導線テンプレート'",
        ]},
      ]},
      history: [],
    },
    {
      step: 6, title: "リスク分析・未確認事項",
      description: "リスク表 + 未確認事項 + PM への注意事項",
      status: "draft", artifact_id: "demo-6",
      center: { step: 6, sections: [
        { key: "risks", label: "リスク一覧", items: [
          "[技術] Shippinno API のレート制限 (1分100req) で大量注文時に遅延 → キュー処理で吸収",
          "[運用] 倉庫スタッフが管理画面に不慣れ → リリース 2 週間前に研修 + 動画マニュアル",
          "[要件] BtoB の与信ロジックが未確定 → 8/15 までに与信基準を業務側で確定",
          "[スケジュール] 9 月リリースに対しデザイン未着手 → 6 月中にデザイン完了が前提",
        ]},
        { key: "unresolved", label: "未確認事項", items: [
          "BtoB の請求書発行は Paid 経由?自社発行?税理士確認待ち",
          "メールマーケティングのステップ配信本数 (3 本 or 5 本)",
          "定期便の同梱クーポンチラシ印刷の可否",
        ]},
        { key: "pm_notes", label: "PM への注意事項", items: [
          "クライアント代表者が技術詳細を理解されないため、画面モックでの合意形成を最優先",
          "現行 BASE データの構造を 6 月前半までに精査 (移行スクリプトの工数に直結)",
        ]},
      ]},
      history: [
        { id: 7, role: "ai", content: "STEP 6 リスク分析です。技術・運用・要件・スケジュールの 4 観点でリスクを洗い出しましょう。最も懸念しているリスクは何ですか?", step: 6 },
        { id: 8, role: "user", content: "倉庫連携がうまく動くかと、9 月リリースに間に合うかが心配です。", step: 6 },
      ],
    },
    {
      step: 7, title: "最終出力",
      description: "HTML / Markdown / JSON 一式を生成・確定",
      status: "not_started", artifact_id: null,
      center: { step: 7, sections: [
        { key: "summary", label: "要件定義書サマリー", items: [] },
      ]},
      history: [],
    },
  ],
};

const DEMO_AGGREGATED: AggregatedView = {
  workspace_id: 1,
  tabs: [
    { key: "overview", label: "プロジェクト概要", locked: false, source_steps: [1],
      sections: [
        { key: "overview", label: "プロジェクト概要", source_step: 1, items: DEMO_STATE.steps[0].center.sections[0].items },
        { key: "challenges", label: "現状の課題", source_step: 1, items: DEMO_STATE.steps[0].center.sections[1].items },
        { key: "kpi", label: "成功の定義・KPI", source_step: 1, items: DEMO_STATE.steps[0].center.sections[2].items },
        { key: "constraints_initial", label: "背景・制約", source_step: 1, items: DEMO_STATE.steps[0].center.sections[3].items },
      ]},
    { key: "users", label: "ターゲットユーザー", locked: false, source_steps: [2],
      sections: [
        { key: "users", label: "ターゲットユーザー (ペルソナ)", source_step: 2, items: DEMO_STATE.steps[1].center.sections[0].items },
        { key: "scenes", label: "利用シーン", source_step: 2, items: DEMO_STATE.steps[1].center.sections[1].items },
      ]},
    { key: "features", label: "主要機能一覧", locked: false, source_steps: [2],
      sections: [
        { key: "features", label: "主要機能一覧 (大分類)", source_step: 2, items: DEMO_STATE.steps[1].center.sections[3].items },
        { key: "system_overview", label: "システム全体像", source_step: 2, items: DEMO_STATE.steps[1].center.sections[2].items },
      ]},
    { key: "functional", label: "機能要件詳細", locked: false, source_steps: [3],
      sections: [
        { key: "functional", label: "機能要件 (詳細)", source_step: 3, items: DEMO_STATE.steps[2].center.sections[0].items },
      ]},
    { key: "nonfunctional", label: "非機能要件", locked: false, source_steps: [4],
      sections: [
        { key: "nonfunctional", label: "非機能要件", source_step: 4, items: DEMO_STATE.steps[3].center.sections[0].items },
      ]},
    { key: "screens", label: "画面・UX", locked: false, source_steps: [4],
      sections: [
        { key: "screens", label: "画面・UX", source_step: 4, items: DEMO_STATE.steps[3].center.sections[1].items },
      ]},
    { key: "data", label: "データ構造", locked: false, source_steps: [4],
      sections: [
        { key: "data", label: "データ構造", source_step: 4, items: DEMO_STATE.steps[3].center.sections[2].items },
      ]},
    { key: "integrations", label: "外部連携", locked: false, source_steps: [4],
      sections: [
        { key: "integrations", label: "外部連携", source_step: 4, items: DEMO_STATE.steps[3].center.sections[3].items },
      ]},
    { key: "legal", label: "法的考慮・コンプライアンス", locked: false, source_steps: [5],
      sections: [
        { key: "legal_domain", label: "業種・取扱データ判定", source_step: 5, items: DEMO_STATE.steps[4].center.sections[0].items },
        { key: "legal_regulations", label: "適用法令・規制 一覧", source_step: 5, items: DEMO_STATE.steps[4].center.sections[1].items },
        { key: "legal_features", label: "必要な実装要件", source_step: 5, items: DEMO_STATE.steps[4].center.sections[2].items },
        { key: "legal_nfr", label: "非機能要件への追加", source_step: 5, items: DEMO_STATE.steps[4].center.sections[3].items },
        { key: "legal_risks", label: "法的リスク・要確認事項", source_step: 5, items: DEMO_STATE.steps[4].center.sections[4].items },
      ]},
    { key: "risks", label: "リスク・懸念点", locked: false, source_steps: [6],
      sections: [
        { key: "risks", label: "リスク一覧", source_step: 6, items: DEMO_STATE.steps[5].center.sections[0].items },
      ]},
    { key: "infra_cost", label: "インフラコスト試算", locked: false, source_steps: [6],
      sections: [
        { key: "infra_cost", label: "3 段階コスト試算", source_step: 6, items: ["デモ表示用 (リッチビュー)"] },
      ]},
    { key: "unresolved", label: "未確認事項", locked: false, source_steps: [6],
      sections: [
        { key: "unresolved", label: "未確認事項", source_step: 6, items: DEMO_STATE.steps[5].center.sections[1].items },
        { key: "pm_notes", label: "PM への注意事項", source_step: 6, items: DEMO_STATE.steps[5].center.sections[2].items },
      ]},
    { key: "scope", label: "スコープ・スケジュール", locked: false, source_steps: [7],
      sections: [
        { key: "scope", label: "スコープ", source_step: 7, items: ["デモ表示用 (リッチビュー)"] },
      ]},
    { key: "history", label: "改訂履歴", locked: false, source_steps: [7],
      sections: [
        { key: "history", label: "改訂履歴", source_step: 7, items: ["デモ表示用 (リッチビュー)"] },
      ]},
  ],
};
