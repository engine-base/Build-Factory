"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Workspace, fetchWorkspace, fetchWorkspaceTasks } from "@/lib/workspaces";
import { WorkspaceShell } from "@/components/workspace-shell";
import { TaskKanban, type Task, type GroupBy } from "@/components/tasks/TaskKanban";
import { TaskDetailDrawer } from "@/components/tasks/TaskDetailDrawer";
import { Plus, Filter } from "lucide-react";

const API = "http://localhost:8001";

/**
 * ワークスペース内タスク管理画面 — 機能/画面別 Kanban + 詳細 Drawer + MCP 引き継ぎ
 * デザイン: Calm Industrial (Build-Factory/docs/DESIGN-SYSTEM.md)
 * データ: /api/workspaces/{id}/tasks 経由 (workspace_id ↔ project_id 連携)
 */
export default function WorkspaceTasksPage() {
  const params = useParams();
  const id = Number(params?.id);
  const qc = useQueryClient();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [groupBy, setGroupBy] = useState<GroupBy>("feature");
  const [activeTask, setActiveTask] = useState<Task | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchWorkspace(id).then(setWorkspace).catch(() => setWorkspace(null));
  }, [id]);

  const { data: detail } = useQuery({
    queryKey: ["workspace-tasks", id],
    queryFn: () => fetchWorkspaceTasks(id),
    enabled: !!id,
    refetchInterval: 3000,
  });

  const tasks: Task[] = (detail?.tasks ?? []) as Task[];
  const projectId = detail?.project_id;

  const patchTask = useMutation({
    mutationFn: async ({ taskId, ...patch }: { taskId: number; status?: string; parent_task_id?: number | null }) => {
      const r = await fetch(`${API}/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!r.ok) throw new Error("update failed");
      return r.json();
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["workspace-tasks", id] }),
  });

  if (!workspace) {
    return <div className="p-6" style={{ color: "var(--bf-text-3)" }}>読み込み中…</div>;
  }

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      progressPercent={45}
      daysLeft={23}
      active="tasks"
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: "タスク管理" },
      ]}
    >
      <div style={{ marginBottom: "var(--bf-space-6)" }}>
        <div className="flex items-start gap-6 flex-wrap">
          <div>
            <h1 style={{
              fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em",
              color: "var(--bf-text-1)", marginBottom: 4,
            }}>
              タスク管理
            </h1>
            <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>
              機能/画面別 Kanban + Claude Code MCP 引き継ぎ ・ 全 {tasks.length} タスク
            </div>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <button
              className="inline-flex items-center gap-1.5"
              style={{
                height: 34, padding: "0 14px",
                background: "var(--bf-bg-elev)", color: "var(--bf-text-1)",
                border: "1px solid var(--bf-border)",
                borderRadius: "var(--bf-radius-md)",
                fontSize: 13, fontWeight: 600,
              }}
            >
              <Filter className="w-3.5 h-3.5" />
              フィルタ
            </button>
            <button
              className="inline-flex items-center gap-1.5"
              style={{
                height: 34, padding: "0 14px",
                background: "var(--bf-primary)", color: "#fff",
                borderRadius: "var(--bf-radius-md)",
                fontSize: 13, fontWeight: 600,
              }}
            >
              <Plus className="w-3.5 h-3.5" />
              タスク追加
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap" style={{ marginTop: "var(--bf-space-5)" }}>
          <div
            className="flex"
            style={{
              background: "var(--bf-bg-elev)",
              border: "1px solid var(--bf-border)",
              borderRadius: "var(--bf-radius-md)",
              padding: 3,
            }}
          >
            <ToggleBtn active={groupBy === "feature"} onClick={() => setGroupBy("feature")}>
              機能/画面別
            </ToggleBtn>
            <ToggleBtn active={groupBy === "status"} onClick={() => setGroupBy("status")}>
              ステータス別
            </ToggleBtn>
          </div>
        </div>
      </div>

      {tasks.length === 0 ? (
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
          このプロジェクトにタスクはまだありません
        </div>
      ) : (
        <TaskKanban
          tasks={tasks}
          groupBy={groupBy}
          onTaskClick={(t) => setActiveTask(t)}
          onStatusChange={(taskId, status) => patchTask.mutate({ taskId, status })}
          onParentChange={(taskId, parent_task_id) => patchTask.mutate({ taskId, parent_task_id })}
        />
      )}

      <TaskDetailDrawer
        task={activeTask}
        onClose={() => setActiveTask(null)}
        onStatusChange={(taskId, status) => patchTask.mutate({ taskId, status })}
      />
    </WorkspaceShell>
  );
}

function ToggleBtn({
  active, onClick, children,
}: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1 transition-colors"
      style={{
        padding: "6px 12px",
        borderRadius: 4,
        fontSize: 12.5,
        fontWeight: 600,
        background: active ? "var(--bf-primary-bg)" : "transparent",
        color: active ? "var(--bf-primary)" : "var(--bf-text-3)",
      }}
    >
      {children}
    </button>
  );
}
