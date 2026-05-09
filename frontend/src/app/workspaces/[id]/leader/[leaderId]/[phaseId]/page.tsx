"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Workspace, fetchWorkspace } from "@/lib/workspaces";
import { designsApi, type DesignMock } from "@/lib/designs-api";
import { WorkspaceShell, LEADERS } from "@/components/workspace-shell";
import type { LeaderId } from "@/components/workspace-shell";
import {
  LeaderWorkArea, type StepDef, type ArtifactRef, type ChatMsg, type PhaseStatus,
  type PhaseCta,
} from "@/components/workspace-shell/LeaderWorkArea";
import { HearingFlow } from "@/components/workspace-shell/HearingFlow";
import { RequirementsFlow } from "@/components/workspace-shell/RequirementsFlow";
import { PricingDesignFlow } from "@/components/workspace-shell/PricingDesignFlow";
import { ProposalFlow } from "@/components/workspace-shell/ProposalFlow";
import { EstimateFlow } from "@/components/workspace-shell/EstimateFlow";
import { LeaderAvatar } from "@/components/workspace-shell";
import { FileText, Palette, ExternalLink, Layers, UserCog } from "lucide-react";

/**
 * リーダー × フェーズ別の作業画面。
 * 例: /workspaces/1/leader/pm/proposal
 */
export default function LeaderPhasePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const isDemo = searchParams?.get("demo") === "1";
  const id = Number(params?.id);
  const leaderId = params?.leaderId as LeaderId;
  const phaseId = params?.phaseId as string;
  const [workspace, setWorkspace] = useState<Workspace | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchWorkspace(id).then(setWorkspace).catch(() => setWorkspace(null));
  }, [id]);

  const leader = LEADERS.find((l) => l.id === leaderId);
  const phase = leader?.phases.find((p) => p.id === phaseId);

  // デザイン系フェーズは実 designsApi からキャンバス一覧を取得
  const { data: designs = [] } = useQuery<DesignMock[]>({
    queryKey: ["designs", id],
    queryFn: () => designsApi.list(id),
    enabled: !!id && leaderId === "design",
  });

  if (!workspace || !leader || !phase) {
    return <div className="p-6" style={{ color: "var(--bf-text-3)" }}>読み込み中…</div>;
  }

  // ヒアリングは対話駆動 UI (HearingFlow) を使う
  const isHearing = leaderId === "pm" && phaseId === "hearing";
  // 要件定義は IDE 風タブ UI (RequirementsFlow) を使う
  const isRequirements = leaderId === "pm" && (phaseId === "requirements" || phaseId === "requirements-definition");
  // 価格設計は IDE 風タブ UI (PricingDesignFlow) を使う
  const isPricing = leaderId === "pm" && (phaseId === "pricing-design" || phaseId === "pricing");
  // 提案書はスクロール 1 本 + TOC (ProposalFlow)
  const isProposal = leaderId === "pm" && phaseId === "proposal";
  // 見積書は 4 タブ (EstimateFlow)
  const isEstimate = leaderId === "pm" && phaseId === "estimate";

  if (isHearing || isRequirements || isPricing || isProposal || isEstimate) {
    const headerTitle = isHearing
      ? "ヒアリング — PM AI と対話で進めます"
      : isRequirements
        ? "要件定義 — IDE 風タブ + 統合チャットで進めます"
        : isPricing
          ? "価格設計 — 3 軸試算 + 推奨料金体系を AI と決めます"
          : isProposal
            ? "提案書 — 8 章のドラフトを AI と章ごとに仕上げます"
            : "見積書 — 4 タブで明細・条件を確定 → 出力";
    const headerDesc = isHearing
      ? "4 STEP を順に進行。PM AI の質問に答えると、左の中央エリアにリアルタイム反映されます。"
      : isRequirements
        ? "7 STEP を順に進行。完了 STEP に対応するタブが順次活性化し、HTML/MD/JSON でダウンロードできます。"
        : isPricing
          ? "3 STEP (原価試算 → 市場相場・価値試算 → 推奨レンジ) で価格を確定。"
          : isProposal
            ? "5 STEP × 8 章。スクロール 1 本で提案書ドラフト。章ごとに HTML/MD/JSON ダウンロード可。"
            : "2 STEP × 4 タブ。価格設計の推奨見積金額を反映 → 見積書を確定。";

    return (
      <WorkspaceShell
        workspaceId={id}
        workspaceName={workspace.name}
        progressPercent={45}
        daysLeft={23}
        active={leaderId}
        expandedLeader={leaderId}
        breadcrumbs={[
          { label: "Workspaces", href: "/workspaces" },
          { label: workspace.name, href: `/workspaces/${id}` },
          { label: `${leader.label} ライン`, href: `/workspaces/${id}/leader/${leader.id}` },
          { label: phase.label },
        ]}
      >
        <div
          className="flex items-center gap-4"
          style={{
            padding: "var(--bf-space-5) var(--bf-space-6)",
            background: "linear-gradient(135deg, var(--bf-primary-soft) 0%, var(--bf-primary-bg) 100%)",
            border: "1px solid var(--bf-border)",
            borderRadius: "var(--bf-radius-lg)",
            marginBottom: "var(--bf-space-5)",
          }}
        >
          <LeaderAvatar id="pm" size={48} />
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: 18, fontWeight: 700, color: "var(--bf-text-1)", marginBottom: 2 }}>
              {headerTitle}
            </h1>
            <div style={{ fontSize: 12.5, color: "var(--bf-text-3)" }}>
              {headerDesc}
            </div>
          </div>
          <button className="inline-flex items-center gap-1" style={{ height: 28, padding: "0 10px", background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)", fontSize: 12, fontWeight: 600, color: "var(--bf-text-1)" }}>
            <UserCog className="w-3.5 h-3.5" />
            担当 AI
          </button>
        </div>

        {isHearing ? (
          <HearingFlow workspaceId={id} />
        ) : isRequirements ? (
          <RequirementsFlow workspaceId={id} demoMode={isDemo} />
        ) : isPricing ? (
          <PricingDesignFlow workspaceId={id} demoMode={isDemo} />
        ) : isProposal ? (
          <ProposalFlow workspaceId={id} demoMode={isDemo} />
        ) : (
          <EstimateFlow workspaceId={id} demoMode={isDemo} />
        )}
      </WorkspaceShell>
    );
  }

  const data = buildPhaseData(leader.id, phaseId, id, designs);

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      progressPercent={45}
      daysLeft={23}
      active={leaderId}
      expandedLeader={leaderId}
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: `${leader.label} ライン`, href: `/workspaces/${id}/leader/${leader.id}` },
        { label: phase.label },
      ]}
    >
      <LeaderWorkArea
        workspaceId={id}
        leader={leader}
        activePhaseId={phaseId}
        phaseStatuses={data.phaseStatuses}
        phaseTitle={phase.label}
        phaseSkill={data.skill}
        phaseStatus={data.phaseStatus}
        steps={data.steps}
        outputPreview={data.outputPreview}
        phaseCta={data.phaseCta}
        artifacts={data.artifacts}
        initialChat={data.chat}
        suggestionChips={data.chips}
      />
    </WorkspaceShell>
  );
}

/* ──────────────────────────────────────────────────
 *  フェーズ別 デモデータ (実データ接続まではこれで動かす)
 * ────────────────────────────────────────────────── */

type PhaseData = {
  skill: string;
  phaseStatus: "done" | "in-progress" | "pending";
  phaseStatuses: Record<string, PhaseStatus>;
  steps: StepDef[];
  outputPreview?: string;
  phaseCta?: PhaseCta;
  artifacts: ArtifactRef[];
  chat: ChatMsg[];
  chips: string[];
};

function buildPhaseData(leaderId: LeaderId, phaseId: string, workspaceId: number, designs: DesignMock[] = []): PhaseData {
  // PM ライン: 各フェーズのデモデータ
  if (leaderId === "pm") {
    const pmStatuses: Record<string, PhaseStatus> = {
      "hearing": "done",
      "requirements-definition": "done",
      "proposal": "in-progress",
      "acceptance-criteria": "pending",
    };
    if (phaseId === "hearing") {
      return {
        skill: "hearing",
        phaseStatus: "done",
        phaseStatuses: pmStatuses,
        steps: [
          { num: 1, title: "STEP 1: プロジェクト全体像", desc: "目的・背景・規模感の確認", status: "done", meta: "完了 ・ 2 日前" },
          { num: 2, title: "STEP 2: 制約とステークホルダー", desc: "予算・期限・関係者の整理", status: "done", meta: "完了 ・ 2 日前" },
          { num: 3, title: "STEP 3: 優先順位", desc: "Must/Should/Could/Won't", status: "done", meta: "完了 ・ 2 日前" },
          { num: 4, title: "STEP 4: 最終ブリーフ", desc: "Markdown + JSON 出力", status: "done", meta: "完了 ・ 2 日前" },
        ],
        artifacts: [
          { id: 1, title: "プロジェクト起点ブリーフ",   meta: "v1 ・ 2 日前 ・ 承認済", icon: FileText, latest: true },
          { id: 2, title: "ヒアリング議事録",            meta: "v1 ・ 3 日前 ・ クライアント確認済", icon: FileText },
        ],
        chat: [
          { id: 1, role: "ai", body: "ヒアリング全 STEP を完了しました。プロジェクト起点ブリーフを生成済みです。次フェーズ (要件定義) に進めます。", time: "2 日前" },
        ],
        chips: ["ヒアリングをやり直す", "ブリーフを編集", "要件定義へ進む"],
      };
    }
    if (phaseId === "requirements-definition") {
      return {
        skill: "requirements-definition",
        phaseStatus: "done",
        phaseStatuses: pmStatuses,
        steps: [
          { num: 1, title: "STEP 1: プロジェクト概要・KPI", desc: "目的・現状課題・成功定義", status: "done", meta: "完了" },
          { num: 2, title: "STEP 2: ターゲット・構造設計", desc: "ペルソナ・利用シーン・全体像", status: "done", meta: "完了" },
          { num: 3, title: "STEP 3: 機能要件詳細", desc: "各機能の入出力・エラーケース", status: "done", meta: "完了" },
          { num: 4, title: "STEP 4: 非機能要件・UX・データ", desc: "性能・セキュリティ・画面・ER", status: "done", meta: "完了" },
          { num: 5, title: "STEP 5: リスク・未確認事項", desc: "懸念点と決め切れていないこと", status: "done", meta: "完了" },
          { num: 6, title: "STEP 6: 最終出力", desc: "HTML 要件定義書 + JSON", status: "done", meta: "完了 ・ 42 分前" },
        ],
        artifacts: [
          { id: 1, title: "要件定義書",       meta: "v2.0 ・ 42 分前 ・ レビュー中", icon: FileText, latest: true },
          { id: 2, title: "要件定義書 (旧版)", meta: "v1.0 ・ 3 時間前 ・ アーカイブ", icon: FileText },
        ],
        chat: [
          { id: 1, role: "ai", body: "要件定義書 v2.0 を出力しました。クライアントレビュー反映済 (認証 Must / レポート除外 / 既存 DB 連携追加)。承認をお願いします。", time: "42 分前" },
        ],
        chips: ["v2.0 を承認", "差し戻し", "次フェーズ (提案・見積) へ"],
      };
    }
    if (phaseId === "proposal") {
      return {
        skill: "proposal",
        phaseStatus: "in-progress",
        phaseStatuses: pmStatuses,
        steps: [
          { num: 1, title: "STEP 1: クライアント情報の整理",   desc: "企業規模・業界・予算感・競合の確認", status: "done", meta: "完了 ・ 1 時間前" },
          { num: 2, title: "STEP 2: スコープ整理",              desc: "機能・非機能要件 / 工数見積 / マイルストーン", status: "done", meta: "完了 ・ 45 分前" },
          { num: 3, title: "STEP 3: 価格設計 (進行中)",         desc: "フェーズ別単価 / 一括 / 月額継続 / 成果報酬の選定", status: "in-progress", meta: "PM AI が作業中…" },
          { num: 4, title: "STEP 4: 提案書作成",                desc: "エグゼクティブサマリー / スコープ / 価格 / 納期 / 体制", status: "pending" },
          { num: 5, title: "STEP 5: クライアントレビュー依頼",  desc: "提案書を共有 → コメント受領 → 必要なら改訂", status: "pending" },
        ],
        outputPreview: `## 価格構成案 (案 A: フェーズ別単価)

| フェーズ | 工数 | 単価 | 小計 |
|---|---|---|---|
| ヒアリング | 8h | ¥15,000 | ¥120,000 |
| 要件定義 | 32h | ¥15,000 | ¥480,000 |
| 設計 (アーキ + デザイン) | 60h | ¥18,000 | ¥1,080,000 |
| 実装 | 240h | ¥12,000 | ¥2,880,000 |
| QA + リリース | 40h | ¥15,000 | ¥600,000 |
| **合計** | **380h** | | **¥5,160,000** |

※ クライアント既存の Slack / GitHub / Notion 環境を前提とし、追加の DevOps 構築費は別途見積。
※ 月次定例 MTG (60min) は実費 ¥30,000 にて提供。`,
        artifacts: [
          { id: 1, title: "要件定義書",  meta: "v2.0 ・ 42 分前 ・ PM AI が要件定義スキルで生成", icon: FileText, latest: true },
          { id: 2, title: "ヒアリング議事録", meta: "v1 ・ 2 日前 ・ クライアント確認済", icon: FileText },
        ],
        chat: [
          { id: 1, role: "ai",   body: "こんにちは、PM AI です。要件定義書 v2.0 が完成したので、続けて提案・見積に入ります。価格設計は \"フェーズ別単価\" と \"一括\" どちらの形式が良いですか？", time: "1 時間前" },
          { id: 2, role: "user", body: "フェーズ別単価でお願いします。クライアントが途中で止まる可能性もあるので。", time: "55 分前" },
          { id: 3, role: "ai",   body: "承知しました。フェーズ別単価で構成します。アーキ・デザインは別フェーズに分けますか？それとも「設計」一括にしますか？", time: "53 分前" },
          { id: 4, role: "user", body: "設計は一括でいいです。デザインだけ別出しすると複雑になりそう。", time: "52 分前" },
          { id: 5, role: "ai",   body: "了解です。STEP 3 の中間出力を上のエリアに表示しています。確認の上「STEP を完了させる」で次に進みます。", time: "5 分前" },
        ],
        chips: ["価格を 10% 下げて", "月額継続案も追加", "見積の根拠を出して"],
      };
    }
    if (phaseId === "acceptance-criteria") {
      return {
        skill: "acceptance-criteria",
        phaseStatus: "pending",
        phaseStatuses: pmStatuses,
        steps: [
          { num: 1, title: "STEP 1: 機能リスト読み込み",        desc: "要件定義書から機能 12 項目を取得", status: "pending" },
          { num: 2, title: "STEP 2: Gherkin 形式で AC 起こし", desc: "Given / When / Then のシナリオ化",  status: "pending" },
          { num: 3, title: "STEP 3: 受入チェックリスト出力",   desc: "各機能の合格条件を Markdown で",     status: "pending" },
        ],
        artifacts: [],
        chat: [
          { id: 1, role: "ai", body: "要件定義の機能 12 項目に対して受入条件を Gherkin 形式で起こします。「並行で開始」を押せば AI が自動生成します。", time: "今" },
        ],
        chips: ["並行で開始", "テンプレートを変更", "後で"],
      };
    }
  }

  // 設計 ライン
  if (leaderId === "arch") {
    const archStatuses: Record<string, PhaseStatus> = {
      "architecture-design": "in-progress",
      "api-design": "pending",
      "feature-decomposition": "locked",
      "task-decomposition": "locked",
    };
    if (phaseId === "architecture-design") {
      return {
        skill: "architecture-design",
        phaseStatus: "in-progress",
        phaseStatuses: archStatuses,
        steps: [
          { num: 1, title: "STEP 1: 要件・制約の把握",     desc: "規模感・チーム・予算・既存システム", status: "done", meta: "完了" },
          { num: 2, title: "STEP 2: アーキパターン選定",   desc: "モノリス / モジュラー / マイクロサービス", status: "done", meta: "完了" },
          { num: 3, title: "STEP 3: DB 設計方針",          desc: "PostgreSQL / Redis / S3 構成", status: "done", meta: "完了 ・ 2 時間前" },
          { num: 4, title: "STEP 4: インフラ・セキュリティ", desc: "CI/CD / 認証 / ロール / レートリミット", status: "in-progress", meta: "設計 AI が作業中…" },
        ],
        outputPreview: `## STEP 4 中間出力: インフラ & セキュリティ方針

### 環境構成
- development: Docker (ローカル)
- staging: Vercel (フロント) + Railway (バック)
- production: AWS ECS + RDS + Cloudflare

### セキュリティ
- 認証: JWT (15min) + Refresh (7 日)
- 認可: RBAC (admin / contributor / viewer / client)
- 通信: HTTPS + HSTS, CORS は frontend ドメインのみ
- レートリミット: 100 req/min/user

### 監視
- Sentry (フロント + バック)
- Datadog (APM + ログ集約)`,
        artifacts: [
          { id: 1, title: "アーキ設計書 + ER 図",         meta: "v1.1 ・ 2 時間前 ・ 設計 AI", icon: FileText, latest: true },
          { id: 2, title: "技術スタック比較メモ",          meta: "v1   ・ 1 日前 ・ tech-stack スキル",     icon: FileText },
        ],
        chat: [
          { id: 1, role: "ai", body: "アーキテクチャ STEP 4 の中間出力を上に表示しました。インフラ + セキュリティ方針の確定をお願いします。", time: "5 分前" },
        ],
        chips: ["AWS から GCP に変えて", "本番は別構成にして", "監視 SaaS の選定理由"],
      };
    }
  }

  // デザイナー (designsApi の実データで構築)
  if (leaderId === "design") {
    const designStatuses: Record<string, PhaseStatus> = {
      "design-md":     "done",
      "ui-mockup":     designs.length > 0 ? "in-progress" : "pending",
      "design-review": "pending",
    };

    // designs を ArtifactRef に変換 (Penpot エディタへリンク)
    const designArtifacts: ArtifactRef[] = designs.slice(0, 8).map((d, i) => ({
      id: d.id,
      title: d.name,
      meta: `${d.status} ${d.route_path ? "・ " + d.route_path : ""} ${d.updated_at ? "・ " + new Date(d.updated_at).toLocaleString("ja-JP") : ""}`,
      icon: Palette,
      href: `/workspaces/${workspaceId}/designs/${d.id}/editor`,
      latest: i === 0,
    }));

    if (phaseId === "design-md") {
      return {
        skill: "design-md",
        phaseStatus: "done",
        phaseStatuses: designStatuses,
        steps: [
          { num: 1, title: "STEP 1: ヒアリング",                       desc: "ブランド・配色・タイポの方針",   status: "done", meta: "完了" },
          { num: 2, title: "STEP 2: DESIGN.md + プレビュー HTML 生成", desc: "Calm Industrial スタイル",        status: "done", meta: "完了 ・ 1 日前" },
        ],
        artifacts: [
          { id: "ds-md",  title: "DESIGN.md",       meta: "v1.0 ・ 1 日前 ・ 承認済",        icon: FileText, latest: true,
            href: "/Build-Factory/docs/DESIGN-SYSTEM.md", external: true },
          { id: "ds-mock", title: "BF プレビューモック (mock/index.html)", meta: "11 画面 ・ 1 日前", icon: Layers,
            href: "/mock/index.html", external: true },
        ],
        chat: [
          { id: 1, role: "ai", body: "DESIGN.md と プレビュー HTML を生成しました。Calm Industrial スタイル (SmartHR ベース) で確定済みです。次は モック作成に進みます。", time: "1 日前" },
        ],
        chips: ["DESIGN.md を編集", "別スタイルで作り直す", "モック作成へ"],
      };
    }

    if (phaseId === "ui-mockup") {
      const totalDesigns = designs.length;
      const inProgressCount = designs.filter((d) => d.status === "in_progress" || d.status === "draft").length;
      const completedCount = designs.filter((d) => d.status === "approved" || d.status === "review").length;

      return {
        skill: "ui-mockup",
        phaseStatus: totalDesigns > 0 ? "in-progress" : "pending",
        phaseStatuses: designStatuses,
        steps: [
          { num: 1, title: "STEP 1: 主要画面リスト",     desc: "ホーム / ログイン / ダッシュボード ...", status: totalDesigns > 0 ? "done" : "pending", meta: totalDesigns > 0 ? `完了 ・ ${totalDesigns} 画面` : "未着手" },
          { num: 2, title: "STEP 2: モック生成 (Penpot)", desc: "DESIGN.md トークンで自動生成",          status: totalDesigns > 0 ? "in-progress" : "pending", meta: `${completedCount} / ${totalDesigns} 画面 確定` },
          { num: 3, title: "STEP 3: クライアントレビュー", desc: "コメント受領 → 修正",                   status: "pending" },
        ],
        phaseCta: {
          label: "Penpot キャンバス一覧を開く",
          description: `このワークスペースの ${totalDesigns} 画面のモックを管理`,
          href: `/workspaces/${workspaceId}/designs`,
          icon: Palette,
        },
        artifacts: designArtifacts.length > 0 ? designArtifacts : [
          { id: "empty", title: "(まだモックがありません)", meta: "Penpot キャンバスから新規作成", icon: Palette },
        ],
        chat: [
          { id: 1, role: "ai", body: totalDesigns > 0
            ? `現在 ${totalDesigns} 画面のモックを管理中。確定 ${completedCount} / 進行 ${inProgressCount} です。続けて生成しますか？`
            : "デザインモックがまだありません。「Penpot キャンバス一覧」から新規モックを作成できます。", time: "10 分前" },
        ],
        chips: ["残りを続けて生成", "クライアントに送る", "Penpot を開く"],
      };
    }

    if (phaseId === "design-review") {
      const reviewable = designs.filter((d) => d.status === "review" || d.status === "in_progress");
      return {
        skill: "design-review",
        phaseStatus: reviewable.length > 0 ? "in-progress" : "pending",
        phaseStatuses: designStatuses,
        steps: [
          { num: 1, title: "STEP 1: レビュー対象抽出",       desc: "review / in_progress ステータスのモック",  status: reviewable.length > 0 ? "done" : "pending", meta: `${reviewable.length} 画面` },
          { num: 2, title: "STEP 2: クライアント承認待ち",   desc: "Penpot コメント受領 → 修正反映",            status: "pending" },
          { num: 3, title: "STEP 3: 承認後 実装引き継ぎ",     desc: "approved にステータス変更 → エンジニア AI へ", status: "pending" },
        ],
        phaseCta: {
          label: "Penpot キャンバスでレビュー",
          description: reviewable.length > 0
            ? `${reviewable.length} 画面が確認待ち。クリックでデザイン一覧を開きます`
            : "デザイン一覧から確認したい画面を選択してください",
          href: `/workspaces/${workspaceId}/designs`,
          icon: Palette,
        },
        artifacts: designArtifacts.length > 0 ? designArtifacts : [
          { id: "empty-rev", title: "(レビュー対象がまだありません)", meta: "ui-mockup フェーズでモック作成後に表示されます", icon: Palette },
        ],
        chat: [
          { id: 1, role: "ai", body: reviewable.length > 0
            ? `${reviewable.length} 画面が承認待ちです。Penpot キャンバスで確認してください。承認後、自動的にエンジニア AI へ引き継ぎます。`
            : "レビュー対象のモックがまだありません。ui-mockup フェーズでモックを生成した後にここに並びます。", time: "今" },
        ],
        chips: ["全て承認", "クライアントにまとめて送る", "Penpot 開く"],
      };
    }
  }

  // デフォルト (未着手のフェーズ)
  return {
    skill: phaseId,
    phaseStatus: "pending",
    phaseStatuses: {},
    steps: [
      { num: 1, title: "STEP 1: 開始準備", desc: "前提条件の確認", status: "pending" },
      { num: 2, title: "STEP 2: 実行",     desc: "AI スキル実行",   status: "pending" },
      { num: 3, title: "STEP 3: レビュー", desc: "PM 承認",         status: "pending" },
    ],
    artifacts: [],
    chat: [
      { id: 1, role: "ai", body: "このフェーズはまだ開始されていません。「並行で開始」または前提フェーズの完了をお待ちください。", time: "今" },
    ],
    chips: ["並行で開始", "前提を確認", "後で"],
  };
}
