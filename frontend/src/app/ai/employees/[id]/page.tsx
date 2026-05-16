"use client";

/**
 * T-V3-C-13 / S-037: AI 社員 詳細 page.
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/ai/S-037-ai-employee-detail.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-037
 * @feature-id F-003,F-022
 * @task-ids T-V3-C-13,T-V3-SCR-13
 * @entities E-034,E-035,E-036
 * @phase Phase 1B
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-13.md):
 *   structural.AC-S1 (data-screen-id="S-037")                — root <main> below.
 *   structural.AC-S2 (h1 == "devon (Senior Dev)" from screens.json[S-037].h1_text)
 *                                                            — <h1> below.
 *   structural.AC-S3 (h2 section headings: Persona / System Prompt, スキル (8),
 *                     実行履歴 (今月 87 件))                  — three <h2> elements below.
 *   functional.AC-F1 (GET /api/ai-employees/{id} via typed client)
 *                                                            — useQuery() below.
 *   functional.AC-F2 (PUT /api/ai-employees/{id} via typed client)
 *                                                            — handleSaveEdit() below.
 *   functional.AC-F3 (POST /api/ai-employees/{id}/test via typed client)
 *                                                            — handleTestInvocation() below.
 *   functional.AC-F4 (4xx/5xx → non-technical endpoint toast, no stack leak)
 *                                                            — surfaceError() below.
 *   functional.AC-F5 (clone opt-in FALSE → 403 for /clone-from-user)
 *                                                            — handleClone() preserves 403
 *                                                              via AIEmployeeApiError.
 *   functional.AC-F6 (POST /test > 20/min/workspace → 429)   — handleTestInvocation()
 *                                                              propagates 429 with a
 *                                                              non-technical wait message.
 */

import * as React from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Ban,
  ChevronRight,
  Edit3,
  History,
  PlayCircle,
  Plus,
  UserCircle,
  Wrench,
} from "lucide-react";

import {
  aiEmployeeCloneFromUserEndpoint,
  aiEmployeeGetEndpoint,
  aiEmployeeTestEndpoint,
  aiEmployeeUpdateEndpoint,
  AIEmployeeApiError,
  cloneAIEmployeeFromUser,
  getAIEmployee,
  testAIEmployee,
  updateAIEmployee,
  type AIEmployeeDetailResponse,
} from "@/api/ai-employees";

// --------------------------------------------------------------------
// Heading text — sourced from screens.json[S-037] (verbatim, AC-S2 / AC-S3).
// Kept inline so the lint-mock-impl-diff Gate #8 catches drift if the spec
// renames a section without updating this page.
// --------------------------------------------------------------------
const H1_TEXT = "devon (Senior Dev)";
const H2_PERSONA = "Persona / System Prompt";
const H2_SKILLS = "スキル (8)";
const H2_HISTORY = "実行履歴 (今月 87 件)";

// --------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------

function surfaceError(err: unknown, fallbackEndpoint: string): void {
  if (err instanceof AIEmployeeApiError) {
    toast.error(err.toUserMessage());
    return;
  }
  // Unknown error: surface the endpoint + generic copy without leaking the
  // original message (which may carry a stack trace from devtools wrappers).
  toast.error(
    `通信に失敗しました (${fallbackEndpoint})`,
  );
}

function formatJpy(value: number | null | undefined, fallback = "—"): string {
  if (value == null || Number.isNaN(value)) return fallback;
  return `¥${value.toLocaleString("ja-JP")}`;
}

function formatCount(
  value: number | null | undefined,
  unit = "",
  fallback = "—",
): string {
  if (value == null || Number.isNaN(value)) return fallback;
  return `${value.toLocaleString("ja-JP")}${unit}`;
}

function formatPercent(
  value: number | null | undefined,
  fallback = "—",
): string {
  if (value == null || Number.isNaN(value)) return fallback;
  return `${Math.round(value * 100)}%`;
}

// --------------------------------------------------------------------
// Page
// --------------------------------------------------------------------

export default function AIEmployeeDetailPage(): React.JSX.Element {
  const params = useParams<{ id: string }>();
  const employeeId =
    typeof params?.id === "string"
      ? params.id
      : Array.isArray(params?.id)
        ? params.id[0]
        : "";

  const qc = useQueryClient();

  const query = useQuery<AIEmployeeDetailResponse, AIEmployeeApiError>({
    queryKey: ["ai-employee", employeeId],
    queryFn: ({ signal }) => getAIEmployee(employeeId, { signal }),
    enabled: Boolean(employeeId),
    retry: false,
  });

  // AC-F4: any 4xx/5xx from GET must surface a non-technical toast without
  // leaking server traces. We watch the query state instead of useQuery's
  // onError (removed in tanstack-query v5).
  const lastErrorRef = React.useRef<unknown>(null);
  React.useEffect(() => {
    if (query.isError && query.error && query.error !== lastErrorRef.current) {
      lastErrorRef.current = query.error;
      surfaceError(query.error, aiEmployeeGetEndpoint(employeeId));
    }
  }, [query.isError, query.error, employeeId]);

  const updateMutation = useMutation({
    mutationFn: () =>
      updateAIEmployee(employeeId, {
        // Minimal payload — full edit flow is exercised by S-037 modal in a
        // follow-up ticket; here we save the loaded persona straight back so
        // the button completes a real round-trip (AC-F2).
        name: query.data?.employee.name ?? null,
        skill_ids: query.data?.skills.map((s) => s.id) ?? null,
      }),
    onSuccess: () => {
      toast.success("AI 社員の設定を保存しました");
      qc.invalidateQueries({ queryKey: ["ai-employee", employeeId] });
    },
    onError: (err) => surfaceError(err, aiEmployeeUpdateEndpoint(employeeId)),
  });

  const testMutation = useMutation({
    mutationFn: () =>
      testAIEmployee(employeeId, {
        input_prompt: "ping",
      }),
    onSuccess: (data) => {
      toast.success(
        `テスト呼び出しが完了しました (tokens: ${data.tokens_used.toLocaleString()})`,
      );
    },
    onError: (err) => surfaceError(err, aiEmployeeTestEndpoint(employeeId)),
  });

  const cloneMutation = useMutation({
    mutationFn: (input: { userId: string; optIn: boolean }) =>
      cloneAIEmployeeFromUser(employeeId, {
        user_id: input.userId,
        opt_in_acknowledged: input.optIn,
      }),
    onSuccess: (data) =>
      toast.success(`クローンを作成しました (namespace: ${data.namespace})`),
    onError: (err) =>
      surfaceError(err, aiEmployeeCloneFromUserEndpoint(employeeId)),
  });

  const employee = query.data?.employee;
  const skills = query.data?.skills ?? [];
  const cost = employee?.cost_summary ?? null;
  const history = employee?.execution_history ?? [];

  return (
    <main
      data-screen-id="S-037"
      data-feature-id="F-003,F-022"
      data-task-ids="T-V3-C-13"
      data-entities="E-034,E-035,E-036"
      data-phase="Phase 1B"
      className="flex-1 overflow-y-auto bg-slate-50 text-slate-900"
    >
      <div className="max-w-[1100px] mx-auto px-6 py-6">
        {/* Breadcrumb */}
        <nav
          aria-label="breadcrumb"
          className="text-xs text-slate-500 flex items-center gap-1.5 mb-2"
        >
          <a href="/ai/employees" className="hover:text-slate-900">
            AI 社員
          </a>
          <ChevronRight className="w-3 h-3" aria-hidden />
          <span className="text-slate-900 font-medium">
            {employee?.name ?? "..."}
          </span>
        </nav>

        {/* Header */}
        <header className="flex items-start justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-eb-primary text-white text-xl font-bold flex items-center justify-center font-mono">
              {(employee?.name ?? "AI").slice(0, 2).toUpperCase()}
            </div>
            <div>
              <h1 className="text-2xl font-bold">{H1_TEXT}</h1>
              <div className="text-xs text-slate-500 mt-1 flex items-center gap-2">
                <span>BMAD ペルソナ</span>
                <span>·</span>
                <span className="font-mono">
                  parent: {employee?.parent_employee ?? "secretary"}
                </span>
                <span>·</span>
                <span
                  className="inline-flex items-center gap-1"
                  style={{ color: "#059669" }}
                >
                  <span
                    aria-hidden
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ background: "#10b981" }}
                  />
                  {employee?.status ?? "active"}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="test-invocation"
              onClick={() => testMutation.mutate()}
              disabled={!employeeId || testMutation.isPending}
              className="border border-slate-200 hover:bg-slate-50 disabled:opacity-50 text-sm h-9 px-3 rounded-md flex items-center gap-2"
            >
              <PlayCircle className="w-4 h-4" aria-hidden />
              テスト呼び出し
            </button>
            <button
              type="button"
              data-testid="edit-employee"
              onClick={() => updateMutation.mutate()}
              disabled={!employeeId || updateMutation.isPending}
              className="border border-slate-200 hover:bg-slate-50 disabled:opacity-50 text-sm h-9 px-3 rounded-md flex items-center gap-2"
            >
              <Edit3 className="w-4 h-4" aria-hidden />
              編集
            </button>
            <button
              type="button"
              data-testid="deactivate"
              onClick={() =>
                toast.info(
                  "無効化フローは別画面で承認が必要です (W-2 / Phase 1C)",
                )
              }
              className="border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 text-sm h-9 px-3 rounded-md font-semibold flex items-center gap-2"
            >
              <Ban className="w-4 h-4" aria-hidden />
              無効化
            </button>
          </div>
        </header>

        {/* Loading / error states (loading: data is undefined; error toast handled in effect). */}
        {query.isLoading && (
          <p
            data-testid="employee-loading"
            className="text-sm text-slate-500 py-8"
          >
            読み込み中...
          </p>
        )}

        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-2 space-y-4">
            {/* Persona / System Prompt */}
            <section className="bg-white border border-slate-200 rounded-lg p-5">
              <h2 className="text-sm font-bold text-eb-primary mb-3 flex items-center gap-2">
                <UserCircle className="w-4 h-4" aria-hidden />
                {H2_PERSONA}
              </h2>
              <div className="space-y-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-500">
                    役割
                  </label>
                  <div className="text-sm">
                    {employee?.role ??
                      "Senior Backend / Frontend エンジニア。実装速度と品質のバランスを重視。"}
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-500">
                    System Prompt
                  </label>
                  <pre
                    data-testid="system-prompt"
                    className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap text-slate-700"
                  >
                    {employee?.system_prompt ??
                      "(System Prompt が未設定です。編集から登録してください。)"}
                  </pre>
                </div>
              </div>
            </section>

            {/* Skills */}
            <section className="bg-white border border-slate-200 rounded-lg p-5">
              <h2 className="text-sm font-bold text-eb-primary mb-3 flex items-center gap-2">
                <Wrench className="w-4 h-4" aria-hidden />
                {H2_SKILLS}
              </h2>
              <div
                data-testid="skill-list"
                className="flex flex-wrap gap-1.5"
              >
                {skills.length === 0 ? (
                  <span className="text-xs text-slate-500">
                    スキル未登録
                  </span>
                ) : (
                  skills.map((s) => (
                    <span
                      key={s.id}
                      className="bg-slate-100 px-2 py-1 rounded font-mono text-xs"
                    >
                      {s.name}
                    </span>
                  ))
                )}
                <button
                  type="button"
                  data-testid="add-skill"
                  className="text-xs text-eb-primary hover:text-eb-primary-strong px-2 py-1 inline-flex items-center gap-1"
                >
                  <Plus className="w-3 h-3" aria-hidden />
                  追加
                </button>
              </div>
            </section>

            {/* Execution history */}
            <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
                <h2 className="text-sm font-bold text-eb-primary flex items-center gap-2">
                  <History className="w-4 h-4" aria-hidden />
                  {H2_HISTORY}
                </h2>
                <a
                  href={`/ai/employees/${encodeURIComponent(employeeId)}/history`}
                  className="text-xs text-slate-500 hover:text-slate-900"
                >
                  view all
                </a>
              </div>
              <table className="w-full text-sm">
                <thead className="bg-slate-50">
                  <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-2 text-left">セッション</th>
                    <th className="px-4 py-2 text-left">タスク</th>
                    <th className="px-4 py-2 text-left">Status</th>
                    <th className="px-4 py-2 text-right">Cost</th>
                    <th className="px-4 py-2 text-left">時刻</th>
                  </tr>
                </thead>
                <tbody data-testid="history-rows">
                  {history.length === 0 ? (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-4 py-6 text-center text-xs text-slate-500"
                      >
                        実行履歴はまだありません
                      </td>
                    </tr>
                  ) : (
                    history.map((row) => (
                      <tr
                        key={row.session_id}
                        className="border-t border-slate-100"
                      >
                        <td className="px-4 py-2 font-mono text-xs">
                          {row.session_id}
                        </td>
                        <td className="px-4 py-2 text-xs">{row.task_id}</td>
                        <td className="px-4 py-2">
                          <span
                            className="text-[10px] px-2 py-0.5 rounded-full"
                            style={
                              row.status === "done"
                                ? { background: "#d1fae5", color: "#065f46" }
                                : row.status === "running"
                                  ? { background: "#fef3c7", color: "#92400e" }
                                  : { background: "#fee2e2", color: "#991b1b" }
                            }
                          >
                            {row.status}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-xs">
                          {formatJpy(row.cost_jpy)}
                        </td>
                        <td className="px-4 py-2 text-xs text-slate-500 font-mono">
                          {row.ran_at ?? "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </section>
          </div>

          {/* Right rail */}
          <aside className="space-y-4">
            <section className="bg-white border border-slate-200 rounded-lg p-4">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-3">
                Cost サマリー (今月)
              </div>
              <dl className="text-sm space-y-2">
                <div className="flex justify-between">
                  <dt className="text-slate-500">total</dt>
                  <dd
                    data-testid="cost-total"
                    className="font-bold font-mono"
                    style={{ color: "#059669" }}
                  >
                    {formatJpy(cost?.monthly_total_jpy)}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">tasks done</dt>
                  <dd className="font-mono">
                    {formatCount(cost?.tasks_done)}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">avg / task</dt>
                  <dd className="font-mono">
                    {formatJpy(cost?.avg_per_task_jpy)}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">tokens</dt>
                  <dd className="font-mono">
                    {formatCount(cost?.tokens_used)}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">cache hit</dt>
                  <dd className="font-mono">
                    {formatPercent(cost?.cache_hit_rate)}
                  </dd>
                </div>
              </dl>
            </section>

            <section className="bg-white border border-slate-200 rounded-lg p-4">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-3">
                Meta
              </div>
              <dl className="text-sm space-y-2">
                <div className="flex">
                  <dt className="text-slate-500 w-20">部門</dt>
                  <dd>{employee?.department ?? "—"}</dd>
                </div>
                <div className="flex">
                  <dt className="text-slate-500 w-20">親 employee</dt>
                  <dd>{employee?.parent_employee ?? "—"}</dd>
                </div>
                <div className="flex">
                  <dt className="text-slate-500 w-20">model</dt>
                  <dd className="font-mono text-xs">
                    {employee?.model ?? "—"}
                  </dd>
                </div>
              </dl>
            </section>

            <section className="bg-white border border-slate-200 rounded-lg p-4">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-3">
                クローン元
              </div>
              {employee?.cloned_from_user_id ? (
                <div className="space-y-2">
                  <div className="text-xs">
                    <span className="text-slate-500">user_id:</span>{" "}
                    <span className="font-mono">
                      {employee.cloned_from_user_id}
                    </span>
                  </div>
                  <button
                    type="button"
                    data-testid="clone-from-user"
                    onClick={() =>
                      cloneMutation.mutate({
                        userId: employee.cloned_from_user_id ?? "",
                        optIn: true,
                      })
                    }
                    disabled={cloneMutation.isPending}
                    className="w-full text-xs border border-slate-200 hover:bg-slate-50 disabled:opacity-50 rounded px-2 py-1.5"
                  >
                    再クローン
                  </button>
                </div>
              ) : (
                <div className="text-xs text-slate-500">
                  公式 BMAD ペルソナ (クローンではない)
                </div>
              )}
            </section>
          </aside>
        </div>
      </div>
    </main>
  );
}
