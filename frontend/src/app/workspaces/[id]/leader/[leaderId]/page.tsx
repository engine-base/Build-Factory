"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Workspace, fetchWorkspace } from "@/lib/workspaces";
import { WorkspaceShell, LEADERS } from "@/components/workspace-shell";
import type { LeaderId } from "@/components/workspace-shell";

/**
 * リーダーラインのトップ。
 * 配下に最初のフェーズがある場合は自動で /[id]/leader/[leaderId]/[phaseId] へ遷移。
 * 配下フェーズがない (秘書) 場合のみライン情報トップを表示。
 */
export default function LeaderTopPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params?.id);
  const leaderId = params?.leaderId as LeaderId;
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const leader = LEADERS.find((l) => l.id === leaderId);

  useEffect(() => {
    if (!id) return;
    fetchWorkspace(id).then(setWorkspace).catch(() => setWorkspace(null));
  }, [id]);

  // 配下フェーズがあれば最初のフェーズへリダイレクト (UX 一直線化)
  useEffect(() => {
    if (!id || !leader) return;
    if (leader.phases.length > 0) {
      router.replace(`/workspaces/${id}/leader/${leaderId}/${leader.phases[0].id}`);
    }
  }, [id, leader, leaderId, router]);

  if (!workspace || !leader) {
    return <div className="p-6" style={{ color: "var(--bf-text-3)" }}>読み込み中…</div>;
  }

  // 秘書 AI など phases なしの場合のみここを表示
  if (leader.phases.length > 0) {
    return <div className="p-6" style={{ color: "var(--bf-text-3)" }}>フェーズに遷移中…</div>;
  }

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      progressPercent={45}
      daysLeft={23}
      active={leaderId}
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: `${leader.label} ライン` },
      ]}
    >
      <div style={{ marginBottom: "var(--bf-space-6)" }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--bf-text-1)", marginBottom: 4 }}>
          {leader.label}
        </h1>
        <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>
          全プロジェクト横断のハブ。各大分類リーダーへの委任を担当。
        </div>
      </div>
      <div style={{
        background: "var(--bf-bg-elev)",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-lg)",
        padding: "var(--bf-space-12) var(--bf-space-6)",
        textAlign: "center",
        color: "var(--bf-text-3)",
        fontSize: 13,
      }}>
        秘書チャットはアカウントレベル機能のため、サイドバー上部の「秘書チャット」から起動してください。
      </div>
    </WorkspaceShell>
  );
}
