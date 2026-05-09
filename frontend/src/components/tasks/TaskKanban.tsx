"use client";

import { useMemo, useState } from "react";
import {
  Bot, Clock, CheckCircle, XCircle, AlertCircle, HelpCircle,
  GripVertical, Folder,
} from "lucide-react";

export type Task = {
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

export type GroupBy = "feature" | "status";

const STATUS_DEF = {
  pending:           { label: "未着手",   bg: "#F3F4F6", color: "#6B7280", accent: "#94A3B8", Icon: Clock },
  in_progress:       { label: "進行中",   bg: "#DBEAFE", color: "#1E40AF", accent: "#1E40AF", Icon: Clock },
  blocked_question:  { label: "質問待ち", bg: "#FEF3C7", color: "#92400E", accent: "#D97706", Icon: HelpCircle },
  blocked_dependency:{ label: "依存待ち", bg: "#FEF3C7", color: "#92400E", accent: "#D97706", Icon: AlertCircle },
  review_needed:     { label: "確認待ち", bg: "#E0F2FE", color: "#0369A1", accent: "#0369A1", Icon: AlertCircle },
  completed:         { label: "完了",     bg: "#DCFCE7", color: "#16A34A", accent: "#16A34A", Icon: CheckCircle },
  failed:            { label: "失敗",     bg: "#FEE2E2", color: "#DC2626", accent: "#DC2626", Icon: XCircle },
  cancelled:         { label: "中止",     bg: "#F3F4F6", color: "#6B7280", accent: "#94A3B8", Icon: XCircle },
} as const;

type StatusKey = keyof typeof STATUS_DEF;
const statusOf = (s: string) =>
  STATUS_DEF[s as StatusKey] ?? STATUS_DEF.pending;

const STATUS_COLUMNS: { id: string; title: string; matches: string[] }[] = [
  { id: "todo",    title: "TODO",     matches: ["pending"] },
  { id: "doing",   title: "進行中",   matches: ["in_progress"] },
  { id: "blocked", title: "ブロック", matches: ["blocked_question", "blocked_dependency"] },
  { id: "review",  title: "レビュー", matches: ["review_needed"] },
  { id: "done",    title: "完了",     matches: ["completed"] },
  { id: "failed",  title: "失敗/中止", matches: ["failed", "cancelled"] },
];

const STATUS_COLUMN_TARGET: Record<string, string> = {
  todo: "pending", doing: "in_progress",
  blocked: "blocked_question", review: "review_needed",
  done: "completed", failed: "failed",
};

const STATUS_SORT_ORDER: Record<string, number> = {
  pending: 0, in_progress: 1, review_needed: 2,
  blocked_question: 3, blocked_dependency: 3,
  completed: 4, failed: 5, cancelled: 5,
};

interface Props {
  tasks: Task[];
  groupBy: GroupBy;
  onTaskClick?: (task: Task) => void;
  onStatusChange?: (taskId: number, newStatus: string) => void;
  onParentChange?: (taskId: number, newParentId: number | null) => void;
}

export function TaskKanban({ tasks, groupBy, onTaskClick, onStatusChange, onParentChange }: Props) {
  if (groupBy === "feature") {
    return (
      <FeatureBoard
        tasks={tasks}
        onTaskClick={onTaskClick}
        onParentChange={onParentChange}
      />
    );
  }
  return (
    <StatusBoard
      tasks={tasks}
      onTaskClick={onTaskClick}
      onStatusChange={onStatusChange}
    />
  );
}

/* ================================================================
 *  機能/画面別ボード — カラム = 親タスク (level=0)
 * ================================================================ */

function FeatureBoard({
  tasks, onTaskClick, onParentChange,
}: {
  tasks: Task[];
  onTaskClick?: (t: Task) => void;
  onParentChange?: (id: number, parentId: number | null) => void;
}) {
  const [dragId, setDragId] = useState<number | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);

  // 親 = 機能 / 画面
  const features = useMemo(
    () => tasks.filter((t) => t.parent_task_id == null),
    [tasks],
  );

  const groups = useMemo(() => {
    const map = new Map<string, Task[]>();
    map.set("__orphan__", []);
    for (const f of features) map.set(String(f.id), []);
    for (const t of tasks) {
      if (t.parent_task_id == null) continue; // 親自体は子として表示しない
      const key = String(t.parent_task_id);
      if (map.has(key)) map.get(key)!.push(t);
      else map.get("__orphan__")!.push(t);
    }
    for (const list of map.values()) {
      list.sort(
        (a, b) =>
          (STATUS_SORT_ORDER[a.status] ?? 99) - (STATUS_SORT_ORDER[b.status] ?? 99),
      );
    }
    return map;
  }, [tasks, features]);

  const orphans = groups.get("__orphan__") ?? [];

  const handleDrop = (colId: string) => {
    if (dragId == null) return;
    const newParent = colId === "__orphan__" ? null : Number(colId);
    onParentChange?.(dragId, newParent);
    setDragId(null);
    setOverCol(null);
  };

  return (
    <div className="flex gap-3 overflow-x-auto pb-4 px-1">
      {features.map((feat) => {
        const items = groups.get(String(feat.id)) ?? [];
        return (
          <FeatureColumn
            key={feat.id}
            feature={feat}
            items={items}
            isOver={overCol === String(feat.id)}
            onDragOver={() => setOverCol(String(feat.id))}
            onDragLeave={() => setOverCol((c) => (c === String(feat.id) ? null : c))}
            onDrop={() => handleDrop(String(feat.id))}
            onTaskClick={onTaskClick}
            onCardDragStart={setDragId}
            onCardDragEnd={() => { setDragId(null); setOverCol(null); }}
            dragId={dragId}
            onFeatureClick={onTaskClick}
          />
        );
      })}

      {orphans.length > 0 && (
        <FeatureColumn
          feature={null}
          items={orphans}
          isOver={overCol === "__orphan__"}
          onDragOver={() => setOverCol("__orphan__")}
          onDragLeave={() => setOverCol((c) => (c === "__orphan__" ? null : c))}
          onDrop={() => handleDrop("__orphan__")}
          onTaskClick={onTaskClick}
          onCardDragStart={setDragId}
          onCardDragEnd={() => { setDragId(null); setOverCol(null); }}
          dragId={dragId}
        />
      )}
    </div>
  );
}

function FeatureColumn({
  feature, items, isOver, onDragOver, onDragLeave, onDrop,
  onTaskClick, onCardDragStart, onCardDragEnd, dragId, onFeatureClick,
}: {
  feature: Task | null;
  items: Task[];
  isOver: boolean;
  onDragOver: () => void;
  onDragLeave: () => void;
  onDrop: () => void;
  onTaskClick?: (t: Task) => void;
  onCardDragStart: (id: number) => void;
  onCardDragEnd: () => void;
  dragId: number | null;
  onFeatureClick?: (t: Task) => void;
}) {
  const featStatus = feature ? statusOf(feature.status) : null;
  const completed = items.filter((t) => t.status === "completed").length;

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); onDragOver(); }}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className="flex w-[300px] shrink-0 flex-col rounded-xl"
      style={{
        background: isOver ? "var(--eb-primary-container)" : "var(--eb-surface-variant)",
        border: `1px solid ${isOver ? "var(--eb-primary)" : "var(--eb-border)"}`,
        transition: "background 120ms, border-color 120ms",
      }}
    >
      <div
        className="px-3 py-2.5 cursor-pointer hover:bg-white/60 rounded-t-xl"
        style={{ borderBottom: "1px solid var(--eb-border)" }}
        onClick={() => feature && onFeatureClick?.(feature)}
      >
        <div className="flex items-center gap-2 mb-1">
          <Folder
            className="w-3.5 h-3.5 shrink-0"
            style={{ color: featStatus?.accent ?? "var(--eb-neutral)" }}
          />
          <span
            className="text-[12px] font-bold flex-1 truncate"
            style={{ fontFamily: "var(--font-noto-sans-jp)", color: "#111827" }}
          >
            {feature?.title ?? "未分類"}
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded font-mono"
            style={{ background: "#fff", border: "1px solid var(--eb-border)", color: "var(--eb-neutral)" }}
          >
            {completed}/{items.length}
          </span>
        </div>
        {feature && featStatus && (
          <div className="flex items-center gap-1.5">
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-semibold inline-flex items-center gap-0.5"
              style={{ background: featStatus.bg, color: featStatus.color, fontFamily: "var(--font-inter)" }}
            >
              <featStatus.Icon className="w-2.5 h-2.5" />
              {featStatus.label}
            </span>
            <ProgressBar items={items} />
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2 p-2 min-h-[200px]">
        {items.length === 0 ? (
          <div
            className="text-center py-8 text-[11px]"
            style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}
          >
            タスクなし
          </div>
        ) : (
          items.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onClick={() => onTaskClick?.(task)}
              onDragStart={() => onCardDragStart(task.id)}
              onDragEnd={onCardDragEnd}
              isDragging={dragId === task.id}
            />
          ))
        )}
      </div>
    </div>
  );
}

function ProgressBar({ items }: { items: Task[] }) {
  if (items.length === 0) return null;
  const segs = items.map((t) => statusOf(t.status).accent);
  return (
    <div className="flex-1 flex gap-0.5 h-1 rounded overflow-hidden">
      {segs.map((c, i) => (
        <span key={i} className="flex-1 rounded-sm" style={{ background: c, opacity: 0.85 }} />
      ))}
    </div>
  );
}

/* ================================================================
 *  ステータス別ボード — カラム = ステータス
 * ================================================================ */

function StatusBoard({
  tasks, onTaskClick, onStatusChange,
}: {
  tasks: Task[];
  onTaskClick?: (t: Task) => void;
  onStatusChange?: (id: number, status: string) => void;
}) {
  const [dragId, setDragId] = useState<number | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const map: Record<string, Task[]> = {};
    for (const col of STATUS_COLUMNS) map[col.id] = [];
    for (const t of tasks) {
      const col = STATUS_COLUMNS.find((c) => c.matches.includes(t.status));
      if (col) map[col.id].push(t);
    }
    return map;
  }, [tasks]);

  const handleDrop = (colId: string) => {
    if (dragId == null) return;
    const newStatus = STATUS_COLUMN_TARGET[colId];
    if (newStatus) onStatusChange?.(dragId, newStatus);
    setDragId(null);
    setOverCol(null);
  };

  return (
    <div className="flex gap-3 overflow-x-auto pb-4 px-1">
      {STATUS_COLUMNS.map((col) => {
        const items = grouped[col.id] ?? [];
        const isOver = overCol === col.id;
        const accent = statusOf(STATUS_COLUMN_TARGET[col.id]).accent;
        return (
          <div
            key={col.id}
            onDragOver={(e) => { e.preventDefault(); setOverCol(col.id); }}
            onDragLeave={() => setOverCol((c) => (c === col.id ? null : c))}
            onDrop={() => handleDrop(col.id)}
            className="flex w-[280px] shrink-0 flex-col rounded-xl"
            style={{
              background: isOver ? "var(--eb-primary-container)" : "var(--eb-surface-variant)",
              border: `1px solid ${isOver ? "var(--eb-primary)" : "var(--eb-border)"}`,
              transition: "background 120ms, border-color 120ms",
            }}
          >
            <div
              className="flex items-center justify-between px-3 py-2.5"
              style={{ borderBottom: "1px solid var(--eb-border)" }}
            >
              <div className="flex items-center gap-2">
                <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: accent }} />
                <span
                  className="text-[11px] font-bold uppercase tracking-wider"
                  style={{ fontFamily: "var(--font-inter)", color: "#1F2937" }}
                >
                  {col.title}
                </span>
              </div>
              <span
                className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                style={{ background: "#fff", border: "1px solid var(--eb-border)", color: "var(--eb-neutral)" }}
              >
                {items.length}
              </span>
            </div>

            <div className="flex flex-col gap-2 p-2 min-h-[200px]">
              {items.length === 0 ? (
                <div
                  className="text-center py-8 text-[11px]"
                  style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}
                >
                  タスクなし
                </div>
              ) : (
                items.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    onClick={() => onTaskClick?.(task)}
                    onDragStart={() => setDragId(task.id)}
                    onDragEnd={() => { setDragId(null); setOverCol(null); }}
                    isDragging={dragId === task.id}
                  />
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ================================================================
 *  共通カード
 * ================================================================ */

function TaskCard({
  task, onClick, onDragStart, onDragEnd, isDragging,
}: {
  task: Task;
  onClick: () => void;
  onDragStart: () => void;
  onDragEnd: () => void;
  isDragging: boolean;
}) {
  const s = statusOf(task.status);
  const isFeature = task.skill_name === "feature";
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      className="group cursor-grab active:cursor-grabbing rounded-lg bg-white p-2.5 shadow-sm hover:shadow-md transition-shadow"
      style={{
        border: "1px solid var(--eb-border)",
        borderLeft: `3px solid ${s.accent}`,
        opacity: isDragging ? 0.4 : 1,
      }}
    >
      <div className="flex items-start gap-1.5">
        <GripVertical className="w-3 h-3 mt-0.5 opacity-0 group-hover:opacity-40 transition-opacity shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <span
              className="text-[9px] font-mono px-1 py-0.5 rounded shrink-0"
              style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)" }}
            >
              #{task.id}
            </span>
            <p
              className="text-[13px] font-medium leading-tight line-clamp-2"
              style={{ fontFamily: "var(--font-noto-sans-jp)", color: "#111827" }}
            >
              {task.title}
            </p>
          </div>

          {task.description && (
            <p
              className="text-[11px] mt-1 line-clamp-2"
              style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}
            >
              {task.description}
            </p>
          )}

          <div className="flex items-center gap-1.5 mt-2 flex-wrap">
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-semibold inline-flex items-center gap-0.5"
              style={{ background: s.bg, color: s.color, fontFamily: "var(--font-inter)" }}
            >
              <s.Icon className="w-2.5 h-2.5" />
              {s.label}
            </span>
            {task.skill_name && !isFeature && (
              <code
                className="text-[10px] px-1.5 py-0.5 rounded"
                style={{
                  background: "var(--eb-tertiary-container)",
                  color: "var(--eb-on-tertiary-container)",
                  fontFamily: "var(--font-inter)",
                }}
              >
                {task.skill_name}
              </code>
            )}
            {task.assignee_name && (
              <span
                className="flex items-center gap-0.5 text-[10px] ml-auto"
                style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}
              >
                <Bot className="w-2.5 h-2.5" />
                {task.assignee_name}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
