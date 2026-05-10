/**
 * Workspace Shell — 共有型定義
 * Calm Industrial デザイン基準: Build-Factory/docs/DESIGN-SYSTEM.md
 */

export type LeaderId = "secretary" | "pm" | "arch" | "design" | "eng" | "qa" | "ops";

export type SidebarKey =
  | "home"
  | "progress"
  | "tasks"
  | "schedule"
  | "minutes"
  | "alerts"
  | "members"
  | "share"
  | "settings"
  | LeaderId;

export type PhaseId =
  | "hearing"
  | "requirements-definition"
  | "pricing-design"
  | "proposal"
  | "estimate"
  | "acceptance-criteria"
  | "architecture-design"
  | "tech-stack"
  | "api-design"
  | "feature-decomposition"
  | "task-decomposition"
  | "design-md"
  | "ui-mockup"
  | "design-review"
  | "distributed-dev"
  | "integration"
  | "test-verification"
  | "code-review"
  | "e2e-testing"
  | "release-planning"
  | "delivery"
  | "operations"
  | "support-response"
  | "documentation";

export type PhaseStatus = "done" | "in-progress" | "pending" | "locked" | "review";

export type LeaderDef = {
  id: LeaderId;
  label: string;
  shortName: string;
  colorVar: string;
  phases: { id: PhaseId; label: string }[];
};

export const LEADERS: LeaderDef[] = [
  {
    id: "secretary",
    label: "秘書 AI",
    shortName: "秘",
    colorVar: "var(--bf-leader-secretary)",
    phases: [],
  },
  {
    id: "pm",
    label: "PM AI",
    shortName: "PM",
    colorVar: "var(--bf-leader-pm)",
    phases: [
      { id: "hearing", label: "ヒアリング" },
      { id: "requirements-definition", label: "要件定義" },
      { id: "pricing-design", label: "価格設計" },
      { id: "proposal", label: "提案書" },
      { id: "estimate", label: "見積書" },
      { id: "acceptance-criteria", label: "受入条件" },
    ],
  },
  {
    id: "arch",
    label: "設計 AI",
    shortName: "設",
    colorVar: "var(--bf-leader-arch)",
    phases: [
      { id: "architecture-design", label: "アーキテクチャ" },
      { id: "api-design", label: "API 設計" },
      { id: "feature-decomposition", label: "機能分解" },
      { id: "task-decomposition", label: "タスク分解" },
    ],
  },
  {
    id: "design",
    label: "デザイナー AI",
    shortName: "デ",
    colorVar: "var(--bf-leader-design)",
    phases: [
      { id: "design-md", label: "デザインシステム" },
      { id: "ui-mockup", label: "モック作成" },
      { id: "design-review", label: "デザインレビュー" },
    ],
  },
  {
    id: "eng",
    label: "エンジニア AI",
    shortName: "エ",
    colorVar: "var(--bf-leader-eng)",
    phases: [
      { id: "distributed-dev", label: "実装引き継ぎ" },
      { id: "integration", label: "統合" },
    ],
  },
  {
    id: "qa",
    label: "品質 AI",
    shortName: "品",
    colorVar: "var(--bf-leader-qa)",
    phases: [
      { id: "test-verification", label: "テスト戦略" },
      { id: "code-review", label: "レビュー" },
    ],
  },
  {
    id: "ops",
    label: "DevOps AI",
    shortName: "運",
    colorVar: "var(--bf-leader-ops)",
    phases: [
      { id: "release-planning", label: "リリース計画" },
      { id: "operations", label: "運用" },
      { id: "documentation", label: "ドキュメント" },
    ],
  },
];

export type WorkspaceContextValue = {
  workspaceId: number;
  workspaceName: string;
  clientName?: string;
  progressPercent: number;
  daysLeft?: number;
};
