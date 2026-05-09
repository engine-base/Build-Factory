"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Workspace, fetchWorkspace } from "@/lib/workspaces";
import { WorkspaceShell } from "@/components/workspace-shell";
import {
  CircleHelp, FileSearch, CheckCircle2, MessageSquare, AlertOctagon,
  CheckCheck, BellOff,
} from "lucide-react";

type AlertItem = {
  id: number;
  type: "question" | "review" | "approve" | "comment" | "block";
  urgent?: boolean;
  read?: boolean;
  title: string;
  source: string;
  message: string;
  badge?: string;
  actions: { label: string; primary?: boolean }[];
  time: string;
};

const ALERTS: AlertItem[] = [
  {
    id: 1, type: "question", urgent: true,
    title: "予算上限の確認", badge: "優先",
    source: "秘書 AI から ・ ヒアリング STEP 4 ・ プロジェクト管理",
    message: "プロジェクト全体の予算上限を確定させたいです。クライアントとのすり合わせで「500 万円程度」とありましたが、上振れの許容幅を教えてください (10% / 20% / 30%)。",
    actions: [{ label: "回答する", primary: true }, { label: "クライアントに確認" }, { label: "後で" }],
    time: "15分前",
  },
  {
    id: 2, type: "review",
    title: "要件定義書 v2.0 のレビュー依頼",
    source: "PM AI から ・ 要件定義 STEP 6 完了",
    message: "要件定義書 v2.0 が完成しました。6 項目 (機能要件 / 非機能要件 / 画面 / データ / リスク / 未確認事項) のチェックをお願いします。承認後、設計フェーズが本格化します。",
    actions: [{ label: "レビューを開く", primary: true }, { label: "差し戻し" }],
    time: "42分前",
  },
  {
    id: 3, type: "approve",
    title: "API 設計書 の承認待ち",
    source: "設計 AI から ・ API 設計フェーズ完了",
    message: "API 設計書の作成が完了しました。承認後、機能分解 + タスク分解フェーズへ進みます。エンドポイント数: 24 個 / 認証スキーム: JWT / レスポンス形式: JSON。",
    actions: [{ label: "承認", primary: true }, { label: "確認してから" }, { label: "差し戻し" }],
    time: "1時間前",
  },
  {
    id: 4, type: "comment",
    title: "クライアントからのコメント", badge: "山田 太郎",
    source: "●●株式会社 山田 太郎 様 ・ デザインモック (3 画面) について",
    message: "「モックを拝見しました。全体的に良い感じです。1 点、ホーム画面の右側カラムの導線が分かりづらい気がします。タスク一覧へのリンクをもう少し目立つ位置に置けないでしょうか？」",
    actions: [{ label: "返信", primary: true }, { label: "モックを開く" }, { label: "デザイナー AI に修正依頼" }],
    time: "3時間前",
  },
  {
    id: 5, type: "question", read: true,
    title: "既存 DB との連携要否", badge: "回答済",
    source: "設計 AI から ・ アーキ STEP 3",
    message: "既存の社内 Oracle DB との連携は読み取り専用で。VPN + IP ホワイトリスト経由で接続します。スキーマ詳細を山田様から後日受領予定。",
    actions: [],
    time: "昨日",
  },
];

const FILTERS = [
  { key: "all",      label: "全て",          count: 5 },
  { key: "question", label: "質問",          count: 2 },
  { key: "review",   label: "レビュー依頼",  count: 1 },
  { key: "approve",  label: "承認待ち",      count: 1 },
  { key: "comment",  label: "コメント",      count: 1 },
  { key: "block",    label: "ブロッカー",    count: 0 },
];

export default function AlertsPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    if (!id) return;
    fetchWorkspace(id).then(setWorkspace).catch(() => setWorkspace(null));
  }, [id]);

  if (!workspace) return <div className="p-6" style={{ color: "var(--bf-text-3)" }}>読み込み中…</div>;

  const items = filter === "all" ? ALERTS : ALERTS.filter((a) => a.type === filter);

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      progressPercent={45}
      daysLeft={23}
      active="alerts"
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: "アラート / 質問" },
      ]}
    >
      <div style={{ marginBottom: "var(--bf-space-6)" }}>
        <div className="flex items-start gap-6 flex-wrap">
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--bf-text-1)", marginBottom: 4 }}>
              アラート / 質問
            </h1>
            <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>
              人間決裁が必要な通知センター。質問 / レビュー / 承認 / ブロッカー
            </div>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <button className="inline-flex items-center gap-1.5" style={btnSecondary}>
              <CheckCheck className="w-3.5 h-3.5" /> 全て既読にする
            </button>
            <button className="inline-flex items-center gap-1.5" style={btnSecondary}>
              <BellOff className="w-3.5 h-3.5" /> 通知設定
            </button>
          </div>
        </div>
      </div>

      <div className="flex gap-1" style={{ marginBottom: "var(--bf-space-5)", borderBottom: "1px solid var(--bf-border)" }}>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className="inline-flex items-center gap-1.5"
            style={{
              padding: "10px 16px",
              fontSize: 13, fontWeight: filter === f.key ? 600 : 500,
              color: filter === f.key ? "var(--bf-primary)" : "var(--bf-text-3)",
              borderBottom: `2px solid ${filter === f.key ? "var(--bf-primary)" : "transparent"}`,
              marginBottom: -1,
            }}
          >
            {f.label}
            <span style={{
              background: filter === f.key ? "var(--bf-primary-bg)" : "var(--bf-bg-soft)",
              color:      filter === f.key ? "var(--bf-primary)"    : "var(--bf-text-3)",
              border: `1px solid ${filter === f.key ? "var(--bf-primary-bg)" : "var(--bf-border)"}`,
              borderRadius: 999,
              padding: "1px 6px",
              fontSize: 11,
            }}>
              {f.count}
            </span>
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-2">
        {items.map((a) => <AlertCard key={a.id} alert={a} />)}
      </div>
    </WorkspaceShell>
  );
}

function AlertCard({ alert }: { alert: AlertItem }) {
  const iconMap = {
    question: { Icon: CircleHelp,    bg: "var(--bf-warning-bg)", color: "var(--bf-warning)" },
    review:   { Icon: FileSearch,    bg: "var(--bf-info-bg)",    color: "var(--bf-info)" },
    approve:  { Icon: CheckCircle2,  bg: "var(--bf-success-bg)", color: "var(--bf-success)" },
    comment:  { Icon: MessageSquare, bg: "var(--bf-neutral-bg)", color: "var(--bf-neutral)" },
    block:    { Icon: AlertOctagon,  bg: "var(--bf-danger-bg)",  color: "var(--bf-danger)" },
  };
  const c = iconMap[alert.type];

  return (
    <button
      className="w-full text-left flex gap-4 transition-colors"
      style={{
        padding: "var(--bf-space-4) var(--bf-space-5)",
        background: "var(--bf-bg-elev)",
        border: "1px solid var(--bf-border)",
        borderLeft: `4px solid ${alert.urgent ? "var(--bf-danger)" : "var(--bf-primary)"}`,
        borderRadius: "var(--bf-radius-md)",
        opacity: alert.read ? 0.65 : 1,
      }}
    >
      <div
        className="flex items-center justify-center flex-shrink-0"
        style={{
          width: 38, height: 38,
          borderRadius: "var(--bf-radius-md)",
          background: c.bg, color: c.color,
        }}
      >
        <c.Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2" style={{ marginBottom: 4 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--bf-text-1)", flex: 1 }}>
            {alert.title}
          </div>
          {alert.badge && (
            <span style={{
              padding: "1px 7px",
              borderRadius: 999,
              fontSize: 11, fontWeight: 600,
              background: alert.urgent ? "var(--bf-danger-bg)" : alert.read ? "var(--bf-neutral-bg)" : "var(--bf-primary-bg)",
              color:      alert.urgent ? "var(--bf-danger)"    : alert.read ? "var(--bf-neutral)"    : "var(--bf-primary)",
            }}>
              {alert.badge}
            </span>
          )}
        </div>
        <div style={{ fontSize: 12, color: "var(--bf-text-3)", marginBottom: 8 }}>
          {alert.source}
        </div>
        <div style={{
          fontSize: 12.5, color: "var(--bf-text-2)",
          lineHeight: 1.6,
          background: "var(--bf-bg-soft)",
          borderRadius: "var(--bf-radius-md)",
          padding: "10px 12px",
          marginBottom: 10,
        }}>
          {alert.message}
        </div>
        {alert.actions.length > 0 && (
          <div className="flex gap-1.5">
            {alert.actions.map((a, i) => (
              <span key={i} style={{
                height: 28, padding: "0 10px",
                display: "inline-flex", alignItems: "center",
                background: a.primary ? "var(--bf-primary)" : i === 1 ? "var(--bf-bg-elev)" : "transparent",
                color: a.primary ? "#fff" : "var(--bf-text-2)",
                border: i === 1 ? "1px solid var(--bf-border)" : "1px solid transparent",
                borderRadius: "var(--bf-radius-md)",
                fontSize: 12, fontWeight: 600,
              }}>
                {a.label}
              </span>
            ))}
          </div>
        )}
      </div>
      <div style={{ fontSize: 11.5, color: "var(--bf-text-4)", flexShrink: 0 }}>
        {alert.time}
      </div>
    </button>
  );
}

const btnSecondary: React.CSSProperties = { height: 34, padding: "0 14px", background: "var(--bf-bg-elev)", color: "var(--bf-text-1)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600 };
