"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowLeft, Building2, LayoutDashboard, TrendingUp, CheckSquare,
  Calendar, FileText, BellRing, Users, Share2, Settings,
  ChevronRight, ChevronDown,
} from "lucide-react";
import type { LeaderId, SidebarKey } from "./types";
import { LEADERS } from "./types";
import { LeaderAvatar } from "./LeaderAvatar";

interface Props {
  workspaceId: number;
  workspaceName: string;
  clientName?: string;
  progressPercent?: number;
  daysLeft?: number;
  active?: SidebarKey;
  expandedLeader?: LeaderId | null;
}

const PROJECT_ITEMS: { key: SidebarKey; label: string; icon: any; badge?: string; alert?: boolean }[] = [
  { key: "home",     label: "ホーム",          icon: LayoutDashboard },
  { key: "progress", label: "進捗管理",        icon: TrendingUp },
  { key: "tasks",    label: "タスク管理",      icon: CheckSquare,  badge: "12" },
  { key: "schedule", label: "スケジュール",    icon: Calendar },
  { key: "minutes",  label: "議事録",          icon: FileText },
  { key: "alerts",   label: "アラート / 質問", icon: BellRing,     badge: "5", alert: true },
];

const ADMIN_ITEMS: { key: SidebarKey; label: string; icon: any }[] = [
  { key: "members",  label: "メンバー / 権限", icon: Users },
  { key: "share",    label: "共有設定",        icon: Share2 },
  { key: "settings", label: "プロジェクト設定", icon: Settings },
];

export function WorkspaceSidebar({
  workspaceId, workspaceName, clientName, progressPercent = 0, daysLeft,
  active, expandedLeader = null,
}: Props) {
  const pathname = usePathname();
  const base = `/workspaces/${workspaceId}`;

  const itemHref = (key: SidebarKey): string => {
    switch (key) {
      case "home":     return base;
      case "progress": return `${base}/progress`;
      case "tasks":    return `${base}/tasks`;
      case "schedule": return `${base}/schedule`;
      case "minutes":  return `${base}/minutes`;
      case "alerts":   return `${base}/alerts`;
      case "members":  return `${base}/members`;
      case "share":    return `${base}/share`;
      case "settings": return `${base}/settings`;
      default:         return `${base}/leader/${key}`;
    }
  };

  const isActive = (key: SidebarKey): boolean => {
    if (active) return active === key;
    const href = itemHref(key);
    if (key === "home") return pathname === base;
    return pathname?.startsWith(href) ?? false;
  };

  return (
    <aside
      className="flex flex-col overflow-y-auto"
      style={{
        width: "var(--bf-sidebar-w)",
        background: "var(--bf-bg-app)",
        borderRight: "1px solid var(--bf-border)",
        padding: "var(--bf-space-3) 0 var(--bf-space-6)",
        height: "100%",
      }}
    >
      <Link
        href="/workspaces"
        className="flex items-center gap-2 transition-colors"
        style={{
          padding: "6px var(--bf-space-4)",
          color: "var(--bf-text-3)",
          fontSize: 12,
          borderRadius: "var(--bf-radius-md)",
          margin: "0 var(--bf-space-3) var(--bf-space-3)",
        }}
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        Workspaces 一覧へ
      </Link>

      {/* プロジェクトカード */}
      <div
        style={{
          padding: "var(--bf-space-3) var(--bf-space-4)",
          margin: "0 var(--bf-space-3) var(--bf-space-2)",
          background: "var(--bf-bg-elev)",
          border: "1px solid var(--bf-border)",
          borderRadius: "var(--bf-radius-md)",
        }}
      >
        <div
          className="truncate"
          style={{ fontWeight: 600, fontSize: 13, color: "var(--bf-text-1)" }}
        >
          {workspaceName}
        </div>
        {clientName && (
          <div
            className="flex items-center gap-2 mt-1.5"
            style={{ fontSize: 11, color: "var(--bf-text-3)" }}
          >
            <Building2 className="w-3.5 h-3.5" />
            {clientName}
          </div>
        )}
        <div
          style={{
            marginTop: 8, height: 4,
            background: "var(--bf-border)",
            borderRadius: 999, overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${Math.min(100, Math.max(0, progressPercent))}%`,
              background: "var(--bf-primary)",
            }}
          />
        </div>
        <div
          className="flex items-center justify-between"
          style={{ fontSize: 11, color: "var(--bf-text-3)", marginTop: 6 }}
        >
          <span>進捗 {progressPercent}%</span>
          {daysLeft != null && <span>残 {daysLeft} 日</span>}
        </div>
      </div>

      <SectionTitle>プロジェクト管理</SectionTitle>
      {PROJECT_ITEMS.map((it) => (
        <SidebarLink
          key={it.key}
          href={itemHref(it.key)}
          active={isActive(it.key)}
          icon={<it.icon className="w-4 h-4" />}
          label={it.label}
          badge={it.badge}
          alert={it.alert}
        />
      ))}

      <SectionTitle>開発フロー</SectionTitle>
      {LEADERS.map((leader) => {
        const expanded = expandedLeader === leader.id || isActive(leader.id);
        return (
          <div key={leader.id}>
            <SidebarLeaderLink
              href={itemHref(leader.id)}
              active={isActive(leader.id)}
              expanded={expanded}
              leaderId={leader.id}
              label={leader.label}
              hasPhases={leader.phases.length > 0}
            />
            {expanded && leader.phases.length > 0 && (
              <div style={{ padding: "2px 0 4px 36px" }}>
                {leader.phases.map((p) => (
                  <Link
                    key={p.id}
                    href={`${base}/leader/${leader.id}/${p.id}`}
                    className="flex items-center justify-between transition-colors"
                    style={{
                      padding: "5px 12px",
                      margin: "1px 12px 1px 0",
                      borderRadius: "var(--bf-radius-md)",
                      fontSize: 12.5,
                      color: "var(--bf-text-3)",
                    }}
                  >
                    <span>{p.label}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        );
      })}

      <SectionTitle>管理</SectionTitle>
      {ADMIN_ITEMS.map((it) => (
        <SidebarLink
          key={it.key}
          href={itemHref(it.key)}
          active={isActive(it.key)}
          icon={<it.icon className="w-4 h-4" />}
          label={it.label}
        />
      ))}
    </aside>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        margin: "var(--bf-space-5) var(--bf-space-5) var(--bf-space-2)",
        fontSize: 10.5,
        fontWeight: 700,
        letterSpacing: "0.08em",
        color: "var(--bf-text-4)",
        textTransform: "uppercase",
      }}
    >
      {children}
    </div>
  );
}

function SidebarLink({
  href, active, icon, label, badge, alert,
}: {
  href: string; active: boolean;
  icon: React.ReactNode; label: string;
  badge?: string; alert?: boolean;
}) {
  return (
    <Link
      href={href}
      className="relative flex items-center gap-2.5 transition-colors"
      style={{
        padding: "7px var(--bf-space-4)",
        margin: "1px var(--bf-space-3)",
        borderRadius: "var(--bf-radius-md)",
        background: active ? "var(--bf-primary-bg)" : "transparent",
        color: active ? "var(--bf-primary)" : "var(--bf-text-2)",
        fontSize: 13,
        fontWeight: active ? 600 : 500,
      }}
    >
      {active && (
        <span
          aria-hidden
          style={{
            position: "absolute", left: -12, top: 6, bottom: 6, width: 3,
            background: "var(--bf-primary)",
            borderRadius: "0 2px 2px 0",
          }}
        />
      )}
      {icon}
      <span className="flex-1">{label}</span>
      {badge && (
        <span
          style={{
            fontSize: 10.5,
            fontWeight: 600,
            padding: "1px 6px",
            borderRadius: 999,
            background: alert ? "var(--bf-danger-bg)" : "var(--bf-bg-elev)",
            color:      alert ? "var(--bf-danger)"    : "var(--bf-text-3)",
            border:     alert ? "none" : "1px solid var(--bf-border)",
          }}
        >
          {badge}
        </span>
      )}
    </Link>
  );
}

function SidebarLeaderLink({
  href, active, expanded, leaderId, label, hasPhases,
}: {
  href: string; active: boolean; expanded: boolean;
  leaderId: LeaderId; label: string; hasPhases: boolean;
}) {
  return (
    <Link
      href={href}
      className="relative flex items-center gap-2.5 transition-colors"
      style={{
        padding: "8px var(--bf-space-4)",
        margin: "1px var(--bf-space-3)",
        borderRadius: "var(--bf-radius-md)",
        background: active ? "var(--bf-primary-bg)" : "transparent",
        color: active ? "var(--bf-primary)" : "var(--bf-text-2)",
        fontSize: 13,
        fontWeight: active ? 600 : 500,
      }}
    >
      {active && (
        <span
          aria-hidden
          style={{
            position: "absolute", left: -12, top: 6, bottom: 6, width: 3,
            background: "var(--bf-primary)",
            borderRadius: "0 2px 2px 0",
          }}
        />
      )}
      <LeaderAvatar id={leaderId} size={22} />
      <span className="flex-1">{label}</span>
      {hasPhases && (
        expanded
          ? <ChevronDown className="w-3.5 h-3.5" style={{ color: "var(--bf-text-4)" }} />
          : <ChevronRight className="w-3.5 h-3.5" style={{ color: "var(--bf-text-4)" }} />
      )}
    </Link>
  );
}
