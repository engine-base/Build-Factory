"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Workspace, fetchWorkspace } from "@/lib/workspaces";
import { WorkspaceShell, LeaderAvatar } from "@/components/workspace-shell";
import type { LeaderId } from "@/components/workspace-shell";
import { Card, CardHeader } from "@/components/workspace-shell/HomeBlocks";
import {
  Milestone, Calendar, ListOrdered, Plus, Link as LinkIcon,
  Check, Loader2, Circle, Flag, Clock, Users, MapPin, CheckCircle2,
  ChevronLeft, ChevronRight,
} from "lucide-react";

type TimelineKind = "done" | "current" | "upcoming";

type TimelineItem = {
  date: string; title: string; desc?: string;
  kind: TimelineKind;
  meta?: { icon?: any; label: string }[];
  isDeadline?: boolean;
};

const TIMELINE: TimelineItem[] = [
  { date: "4月30日 (水)", title: "ヒアリング完了",       desc: "プロジェクト起点ブリーフ生成 ・ クライアント承認済", kind: "done",     meta: [{ label: "PM AI" }] },
  { date: "5月3日 (土)",  title: "要件定義 v2.0 完了",   desc: "クライアントレビュー反映 ・ 認証 Must / DB 連携追加", kind: "done",     meta: [{ label: "PM AI" }] },
  { date: "5月4日 (日) 〜 進行中", title: "設計フェーズ (アーキ + デザイン)", desc: "並行進行中 ・ アーキ 90% / モック 38%", kind: "current",  meta: [{ label: "設計 AI" }, { label: "デザイナー AI" }] },
  { date: "5月8日 (木) 14:00", title: "アーキ設計 中間レビュー (クライアント)", desc: "山田様 + 高本 + 設計 AI ・ 既存 DB 連携の設計確認", kind: "upcoming", meta: [{ icon: MapPin, label: "Online" }, { icon: Users, label: "3 名" }] },
  { date: "5月12日 (月)", title: "設計フェーズ完了予定", desc: "アーキ + デザイン + API + 機能・タスク分解 まで完了", kind: "upcoming", meta: [{ icon: CheckCircle2, label: "承認ゲート" }] },
  { date: "5月13日 (火) 〜", title: "実装フェーズ開始",   desc: "Claude Code MCP 経由でタスク分散実装", kind: "upcoming", meta: [{ label: "エンジニア AI" }] },
  { date: "5月25日 (日)", title: "テスト + QA フェーズ", desc: "E2E + 受入テスト + コードレビュー", kind: "upcoming" },
  { date: "5月20日 (火) ・ 納期", title: "本番リリース ★ 納期", desc: "●●株式会社 へ納品 ・ 残 23 日", kind: "upcoming", isDeadline: true },
];

type EventItem = {
  month: string; day: string; title: string;
  metaIcon?: any; meta?: string;
  kind?: "today" | "danger";
};

const EVENTS: EventItem[] = [
  { month: "May", day: "4",  title: "設計フェーズ 進行中",          metaIcon: Loader2,      meta: "並行: アーキ + モック", kind: "today" },
  { month: "May", day: "8",  title: "アーキ中間レビュー MTG",        metaIcon: Clock,        meta: "14:00 〜 15:00 / クライアント" },
  { month: "May", day: "12", title: "設計フェーズ完了予定",          metaIcon: CheckCircle2, meta: "承認ゲート" },
  { month: "May", day: "20", title: "本番リリース (納期)",           metaIcon: Flag,         meta: "残 16 日", kind: "danger" },
  { month: "May", day: "25", title: "QA + 受入テスト",                metaIcon: Users,        meta: "クライアント受入" },
];

export default function SchedulePage() {
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
      active="schedule"
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: "スケジュール" },
      ]}
    >
      <div style={{ marginBottom: "var(--bf-space-6)" }}>
        <div className="flex items-start gap-6 flex-wrap">
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--bf-text-1)", marginBottom: 4 }}>
              スケジュール
            </h1>
            <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>
              マイルストーン + フェーズ完了予定 + クライアントとの重要日程
            </div>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <button className="inline-flex items-center gap-1.5" style={btnSecondary}>
              <LinkIcon className="w-3.5 h-3.5" /> Google Calendar 連携
            </button>
            <button className="inline-flex items-center gap-1.5" style={btnPrimary}>
              <Plus className="w-3.5 h-3.5" /> 予定を追加
            </button>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: "var(--bf-space-5)" }}>
        {/* Timeline */}
        <Card>
          <CardHeader title="マイルストーン" icon={<Milestone className="w-3.5 h-3.5" />} meta={`完了 2 / 残り ${TIMELINE.length - 2}`} />
          <div style={{ padding: "var(--bf-space-5) var(--bf-space-6)" }}>
            <div style={{ position: "relative", paddingLeft: 30 }}>
              <div style={{ position: "absolute", left: 8, top: 0, bottom: 0, width: 2, background: "var(--bf-border)" }} />
              {TIMELINE.map((t, i) => (
                <TimelineRow key={i} item={t} />
              ))}
            </div>
          </div>
        </Card>

        {/* Right column */}
        <div>
          <Card className="mb-5">
            <CardHeader
              title="5月 2026"
              icon={<Calendar className="w-3.5 h-3.5" />}
              meta={
                <div className="flex gap-1">
                  <button style={iconBtn}><ChevronLeft className="w-3.5 h-3.5" /></button>
                  <button style={iconBtn}><ChevronRight className="w-3.5 h-3.5" /></button>
                </div>
              }
            />
            <div style={{ padding: "var(--bf-space-4) var(--bf-space-5)" }}>
              <CalendarGrid />
            </div>
          </Card>

          <Card>
            <CardHeader title="今後の予定" icon={<ListOrdered className="w-3.5 h-3.5" />} />
            <div>
              {EVENTS.map((e, i) => (
                <EventRow key={i} ev={e} last={i === EVENTS.length - 1} />
              ))}
            </div>
          </Card>
        </div>
      </div>
    </WorkspaceShell>
  );
}

function TimelineRow({ item }: { item: TimelineItem }) {
  const dotStyle: Record<TimelineKind, React.CSSProperties> = {
    done:     { background: "var(--bf-success)", borderColor: "var(--bf-success)" },
    current:  { background: "var(--bf-primary)", borderColor: "var(--bf-primary)", boxShadow: "0 0 0 4px var(--bf-primary-bg)" },
    upcoming: { background: "var(--bf-bg-elev)", borderColor: "var(--bf-border-strong)" },
  };
  const Icon = item.kind === "done" ? Check : item.kind === "current" ? Loader2 : item.isDeadline ? Flag : Circle;

  return (
    <div style={{ position: "relative", marginBottom: "var(--bf-space-5)" }}>
      <span style={{
        position: "absolute", left: -27, top: 4,
        width: 16, height: 16, borderRadius: "50%",
        border: "2px solid",
        ...dotStyle[item.kind],
      }} />
      <div style={{ fontSize: 11.5, color: item.isDeadline ? "var(--bf-danger)" : "var(--bf-text-3)", fontWeight: 600, marginBottom: 4, display: "flex", alignItems: "center", gap: 6 }}>
        <Icon className={`w-3.5 h-3.5 ${item.kind === "current" ? "animate-spin" : ""}`} />
        {item.date}
      </div>
      <div style={{
        background: item.isDeadline ? "var(--bf-danger-bg)" : "var(--bf-bg-elev)",
        border: `1px solid ${item.kind === "current" ? "var(--bf-primary)" : item.isDeadline ? "var(--bf-danger)" : "var(--bf-border)"}`,
        borderRadius: "var(--bf-radius-md)",
        padding: "var(--bf-space-4)",
        ...(item.kind === "current" ? { background: "var(--bf-primary-soft)" } : {}),
      }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: item.isDeadline ? "var(--bf-danger)" : "var(--bf-text-1)", marginBottom: 4 }}>
          {item.title}
        </div>
        {item.desc && (
          <div style={{ fontSize: 12.5, color: "var(--bf-text-3)", lineHeight: 1.6, marginBottom: 8 }}>
            {item.desc}
          </div>
        )}
        {item.meta && (
          <div className="flex items-center gap-2.5 flex-wrap" style={{ fontSize: 11.5, color: "var(--bf-text-3)" }}>
            {item.meta.map((m, i) => {
              const I = m.icon;
              return (
                <span key={i} className="inline-flex items-center gap-1">
                  {I && <I className="w-3.5 h-3.5" />}
                  {m.label}
                </span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function CalendarGrid() {
  const dows = ["日", "月", "火", "水", "木", "金", "土"];
  // 簡易カレンダー (5月 2026 ・ 日曜始まり)
  const days: { day: number; muted?: boolean; today?: boolean; event?: boolean; deadline?: boolean }[] = [];
  // 4月末
  [27, 28, 29].forEach((d) => days.push({ day: d, muted: true }));
  days.push({ day: 30, event: true });
  days.push({ day: 1, event: true });
  [2].forEach((d) => days.push({ day: d }));
  days.push({ day: 3, event: true });
  days.push({ day: 4, today: true, event: true });
  [5, 6, 7].forEach((d) => days.push({ day: d }));
  days.push({ day: 8, event: true });
  [9, 10, 11].forEach((d) => days.push({ day: d }));
  days.push({ day: 12, event: true });
  for (let d = 13; d <= 19; d++) days.push({ day: d });
  days.push({ day: 20, deadline: true });
  for (let d = 21; d <= 24; d++) days.push({ day: d });
  days.push({ day: 25, event: true });
  for (let d = 26; d <= 31; d++) days.push({ day: d });

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4, marginBottom: 6 }}>
        {dows.map((d) => (
          <div key={d} style={{ textAlign: "center", fontSize: 10.5, fontWeight: 600, color: "var(--bf-text-3)", padding: "6px 0", textTransform: "uppercase" }}>
            {d}
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
        {days.map((d, i) => (
          <div
            key={i}
            style={{
              aspectRatio: "1",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12.5,
              color: d.today ? "#fff" : d.muted ? "var(--bf-text-4)" : "var(--bf-text-2)",
              borderRadius: "var(--bf-radius-sm)",
              cursor: "pointer",
              background: d.today ? "var(--bf-primary)" : "transparent",
              fontWeight: d.today ? 700 : 400,
              position: "relative",
            }}
          >
            {d.day}
            {(d.event || d.deadline) && (
              <span style={{
                position: "absolute", bottom: 4, left: "50%", transform: "translateX(-50%)",
                width: 4, height: 4, borderRadius: "50%",
                background: d.deadline ? "var(--bf-danger)" : d.today ? "#fff" : "var(--bf-primary)",
              }} />
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function EventRow({ ev, last }: { ev: EventItem; last: boolean }) {
  const blockBg = ev.kind === "today" ? "var(--bf-primary)" : ev.kind === "danger" ? "var(--bf-danger-bg)" : "var(--bf-bg-soft)";
  const blockBorder = ev.kind === "today" ? "var(--bf-primary)" : ev.kind === "danger" ? "var(--bf-danger)" : "var(--bf-border)";
  const blockFg = ev.kind === "today" ? "#fff" : ev.kind === "danger" ? "var(--bf-danger)" : "var(--bf-text-1)";
  const Icon = ev.metaIcon;

  return (
    <div className="flex items-start gap-3" style={{
      padding: "12px var(--bf-space-5)",
      borderBottom: last ? undefined : "1px solid var(--bf-divider)",
    }}>
      <div style={{
        width: 56, textAlign: "center", flexShrink: 0,
        background: blockBg,
        border: `1px solid ${blockBorder}`,
        borderRadius: "var(--bf-radius-md)",
        padding: "6px 4px",
        color: blockFg,
      }}>
        <div style={{ fontSize: 9, fontWeight: 600, textTransform: "uppercase", marginBottom: 1, opacity: 0.8 }}>{ev.month}</div>
        <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1 }}>{ev.day}</div>
      </div>
      <div className="flex-1 min-w-0">
        <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--bf-text-1)", marginBottom: 2 }}>
          {ev.title}
        </div>
        {ev.meta && (
          <div className="flex items-center gap-1" style={{ fontSize: 11.5, color: ev.kind === "danger" ? "var(--bf-danger)" : "var(--bf-text-3)", fontWeight: ev.kind === "danger" ? 600 : 400 }}>
            {Icon && <Icon className="w-3.5 h-3.5" />}
            {ev.meta}
          </div>
        )}
      </div>
    </div>
  );
}

const btnSecondary: React.CSSProperties = { height: 34, padding: "0 14px", background: "var(--bf-bg-elev)", color: "var(--bf-text-1)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600 };
const btnPrimary:   React.CSSProperties = { height: 34, padding: "0 14px", background: "var(--bf-primary)", color: "#fff", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600 };
const iconBtn:      React.CSSProperties = { width: 32, height: 32, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--bf-text-3)", borderRadius: "var(--bf-radius-md)" };
