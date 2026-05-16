"use client";

/**
 * S-036 AI 社員 組織図 — T-V3-C-12 / F-003.
 *
 * @screen-id S-036
 * @feature-id F-003,F-022
 * @task-ids T-V3-C-12,T-V3-RF-18,T-V3-DRIFT-04
 * @entities E-034
 * @phase Phase 1B
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/ai/S-036-ai-employees-org-chart.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-12.md):
 *   structural.AC-S1 (data-screen-id="S-036")              — root <div>.
 *   structural.AC-S2 (h1 == "AI 社員 組織図")               — page heading.
 *   functional.AC-F1 (GET  /api/ai-employees/org-chart typed client)
 *     — useEffect on mount + manual refresh button.
 *   functional.AC-F2 (POST /api/ai-employees typed client) — "AI 社員を作成"
 *     dialog Submit button.
 *   functional.AC-F3 (POST /api/ai-employees/{id}/clone-from-user typed client)
 *     — "ユーザーをクローン" form Submit button.
 *   functional.AC-F4 (4xx/5xx -> non-technical toast referencing endpoint)
 *     — `AiEmployeesApiError.toUserMessage()` consumed via local error state.
 *   functional.AC-F5 (GET org-chart returns hierarchical tree of non-archived
 *     employees — backend responsibility, UI renders the tree as-returned).
 *   functional.AC-F6 (POST /api/ai-employees enforces hierarchy_level 1..3 —
 *     backend AC; UI only allows 1..3 in the level select).
 *   functional.AC-F7 (UNWANTED 409 on circular parent — backend AC; UI surfaces
 *     the 409 user message via surfaceError()).
 *   functional.AC-F8 (UNWANTED 403 on clone when opt-in is FALSE — backend AC;
 *     UI surfaces the 403 user message via surfaceError()).
 *   functional.AC-F9 (UNWANTED 429 on /test rate limit — covered by the sibling
 *     S-037 page; UI ack here is endpoint-tagged toast helper).
 */

import * as React from "react";
import {
  AlertTriangle,
  ArrowLeft,
  LayoutDashboard,
  Plus,
  RefreshCw,
  User,
  UserPlus,
  Users,
  Wrench,
} from "lucide-react";

import {
  AI_EMPLOYEES_CLONE_FROM_USER_ENDPOINT,
  AI_EMPLOYEES_CREATE_ENDPOINT,
  AI_EMPLOYEES_ORG_CHART_ENDPOINT,
  AiEmployeesApiError,
  cloneAiEmployeeFromUser,
  createAiEmployee,
  getAiEmployeesOrgChart,
  type AiEmployeeNode,
  type AiEmployeesOrgChartResponse,
} from "@/api/ai-employees";

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

/** Map persona name → tailwind colour (kept loose so the mock and impl stay in
 *  sync without hard-coding 10 personas). */
function personaTone(persona: string): { bg: string; border: string; chip: string } {
  const p = persona.toLowerCase();
  if (p.includes("secretary")) {
    return {
      bg: "bg-purple-50",
      border: "border-purple-300",
      chip: "bg-purple-500",
    };
  }
  if (p.includes("mary") || p.includes("ba")) {
    return {
      bg: "bg-emerald-50",
      border: "border-emerald-300",
      chip: "bg-emerald-500",
    };
  }
  if (p.includes("preston") || p.includes("pm") || p.includes("quinn")) {
    return {
      bg: "bg-amber-50",
      border: "border-amber-300",
      chip: "bg-amber-500",
    };
  }
  if (p.includes("winston") || p.includes("architect")) {
    return {
      bg: "bg-blue-50",
      border: "border-blue-300",
      chip: "bg-blue-500",
    };
  }
  if (p.includes("sally") || p.includes("devon") || p.includes("po") || p.includes("dev")) {
    return {
      bg: "bg-eb-50",
      border: "border-eb-500",
      chip: "bg-eb-500",
    };
  }
  return {
    bg: "bg-slate-50",
    border: "border-slate-300",
    chip: "bg-slate-500",
  };
}

function personaInitials(name: string): string {
  const cleaned = name.replace(/[^a-zA-Z]/g, "");
  if (cleaned.length === 0) return name.slice(0, 2).toUpperCase();
  return cleaned.slice(0, 2).toUpperCase();
}

/** Walk the tree depth-first and yield every non-clone node. */
function flattenTree(nodes: AiEmployeeNode[] | undefined): AiEmployeeNode[] {
  if (!nodes) return [];
  const out: AiEmployeeNode[] = [];
  const stack: AiEmployeeNode[] = [...nodes];
  while (stack.length > 0) {
    const node = stack.shift();
    if (!node) continue;
    out.push(node);
    if (node.children?.length) {
      // depth-first traversal — push children to the *front* of the queue.
      stack.unshift(...node.children);
    }
  }
  return out;
}

function isCloneNode(node: AiEmployeeNode): boolean {
  const dept = String(node.department ?? "").toLowerCase();
  const persona = node.persona.toLowerCase();
  return dept === "clone" || persona.includes("clone");
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

type CreateFormState = {
  name: string;
  persona: string;
  hierarchy_level: 1 | 2 | 3;
  parent_id: string;
  department: string;
};

const INITIAL_CREATE_FORM: CreateFormState = {
  name: "",
  persona: "",
  hierarchy_level: 2,
  parent_id: "",
  department: "Dev",
};

export default function AiEmployeesOrgChartPage() {
  const [orgChart, setOrgChart] =
    React.useState<AiEmployeesOrgChartResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  // Department filter (UI-only; backend tree is rendered as-returned per AC-F5).
  const [departmentFilter, setDepartmentFilter] = React.useState<string>("all");

  // "AI 社員を作成" dialog state (AC-F2 trigger).
  const [createOpen, setCreateOpen] = React.useState(false);
  const [createForm, setCreateForm] =
    React.useState<CreateFormState>(INITIAL_CREATE_FORM);
  const [createBusy, setCreateBusy] = React.useState(false);

  // "ユーザーをクローン" dialog state (AC-F3 trigger).
  const [cloneOpen, setCloneOpen] = React.useState(false);
  const [cloneTargetEmployeeId, setCloneTargetEmployeeId] =
    React.useState<string>("");
  const [cloneSourceUserId, setCloneSourceUserId] = React.useState<string>("");
  const [cloneBusy, setCloneBusy] = React.useState(false);

  // ----------------------------------------------------------------------
  // AC-F4 helper: surface a non-technical message referencing the endpoint
  // without leaking server stack traces.
  // ----------------------------------------------------------------------
  const surfaceError = React.useCallback(
    (err: unknown, fallbackEndpoint: string) => {
      const msg =
        err instanceof AiEmployeesApiError
          ? err.toUserMessage()
          : `通信に失敗しました (${fallbackEndpoint})`;
      setErrorMessage(msg);
    },
    [],
  );

  // ----------------------------------------------------------------------
  // AC-F1: GET /api/ai-employees/org-chart on mount + manual refresh.
  // ----------------------------------------------------------------------
  const loadOrgChart = React.useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const data = await getAiEmployeesOrgChart();
      setOrgChart(data);
    } catch (err) {
      surfaceError(err, AI_EMPLOYEES_ORG_CHART_ENDPOINT);
      setOrgChart(null);
    } finally {
      setLoading(false);
    }
  }, [surfaceError]);

  React.useEffect(() => {
    void loadOrgChart();
  }, [loadOrgChart]);

  // ----------------------------------------------------------------------
  // AC-F2: POST /api/ai-employees (create employee).
  // ----------------------------------------------------------------------
  const handleCreate = React.useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (createBusy) return;
      if (!createForm.name.trim() || !createForm.persona.trim()) return;
      setCreateBusy(true);
      setErrorMessage(null);
      try {
        await createAiEmployee({
          name: createForm.name.trim(),
          persona: createForm.persona.trim(),
          hierarchy_level: createForm.hierarchy_level,
          parent_id: createForm.parent_id.trim() || null,
          department: createForm.department.trim() || "Dev",
        });
        setCreateOpen(false);
        setCreateForm(INITIAL_CREATE_FORM);
        await loadOrgChart();
      } catch (err) {
        surfaceError(err, AI_EMPLOYEES_CREATE_ENDPOINT);
      } finally {
        setCreateBusy(false);
      }
    },
    [createBusy, createForm, loadOrgChart, surfaceError],
  );

  // ----------------------------------------------------------------------
  // AC-F3: POST /api/ai-employees/{id}/clone-from-user.
  // ----------------------------------------------------------------------
  const handleClone = React.useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (cloneBusy) return;
      if (!cloneTargetEmployeeId.trim() || !cloneSourceUserId.trim()) return;
      setCloneBusy(true);
      setErrorMessage(null);
      const endpoint = AI_EMPLOYEES_CLONE_FROM_USER_ENDPOINT(
        cloneTargetEmployeeId.trim(),
      );
      try {
        await cloneAiEmployeeFromUser(cloneTargetEmployeeId.trim(), {
          source_user_id: cloneSourceUserId.trim(),
        });
        setCloneOpen(false);
        setCloneTargetEmployeeId("");
        setCloneSourceUserId("");
        await loadOrgChart();
      } catch (err) {
        surfaceError(err, endpoint);
      } finally {
        setCloneBusy(false);
      }
    },
    [cloneBusy, cloneTargetEmployeeId, cloneSourceUserId, loadOrgChart, surfaceError],
  );

  // ----------------------------------------------------------------------
  // Derived: BMAD personas vs personal clones (mock has two sections).
  // ----------------------------------------------------------------------
  const allNodes = React.useMemo(
    () => flattenTree(orgChart?.tree),
    [orgChart],
  );
  const bmadRoot = orgChart?.tree?.[0];
  const cloneNodes = React.useMemo(
    () => allNodes.filter(isCloneNode),
    [allNodes],
  );

  const filteredNodes = React.useMemo(() => {
    if (departmentFilter === "all") return allNodes.filter((n) => !isCloneNode(n));
    return allNodes.filter(
      (n) => !isCloneNode(n) && (n.department ?? "").toLowerCase() === departmentFilter.toLowerCase(),
    );
  }, [allNodes, departmentFilter]);

  return (
    <div
      data-screen-id="S-036"
      data-feature-id="F-003,F-022"
      data-task-ids="T-V3-C-12,T-V3-RF-18,T-V3-DRIFT-04"
      data-entities="E-034"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-50 text-slate-900 flex"
    >
      {/* Sidebar (matches mock S-036 left nav) */}
      <aside className="w-[240px] bg-eb-700 text-white flex flex-col shrink-0">
        <div className="px-5 py-4 border-b border-eb-600">
          <div className="text-[11px] tracking-widest text-eb-100 font-bold">
            BUILD-FACTORY
          </div>
          <div className="text-sm font-bold mt-1">ENGINE BASE</div>
        </div>
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          <a
            href="/dashboard"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100 text-sm"
          >
            <LayoutDashboard className="w-4 h-4" aria-hidden />
            Account
          </a>
          <div className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold">
            AI Management
          </div>
          <span className="px-3 py-1.5 rounded-md flex items-center gap-2 bg-eb-600 font-semibold text-sm">
            <Users className="w-4 h-4" aria-hidden />
            AI 社員 組織図
          </span>
          <a
            href="/ai-employees/1"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100 text-sm"
          >
            <User className="w-4 h-4" aria-hidden />
            社員詳細
          </a>
          <a
            href="/skills"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100 text-sm"
          >
            <Wrench className="w-4 h-4" aria-hidden />
            スキル管理
          </a>
        </nav>
        <div className="px-4 py-3 border-t border-eb-600">
          <a
            href="/dashboard"
            className="text-[11px] text-eb-100 inline-flex items-center gap-1 hover:text-white"
          >
            <ArrowLeft className="w-3 h-3" aria-hidden />
            ダッシュボードへ戻る
          </a>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="px-6 py-4 border-b border-slate-200 bg-white">
          <div className="flex items-end justify-between">
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2">
                <Users className="w-6 h-6 text-eb-500" aria-hidden />
                AI 社員 組織図
              </h1>
              <p className="text-sm text-slate-600 mt-1">
                BMAD 10 ペルソナ + 個人クローン / 階層構造で表示
              </p>
            </div>
            <div className="flex items-center gap-2">
              <select
                data-testid="department-filter"
                aria-label="部門フィルタ"
                className="border border-slate-200 text-xs h-8 px-2 rounded-md"
                value={departmentFilter}
                onChange={(e) => setDepartmentFilter(e.target.value)}
              >
                <option value="all">全部門</option>
                <option value="Dev">Dev</option>
                <option value="QA">QA</option>
                <option value="Spec">Spec</option>
              </select>
              <button
                type="button"
                data-testid="refresh-org-chart"
                onClick={() => void loadOrgChart()}
                disabled={loading}
                className="bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-sm h-9 px-3 rounded-md font-semibold flex items-center gap-2"
              >
                <RefreshCw className="w-4 h-4" aria-hidden />
                再読み込み
              </button>
              <button
                type="button"
                data-testid="create-employee-open"
                onClick={() => setCreateOpen(true)}
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm h-9 px-4 rounded-md font-semibold flex items-center gap-2"
              >
                <UserPlus className="w-4 h-4" aria-hidden />
                AI 社員を作成
              </button>
            </div>
          </div>
        </div>

        {/* Error banner (AC-F4) */}
        {errorMessage && (
          <div
            role="alert"
            data-testid="org-chart-error"
            className="mx-6 mt-4 p-3 rounded-md bg-amber-50 border border-amber-300 text-amber-800 text-sm flex items-start gap-2"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
            <span>{errorMessage}</span>
          </div>
        )}

        <div className="p-6">
          {/* Loading state */}
          {loading && !orgChart && (
            <div className="text-sm text-slate-500" data-testid="org-chart-loading">
              読み込み中…
            </div>
          )}

          {/* Section 1: BMAD 10 personas tree */}
          {!loading && orgChart && (
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold">
                  BMAD 10 ペルソナ (公式)
                </div>
                <div className="text-[11px] text-slate-500 mono">
                  total: {orgChart.total} / shown: {filteredNodes.length}
                </div>
              </div>
              <div
                data-testid="org-tree"
                className="bg-white border border-slate-200 rounded-lg p-6"
              >
                {bmadRoot ? (
                  <OrgTreeNode node={bmadRoot} depth={0} />
                ) : (
                  <div className="text-sm text-slate-500">
                    非アーカイブ AI 社員はまだ登録されていません。
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Section 2: Personal clones (opt-in) */}
          {!loading && orgChart && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold">
                  個人クローン (opt-in)
                </div>
                <button
                  type="button"
                  data-testid="clone-from-user-open"
                  onClick={() => setCloneOpen(true)}
                  className="text-xs text-eb-500 hover:text-eb-600 font-semibold flex items-center gap-1"
                >
                  <Plus className="w-3 h-3" aria-hidden />
                  ユーザーをクローン
                </button>
              </div>
              <div className="bg-white border border-slate-200 rounded-lg p-5">
                {cloneNodes.length === 0 ? (
                  <div className="text-xs text-slate-500">
                    まだクローンはいません。
                  </div>
                ) : (
                  <ul className="grid grid-cols-4 gap-3">
                    {cloneNodes.map((node) => (
                      <li
                        key={node.id}
                        className="border border-slate-200 rounded-lg p-3 text-center"
                      >
                        <div
                          className={`w-10 h-10 rounded-full text-white text-xs font-bold flex items-center justify-center mx-auto mono mb-2 ${personaTone(node.persona).chip}`}
                        >
                          {personaInitials(node.name)}
                        </div>
                        <div className="text-xs font-bold">{node.name}</div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          {node.persona}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>
      </main>

      {/* AC-F2 dialog: "AI 社員を作成" */}
      {createOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-employee-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40"
          onClick={() => !createBusy && setCreateOpen(false)}
        >
          <form
            onSubmit={handleCreate}
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-lg shadow-xl w-[420px] p-5 space-y-3"
            data-testid="create-employee-form"
          >
            <h2 id="create-employee-title" className="text-base font-bold">
              AI 社員を作成
            </h2>
            <div className="space-y-1.5">
              <label htmlFor="emp-name" className="text-xs font-medium block">
                名前
              </label>
              <input
                id="emp-name"
                type="text"
                value={createForm.name}
                onChange={(e) =>
                  setCreateForm({ ...createForm, name: e.target.value })
                }
                className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm"
                required
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="emp-persona" className="text-xs font-medium block">
                ペルソナ (mary / devon / quinn …)
              </label>
              <input
                id="emp-persona"
                type="text"
                value={createForm.persona}
                onChange={(e) =>
                  setCreateForm({ ...createForm, persona: e.target.value })
                }
                className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm"
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label htmlFor="emp-level" className="text-xs font-medium block">
                  階層 (1..3)
                </label>
                <select
                  id="emp-level"
                  value={createForm.hierarchy_level}
                  onChange={(e) =>
                    setCreateForm({
                      ...createForm,
                      hierarchy_level: Number(e.target.value) as 1 | 2 | 3,
                    })
                  }
                  className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm"
                >
                  <option value={1}>1 (secretary)</option>
                  <option value={2}>2 (leader)</option>
                  <option value={3}>3 (member)</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <label
                  htmlFor="emp-dept"
                  className="text-xs font-medium block"
                >
                  部門
                </label>
                <input
                  id="emp-dept"
                  type="text"
                  value={createForm.department}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, department: e.target.value })
                  }
                  className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="emp-parent" className="text-xs font-medium block">
                親 ID (任意 / UUID)
              </label>
              <input
                id="emp-parent"
                type="text"
                value={createForm.parent_id}
                onChange={(e) =>
                  setCreateForm({ ...createForm, parent_id: e.target.value })
                }
                className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm mono"
                placeholder="(root の場合は空)"
              />
            </div>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                disabled={createBusy}
                className="text-sm h-9 px-3 rounded-md border border-slate-200 hover:bg-slate-50"
              >
                キャンセル
              </button>
              <button
                type="submit"
                data-testid="create-employee-submit"
                disabled={createBusy}
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm h-9 px-4 rounded-md font-semibold"
              >
                {createBusy ? "作成中…" : "作成"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* AC-F3 dialog: "ユーザーをクローン" */}
      {cloneOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="clone-from-user-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40"
          onClick={() => !cloneBusy && setCloneOpen(false)}
        >
          <form
            onSubmit={handleClone}
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-lg shadow-xl w-[420px] p-5 space-y-3"
            data-testid="clone-from-user-form"
          >
            <h2 id="clone-from-user-title" className="text-base font-bold">
              ユーザーをクローン
            </h2>
            <p className="text-xs text-slate-600">
              対象ユーザーが opt-in している場合のみ複製できます。opt-in が
              FALSE の場合、サーバーは 403 を返します。
            </p>
            <div className="space-y-1.5">
              <label htmlFor="clone-emp-id" className="text-xs font-medium block">
                クローン先 AI 社員 ID
              </label>
              <input
                id="clone-emp-id"
                type="text"
                value={cloneTargetEmployeeId}
                onChange={(e) => setCloneTargetEmployeeId(e.target.value)}
                className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm mono"
                required
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="clone-src-id" className="text-xs font-medium block">
                ソース ユーザー ID
              </label>
              <input
                id="clone-src-id"
                type="text"
                value={cloneSourceUserId}
                onChange={(e) => setCloneSourceUserId(e.target.value)}
                className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm mono"
                required
              />
            </div>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setCloneOpen(false)}
                disabled={cloneBusy}
                className="text-sm h-9 px-3 rounded-md border border-slate-200 hover:bg-slate-50"
              >
                キャンセル
              </button>
              <button
                type="submit"
                data-testid="clone-from-user-submit"
                disabled={cloneBusy}
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm h-9 px-4 rounded-md font-semibold"
              >
                {cloneBusy ? "実行中…" : "クローン実行"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Tree node — recursive render of the hierarchical org chart.
// --------------------------------------------------------------------------

function OrgTreeNode({ node, depth }: { node: AiEmployeeNode; depth: number }) {
  const tone = personaTone(node.persona);
  return (
    <div
      className={depth === 0 ? "" : "ml-6 mt-3 pl-4 border-l border-slate-200"}
      data-testid={`org-node-${node.id}`}
    >
      <div
        className={`inline-flex items-center gap-2 rounded-lg border ${tone.bg} ${tone.border} p-2.5`}
      >
        <div
          className={`w-9 h-9 rounded-full text-white text-xs font-bold flex items-center justify-center mono ${tone.chip}`}
        >
          {personaInitials(node.name)}
        </div>
        <div>
          <div className="text-sm font-bold">{node.name}</div>
          <div className="text-[10px] text-slate-500">
            {node.persona}
            {node.department ? ` · ${node.department}` : ""} · L
            {node.hierarchy_level}
          </div>
        </div>
      </div>
      {node.children && node.children.length > 0 && (
        <ul className="mt-2 space-y-2" data-testid={`org-children-${node.id}`}>
          {node.children.map((child) => (
            <li key={child.id}>
              <OrgTreeNode node={child} depth={depth + 1} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
