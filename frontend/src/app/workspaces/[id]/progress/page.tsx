"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Workspace, fetchWorkspace, fetchWorkspaceTasks,
  type WorkspaceTask,
} from "@/lib/workspaces";
import { listWorkspaceArtifacts, type Artifact } from "@/lib/artifacts-api";
import { WorkspaceShell, LeaderAvatar } from "@/components/workspace-shell";
import type { LeaderId } from "@/components/workspace-shell";
import { Card, CardHeader } from "@/components/workspace-shell/HomeBlocks";
import {
  GitBranch, BarChartHorizontal, FolderTree, Filter, Download,
  CheckCircle2, Loader2, Circle, CircleDot, Lock, ExternalLink, ChevronRight,
} from "lucide-react";

type NodeStatus = "done" | "in-progress" | "pending" | "locked";

const SKILL_TO_LEADER: Record<string, LeaderId> = {
  "feature": "pm",  // 親タスクのデフォルト (skill_name に明記がない場合の暫定)
  "hearing": "pm",
  "requirements-definition": "pm",
  "proposal": "pm",
  "estimate": "pm",
  "acceptance-criteria": "pm",
  "meeting-minutes": "pm",
  "architecture-design": "arch",
  "tech-stack": "arch",
  "api-design": "arch",
  "feature-decomposition": "arch",
  "task-decomposition": "arch",
  "deployment-patterns": "arch",
  "design-md": "design",
  "ui-mockup": "design",
  "frontend-design": "design",
  "distributed-dev": "eng",
  "integration": "eng",
  "test-verification": "qa",
  "code-review": "qa",
  "e2e-testing": "qa",
  "release-planning": "ops",
  "delivery": "ops",
  "operations": "ops",
  "documentation": "ops",
};

const LEADER_LABEL: Record<LeaderId, string> = {
  secretary: "秘書 ライン",
  pm: "PM ライン",
  arch: "設計 ライン",
  design: "デザイン ライン",
  eng: "エンジニア",
  qa: "品質 ライン",
  ops: "DevOps",
};

function leaderForSkill(skill: string | null | undefined): LeaderId {
  if (!skill) return "pm";
  return SKILL_TO_LEADER[skill] ?? "pm";
}

function statusToNode(s: string, locked = false): NodeStatus {
  if (locked) return "locked";
  if (s === "completed") return "done";
  if (s === "in_progress") return "in-progress";
  return "pending";
}

function relativeTime(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "今";
  if (diffMin < 60) return `${diffMin}分前`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}時間前`;
  const diffD = Math.floor(diffH / 24);
  return `${diffD}日前`;
}

export default function ProgressPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchWorkspace(id).then(setWorkspace).catch(() => setWorkspace(null));
  }, [id]);

  const { data: taskData } = useQuery({
    queryKey: ["workspace-tasks", id],
    queryFn: () => fetchWorkspaceTasks(id),
    enabled: !!id,
    refetchInterval: 5000,
  });
  const tasks = taskData?.tasks ?? [];

  const { data: artifacts = [] } = useQuery<Artifact[]>({
    queryKey: ["workspace-artifacts", id],
    queryFn: () => listWorkspaceArtifacts(id, { limit: 50 }),
    enabled: !!id,
    refetchInterval: 10000,
  });

  // ── DAG: 親タスク (level=0 / skill=feature) を行ごとに leader 別グループ化 ──
  const dagRows = useMemo(() => {
    const rootTasks = tasks.filter((t) => !t.parent_task_id);
    // leader → root tasks にグループ化
    const grouped = new Map<LeaderId, WorkspaceTask[]>();
    for (const r of rootTasks) {
      const leaderId = leaderForSkill(r.skill_name);
      if (!grouped.has(leaderId)) grouped.set(leaderId, []);
      grouped.get(leaderId)!.push(r);
    }
    return Array.from(grouped.entries()).map(([leaderId, roots]) => ({
      leaderId,
      leaderLabel: LEADER_LABEL[leaderId],
      nodes: roots.map((root) => {
        const children = tasks.filter((t) => t.parent_task_id === root.id);
        const total = children.length;
        const done = children.filter((c) => c.status === "completed").length;
        const inProg = children.filter((c) => c.status === "in_progress").length;
        let nodeStatus: NodeStatus = statusToNode(root.status);
        if (total > 0) {
          if (done === total) nodeStatus = "done";
          else if (inProg > 0 || done > 0) nodeStatus = "in-progress";
          else nodeStatus = "pending";
        }
        const meta = total > 0
          ? `${done} / ${total} 完了${inProg > 0 ? ` ・ 進行中 ${inProg}` : ""}`
          : (root.status === "completed" ? relativeTime(root.created_at) : root.status);
        return { id: String(root.id), label: root.title, status: nodeStatus, meta };
      }),
    }));
  }, [tasks]);

  // ── ガント: 親タスクごとに 1 バー描画 ──
  // 期間: 全 task の started_at の最古〜今日+30日 を範囲として%計算
  const gantt = useMemo(() => {
    const allWithStart = tasks
      .map((t) => (t.created_at ? new Date(t.created_at).getTime() : null))
      .filter((v): v is number => v !== null);
    const minTs = allWithStart.length > 0 ? Math.min(...allWithStart) : Date.now() - 14 * 86400_000;
    const maxTs = Math.max(Date.now() + 14 * 86400_000, ...allWithStart);
    const totalSpan = maxTs - minTs;

    const todayPercent = ((Date.now() - minTs) / totalSpan) * 100;

    const rootTasks = tasks.filter((t) => !t.parent_task_id);
    const bars = rootTasks.map((root) => {
      const children = tasks.filter((t) => t.parent_task_id === root.id);
      const all = children.length > 0 ? children : [root];
      const starts = all.map((t) => t.created_at ? new Date(t.created_at).getTime() : minTs);
      const ends = all.map((t) => {
        if (t.status === "completed") return Date.now();
        return Math.min(Date.now() + 14 * 86400_000, minTs + totalSpan);
      });
      const start = Math.min(...starts);
      const end = Math.max(...ends);
      const startPct = ((start - minTs) / totalSpan) * 100;
      const widthPct = Math.max(2, ((end - start) / totalSpan) * 100);
      const total = children.length || 1;
      const done = children.filter((c) => c.status === "completed").length;
      const percent = total > 0 ? Math.round((done / total) * 100) : 0;

      let status: "done" | "in-progress" | "planned" = "planned";
      if (percent === 100) status = "done";
      else if (children.some((c) => c.status === "in_progress" || c.status === "completed")) status = "in-progress";

      return {
        leaderId: leaderForSkill(root.skill_name),
        label: root.title,
        start: startPct,
        width: widthPct,
        status,
        percent,
      };
    });

    // 期間ラベル (週ごと)
    const labels: { label: string; pct: number }[] = [];
    const weekMs = 7 * 86400_000;
    const start = new Date(minTs);
    start.setHours(0, 0, 0, 0);
    let cursor = start.getTime();
    while (cursor < maxTs) {
      const d = new Date(cursor);
      labels.push({
        label: `${d.getMonth() + 1}/${d.getDate()}`,
        pct: ((cursor - minTs) / totalSpan) * 100,
      });
      cursor += weekMs;
    }

    return { bars, todayPercent, labels };
  }, [tasks]);

  if (!workspace) return <div className="p-6" style={{ color: "var(--bf-text-3)" }}>読み込み中…</div>;

  const totalRoots = tasks.filter((t) => !t.parent_task_id).length;
  const completedRoots = tasks.filter((t) => !t.parent_task_id && t.status === "completed").length;
  const inProgressRoots = tasks.filter((t) => !t.parent_task_id && t.status === "in_progress").length;

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      progressPercent={totalRoots > 0 ? Math.round((completedRoots / totalRoots) * 100) : 0}
      daysLeft={23}
      active="progress"
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: "進捗管理" },
      ]}
    >
      <div style={{ marginBottom: "var(--bf-space-6)" }}>
        <div className="flex items-start gap-6 flex-wrap">
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--bf-text-1)", marginBottom: 4 }}>
              進捗管理
            </h1>
            <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>
              DAG ビジュアル + ガントチャート + フェーズ毎の成果物履歴 (実データ)
            </div>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <SecondaryButton icon={<Filter className="w-3.5 h-3.5" />}>フィルタ</SecondaryButton>
            <SecondaryButton icon={<Download className="w-3.5 h-3.5" />}>エクスポート</SecondaryButton>
          </div>
        </div>
      </div>

      <Card className="mb-5">
        <CardHeader
          title="フェーズ DAG"
          icon={<GitBranch className="w-3.5 h-3.5" />}
          meta={`完了 ${completedRoots} / 進行中 ${inProgressRoots} / 全 ${totalRoots} 機能`}
        />
        <div style={{ padding: "var(--bf-space-6)", overflowX: "auto" }}>
          {dagRows.length === 0 ? (
            <div style={{ textAlign: "center", color: "var(--bf-text-3)", fontSize: 13, padding: "var(--bf-space-8) 0" }}>
              タスクがまだありません。秘書チャットで依頼すると自動分解されます。
            </div>
          ) : dagRows.map((row) => (
            <div key={row.leaderId} className="flex items-center gap-3" style={{ marginBottom: "var(--bf-space-4)", minWidth: 1200 }}>
              <div className="flex items-center gap-1.5 flex-shrink-0" style={{ width: 110, fontSize: 11.5, fontWeight: 600, color: "var(--bf-text-2)" }}>
                <LeaderAvatar id={row.leaderId} size={18} />
                {row.leaderLabel}
              </div>
              <div className="flex items-center gap-2 flex-1 flex-wrap">
                {row.nodes.map((node, i) => (
                  <div key={node.id} className="flex items-center gap-2">
                    <DagNodeCard node={node} />
                    {i < row.nodes.length - 1 && (
                      <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" style={{ color: "var(--bf-text-4)" }} />
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="mb-5">
        <CardHeader title="ガントチャート" icon={<BarChartHorizontal className="w-3.5 h-3.5" />} meta="created_at / completed_at から自動算出" />
        <GanttHeaderRow labels={gantt.labels} />
        {gantt.bars.length === 0 ? (
          <div style={{ padding: "var(--bf-space-8)", textAlign: "center", color: "var(--bf-text-3)", fontSize: 13 }}>
            親タスクがまだありません
          </div>
        ) : gantt.bars.map((bar, i) => (
          <GanttRowItem key={i} bar={bar} todayPercent={gantt.todayPercent} />
        ))}
      </Card>

      <Card>
        <CardHeader
          title="フェーズ別 成果物履歴"
          icon={<FolderTree className="w-3.5 h-3.5" />}
          meta={`${artifacts.length} 件`}
        />
        <div style={{ overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["タイプ", "タイトル", "カテゴリ", "最終更新", ""].map((h, i) => (
                  <th key={i} style={{ textAlign: "left", fontSize: 11.5, fontWeight: 600, color: "var(--bf-text-3)", textTransform: "uppercase", letterSpacing: "0.04em", padding: "10px var(--bf-space-5)", borderBottom: "1px solid var(--bf-border)", background: "var(--bf-bg-soft)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {artifacts.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ ...tdBase, textAlign: "center", color: "var(--bf-text-3)" }}>
                    まだ成果物がありません
                  </td>
                </tr>
              ) : artifacts.map((a) => (
                <tr key={a.id}>
                  <td style={tdBase}><code style={codeStyle}>{a.type}</code></td>
                  <td style={tdBase}>{a.title || "(無題)"}</td>
                  <td style={{ ...tdBase, fontSize: 11.5, color: "var(--bf-text-3)" }}>
                    {(a.category_tags ?? []).join(" / ")}
                  </td>
                  <td style={{ ...tdBase, fontSize: 12, color: "var(--bf-text-3)" }}>
                    {relativeTime(a.updated_at)}
                  </td>
                  <td style={tdBase}><ExternalLink className="w-3.5 h-3.5" style={{ color: "var(--bf-text-4)" }} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </WorkspaceShell>
  );
}

const tdBase: React.CSSProperties = { padding: "12px var(--bf-space-5)", borderBottom: "1px solid var(--bf-divider)", fontSize: 13, color: "var(--bf-text-1)" };
const codeStyle: React.CSSProperties = { fontFamily: "Inter, monospace", fontSize: 10.5, background: "var(--bf-bg-soft)", border: "1px solid var(--bf-border)", borderRadius: 4, padding: "1px 5px", color: "var(--bf-text-3)" };

function DagNodeCard({ node }: { node: { id: string; label: string; status: NodeStatus; meta?: string } }) {
  const styleByStatus: Record<NodeStatus, React.CSSProperties> = {
    "done":        { background: "var(--bf-success-bg)", borderColor: "var(--bf-success)", color: "var(--bf-success)" },
    "in-progress": { background: "var(--bf-primary-bg)", borderColor: "var(--bf-primary)", color: "var(--bf-primary)" },
    "pending":     { background: "var(--bf-bg-elev)",    borderColor: "var(--bf-border)",  color: "var(--bf-text-2)" },
    "locked":      { background: "var(--bf-bg-elev)",    borderColor: "var(--bf-border)",  color: "var(--bf-text-2)", opacity: 0.45 },
  };
  const Icon = node.status === "done" ? CheckCircle2 : node.status === "in-progress" ? Loader2 : node.status === "locked" ? Lock : node.status === "pending" ? CircleDot : Circle;

  return (
    <div className="flex-shrink-0" style={{ minWidth: 130, padding: "10px 12px", border: "1.5px solid", borderRadius: "var(--bf-radius-md)", cursor: "pointer", ...styleByStatus[node.status] }}>
      <div style={{ fontWeight: 600, fontSize: 12.5 }}>{node.label}</div>
      {node.meta && (
        <div className="flex items-center gap-1" style={{ marginTop: 4, fontSize: 10.5, opacity: 0.8 }}>
          <Icon className={`w-3 h-3 ${node.status === "in-progress" ? "animate-spin" : ""}`} />
          {node.meta}
        </div>
      )}
    </div>
  );
}

function GanttHeaderRow({ labels }: { labels: { label: string; pct: number }[] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", background: "var(--bf-bg-soft)", borderBottom: "1px solid var(--bf-divider)" }}>
      <div style={{ padding: "12px var(--bf-space-5)", borderRight: "1px solid var(--bf-divider)", fontSize: 11, fontWeight: 600, color: "var(--bf-text-3)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
        フェーズ
      </div>
      <div style={{ position: "relative", height: 36 }}>
        {labels.map((l, i) => (
          <span key={i} style={{ position: "absolute", left: `${l.pct}%`, top: 12, fontSize: 10.5, fontWeight: 500, color: "var(--bf-text-3)", transform: "translateX(-50%)" }}>
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function GanttRowItem({ bar, todayPercent }: { bar: { leaderId: LeaderId; label: string; start: number; width: number; status: "done" | "in-progress" | "planned"; percent?: number }; todayPercent: number }) {
  const barColor: Record<"done" | "in-progress" | "planned", React.CSSProperties> = {
    done: { background: "var(--bf-success)", color: "#fff" },
    "in-progress": {
      background: "var(--bf-primary)", color: "#fff",
      backgroundImage: "linear-gradient(45deg, rgba(255,255,255,0.18) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.18) 50%, rgba(255,255,255,0.18) 75%, transparent 75%)",
      backgroundSize: "14px 14px",
    },
    planned: { background: "var(--bf-bg-soft)", border: "1.5px dashed var(--bf-border-strong)", color: "var(--bf-text-3)" },
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", borderBottom: "1px solid var(--bf-divider)" }}>
      <div className="flex items-center gap-2" style={{ padding: "12px var(--bf-space-5)", fontSize: 13, color: "var(--bf-text-1)", borderRight: "1px solid var(--bf-divider)", fontWeight: 500 }}>
        <LeaderAvatar id={bar.leaderId} size={18} />
        <span className="truncate">{bar.label}</span>
      </div>
      <div style={{ position: "relative", height: 44, padding: "12px 0" }}>
        <div style={{
          position: "absolute", top: 12, bottom: 12,
          left: `${bar.start}%`, width: `${bar.width}%`,
          borderRadius: 4, display: "flex", alignItems: "center",
          padding: "0 8px", fontSize: 11, fontWeight: 600,
          ...barColor[bar.status],
        }}>
          {bar.percent != null ? `${bar.percent}%` : "予定"}
        </div>
        <div style={{ position: "absolute", top: 0, bottom: 0, left: `${todayPercent}%`, width: 2, background: "var(--bf-danger)", pointerEvents: "none" }}>
          <span style={{ position: "absolute", top: -10, left: 4, background: "var(--bf-danger)", color: "#fff", fontSize: 9, fontWeight: 600, padding: "1px 5px", borderRadius: 3, whiteSpace: "nowrap" }}>
            今日
          </span>
        </div>
      </div>
    </div>
  );
}

function SecondaryButton({ icon, children }: { icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <button className="inline-flex items-center gap-1.5 transition-colors" style={{ height: 34, padding: "0 14px", background: "var(--bf-bg-elev)", color: "var(--bf-text-1)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600 }}>
      {icon}
      {children}
    </button>
  );
}
