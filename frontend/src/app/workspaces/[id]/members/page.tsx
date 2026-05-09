"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Workspace, fetchWorkspace } from "@/lib/workspaces";
import { WorkspaceShell, LeaderAvatar, LEADERS } from "@/components/workspace-shell";
import { Card, CardHeader } from "@/components/workspace-shell/HomeBlocks";
import {
  Users, Bot, ShieldCheck, Link as LinkIcon, UserPlus, MoreHorizontal,
  CheckCircle2, Eye, XCircle, MessageSquare, PenLine,
} from "lucide-react";

const HUMAN_MEMBERS = [
  { id: 1, name: "高本 まさと", email: "info@engine-base.com", initials: "MA", role: "admin",       scope: "プロジェクト全権 / クライアント窓口", lastSeen: "オンライン", online: true,  bg: "linear-gradient(135deg,#2563EB,#06B6D4)" },
  { id: 2, name: "佐藤 健太",   email: "sato@engine-base.com",  initials: "SK", role: "contributor", scope: "エンジニア / 実装担当",                lastSeen: "2 時間前",   online: false, bg: "var(--bf-leader-eng)" },
  { id: 3, name: "山田 太郎",   email: "yamada@example.co.jp",  initials: "山", role: "client",      scope: "●●株式会社 / 発注元担当",              lastSeen: "30 分前",    online: false, bg: undefined },
];

const AI_MEMBERS = [
  { leaderId: "secretary" as const, label: "秘書 AI",       sub: "PM 全体ハブ ・ 振り分け担当",       skills: "secretary",                                                                       knowledge: "共通 / 全社",   working: false },
  { leaderId: "pm"        as const, label: "PM AI",         sub: "ヒアリング → 要件 → 提案",          skills: "hearing, requirements-definition, proposal, estimate, acceptance-criteria",       knowledge: "PM領域",        working: true  },
  { leaderId: "arch"      as const, label: "設計 AI",       sub: "アーキ / API / 機能・タスク分解",   skills: "architecture-design, tech-stack, api-design, feature-decomposition, task-decomposition", knowledge: "設計領域",  working: true  },
  { leaderId: "design"    as const, label: "デザイナー AI", sub: "DESIGN.md + Penpot モック",         skills: "design-md, ui-mockup",                                                            knowledge: "デザイン領域",  working: true  },
  { leaderId: "eng"       as const, label: "エンジニア AI", sub: "実装引き継ぎ / 統合",                skills: "distributed-dev, integration",                                                    knowledge: "実装領域",      working: false },
  { leaderId: "qa"        as const, label: "品質 AI",       sub: "テスト戦略 + コードレビュー",        skills: "test-verification, code-review, e2e-testing",                                     knowledge: "品質領域",      working: false },
  { leaderId: "ops"       as const, label: "DevOps AI",     sub: "リリース / 運用 / ドキュメント",     skills: "release-planning, delivery, operations, support-response, documentation",         knowledge: "運用領域",      working: false },
];

const ACCESS_MATRIX: { feature: string; admin: string; contributor: string; viewer: string; client: string }[] = [
  { feature: "ホーム",                  admin: "edit",      contributor: "edit",      viewer: "read", client: "read" },
  { feature: "進捗管理 (DAG / ガント)", admin: "edit",      contributor: "edit",      viewer: "read", client: "read" },
  { feature: "タスク管理 (Kanban)",     admin: "edit",      contributor: "edit",      viewer: "read", client: "deny" },
  { feature: "AI 大分類チャット",       admin: "edit-all",  contributor: "edit-all",  viewer: "deny", client: "edit-secretary" },
  { feature: "各フェーズ作業 (実行)",   admin: "edit",      contributor: "edit",      viewer: "deny", client: "deny" },
  { feature: "デザインモック (Penpot)", admin: "edit",      contributor: "edit",      viewer: "read", client: "comment" },
  { feature: "議事録",                  admin: "edit",      contributor: "edit",      viewer: "read", client: "read" },
  { feature: "アラート / 質問",         admin: "edit",      contributor: "edit",      viewer: "deny", client: "self-only" },
  { feature: "メンバー管理",            admin: "invite",    contributor: "read",      viewer: "read", client: "self-only" },
  { feature: "共有設定",                admin: "edit",      contributor: "deny",      viewer: "deny", client: "deny" },
  { feature: "プロジェクト設定",        admin: "edit",      contributor: "deny",      viewer: "deny", client: "deny" },
];

export default function MembersPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchWorkspace(id).then(setWorkspace).catch(() => setWorkspace(null));
  }, [id]);

  if (!workspace) return <div className="p-6" style={{ color: "var(--bf-text-3)" }}>読み込み中…</div>;

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      progressPercent={45}
      daysLeft={23}
      active="members"
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: "メンバー / 権限" },
      ]}
    >
      <div style={{ marginBottom: "var(--bf-space-6)" }}>
        <div className="flex items-start gap-6 flex-wrap">
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--bf-text-1)", marginBottom: 4 }}>
              メンバー / 権限
            </h1>
            <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>
              プロジェクト参加者・AI 社員・ロール別アクセス権限
            </div>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <button className="inline-flex items-center gap-1.5" style={btnSecondary}>
              <LinkIcon className="w-3.5 h-3.5" />
              招待リンクを発行
            </button>
            <button className="inline-flex items-center gap-1.5" style={btnPrimary}>
              <UserPlus className="w-3.5 h-3.5" />
              メンバー招待
            </button>
          </div>
        </div>
      </div>

      <Card className="mb-5">
        <CardHeader title="人間メンバー" icon={<Users className="w-3.5 h-3.5" />} meta={`${HUMAN_MEMBERS.length} 名`} />
        <table style={tableStyle}>
          <thead>
            <tr>
              <Th width={280}>メンバー</Th>
              <Th width={120}>ロール</Th>
              <Th>担当範囲</Th>
              <Th width={130}>最終アクセス</Th>
              <Th width={60}></Th>
            </tr>
          </thead>
          <tbody>
            {HUMAN_MEMBERS.map((m) => (
              <tr key={m.id}>
                <td style={tdBase}>
                  <div className="flex items-center gap-2.5">
                    <Avatar text={m.initials} bg={m.bg ?? "var(--bf-bg-soft)"} online={m.online} clientStyle={!m.bg} />
                    <div>
                      <div style={{ fontWeight: 600 }}>{m.name}</div>
                      <div style={{ fontSize: 11.5, color: "var(--bf-text-3)" }}>{m.email}</div>
                    </div>
                  </div>
                </td>
                <td style={tdBase}><RoleBadge role={m.role} /></td>
                <td style={{ ...tdBase, fontSize: 12.5, color: "var(--bf-text-3)" }}>{m.scope}</td>
                <td style={{ ...tdBase, fontSize: 12, color: "var(--bf-text-3)" }}>{m.lastSeen}</td>
                <td style={tdBase}>
                  <button style={iconBtnStyle}><MoreHorizontal className="w-3.5 h-3.5" /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card className="mb-5">
        <CardHeader title="AI 社員 (大分類リーダー)" icon={<Bot className="w-3.5 h-3.5" />} meta={`${AI_MEMBERS.length} 体`} />
        <table style={tableStyle}>
          <thead>
            <tr>
              <Th width={280}>AI 社員</Th>
              <Th width={120}>ロール</Th>
              <Th>担当スキル</Th>
              <Th width={140}>ナレッジ</Th>
              <Th width={80}>状態</Th>
              <Th width={60}></Th>
            </tr>
          </thead>
          <tbody>
            {AI_MEMBERS.map((m) => (
              <tr key={m.leaderId}>
                <td style={tdBase}>
                  <div className="flex items-center gap-2.5">
                    <LeaderAvatar id={m.leaderId} size={32} />
                    <div>
                      <div style={{ fontWeight: 600 }}>{m.label}</div>
                      <div style={{ fontSize: 11.5, color: "var(--bf-text-3)" }}>{m.sub}</div>
                    </div>
                  </div>
                </td>
                <td style={tdBase}><span style={{ ...rolePill, background: "var(--bf-success-bg)", color: "var(--bf-success)" }}>{m.leaderId === "secretary" ? "秘書" : "リーダー"}</span></td>
                <td style={{ ...tdBase, fontSize: 12 }}>
                  <code style={{ fontSize: 11, fontFamily: "Inter, monospace" }}>{m.skills}</code>
                </td>
                <td style={{ ...tdBase, fontSize: 11.5, color: "var(--bf-text-3)" }}>{m.knowledge}</td>
                <td style={tdBase}>
                  <span style={{ fontSize: 12, color: m.working ? "var(--bf-success)" : "var(--bf-text-4)" }}>
                    {m.working ? "稼働中" : "待機"}
                  </span>
                </td>
                <td style={tdBase}>
                  <button style={iconBtnStyle}><MoreHorizontal className="w-3.5 h-3.5" /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card>
        <CardHeader
          title="ロール別アクセス権限"
          icon={<ShieldCheck className="w-3.5 h-3.5" />}
          meta={
            <button className="inline-flex items-center gap-1" style={{ ...btnSecondary, height: 28, fontSize: 12 }}>
              <PenLine className="w-3.5 h-3.5" />
              編集
            </button>
          }
        />
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["機能 / 画面", "admin", "contributor", "viewer", "client"].map((h, i) => (
                  <th key={h} style={{
                    padding: "10px 12px",
                    background: "var(--bf-bg-soft)",
                    fontWeight: 600,
                    fontSize: 11,
                    color: "var(--bf-text-3)",
                    textTransform: "uppercase",
                    letterSpacing: "0.04em",
                    textAlign: i === 0 ? "left" : "center",
                    borderBottom: "1px solid var(--bf-divider)",
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ACCESS_MATRIX.map((row, i) => (
                <tr key={i}>
                  <td style={{ padding: "10px 12px", borderBottom: "1px solid var(--bf-divider)", fontSize: 12.5, color: "var(--bf-text-1)" }}>{row.feature}</td>
                  <td style={accessCell}><AccessIcon kind={row.admin} /></td>
                  <td style={accessCell}><AccessIcon kind={row.contributor} /></td>
                  <td style={accessCell}><AccessIcon kind={row.viewer} /></td>
                  <td style={accessCell}><AccessIcon kind={row.client} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center gap-4" style={{ padding: "var(--bf-space-3) var(--bf-space-5)", fontSize: 11.5, color: "var(--bf-text-3)", borderTop: "1px solid var(--bf-divider)" }}>
          <span className="inline-flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--bf-success)" }} /> 編集可能</span>
          <span className="inline-flex items-center gap-1"><Eye className="w-3.5 h-3.5" style={{ color: "var(--bf-info)" }} /> 閲覧のみ</span>
          <span className="inline-flex items-center gap-1"><XCircle className="w-3.5 h-3.5" style={{ color: "var(--bf-text-4)" }} /> アクセス不可</span>
        </div>
      </Card>
    </WorkspaceShell>
  );
}

const btnSecondary: React.CSSProperties = { height: 34, padding: "0 14px", background: "var(--bf-bg-elev)", color: "var(--bf-text-1)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600 };
const btnPrimary:   React.CSSProperties = { height: 34, padding: "0 14px", background: "var(--bf-primary)", color: "#fff", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600 };
const tableStyle:   React.CSSProperties = { width: "100%", borderCollapse: "collapse" };
const tdBase:       React.CSSProperties = { padding: "12px var(--bf-space-5)", borderBottom: "1px solid var(--bf-divider)", fontSize: 13, color: "var(--bf-text-1)" };
const iconBtnStyle: React.CSSProperties = { width: 32, height: 32, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--bf-text-3)", borderRadius: "var(--bf-radius-md)" };
const rolePill:     React.CSSProperties = { display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600 };
const accessCell:   React.CSSProperties = { padding: "10px 12px", borderBottom: "1px solid var(--bf-divider)", textAlign: "center" };

function Th({ children, width }: { children?: React.ReactNode; width?: number }) {
  return (
    <th style={{
      width,
      textAlign: "left",
      fontSize: 11.5, fontWeight: 600,
      color: "var(--bf-text-3)",
      textTransform: "uppercase",
      letterSpacing: "0.04em",
      padding: "10px var(--bf-space-5)",
      borderBottom: "1px solid var(--bf-border)",
      background: "var(--bf-bg-soft)",
    }}>
      {children}
    </th>
  );
}

function Avatar({ text, bg, online, clientStyle }: { text: string; bg: string; online?: boolean; clientStyle?: boolean }) {
  return (
    <div style={{
      position: "relative",
      width: 28, height: 28, borderRadius: "50%",
      border: "2px solid #fff",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 10, fontWeight: 700,
      color: clientStyle ? "var(--bf-text-2)" : "#fff",
      background: bg,
      ...(clientStyle ? { borderColor: "var(--bf-border)" } : {}),
    }}>
      {text}
      {online && (
        <span style={{ position: "absolute", bottom: -1, right: -1, width: 7, height: 7, background: "var(--bf-success)", border: "1.5px solid #fff", borderRadius: "50%" }} />
      )}
    </div>
  );
}

function RoleBadge({ role }: { role: string }) {
  const map: Record<string, { bg: string; color: string; label: string }> = {
    admin:       { bg: "var(--bf-danger-bg)",  color: "var(--bf-danger)",  label: "admin" },
    contributor: { bg: "var(--bf-primary-bg)", color: "var(--bf-primary)", label: "contributor" },
    viewer:      { bg: "var(--bf-neutral-bg)", color: "var(--bf-neutral)", label: "viewer" },
    client:      { bg: "var(--bf-info-bg)",    color: "var(--bf-info)",    label: "client" },
  };
  const c = map[role] ?? map.viewer;
  return (
    <span style={{ ...rolePill, background: c.bg, color: c.color }}>{c.label}</span>
  );
}

function AccessIcon({ kind }: { kind: string }) {
  if (kind === "deny") {
    return <XCircle className="w-3.5 h-3.5 inline" style={{ color: "var(--bf-text-4)" }} />;
  }
  if (kind === "read") {
    return <Eye className="w-3.5 h-3.5 inline" style={{ color: "var(--bf-info)" }} />;
  }
  if (kind === "edit" || kind === "edit-all" || kind === "invite") {
    return (
      <span className="inline-flex items-center gap-1">
        <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--bf-success)" }} />
        {kind === "edit-all" && <span style={{ fontSize: 11, color: "var(--bf-text-3)" }}>全 AI</span>}
        {kind === "invite"   && <span style={{ fontSize: 11, color: "var(--bf-text-3)" }}>招待</span>}
      </span>
    );
  }
  if (kind === "edit-secretary") {
    return (
      <span className="inline-flex items-center gap-1">
        <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--bf-success)" }} />
        <span style={{ fontSize: 11, color: "var(--bf-text-3)" }}>秘書のみ</span>
      </span>
    );
  }
  if (kind === "comment") {
    return (
      <span className="inline-flex items-center gap-1">
        <MessageSquare className="w-3.5 h-3.5" style={{ color: "var(--bf-info)" }} />
        <span style={{ fontSize: 11, color: "var(--bf-text-3)" }}>コメント可</span>
      </span>
    );
  }
  if (kind === "self-only") {
    return (
      <span className="inline-flex items-center gap-1">
        <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--bf-success)" }} />
        <span style={{ fontSize: 11, color: "var(--bf-text-3)" }}>自分宛のみ</span>
      </span>
    );
  }
  return null;
}
