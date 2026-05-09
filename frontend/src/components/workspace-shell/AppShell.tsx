"use client";

import { WorkspaceHeader } from "./Header";
import { WorkspaceSidebar } from "./Sidebar";
import type { LeaderId, SidebarKey } from "./types";

interface Props {
  workspaceId: number;
  workspaceName: string;
  clientName?: string;
  progressPercent?: number;
  daysLeft?: number;
  active?: SidebarKey;
  expandedLeader?: LeaderId | null;
  breadcrumbs?: { label: string; href?: string }[];
  children: React.ReactNode;
}

/**
 * Workspace 内 IA の共通シェル。3 ペイン (Header + Sidebar + Main)。
 * 詳細: Build-Factory/docs/DESIGN-SYSTEM.md (Calm Industrial)
 */
export function WorkspaceShell({
  workspaceId, workspaceName, clientName,
  progressPercent = 0, daysLeft, active, expandedLeader,
  breadcrumbs, children,
}: Props) {
  const crumbs = breadcrumbs ?? [
    { label: "Workspaces", href: "/workspaces" },
    { label: workspaceName, href: `/workspaces/${workspaceId}` },
  ];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "var(--bf-sidebar-w) 1fr",
        gridTemplateRows: "var(--bf-header-h) 1fr",
        gridTemplateAreas: '"header header" "sidebar main"',
        height: "100vh",
        background: "var(--bf-bg-app)",
      }}
    >
      <div style={{ gridArea: "header" }}>
        <WorkspaceHeader breadcrumbs={crumbs} />
      </div>
      <div style={{ gridArea: "sidebar", overflow: "hidden" }}>
        <WorkspaceSidebar
          workspaceId={workspaceId}
          workspaceName={workspaceName}
          clientName={clientName}
          progressPercent={progressPercent}
          daysLeft={daysLeft}
          active={active}
          expandedLeader={expandedLeader}
        />
      </div>
      <main
        style={{
          gridArea: "main",
          overflowY: "auto",
          padding: "var(--bf-space-8) var(--bf-space-10)",
        }}
      >
        {children}
      </main>
    </div>
  );
}
