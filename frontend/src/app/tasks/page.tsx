"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ListTodo, ChevronRight, ChevronDown, Bot, Clock, CheckCircle, XCircle, AlertCircle, HelpCircle } from "lucide-react";

const API = "http://localhost:8001";

type Task = {
  id: number;
  project_id: number;
  parent_task_id: number | null;
  title: string;
  description: string;
  assigned_to: number | null;
  assignee_name: string | null;
  skill_name: string;
  status: string;
  result: string;
  level: number;
  created_at: string;
};

type Project = {
  id: number;
  title: string;
  description: string;
  status: string;
  task_count: number;
  done_count: number;
  created_at: string;
  completed_at: string | null;
};

const STATUS_CONFIG: Record<string, { label: string; bg: string; color: string; Icon: any }> = {
  pending:           { label: "未着手", bg: "#F3F4F6", color: "#6B7280", Icon: Clock },
  in_progress:       { label: "進行中", bg: "#DBEAFE", color: "#1E40AF", Icon: Clock },
  blocked_question:  { label: "質問待ち", bg: "#FEF3C7", color: "#92400E", Icon: HelpCircle },
  blocked_dependency:{ label: "依存待ち", bg: "#FEF3C7", color: "#92400E", Icon: AlertCircle },
  review_needed:     { label: "確認待ち", bg: "#E0F2FE", color: "#0369A1", Icon: AlertCircle },
  completed:         { label: "完了",   bg: "#DCFCE7", color: "#16A34A", Icon: CheckCircle },
  failed:            { label: "失敗",   bg: "#FEE2E2", color: "#DC2626", Icon: XCircle },
  cancelled:         { label: "中止",   bg: "#F3F4F6", color: "#6B7280", Icon: XCircle },
};

export default function TasksPage() {
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const { data: projects = [] } = useQuery<Project[]>({
    queryKey: ["projects"],
    queryFn: () => fetch(`${API}/api/projects`).then(r => r.json()),
    refetchInterval: 5000,
  });

  const { data: detail } = useQuery<{ project: Project; tasks: Task[] }>({
    queryKey: ["project", selectedProjectId],
    queryFn: () => fetch(`${API}/api/projects/${selectedProjectId}`).then(r => r.json()),
    enabled: !!selectedProjectId,
    refetchInterval: 3000,
  });

  const tasks = detail?.tasks ?? [];

  const toggle = (id: number) => {
    const ns = new Set(expanded);
    ns.has(id) ? ns.delete(id) : ns.add(id);
    setExpanded(ns);
  };

  const renderTask = (task: Task, allTasks: Task[]) => {
    const children = allTasks.filter(t => t.parent_task_id === task.id);
    const conf = STATUS_CONFIG[task.status] ?? STATUS_CONFIG.pending;
    const Icon = conf.Icon;
    const isExpanded = expanded.has(task.id);
    const hasChildren = children.length > 0;

    return (
      <div key={task.id}>
        <div className="rounded-lg p-3 bg-white"
          style={{
            border: "1px solid var(--eb-border)",
            borderLeft: `3px solid ${conf.color}`,
            marginLeft: task.level * 24,
            marginBottom: 4,
          }}>
          <div className="flex items-start gap-2">
            {hasChildren && (
              <button onClick={() => toggle(task.id)} className="p-0.5 rounded hover:bg-gray-100" style={{ marginTop: 2 }}>
                {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
            )}
            {!hasChildren && <div className="w-4" />}

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                  style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)" }}>
                  #{task.id}
                </span>
                <p className="text-sm font-medium truncate" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                  {task.title}
                </p>
              </div>
              <div className="flex items-center gap-2 text-[11px]">
                <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded font-semibold"
                  style={{ background: conf.bg, color: conf.color, fontFamily: "var(--font-inter)" }}>
                  <Icon className="w-2.5 h-2.5" />
                  {conf.label}
                </span>
                {task.assignee_name && (
                  <span className="flex items-center gap-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                    <Bot className="w-3 h-3" />
                    {task.assignee_name}
                  </span>
                )}
                {task.skill_name && (
                  <code className="text-[10px] opacity-70" style={{ fontFamily: "var(--font-inter)" }}>
                    [{task.skill_name}]
                  </code>
                )}
              </div>
              {task.description && (
                <p className="text-[11px] mt-1.5 line-clamp-2" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
                  {task.description}
                </p>
              )}
              {task.result && (
                <details className="mt-2">
                  <summary className="text-[10px] cursor-pointer" style={{ color: "var(--eb-neutral)" }}>
                    結果を表示
                  </summary>
                  <pre className="mt-1 p-2 rounded text-[11px] whitespace-pre-wrap max-h-40 overflow-auto"
                    style={{ background: "var(--eb-surface-variant)", fontFamily: "var(--font-inter)" }}>
                    {task.result.slice(0, 1000)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        </div>

        {isExpanded && children.map(c => renderTask(c, allTasks))}
      </div>
    );
  };

  const rootTasks = tasks.filter(t => !t.parent_task_id);

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "var(--eb-surface-variant)" }}>
      {/* 左: プロジェクト一覧 */}
      <div className="w-72 shrink-0 flex flex-col bg-white" style={{ borderRight: "1px solid var(--eb-border)" }}>
        <div className="p-4" style={{ borderBottom: "1px solid var(--eb-border)" }}>
          <h1 className="font-bold text-base" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>タスク管理</h1>
          <p className="text-[10px] mt-1" style={{ color: "var(--eb-neutral)" }}>秘書チャットから自動分解されたプロジェクト</p>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {projects.length === 0 && (
            <div className="text-center py-12">
              <ListTodo className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p className="text-xs" style={{ color: "var(--eb-neutral)" }}>プロジェクトなし</p>
              <p className="text-[10px] mt-1" style={{ color: "var(--eb-neutral)" }}>秘書チャットで依頼すると自動作成されます</p>
            </div>
          )}
          {projects.map(p => (
            <button key={p.id} onClick={() => setSelectedProjectId(p.id)}
              className="w-full text-left p-3 rounded-lg transition-colors"
              style={{
                background: selectedProjectId === p.id ? "var(--eb-primary-container)" : "#fff",
                border: `1px solid ${selectedProjectId === p.id ? "var(--eb-primary)" : "var(--eb-border)"}`,
              }}>
              <p className="text-xs font-medium line-clamp-2" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{p.title}</p>
              <div className="flex items-center justify-between mt-1.5">
                <span className="text-[10px]" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                  {p.done_count}/{p.task_count} 完了
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{
                    background: p.status === "completed" ? "#DCFCE7" : "#DBEAFE",
                    color: p.status === "completed" ? "#16A34A" : "#1E40AF",
                    fontFamily: "var(--font-inter)"
                  }}>
                  {p.status}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 右: タスク階層ツリー */}
      <div className="flex-1 overflow-y-auto p-6">
        {detail?.project ? (
          <>
            <div className="mb-6">
              <h2 className="text-xl font-bold mb-2" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                {detail.project.title}
              </h2>
              {detail.project.description && (
                <p className="text-sm" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
                  {detail.project.description}
                </p>
              )}
              <p className="text-[11px] mt-2" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                作成: {new Date(detail.project.created_at).toLocaleString("ja-JP")} • 全{tasks.length}タスク
              </p>
            </div>

            {tasks.length === 0 ? (
              <p className="text-center text-sm py-12" style={{ color: "var(--eb-neutral)" }}>タスクなし</p>
            ) : (
              <div>{rootTasks.map(t => renderTask(t, tasks))}</div>
            )}
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center">
            <ListTodo className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-sm" style={{ color: "var(--eb-neutral)" }}>左からプロジェクトを選択</p>
          </div>
        )}
      </div>
    </div>
  );
}
