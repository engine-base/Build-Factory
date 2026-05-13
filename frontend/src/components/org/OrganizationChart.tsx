"use client";

/**
 * T-022-04: 組織図 UI (React Flow tree).
 *
 * AI 社員 (bf_ai_employees + bf_personas) を tree 構造で可視化する.
 * - Node: AI 社員 (role_level で階層レイアウト: secretary > leader > member)
 * - Edge: 階層関係 (親 → 子)
 *
 * 既存 DependencyGraph.tsx (T-009-02 DAG) と並列の組織ビューア.
 * 既存 DependencyGraph は無改変 (REUSE).
 *
 * AC マッピング:
 *   AC-1 UBIQUITOUS    : React Flow tree 構造で persona/employee を描画.
 *                        既存 @xyflow/react を再利用 (REUSE).
 *   AC-2 EVENT-DRIVEN  : onNodeClick で persona 詳細表示 callback.
 *                        height/width 自動算出 + responsive.
 *   AC-3 STATE-DRIVEN  : data props 不変 (controlled component) / 内部 state
 *                        は React Flow 標準のみ.
 *   AC-4 UNWANTED      : 空 employees / 不正 role_level で何も描画しない (no crash).
 *
 * 色: ENGINE BASE green (#1a6648 / eb-500). 絵文字なし (Lucide のみ).
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
import { Crown, Users, User } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Persona shape (backend `ai_employee_store.Persona.to_dict()` 互換).
 */
export interface PersonaData {
  id: number;
  persona_key: string;
  persona_name: string;
  specialty?: string | null;
  avatar_lucide?: string | null;
}

/**
 * Employee shape (backend `ai_employee_store.AIEmployee.to_dict()` 互換).
 */
export interface EmployeeData extends Record<string, unknown> {
  id: number;
  employee_key: string;
  display_name: string;
  role_level: "secretary" | "leader" | "member";
  is_active: boolean;
  persona_id: number | null;
  persona_name?: string | null;
}

/**
 * Tree edge (parent → child).
 */
export interface OrgEdge {
  parent_employee_id: number;
  child_employee_id: number;
}

export interface OrganizationChartProps {
  employees: EmployeeData[];
  edges?: OrgEdge[];
  onNodeClick?: (employee: EmployeeData) => void;
  className?: string;
  /** Height in pixels (default 600). */
  height?: number;
  /** Show minimap (default true). */
  showMinimap?: boolean;
}

// ──────────────────────────────────────────────────────────────────────
// Role-level → color + icon (ENGINE BASE green = #1a6648 = eb-500)
// ──────────────────────────────────────────────────────────────────────

const ROLE_STYLE: Record<
  EmployeeData["role_level"],
  { borderClass: string; bgClass: string; Icon: typeof Crown }
> = {
  secretary: {
    borderClass: "border-eb-500",
    bgClass: "bg-eb-50",
    Icon: Crown,
  },
  leader: {
    borderClass: "border-eb-400",
    bgClass: "bg-eb-50",
    Icon: Users,
  },
  member: {
    borderClass: "border-eb-200",
    bgClass: "bg-white",
    Icon: User,
  },
};

const VALID_ROLES = ["secretary", "leader", "member"] as const;

// ──────────────────────────────────────────────────────────────────────
// Layout: simple top-down tree (role-level → vertical position)
// ──────────────────────────────────────────────────────────────────────

const ROW_HEIGHT = 140;
const NODE_WIDTH = 220;
const COL_GAP = 40;

function _layoutByRoleLevel(
  employees: EmployeeData[],
): Map<number, { x: number; y: number }> {
  // role_level → row index
  const rowIndex: Record<EmployeeData["role_level"], number> = {
    secretary: 0,
    leader: 1,
    member: 2,
  };

  const byRow: Map<number, EmployeeData[]> = new Map();
  for (const emp of employees) {
    if (!VALID_ROLES.includes(emp.role_level)) continue;
    const row = rowIndex[emp.role_level];
    if (!byRow.has(row)) byRow.set(row, []);
    byRow.get(row)!.push(emp);
  }

  const positions = new Map<number, { x: number; y: number }>();
  for (const [row, emps] of byRow) {
    const totalWidth = emps.length * (NODE_WIDTH + COL_GAP);
    const offsetX = -totalWidth / 2;
    emps.forEach((emp, i) => {
      positions.set(emp.id, {
        x: offsetX + i * (NODE_WIDTH + COL_GAP),
        y: row * ROW_HEIGHT,
      });
    });
  }
  return positions;
}

// ──────────────────────────────────────────────────────────────────────
// Node renderer (Lucide icons only, no emoji)
// ──────────────────────────────────────────────────────────────────────

function _toNodes(
  employees: EmployeeData[],
  positions: Map<number, { x: number; y: number }>,
): Node<EmployeeData>[] {
  return employees
    .filter(
      (emp) =>
        emp.is_active !== false &&
        VALID_ROLES.includes(emp.role_level) &&
        positions.has(emp.id),
    )
    .map((emp) => {
      const style = ROLE_STYLE[emp.role_level];
      const pos = positions.get(emp.id)!;
      return {
        id: String(emp.id),
        type: "default",
        position: pos,
        data: emp,
        className: cn(
          "rounded-lg border-2 px-3 py-2 shadow-sm",
          style.borderClass,
          style.bgClass,
        ),
        style: { width: NODE_WIDTH },
      };
    });
}

function _toEdges(edges: OrgEdge[]): Edge[] {
  return edges.map((e, idx) => ({
    id: `e-${e.parent_employee_id}-${e.child_employee_id}-${idx}`,
    source: String(e.parent_employee_id),
    target: String(e.child_employee_id),
    type: "smoothstep",
    animated: false,
    style: { stroke: "var(--eb-500, #1a6648)" },
  }));
}

// ──────────────────────────────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────────────────────────────

export function OrganizationChart({
  employees,
  edges = [],
  onNodeClick,
  className,
  height = 600,
  showMinimap = true,
}: OrganizationChartProps): React.JSX.Element {
  const validEmployees = React.useMemo(
    () => (Array.isArray(employees) ? employees : []),
    [employees],
  );
  const validEdges = React.useMemo(
    () => (Array.isArray(edges) ? edges : []),
    [edges],
  );

  const positions = React.useMemo(
    () => _layoutByRoleLevel(validEmployees),
    [validEmployees],
  );
  const flowNodes = React.useMemo(
    () => _toNodes(validEmployees, positions),
    [validEmployees, positions],
  );
  const flowEdges = React.useMemo(() => _toEdges(validEdges), [validEdges]);

  const handleNodeClick: NodeMouseHandler = React.useCallback(
    (_evt, node) => {
      if (!onNodeClick) return;
      const emp = node.data as EmployeeData | undefined;
      if (emp) onNodeClick(emp);
    },
    [onNodeClick],
  );

  // 空 employees → fallback (no crash)
  if (flowNodes.length === 0) {
    return (
      <div
        className={cn(
          "flex h-full w-full items-center justify-center text-sm text-gray-500",
          className,
        )}
        style={{ height }}
        data-testid="org-chart-empty"
      >
        <User className="mr-2 h-4 w-4" aria-hidden />
        メンバーがまだ登録されていません
      </div>
    );
  }

  return (
    <div
      className={cn("h-full w-full", className)}
      style={{ height }}
      data-testid="org-chart"
    >
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodeClick={handleNodeClick}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
      >
        <Background />
        <Controls showInteractive={false} />
        {showMinimap && <MiniMap pannable zoomable />}
      </ReactFlow>
    </div>
  );
}

// Test-only exports
export const __testing__ = {
  _layoutByRoleLevel,
  _toNodes,
  _toEdges,
  ROLE_STYLE,
  VALID_ROLES,
};
