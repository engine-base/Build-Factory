"use client";

/**
 * T-009-02 / S-017: DAG 可視化 page.
 *
 * GET /api/workspaces/{id}/dependency-graph で {tasks, edges} を取得し
 * DependencyGraph component で描画する.
 *
 * Phase 1 では backend に該当 endpoint が無いので、 fetch 失敗時は demo data で fallback.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { Network, AlertTriangle } from "lucide-react";

import {
  DependencyGraph,
  type TaskNodeData,
  type TaskEdge,
} from "@/components/dag/DependencyGraph";

interface GraphData {
  tasks: TaskNodeData[];
  edges: TaskEdge[];
}

// Phase 1 demo data — backend 接続前のプレースホルダー
const DEMO: GraphData = {
  tasks: [
    { id: 1, title: "要件定義", status: "completed" },
    { id: 2, title: "DB 設計", status: "completed" },
    { id: 3, title: "API 実装", status: "in_progress" },
    { id: 4, title: "UI 実装", status: "in_progress" },
    { id: 5, title: "結合テスト", status: "pending" },
    { id: 6, title: "デプロイ", status: "pending" },
    { id: 7, title: "要件レビュー (blocked)", status: "blocked_question" },
  ],
  edges: [
    { source: 1, target: 2, kind: "hard" },
    { source: 1, target: 3, kind: "hard" },
    { source: 2, target: 3, kind: "hard" },
    { source: 1, target: 4, kind: "soft" },
    { source: 3, target: 5, kind: "hard" },
    { source: 4, target: 5, kind: "hard" },
    { source: 5, target: 6, kind: "hard" },
    { source: 1, target: 7, kind: "hard" },
  ],
};

export default function DependencyGraphPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const workspaceId = params?.id;

  const [data, setData] = React.useState<GraphData | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(
          `/api/workspaces/${workspaceId}/dependency-graph`,
          { cache: "no-store" },
        );
        if (!res.ok) {
          // AC-4 UNWANTED: 4xx → friendly error + Phase 1 demo fallback
          if (res.status >= 400 && res.status < 500) {
            const body = await res.json().catch(() => ({}));
            const detail = body?.detail;
            const msg =
              typeof detail === "object" && detail?.message
                ? String(detail.message)
                : `HTTP ${res.status}`;
            if (!cancelled) {
              setError(msg);
              setData(DEMO);
            }
            return;
          }
          throw new Error(`HTTP ${res.status}`);
        }
        const json = (await res.json()) as GraphData;
        if (!cancelled) setData(json);
      } catch (e) {
        if (!cancelled) {
          // Phase 1 backend 未実装 → demo data
          setData(DEMO);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const handleNodeClick = React.useCallback(
    (task: TaskNodeData) => {
      router.push(`/workspaces/${workspaceId}/tasks?taskId=${task.id}`);
    },
    [router, workspaceId],
  );

  return (
    <div className="flex h-screen flex-col">
      <header className="border-b bg-background px-6 py-4">
        <div className="flex items-center gap-2">
          <Network className="h-5 w-5 text-eb-500" />
          <h1 className="text-base font-bold text-slate-900">
            タスク依存関係グラフ (DAG)
          </h1>
        </div>
        {error && (
          <div
            role="alert"
            className="mt-2 flex items-start gap-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800"
          >
            <AlertTriangle className="h-4 w-4 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
        {loading && (
          <p className="mt-2 text-xs text-slate-500">読み込み中...</p>
        )}
      </header>
      <div className="flex-1 overflow-hidden">
        {data && (
          <DependencyGraph
            tasks={data.tasks}
            edges={data.edges}
            onNodeClick={handleNodeClick}
          />
        )}
      </div>
    </div>
  );
}