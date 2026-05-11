"use client";

/**
 * T-009-02 / S-017: DAG 可視化 UI (React Flow).
 *
 * タスク (bf_tasks) の依存関係 (task_dependencies) を DAG として描画する.
 * - Node: タスク (status カラーで状態を表現)
 * - Edge: depends_on 関係 (矢印 = 親 → 子)
 *
 * 使い方:
 *   <DependencyGraph
 *     tasks={[{id:1, title:"Setup", status:"completed"}, ...]}
 *     edges={[{source:1, target:2}, ...]}
 *     onNodeClick={(task) => router.push(`/tasks/${task.id}`)}
 *   />
 */

import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import * as React from "react";

import { cn } from "@/lib/utils";

export type TaskStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "blocked_question"
  | "blocked_dependency"
  | "failed";

export interface TaskNodeData extends Record<string, unknown> {
  id: number;
  title: string;
  status: TaskStatus;
  assignee?: string | null;
}

export interface TaskEdge {
  source: number;
  target: number;
  /** 'hard' = blocking dependency, 'soft' = informational */
  kind?: "hard" | "soft";
}

interface DependencyGraphProps {
  tasks: TaskNodeData[];
  edges: TaskEdge[];
  onNodeClick?: (task: TaskNodeData) => void;
  className?: string;
}

// status 別の border 色 (eb-500 系 ENGINE BASE green palette と整合)
const STATUS_BORDER: Record<TaskStatus, string> = {
  pending: "border-slate-400",
  in_progress: "border-eb-500",
  completed: "border-eb-700",
  blocked_question: "border-amber-500",
  blocked_dependency: "border-rose-500",
  failed: "border-rose-700",
};

const STATUS_BG: Record<TaskStatus, string> = {
  pending: "bg-slate-50",
  in_progress: "bg-eb-50",
  completed: "bg-eb-100",
  blocked_question: "bg-amber-50",
  blocked_dependency: "bg-rose-50",
  failed: "bg-rose-100",
};

/**
 * Auto-layout: 入次数 0 を左端、 BFS で列ごとに右にずらす最小限の Sugiyama 風.
 * 数十 node のレベルなら実用十分.
 */
function layoutNodes(tasks: TaskNodeData[], edges: TaskEdge[]): Node<TaskNodeData>[] {
  if (tasks.length === 0) return [];
  const incoming: Map<number, number> = new Map();
  const outgoing: Map<number, number[]> = new Map();
  for (const t of tasks) {
    incoming.set(t.id, 0);
    outgoing.set(t.id, []);
  }
  for (const e of edges) {
    if (!incoming.has(e.target) || !outgoing.has(e.source)) continue;
    incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1);
    outgoing.get(e.source)!.push(e.target);
  }

  // BFS で level 計算
  const level: Map<number, number> = new Map();
  const queue: number[] = [];
  for (const t of tasks) {
    if (incoming.get(t.id) === 0) {
      level.set(t.id, 0);
      queue.push(t.id);
    }
  }
  while (queue.length > 0) {
    const id = queue.shift()!;
    const curLevel = level.get(id) ?? 0;
    for (const next of outgoing.get(id) ?? []) {
      const nextLevel = Math.max(level.get(next) ?? 0, curLevel + 1);
      if (level.get(next) !== nextLevel) {
        level.set(next, nextLevel);
        queue.push(next);
      }
    }
  }
  // 循環で level 未確定の node も最大 level + 1 に置く
  for (const t of tasks) {
    if (!level.has(t.id)) level.set(t.id, 0);
  }

  // level ごとに縦に並べる
  const byLevel: Map<number, TaskNodeData[]> = new Map();
  for (const t of tasks) {
    const l = level.get(t.id) ?? 0;
    if (!byLevel.has(l)) byLevel.set(l, []);
    byLevel.get(l)!.push(t);
  }

  const X_GAP = 220;
  const Y_GAP = 100;
  const nodes: Node<TaskNodeData>[] = [];
  for (const [l, ts] of byLevel.entries()) {
    ts.forEach((t, i) => {
      nodes.push({
        id: String(t.id),
        position: { x: l * X_GAP, y: i * Y_GAP },
        data: t,
        type: "default",
      });
    });
  }
  return nodes;
}

function buildEdges(edges: TaskEdge[]): Edge[] {
  return edges.map((e) => ({
    id: `e-${e.source}-${e.target}`,
    source: String(e.source),
    target: String(e.target),
    animated: e.kind === "hard",
    style: e.kind === "hard" ? undefined : { strokeDasharray: "4 4" },
  }));
}

export function DependencyGraph({
  tasks,
  edges,
  onNodeClick,
  className,
}: DependencyGraphProps) {
  const rfNodes = React.useMemo(
    () => layoutNodes(tasks, edges).map((n) => ({
      ...n,
      data: n.data,
      style: undefined,
      // 上書き: classNames を data 別に
    })),
    [tasks, edges],
  );
  const rfEdges = React.useMemo(() => buildEdges(edges), [edges]);

  const handleNodeClick: NodeMouseHandler = React.useCallback(
    (_event, node) => {
      const data = node.data as unknown as TaskNodeData;
      onNodeClick?.(data);
    },
    [onNodeClick],
  );

  // status 別の class 付き node renderer
  const styledNodes = React.useMemo(
    () =>
      rfNodes.map((n) => {
        const data = n.data as TaskNodeData;
        const statusClass = cn(
          "rounded-md px-3 py-2 text-sm border-2 shadow-sm",
          STATUS_BORDER[data.status],
          STATUS_BG[data.status],
        );
        return {
          ...n,
          className: statusClass,
          data: {
            ...data,
            label: data.title,
          },
        };
      }),
    [rfNodes],
  );

  return (
    <div
      role="region"
      aria-label="dependency graph"
      className={cn("w-full h-full min-h-[400px]", className)}
    >
      <ReactFlow
        nodes={styledNodes}
        edges={rfEdges}
        onNodeClick={handleNodeClick}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}

export default DependencyGraph;