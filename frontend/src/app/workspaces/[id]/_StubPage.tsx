"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Workspace, fetchWorkspace } from "@/lib/workspaces";
import { WorkspaceShell } from "@/components/workspace-shell";
import type { SidebarKey } from "@/components/workspace-shell";

interface Props {
  active: SidebarKey;
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}

/**
 * ワークスペース内ページ用 Stub。実装中の画面でもナビゲーション・シェルを保証する。
 */
export function WorkspaceStubPage({ active, title, subtitle, children }: Props) {
  const params = useParams();
  const id = Number(params?.id);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchWorkspace(id).then(setWorkspace).catch(() => setWorkspace(null));
  }, [id]);

  if (!workspace) {
    return (
      <div className="p-6" style={{ color: "var(--bf-text-3)" }}>読み込み中…</div>
    );
  }

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      progressPercent={45}
      daysLeft={23}
      active={active}
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: title },
      ]}
    >
      <div style={{ marginBottom: "var(--bf-space-6)" }}>
        <h1
          style={{
            fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em",
            color: "var(--bf-text-1)", marginBottom: 4,
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>{subtitle}</div>
        )}
      </div>

      {children ?? (
        <div
          style={{
            background: "var(--bf-bg-elev)",
            border: "1px dashed var(--bf-border)",
            borderRadius: "var(--bf-radius-lg)",
            padding: "var(--bf-space-12) var(--bf-space-6)",
            textAlign: "center",
            color: "var(--bf-text-3)",
            fontSize: 13,
          }}
        >
          この画面は実装中です。
          <div style={{ marginTop: 6, fontSize: 12, color: "var(--bf-text-4)" }}>
            モック原本: <code>frontend/public/mock/{active}.html</code>
          </div>
        </div>
      )}
    </WorkspaceShell>
  );
}
