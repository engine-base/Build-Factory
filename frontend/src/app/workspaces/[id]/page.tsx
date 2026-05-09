"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Workspace, fetchWorkspace, fetchWorkspaceSummary, type WorkspaceSummary,
} from "@/lib/workspaces";
import { WorkspaceShell } from "@/components/workspace-shell";
import type { LeaderId } from "@/components/workspace-shell";
import {
  DagProgress, AlertStrip,
  NextActionsBlock, QueueBlock,
  ActivePhasesBlock, KpiBlock,
  ArtifactsBlock, ActivityBlock, MembersBlock,
  type DagPhase, type NextAction, type QueueItem,
  type PhaseRow, type ArtifactRow, type ActivityItem,
} from "@/components/workspace-shell/HomeBlocks";
import { Download, Play } from "lucide-react";

const SKILL_TO_LEADER: Record<string, { id: LeaderId; label: string }> = {
  "feature":                  { id: "pm",     label: "PM AI" },
  "hearing":                  { id: "pm",     label: "PM AI" },
  "requirements-definition":  { id: "pm",     label: "PM AI" },
  "proposal":                 { id: "pm",     label: "PM AI" },
  "estimate":                 { id: "pm",     label: "PM AI" },
  "acceptance-criteria":      { id: "pm",     label: "PM AI" },
  "architecture-design":      { id: "arch",   label: "設計 AI" },
  "tech-stack":               { id: "arch",   label: "設計 AI" },
  "api-design":               { id: "arch",   label: "設計 AI" },
  "feature-decomposition":    { id: "arch",   label: "設計 AI" },
  "task-decomposition":       { id: "arch",   label: "設計 AI" },
  "design-md":                { id: "design", label: "デザイナー AI" },
  "ui-mockup":                { id: "design", label: "デザイナー AI" },
  "frontend-design":          { id: "design", label: "デザイナー AI" },
  "distributed-dev":          { id: "eng",    label: "エンジニア AI" },
  "integration":              { id: "eng",    label: "エンジニア AI" },
  "test-verification":        { id: "qa",     label: "品質 AI" },
  "code-review":              { id: "qa",     label: "品質 AI" },
  "release-planning":         { id: "ops",    label: "DevOps AI" },
  "operations":               { id: "ops",    label: "DevOps AI" },
  "documentation":            { id: "ops",    label: "DevOps AI" },
};

function leaderFor(skill: string): { id: LeaderId; label: string } {
  return SKILL_TO_LEADER[skill] ?? { id: "secretary", label: "秘書 AI" };
}

/**
 * Workspace ホーム (admin / contributor 向けコックピット)
 * デザイン: Calm Industrial — Build-Factory/docs/DESIGN-SYSTEM.md
 * モック原本: frontend/public/mock/workspace-home.html
 */
export default function WorkspaceHomePage() {
  const params = useParams();
  const id = Number(params?.id);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      try {
        const w = await fetchWorkspace(id);
        setWorkspace(w);
      } catch {
        setWorkspace(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  // 実データサマリ
  const { data: summary } = useQuery<WorkspaceSummary>({
    queryKey: ["workspace-summary", id],
    queryFn: () => fetchWorkspaceSummary(id),
    enabled: !!id,
    refetchInterval: 5000,
  });

  // モックのデモデータ — 本番接続まではこれで動かす
  const phases: DagPhase[] = [
    { id: "hearing",  label: "ヒア",     status: "done" },
    { id: "req",      label: "要件",     status: "done" },
    { id: "proposal", label: "提案",     status: "done" },
    { id: "design",   label: "デザイン", status: "done" },
    { id: "arch",     label: "アーキ",   status: "in-progress" },
    { id: "api",      label: "API",     status: "pending" },
    { id: "feat",     label: "機能分解", status: "pending" },
    { id: "task",     label: "タスク",   status: "pending" },
    { id: "impl",     label: "実装",     status: "pending" },
    { id: "integ",    label: "統合",     status: "pending" },
    { id: "test",     label: "テスト",   status: "pending" },
    { id: "review",   label: "レビュー", status: "pending" },
    { id: "release",  label: "リリース", status: "pending" },
  ];

  const nextActions: NextAction[] = [
    {
      id: 1, leaderId: "arch", leaderLabel: "設計 AI",
      phase: "アーキテクチャ STEP 4 / 4",
      title: "アーキテクチャ設計を完了する",
      reason: "要件定義の最終 STEP が確定済。技術スタック・モジュール構成・ER 図を確定すれば次のフェーズ (API 設計・機能分解) に並行で進めます。",
      recommend: true,
    },
    {
      id: 2, leaderId: "design", leaderLabel: "デザイナー AI",
      phase: "モック作成",
      title: "主要 3 画面のモックを Penpot で起こす",
      reason: "デザインシステム確定済。アーキ完了を待たずに、主要画面 (ホーム / タスク / 設定) のモックを並行で進められます。",
      parallel: true,
    },
    {
      id: 3, leaderId: "pm", leaderLabel: "PM AI",
      phase: "受入条件",
      title: "受入条件を Gherkin 形式で起こす",
      reason: "要件定義の機能リスト 12 項目に対し、各機能の受入条件を AC スキルで自動生成できます。",
      parallel: true,
    },
  ];

  const queue: QueueItem[] = [
    { id: 1, type: "question", title: "予算上限の確認",                   source: "秘書 AI からの質問 ・ ヒアリング",        time: "15分前" },
    { id: 2, type: "review",   title: "要件定義書 v2.0 のレビュー依頼",   source: "PM AI が完成 ・ 6 項目のチェック",       time: "42分前" },
    { id: 3, type: "approve",  title: "API 設計書 の承認待ち",            source: "設計 AI が完成 ・ 承認後フェーズ完了",     time: "1時間前" },
    { id: 4, type: "comment",  title: "クライアント (山田 太郎) のコメント", source: "「モックの導線を確認してほしい」",        time: "3時間前" },
    { id: 5, type: "question", title: "既存 DB との連携要否",             source: "設計 AI からの質問 ・ アーキ",            time: "昨日" },
  ];

  // 進行中フェーズ - summary から動的生成
  const activePhases: PhaseRow[] = (summary?.active_phases ?? []).slice(0, 4).map((p) => {
    const lead = leaderFor(p.skill_name || "");
    const total = p.child_total || 1;
    const done = p.child_done || 0;
    const percent = total > 0 ? Math.round((done / total) * 100) : 0;
    return {
      leaderId: lead.id, leaderLabel: lead.label,
      phaseName: p.title,
      step: p.child_total > 0 ? `${done} / ${total} 完了` : `STEP 進行中`,
      percent, parallel: false,
    };
  });

  // 最新成果物 - summary から動的生成
  const artifacts: ArtifactRow[] = (summary?.recent_artifacts ?? []).slice(0, 5).map((a) => {
    const tags = (a.category_tags ?? []).map((t) => String(t));
    let type: ArtifactRow["type"] = "doc";
    if (a.type === "html" || tags.includes("design"))                 type = "design";
    else if (tags.includes("arch") || a.title.includes("アーキ"))      type = "arch";
    else if (a.type === "code" || tags.includes("code"))              type = "code";
    const ago = new Date(a.updated_at);
    return {
      id: a.id, type, title: a.title || "(無題)",
      version: a.type === "minutes" ? "" : "v1",
      meta: `${ago.toLocaleString("ja-JP")} / ${tags[0] ?? a.type}`,
    };
  });

  const activity: ActivityItem[] = [
    { id: 1, time: "10分前",   text: <><strong>秘書 AI</strong> がヒアリング STEP 4 を完了</> },
    { id: 2, time: "42分前",   text: <><strong>PM AI</strong> が要件定義書 v2.0 を出力</> },
    { id: 3, time: "1時間前",  text: <><strong>設計 AI</strong> がアーキ STEP 3 を完了 → STEP 4 へ</> },
    { id: 4, time: "2時間前",  text: <><strong>あなた</strong> が要件定義書 v1.0 をレビュー</> },
    { id: 5, time: "3時間前",  text: <><strong>山田 太郎</strong> がモックにコメント追加</> },
  ];

  if (loading) {
    return (
      <div className="p-6" style={{ color: "var(--bf-text-3)" }}>読み込み中…</div>
    );
  }
  if (!workspace) {
    return (
      <div className="p-6" style={{ color: "var(--bf-danger)" }}>workspace が見つかりません</div>
    );
  }

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      progressPercent={summary ? Math.round(summary.completion_rate * 100) : 0}
      daysLeft={23}
      active="home"
    >
      {/* Page Header */}
      <div style={{ marginBottom: "var(--bf-space-8)" }}>
        <div className="flex items-start gap-6 flex-wrap">
          <div>
            <h1
              style={{
                fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em",
                color: "var(--bf-text-1)", marginBottom: 4,
              }}
            >
              {workspace.name}
            </h1>
            <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>
              {workspace.description ?? "AI-driven Development OS の MVP 構築"}
            </div>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <button
              className="inline-flex items-center gap-1.5 transition-colors"
              style={{
                height: 34, padding: "0 14px",
                background: "var(--bf-bg-elev)", color: "var(--bf-text-1)",
                border: "1px solid var(--bf-border)",
                borderRadius: "var(--bf-radius-md)",
                fontSize: 13, fontWeight: 600,
              }}
            >
              <Download className="w-3.5 h-3.5" />
              エクスポート
            </button>
            <button
              className="inline-flex items-center gap-1.5 transition-colors"
              style={{
                height: 34, padding: "0 14px",
                background: "var(--bf-primary)", color: "#fff",
                border: "1px solid transparent",
                borderRadius: "var(--bf-radius-md)",
                fontSize: 13, fontWeight: 600,
              }}
            >
              <Play className="w-3.5 h-3.5" />
              次のアクションを実行
            </button>
          </div>
        </div>

        <DagProgress
          phases={phases}
          currentLabel="アーキテクチャ STEP 4"
          completed={4}
          total={13}
        />

        <AlertStrip>
          提案・見積フェーズが未実施のまま設計に進行中です。理由:「既存契約あり、見積省略」
        </AlertStrip>
      </div>

      {/* Row 1: Next + Queue */}
      <div
        className="mb-5"
        style={{
          display: "grid",
          gridTemplateColumns: "1.4fr 1fr",
          gap: "var(--bf-space-5)",
        }}
      >
        <NextActionsBlock actions={nextActions} />
        <QueueBlock items={queue} />
      </div>

      {/* Row 2: Active Phases (2) + KPI (1) */}
      <div
        className="mb-5"
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: "var(--bf-space-5)",
        }}
      >
        <div style={{ gridColumn: "span 2" }}>
          <ActivePhasesBlock phases={activePhases} />
        </div>
        <KpiBlock
          taskDone={summary?.task_stats.completed ?? 0}
          taskTotal={summary?.task_stats.total ?? 0}
          blockers={summary?.task_stats.blockers ?? 0}
          daysLeft={23}
          budgetPercent={35}
        />
      </div>

      {/* Row 3: Artifacts / Activity / Members */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: "var(--bf-space-5)",
        }}
      >
        <ArtifactsBlock artifacts={artifacts} />
        <ActivityBlock items={activity} />
        <MembersBlock
          online={[
            { name: "高本 まさと",        role: "admin",  avatar: "MA", bg: "linear-gradient(135deg,#2563EB,#06B6D4)" },
            { name: "PM AI",              role: "AI",     avatar: "PM", bg: "var(--bf-leader-pm)" },
            { name: "設計 AI",            role: "AI",     avatar: "設", bg: "var(--bf-leader-arch)" },
            { name: "デザイナー AI",      role: "AI",     avatar: "デ", bg: "var(--bf-leader-design)" },
          ]}
          offline={[
            { name: "山田 太郎 (client)", lastSeen: "30 分前" },
          ]}
        />
      </div>
    </WorkspaceShell>
  );
}
