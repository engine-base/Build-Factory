/**
 * Workspace ホーム画面のブロック群 (コックピット)。
 * 各ブロックは workspace データから埋める。
 */
"use client";

import {
  Zap, Inbox, Activity, BarChart3, FolderOpen, History, Users,
  CircleHelp, FileSearch, CheckCircle2, MessageSquare, AlertOctagon,
  Clock, Wallet, Play, PenLine, SkipForward, ArrowRight,
  AlertTriangle, Loader2, FileText, Layers, Palette,
} from "lucide-react";
import { LeaderAvatar } from "./LeaderAvatar";
import type { LeaderId } from "./types";

/* ──────────────────────────────────────────────────
 *  共通カード
 * ────────────────────────────────────────────────── */

export function Card({
  children, className,
}: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={className}
      style={{
        background: "var(--bf-bg-elev)",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-lg)",
        overflow: "hidden",
      }}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title, icon, meta,
}: {
  title: React.ReactNode;
  icon?: React.ReactNode;
  meta?: React.ReactNode;
}) {
  return (
    <div
      className="flex items-center justify-between"
      style={{
        padding: "14px var(--bf-space-5)",
        borderBottom: "1px solid var(--bf-divider)",
      }}
    >
      <h2
        className="flex items-center gap-2"
        style={{
          fontSize: 13, fontWeight: 700, color: "var(--bf-text-1)",
          letterSpacing: "-0.005em",
        }}
      >
        {icon}
        {title}
      </h2>
      {meta && <span style={{ fontSize: 11.5, color: "var(--bf-text-3)" }}>{meta}</span>}
    </div>
  );
}

/* ──────────────────────────────────────────────────
 *  DAG 進捗バー
 * ────────────────────────────────────────────────── */

export type DagPhase = {
  id: string;
  label: string;
  status: "done" | "in-progress" | "pending";
};

export function DagProgress({
  phases, currentLabel, completed, total,
}: {
  phases: DagPhase[];
  currentLabel?: string;
  completed: number;
  total: number;
}) {
  return (
    <div
      style={{
        marginTop: "var(--bf-space-5)",
        padding: "var(--bf-space-4) var(--bf-space-5)",
        background: "var(--bf-bg-elev)",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-lg)",
      }}
    >
      <div className="flex items-center justify-between" style={{ marginBottom: 10 }}>
        <strong style={{ fontSize: 13, color: "var(--bf-text-1)" }}>プロジェクト進捗</strong>
        <span style={{ fontSize: 12, color: "var(--bf-text-3)" }}>
          {completed} / {total} フェーズ完了{currentLabel ? ` ・ 現在: ${currentLabel}` : ""}
        </span>
      </div>
      <div
        className="flex"
        style={{
          height: 8, background: "var(--bf-border)",
          borderRadius: 999, overflow: "hidden", gap: 2,
        }}
      >
        {phases.map((p) => (
          <span
            key={p.id}
            title={p.label}
            style={{
              flex: 1,
              background:
                p.status === "done"        ? "var(--bf-success)"
                : p.status === "in-progress" ? "var(--bf-primary)"
                : "var(--bf-border)",
              backgroundImage: p.status === "in-progress"
                ? "linear-gradient(45deg, rgba(255,255,255,0.25) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.25) 50%, rgba(255,255,255,0.25) 75%, transparent 75%)"
                : undefined,
              backgroundSize: p.status === "in-progress" ? "14px 14px" : undefined,
              animation: p.status === "in-progress" ? "bf-stripe 1.2s linear infinite" : undefined,
            }}
          />
        ))}
      </div>
      <div
        className="flex justify-between"
        style={{ marginTop: 8, fontSize: 11, color: "var(--bf-text-3)" }}
      >
        {phases.map((p) => (
          <span
            key={p.id}
            style={{
              color:
                p.status === "done"        ? "var(--bf-success)"
                : p.status === "in-progress" ? "var(--bf-primary)"
                : undefined,
              fontWeight: p.status === "in-progress" ? 600 : undefined,
            }}
          >
            {p.label}
          </span>
        ))}
      </div>
      <style>{`@keyframes bf-stripe { from{background-position:0 0} to{background-position:28px 0} }`}</style>
    </div>
  );
}

/* ──────────────────────────────────────────────────
 *  強行突破フラグ
 * ────────────────────────────────────────────────── */

export function AlertStrip({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="flex items-center gap-2"
      style={{
        marginTop: "var(--bf-space-3)",
        padding: "8px 12px",
        background: "var(--bf-warning-bg)",
        border: "1px solid #FCD34D",
        borderRadius: "var(--bf-radius-md)",
        color: "var(--bf-warning)",
        fontSize: 12.5, fontWeight: 500,
      }}
    >
      <AlertTriangle className="w-3.5 h-3.5" />
      {children}
    </div>
  );
}

/* ──────────────────────────────────────────────────
 *  Next Action カード
 * ────────────────────────────────────────────────── */

export type NextAction = {
  id: string | number;
  leaderId: LeaderId;
  leaderLabel: string;
  phase: string;
  title: string;
  reason: string;
  recommend?: boolean;
  parallel?: boolean;
};

export function NextActionsBlock({ actions }: { actions: NextAction[] }) {
  return (
    <Card>
      <CardHeader
        title="次のアクション"
        icon={<Zap className="w-3.5 h-3.5" />}
        meta={`AI 提案 (${actions.length} 件)`}
      />
      {actions.map((a) => (
        <div
          key={a.id}
          style={{
            padding: "var(--bf-space-4) var(--bf-space-5)",
            borderBottom: "1px solid var(--bf-divider)",
          }}
        >
          <div className="flex items-start gap-3">
            <div
              style={{
                width: 5, alignSelf: "stretch",
                background: a.recommend ? "var(--bf-primary)" : "var(--bf-info)",
                borderRadius: 999,
              }}
            />
            <div className="flex-1">
              <div
                className="flex items-center gap-2"
                style={{ fontSize: 11, color: "var(--bf-text-3)", marginBottom: 4 }}
              >
                <LeaderTag leaderId={a.leaderId} label={a.leaderLabel} />
                <span>{a.phase}</span>
                {a.recommend && <Badge tone="recommend">推奨</Badge>}
                {a.parallel && <Badge tone="parallel">並行可</Badge>}
              </div>
              <div
                style={{
                  fontSize: 14.5, fontWeight: 600,
                  color: "var(--bf-text-1)", marginBottom: 2,
                }}
              >
                {a.title}
              </div>
              <div style={{ fontSize: 12.5, color: "var(--bf-text-3)" }}>
                {a.reason}
              </div>
              <div className="flex items-center gap-2" style={{ marginTop: 12 }}>
                <Button variant="primary" size="sm" icon={<Play className="w-3.5 h-3.5" />}>
                  AI に進めてもらう
                </Button>
                <Button variant="secondary" size="sm" icon={<PenLine className="w-3.5 h-3.5" />}>
                  自分で編集
                </Button>
                <Button variant="ghost" size="sm" icon={<SkipForward className="w-3.5 h-3.5" />}>
                  スキップ
                </Button>
              </div>
            </div>
          </div>
        </div>
      ))}
    </Card>
  );
}

/* ──────────────────────────────────────────────────
 *  あなた待ち
 * ────────────────────────────────────────────────── */

export type QueueItem = {
  id: string | number;
  type: "review" | "approve" | "question" | "comment";
  title: string;
  source: string;
  time: string;
};

const QUEUE_ICON = {
  review:   { Icon: FileSearch,    bg: "var(--bf-info-bg)",    color: "var(--bf-info)"    },
  approve:  { Icon: CheckCircle2,  bg: "var(--bf-success-bg)", color: "var(--bf-success)" },
  question: { Icon: CircleHelp,    bg: "var(--bf-warning-bg)", color: "var(--bf-warning)" },
  comment:  { Icon: MessageSquare, bg: "var(--bf-neutral-bg)", color: "var(--bf-neutral)" },
};

export function QueueBlock({ items }: { items: QueueItem[] }) {
  return (
    <Card>
      <CardHeader
        title="自分待ち"
        icon={<Inbox className="w-3.5 h-3.5" />}
        meta={`${items.length} 件`}
      />
      {items.map((q) => {
        const c = QUEUE_ICON[q.type];
        return (
          <button
            key={q.id}
            className="w-full text-left flex items-start gap-3 transition-colors"
            style={{
              padding: "12px var(--bf-space-5)",
              borderBottom: "1px solid var(--bf-divider)",
            }}
          >
            <div
              className="flex items-center justify-center flex-shrink-0"
              style={{
                width: 28, height: 28,
                borderRadius: "var(--bf-radius-md)",
                background: c.bg, color: c.color,
              }}
            >
              <c.Icon className="w-3.5 h-3.5" />
            </div>
            <div className="flex-1 min-w-0">
              <div style={{ fontSize: 13, fontWeight: 500, color: "var(--bf-text-1)" }}>
                {q.title}
              </div>
              <div style={{ fontSize: 11.5, color: "var(--bf-text-3)" }}>
                {q.source}
              </div>
            </div>
            <div style={{ fontSize: 11, color: "var(--bf-text-4)", flexShrink: 0 }}>
              {q.time}
            </div>
          </button>
        );
      })}
    </Card>
  );
}

/* ──────────────────────────────────────────────────
 *  進行中フェーズ
 * ────────────────────────────────────────────────── */

export type PhaseRow = {
  leaderId: LeaderId;
  leaderLabel: string;
  phaseName: string;
  step: string;
  percent: number;
  parallel?: boolean;
};

export function ActivePhasesBlock({ phases }: { phases: PhaseRow[] }) {
  return (
    <Card>
      <CardHeader
        title="進行中フェーズ"
        icon={<Activity className="w-3.5 h-3.5" />}
        meta={`${phases.length} 件並行`}
      />
      <div style={{ padding: "var(--bf-space-2) 0" }}>
        {phases.map((p, i) => (
          <div
            key={i}
            className="flex items-center gap-3"
            style={{
              padding: "10px var(--bf-space-5)",
              borderBottom: i < phases.length - 1 ? "1px solid var(--bf-divider)" : undefined,
            }}
          >
            <div
              className="flex items-center gap-1.5"
              style={{ minWidth: 110, fontSize: 11.5, fontWeight: 600, color: "var(--bf-text-2)" }}
            >
              <LeaderAvatar id={p.leaderId} size={18} />
              {p.leaderLabel}
            </div>
            <div className="flex-1" style={{ fontSize: 13, color: "var(--bf-text-1)", fontWeight: 500 }}>
              {p.phaseName}{" "}
              <span style={{ fontSize: 11.5, color: "var(--bf-text-3)", fontWeight: 400 }}>
                / {p.step}
              </span>
            </div>
            <div
              style={{
                width: 60, height: 4,
                background: "var(--bf-border)",
                borderRadius: 999, overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${p.percent}%`,
                  background: "var(--bf-primary)",
                }}
              />
            </div>
            <Badge tone={p.parallel ? "parallel" : "recommend"}>{p.percent}%</Badge>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ──────────────────────────────────────────────────
 *  KPI
 * ────────────────────────────────────────────────── */

export function KpiBlock({
  taskDone, taskTotal, blockers, daysLeft, budgetPercent,
}: {
  taskDone: number; taskTotal: number;
  blockers: number; daysLeft?: number; budgetPercent?: number;
}) {
  return (
    <Card>
      <CardHeader title="KPI" icon={<BarChart3 className="w-3.5 h-3.5" />} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, background: "var(--bf-divider)" }}>
        <KpiCell icon={<CheckCircle2 className="w-3.5 h-3.5" />} label="タスク完了" value={taskDone} unit={`/ ${taskTotal}`} />
        <KpiCell icon={<AlertOctagon className="w-3.5 h-3.5" />} label="ブロッカー"  value={blockers} unit="件" />
        <KpiCell icon={<Clock className="w-3.5 h-3.5" />}        label="残日数"     value={daysLeft ?? "—"} unit="日" />
        <KpiCell icon={<Wallet className="w-3.5 h-3.5" />}       label="予算消化"   value={budgetPercent ?? "—"} unit="%" />
      </div>
    </Card>
  );
}

function KpiCell({
  icon, label, value, unit,
}: {
  icon: React.ReactNode; label: string;
  value: number | string; unit?: string;
}) {
  return (
    <div
      style={{
        padding: "var(--bf-space-4) var(--bf-space-5)",
        background: "var(--bf-bg-elev)",
      }}
    >
      <div
        className="flex items-center gap-1"
        style={{
          fontSize: 11, color: "var(--bf-text-3)",
          textTransform: "uppercase", letterSpacing: "0.05em",
          marginBottom: 6,
        }}
      >
        {icon}
        {label}
      </div>
      <div
        style={{
          fontSize: 20, fontWeight: 700, letterSpacing: "-0.02em",
          color: "var(--bf-text-1)",
        }}
      >
        {value}
        {unit && <span style={{ fontSize: 12, color: "var(--bf-text-3)", fontWeight: 500, marginLeft: 3 }}>{unit}</span>}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────
 *  最新成果物
 * ────────────────────────────────────────────────── */

export type ArtifactRow = {
  id: string | number;
  type: "doc" | "design" | "arch" | "code";
  title: string;
  version: string;
  meta: string;
};

const ART_ICON = {
  doc: FileText, design: Palette, arch: Layers, code: FileText,
};

export function ArtifactsBlock({ artifacts }: { artifacts: ArtifactRow[] }) {
  return (
    <Card>
      <CardHeader
        title="最新の成果物"
        icon={<FolderOpen className="w-3.5 h-3.5" />}
        meta={
          <a
            href="#"
            className="flex items-center gap-1 transition-colors"
            style={{ color: "var(--bf-primary)", fontSize: 12, fontWeight: 600 }}
          >
            全て <ArrowRight className="w-3.5 h-3.5" />
          </a>
        }
      />
      <div style={{ padding: "var(--bf-space-2) 0" }}>
        {artifacts.map((a, i) => {
          const Icon = ART_ICON[a.type];
          return (
            <button
              key={a.id}
              className="w-full text-left flex items-center gap-3 transition-colors"
              style={{
                padding: "10px var(--bf-space-5)",
                borderBottom: i < artifacts.length - 1 ? "1px solid var(--bf-divider)" : undefined,
              }}
            >
              <div
                className="flex items-center justify-center"
                style={{
                  width: 32, height: 32,
                  background: "var(--bf-bg-soft)",
                  border: "1px solid var(--bf-border)",
                  borderRadius: "var(--bf-radius-md)",
                  color: "var(--bf-text-2)",
                  flexShrink: 0,
                }}
              >
                <Icon className="w-3.5 h-3.5" />
              </div>
              <div className="flex-1 min-w-0">
                <div style={{ fontSize: 13, fontWeight: 500, color: "var(--bf-text-1)" }}>
                  {a.title}
                </div>
                <div className="flex items-center gap-1.5" style={{ fontSize: 11.5, color: "var(--bf-text-3)" }}>
                  <span
                    style={{
                      fontFamily: "Inter, monospace",
                      fontSize: 10.5,
                      background: "var(--bf-bg-soft)",
                      border: "1px solid var(--bf-border)",
                      borderRadius: 4,
                      padding: "1px 5px",
                      color: "var(--bf-text-3)",
                    }}
                  >
                    {a.version}
                  </span>
                  <span>{a.meta}</span>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </Card>
  );
}

/* ──────────────────────────────────────────────────
 *  最近の動き
 * ────────────────────────────────────────────────── */

export type ActivityItem = {
  id: string | number;
  time: string;
  text: React.ReactNode;
};

export function ActivityBlock({ items }: { items: ActivityItem[] }) {
  return (
    <Card>
      <CardHeader
        title="最近の動き"
        icon={<History className="w-3.5 h-3.5" />}
        meta={
          <a
            href="#"
            className="flex items-center gap-1"
            style={{ color: "var(--bf-primary)", fontSize: 12, fontWeight: 600 }}
          >
            全件 <ArrowRight className="w-3.5 h-3.5" />
          </a>
        }
      />
      <div style={{ padding: "var(--bf-space-2) 0" }}>
        {items.map((a, i) => (
          <div
            key={a.id}
            className="flex gap-3"
            style={{
              padding: "10px var(--bf-space-5)",
              borderBottom: i < items.length - 1 ? "1px solid var(--bf-divider)" : undefined,
              fontSize: 12.5,
            }}
          >
            <div
              style={{
                fontSize: 11, color: "var(--bf-text-4)",
                width: 60, flexShrink: 0, paddingTop: 1,
              }}
            >
              {a.time}
            </div>
            <div style={{ flex: 1, color: "var(--bf-text-2)" }}>{a.text}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ──────────────────────────────────────────────────
 *  Members presence
 * ────────────────────────────────────────────────── */

export function MembersBlock({
  online, offline,
}: { online: { name: string; role: string; avatar: string; bg?: string }[]; offline?: { name: string; lastSeen: string }[] }) {
  return (
    <Card>
      <CardHeader
        title="メンバー"
        icon={<Users className="w-3.5 h-3.5" />}
      />
      <div style={{ padding: "14px var(--bf-space-5)" }}>
        <div className="flex items-center gap-2" style={{ marginBottom: 14 }}>
          {online.map((m, i) => (
            <div
              key={i}
              title={`${m.name} (${m.role})`}
              style={{
                width: 26, height: 26,
                borderRadius: "50%",
                border: "2px solid #fff",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 10, fontWeight: 700,
                color: "#fff",
                background: m.bg ?? "var(--bf-leader-pm)",
                marginLeft: i === 0 ? 0 : -6,
                position: "relative",
              }}
            >
              {m.avatar}
              <span
                style={{
                  position: "absolute", bottom: -1, right: -1,
                  width: 7, height: 7, background: "var(--bf-success)",
                  border: "1.5px solid #fff", borderRadius: "50%",
                }}
              />
            </div>
          ))}
        </div>
        <div style={{ fontSize: 12, color: "var(--bf-text-3)", display: "flex", flexDirection: "column", gap: 6 }}>
          {online.map((m, i) => (
            <div key={i} className="flex justify-between">
              <span>{m.name} ({m.role})</span>
              <span style={{ color: "var(--bf-success)" }}>オンライン</span>
            </div>
          ))}
          {offline?.map((m, i) => (
            <div key={`o-${i}`} className="flex justify-between">
              <span>{m.name}</span>
              <span>{m.lastSeen}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

/* ──────────────────────────────────────────────────
 *  小コンポーネント
 * ────────────────────────────────────────────────── */

function LeaderTag({
  leaderId, label,
}: { leaderId: LeaderId; label: string }) {
  const colorVar = `var(--bf-leader-${leaderId})`;
  return (
    <span
      className="inline-flex items-center gap-1"
      style={{
        padding: "1px 7px",
        borderRadius: 999,
        fontSize: 11, fontWeight: 600,
        color: "#fff",
        background: colorVar,
      }}
    >
      {label}
    </span>
  );
}

function Badge({
  tone, children,
}: {
  tone: "recommend" | "parallel" | "warn" | "success" | "danger" | "neutral";
  children: React.ReactNode;
}) {
  const map = {
    recommend: { bg: "var(--bf-primary-bg)", color: "var(--bf-primary)" },
    parallel:  { bg: "var(--bf-info-bg)",    color: "var(--bf-info)" },
    warn:      { bg: "var(--bf-warning-bg)", color: "var(--bf-warning)" },
    success:   { bg: "var(--bf-success-bg)", color: "var(--bf-success)" },
    danger:    { bg: "var(--bf-danger-bg)",  color: "var(--bf-danger)" },
    neutral:   { bg: "var(--bf-neutral-bg)", color: "var(--bf-neutral)" },
  };
  const c = map[tone];
  return (
    <span
      className="inline-flex items-center gap-1"
      style={{
        padding: "1px 7px",
        borderRadius: 999,
        fontSize: 11, fontWeight: 600,
        background: c.bg, color: c.color,
      }}
    >
      {children}
    </span>
  );
}

function Button({
  variant = "primary", size = "md", icon, children,
}: {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  const variantStyles = {
    primary:   { background: "var(--bf-primary)",   color: "#fff", border: "1px solid transparent" },
    secondary: { background: "var(--bf-bg-elev)",   color: "var(--bf-text-1)", border: "1px solid var(--bf-border)" },
    ghost:     { background: "transparent",         color: "var(--bf-text-2)", border: "1px solid transparent" },
  };
  const sizeStyles = {
    sm: { height: 28, padding: "0 10px", fontSize: 12 },
    md: { height: 34, padding: "0 14px", fontSize: 13 },
  };
  return (
    <button
      className="inline-flex items-center gap-1.5 transition-colors"
      style={{
        ...variantStyles[variant],
        ...sizeStyles[size],
        borderRadius: "var(--bf-radius-md)",
        fontWeight: 600,
        lineHeight: 1,
      }}
    >
      {icon}
      {children}
    </button>
  );
}
