"use client";

/**
 * T-V3-C-45 / S-035: 納品承認 page (Vertical Slice UI).
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/review/S-035-delivery-approval.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-035
 * @feature-id F-013,F-015
 * @task-ids T-V3-C-45
 * @entities E-018
 * @phase Phase 1
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-45.md):
 *   structural.AC-S1 — h1 == "納品承認" (matches the mock h1).
 *   structural.AC-S2 — section h2 set == {Phase 1 dogfood セットアップ完成 /
 *                       納品 Checklist / テスト結果サマリー /
 *                       納品成果物 HTML プレビュー / クライアント受入状況}.
 *   structural.AC-S3 — Lucide icons exclusively (no emoji glyphs).
 *   functional.AC-F1 — On mount, GET /api/workspaces/{id}/delivery via the typed
 *                       client; 2xx body renders into the page, 4xx surfaces an
 *                       inline error toast + empty state.
 *   functional.AC-F2 — UNWANTED: 401 → router.replace("/login") and no
 *                       workspace-scoped data is rendered before the redirect.
 *   functional.AC-F3 — Calls POST /api/workspaces/{id}/delivery/approve via the
 *                       typed client when the "承認 → クライアント送付" CTA is
 *                       fired. Backend AC enforces workspace_admin + pr_merged
 *                       audit log emission.
 *   functional.AC-F4 — Calls POST /api/workspaces/{id}/delivery/send-client to
 *                       queue the delivery report email when the "送付する"
 *                       button is fired. Backend returns delivery_token + sent_at.
 *
 * NOTE on path: The ticket card lists `frontend/app/s-035-delivery-approval/`
 * as the canonical path but the worktree directive for this session pins the
 * page at `frontend/src/app/(app)/review/delivery/[id]/page.tsx`. Both routes
 * resolve to the same Next.js App Router page; the dynamic [id] segment is
 * read as the workspace id.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AlertCircle,
  ArrowLeft,
  BarChart3,
  Check,
  CheckCircle2,
  Circle,
  Download,
  ExternalLink,
  FileText,
  ListChecks,
  Loader2,
  PackageCheck,
  RotateCcw,
  Send,
  UserCheck,
} from "lucide-react";

import {
  DeliveryApprovalApiError,
  workspaceDeliveryEndpoint,
  workspaceDeliveryApproveEndpoint,
  workspaceDeliverySendClientEndpoint,
  type Delivery,
  type DeliveryChecklistItem,
  type DeliveryTestSummary,
} from "@/lib/api/delivery-approval";
import {
  useApproveDelivery,
  useDeliveryQuery,
  useSendDeliveryToClient,
} from "@/lib/hooks/use-delivery-approval";

// --------------------------------------------------------------------------
// Static copy — verbatim from docs/mocks/2026-05-15_v3/review/S-035-*.html and
// docs/functional-breakdown/2026-05-16_v3/screens.json#S-035.
// Keeping these top-level so lint-mock-impl-diff Gate #8 can grep them.
// --------------------------------------------------------------------------

const SCREEN_H1_TEXT = "納品承認";

const SECTION_H2_TEXTS: readonly string[] = [
  "Phase 1 dogfood セットアップ完成",
  "納品 Checklist",
  "テスト結果サマリー",
  "納品成果物 HTML プレビュー",
  "クライアント受入状況",
];

// --------------------------------------------------------------------------
// Fallback content — mirrors the static mock. Renders while the backend
// payload is still empty (e.g. when the page is opened in design-review mode
// without a workspace_id). Once the backend supplies fields, those take
// precedence, but the fallback keeps the mock's design intact.
// --------------------------------------------------------------------------

const FALLBACK_CHECKLIST: readonly DeliveryChecklistItem[] = [
  {
    id: "all-tasks-done",
    label: "全 main task が done",
    status: "ok",
    detail: "23 / 23",
  },
  {
    id: "no-redline-breach",
    label: "赤線抵触 = 0",
    status: "ok",
    detail: "過去 7 日 / 0 件",
  },
  {
    id: "tests-pass",
    label: "unit + integration test PASS",
    status: "ok",
    detail: "8000 / 8010 PASS · 10 skipped · 0 failed · coverage 84%",
  },
  {
    id: "lint-pass",
    label: "lint #1〜19 全 PASS",
    status: "ok",
    detail: "19 / 19",
  },
  {
    id: "client-acceptance",
    label: "クライアント受入確認",
    status: "warning",
    detail: "未送付",
    actionable: true,
  },
  {
    id: "delivery-pdf",
    label: "納品 PDF 生成",
    status: "pending",
    detail: "未実行",
    actionable: true,
  },
];

const FALLBACK_TEST_SUMMARY: DeliveryTestSummary = {
  unit_pass: 8000,
  unit_total: 8010,
  unit_skipped: 10,
  integration_pass: 187,
  integration_total: 187,
  e2e_pass: 42,
  e2e_total: 42,
  coverage_pct: 84,
};

const FALLBACK_REPORT_ITEMS: readonly string[] = [
  "23 task 完了 (T-V3-INFRA-* / T-V3-AUTH-* / T-V3-DB-* 系)",
  "Vercel + Cloudflare Tunnel + Supabase Pooler セットアップ完了",
  "frontend / backend / DB 全レイヤー稼働確認",
  "test 8000 PASS / coverage 84% / lint 19/19 OK",
];

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function fmtNumber(n: number | null | undefined, fallback = "—"): string {
  if (n === null || n === undefined) return fallback;
  if (!Number.isFinite(n)) return fallback;
  return n.toLocaleString();
}

function fmtPercent(n: number | null | undefined, fallback = "—"): string {
  if (n === null || n === undefined) return fallback;
  if (!Number.isFinite(n)) return fallback;
  return `${Math.round(n)}%`;
}

function checklistIcon(status: DeliveryChecklistItem["status"]) {
  if (status === "ok") {
    return (
      <CheckCircle2
        className="w-5 h-5 text-emerald-600 shrink-0"
        aria-hidden
      />
    );
  }
  if (status === "warning") {
    return (
      <AlertCircle className="w-5 h-5 text-amber-600 shrink-0" aria-hidden />
    );
  }
  return <Circle className="w-5 h-5 text-slate-400 shrink-0" aria-hidden />;
}

function checklistRowClass(status: DeliveryChecklistItem["status"]): string {
  const base = "flex items-center gap-3 p-3 border rounded-md";
  if (status === "warning") {
    return `${base} border-amber-200 bg-amber-50`;
  }
  if (status === "pending") {
    return `${base} border-slate-200 opacity-60`;
  }
  return `${base} border-slate-200`;
}

function isClientAcceptanceItem(item: DeliveryChecklistItem): boolean {
  return item.id === "client-acceptance" || /クライアント受入/.test(item.label);
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function DeliveryApprovalPage(): React.JSX.Element {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const workspaceId = String(params?.id ?? "");

  const deliveryQuery = useDeliveryQuery(workspaceId);
  const approveMutation = useApproveDelivery(workspaceId);
  const sendClientMutation = useSendDeliveryToClient(workspaceId);

  // AC-F2: 401 → redirect to /login, never rendering workspace-scoped data.
  const isUnauthorised =
    deliveryQuery.isError &&
    deliveryQuery.error instanceof DeliveryApprovalApiError &&
    deliveryQuery.error.status === 401;

  React.useEffect(() => {
    if (isUnauthorised) {
      router.replace("/login");
    }
  }, [isUnauthorised, router]);

  // AC-F1: surface a non-technical toast for any other 4xx / 5xx (no stack
  // traces). The toast is debounced to a single instance per error message.
  const lastToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!deliveryQuery.isError) {
      lastToastRef.current = null;
      return;
    }
    if (isUnauthorised) return;
    const err = deliveryQuery.error;
    const endpoint = workspaceDeliveryEndpoint(workspaceId || "{id}");
    const userMsg =
      err instanceof DeliveryApprovalApiError
        ? err.toUserMessage()
        : `納品データの取得に失敗しました (${endpoint})`;
    if (lastToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastToastRef.current = userMsg;
    }
  }, [
    deliveryQuery.isError,
    deliveryQuery.error,
    workspaceId,
    isUnauthorised,
  ]);

  // ----------------------------------------------------------------------
  // Mutation handlers (AC-F3 / AC-F4).
  // ----------------------------------------------------------------------

  const handleApprove = React.useCallback(() => {
    if (!workspaceId || approveMutation.isPending) return;
    approveMutation.mutate(undefined, {
      onSuccess: () => {
        toast.success("納品を承認しました。クライアントへ送付を続けます。");
        // Continue with send-client so the CTA matches the mock label
        // "承認 → クライアント送付".
        sendClientMutation.mutate(undefined, {
          onSuccess: () => {
            toast.success("クライアントへ送付しました");
          },
          onError: (err) => {
            const endpoint = workspaceDeliverySendClientEndpoint(
              workspaceId || "{id}",
            );
            const userMsg =
              err instanceof DeliveryApprovalApiError
                ? err.toUserMessage()
                : `クライアントへの送付に失敗しました (${endpoint})`;
            toast.error(userMsg);
          },
        });
      },
      onError: (err) => {
        const endpoint = workspaceDeliveryApproveEndpoint(
          workspaceId || "{id}",
        );
        const userMsg =
          err instanceof DeliveryApprovalApiError
            ? err.toUserMessage()
            : `承認に失敗しました (${endpoint})`;
        toast.error(userMsg);
      },
    });
  }, [workspaceId, approveMutation, sendClientMutation]);

  const handleSendClientOnly = React.useCallback(() => {
    if (!workspaceId || sendClientMutation.isPending) return;
    sendClientMutation.mutate(undefined, {
      onSuccess: () => {
        toast.success("クライアントへ送付しました");
      },
      onError: (err) => {
        const endpoint = workspaceDeliverySendClientEndpoint(
          workspaceId || "{id}",
        );
        const userMsg =
          err instanceof DeliveryApprovalApiError
            ? err.toUserMessage()
            : `クライアントへの送付に失敗しました (${endpoint})`;
        toast.error(userMsg);
      },
    });
  }, [workspaceId, sendClientMutation]);

  const handleRequestRevision = React.useCallback(() => {
    // Future hook: POST /api/workspaces/{id}/delivery/request-revision (out of
    // scope for T-V3-C-45 backend). For now, surface a friendly notice so the
    // button stays accessible per the mock.
    toast.info("修正依頼フローは Phase 1.5 で実装されます");
  }, []);

  // ----------------------------------------------------------------------
  // Derived view-model.
  // ----------------------------------------------------------------------

  // AC-F2 second-half guarantee — never render workspace-scoped data once
  // we know the visitor is unauthenticated.
  if (isUnauthorised) {
    return (
      <div
        data-screen-id="S-035"
        data-feature-id="F-013,F-015"
        data-task-ids="T-V3-C-45"
        data-entities="E-018"
        data-phase="Phase 1"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  const delivery: Delivery | undefined = deliveryQuery.data?.delivery;

  const phaseLabel = delivery?.phase_label ?? SECTION_H2_TEXTS[0];
  const projectLabel = delivery?.project_label ?? "Build-Factory dogfood";
  const readinessPct = delivery?.readiness_pct ?? 87;
  const tasksDone = delivery?.tasks_done ?? 23;
  const tasksTotal = delivery?.tasks_total ?? 36;
  const dueDate = delivery?.due_date ?? "2026-05-15";

  const checklist: readonly DeliveryChecklistItem[] =
    delivery?.checklist && delivery.checklist.length > 0
      ? delivery.checklist
      : FALLBACK_CHECKLIST;

  const testSummary: DeliveryTestSummary =
    delivery?.test_summary ?? FALLBACK_TEST_SUMMARY;

  const reportItems: readonly string[] =
    delivery?.report_items && delivery.report_items.length > 0
      ? delivery.report_items
      : FALLBACK_REPORT_ITEMS;

  const isEmptyState =
    deliveryQuery.isError && !isUnauthorised && !delivery;

  return (
    <div
      data-screen-id="S-035"
      data-feature-id="F-013,F-015"
      data-task-ids="T-V3-C-45"
      data-entities="E-018"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900 flex"
    >
      <aside className="w-[240px] bg-eb-700 text-white flex flex-col shrink-0">
        <div className="px-5 py-4 border-b border-eb-600">
          <div className="text-[11px] tracking-widest text-eb-100 font-bold">
            BUILD-FACTORY
          </div>
          <div className="text-sm font-bold mt-1">{projectLabel}</div>
        </div>
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          <a
            href={`/workspaces/${encodeURIComponent(workspaceId)}`}
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100 text-sm"
          >
            <ArrowLeft className="w-4 h-4" aria-hidden /> ダッシュボードへ
          </a>
          <div className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold">
            Review
          </div>
          <div className="px-3 py-1.5 rounded-md flex items-center gap-2 bg-eb-600 font-semibold text-sm">
            <PackageCheck className="w-4 h-4" aria-hidden /> 納品承認
          </div>
        </nav>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-[1100px] mx-auto px-6 py-6">
          <div className="flex items-end justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2">
                <PackageCheck
                  className="w-6 h-6 text-eb-500"
                  aria-hidden
                />
                {SCREEN_H1_TEXT}
              </h1>
              <p className="text-sm text-slate-600 mt-1">
                Phase 完了時の最終チェック / クライアント送付
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                data-testid="request-revision-button"
                onClick={handleRequestRevision}
                className="border border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-700 text-sm h-9 px-3 rounded-md font-semibold flex items-center gap-2"
              >
                <RotateCcw className="w-4 h-4" aria-hidden />
                修正依頼
              </button>
              <button
                type="button"
                data-testid="approve-and-send-button"
                onClick={handleApprove}
                disabled={
                  !workspaceId ||
                  approveMutation.isPending ||
                  sendClientMutation.isPending
                }
                className="bg-eb-500 hover:bg-eb-600 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm h-9 px-4 rounded-md font-semibold flex items-center gap-2"
              >
                {approveMutation.isPending || sendClientMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
                ) : (
                  <Check className="w-4 h-4" aria-hidden />
                )}
                承認 → クライアント送付
              </button>
            </div>
          </div>

          {deliveryQuery.isPending && !!workspaceId && (
            <div
              data-state="loading"
              role="status"
              aria-live="polite"
              data-testid="delivery-loading"
              className="flex items-center justify-center py-16 text-slate-500 gap-2"
            >
              <Loader2
                className="w-5 h-5 animate-spin text-eb-500"
                aria-hidden
              />
              <span className="text-sm">納品データを読み込み中...</span>
            </div>
          )}

          {isEmptyState && (
            <div
              role="alert"
              data-testid="delivery-empty-state"
              className="rounded-md border border-amber-200 bg-amber-50 p-4 mb-4 text-sm text-amber-800 flex items-start gap-2"
            >
              <AlertCircle
                className="w-5 h-5 text-amber-600 shrink-0"
                aria-hidden
              />
              <div>
                納品データを取得できませんでした。後でもう一度お試しください。
              </div>
            </div>
          )}

          {/* Section 1 — Overall status (h2 #1) */}
          <section
            className="bg-white border border-eb-200 rounded-lg p-5 mb-4 ring-2 ring-eb-100"
            data-section-id="overall-status"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold">
                  Phase 1 納品準備
                </div>
                <h2 className="text-lg font-bold mt-1">{phaseLabel}</h2>
                <p className="text-xs text-slate-600 mt-1">
                  {projectLabel} / {fmtNumber(tasksDone)} /{" "}
                  {fmtNumber(tasksTotal)} task done · {dueDate} 期限
                </p>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold tabular text-eb-500">
                  {fmtNumber(readinessPct, "—")}
                  <span className="text-sm font-normal">%</span>
                </div>
                <div className="text-xs text-slate-500">準備完了</div>
              </div>
            </div>
            <div className="mt-3 h-2 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-eb-500"
                style={{ width: `${Math.max(0, Math.min(100, readinessPct ?? 0))}%` }}
              />
            </div>
          </section>

          {/* Section 2 — Checklist (h2 #2) */}
          <section
            className="bg-white border border-slate-200 rounded-lg p-5 mb-4"
            data-section-id="checklist"
          >
            <h2 className="text-base font-bold mb-4 flex items-center gap-2">
              <ListChecks className="w-5 h-5 text-eb-500" aria-hidden />
              {SECTION_H2_TEXTS[1]}
            </h2>
            <div className="space-y-2">
              {checklist.map((item) => (
                <div
                  key={item.id}
                  className={checklistRowClass(item.status)}
                  data-testid={`checklist-${item.id}`}
                >
                  {checklistIcon(item.status)}
                  <div className="flex-1">
                    <div className="text-sm font-semibold">{item.label}</div>
                    {item.detail ? (
                      <div className="text-xs text-slate-500 mono flex items-center gap-1">
                        {item.detail}
                        {item.status === "ok" ? (
                          <Check
                            className="w-3 h-3 text-emerald-600"
                            aria-hidden
                          />
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                  {item.actionable && isClientAcceptanceItem(item) ? (
                    <button
                      type="button"
                      data-testid="send-client-button"
                      onClick={handleSendClientOnly}
                      disabled={
                        !workspaceId || sendClientMutation.isPending
                      }
                      className="bg-amber-500 hover:bg-amber-600 disabled:opacity-60 disabled:cursor-not-allowed text-white text-xs h-8 px-3 rounded-md font-semibold flex items-center gap-1"
                    >
                      {sendClientMutation.isPending ? (
                        <Loader2 className="w-3 h-3 animate-spin" aria-hidden />
                      ) : (
                        <Send className="w-3 h-3" aria-hidden />
                      )}
                      送付する
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          {/* Section 3 — Test summary (h2 #3) */}
          <section
            className="bg-white border border-slate-200 rounded-lg p-5 mb-4"
            data-section-id="test-summary"
          >
            <h2 className="text-base font-bold mb-3 flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-eb-500" aria-hidden />
              {SECTION_H2_TEXTS[2]}
            </h2>
            <div className="grid grid-cols-4 gap-3">
              <div className="border border-slate-200 rounded-md p-3">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                  Unit
                </div>
                <div className="text-xl font-bold tabular text-emerald-600">
                  {fmtNumber(testSummary.unit_pass)}
                  <span className="text-xs text-slate-500">
                    {" "}
                    /{fmtNumber(testSummary.unit_total)}
                  </span>
                </div>
                {testSummary.unit_skipped ? (
                  <div className="text-xs text-slate-500">
                    {fmtNumber(testSummary.unit_skipped)} skipped
                  </div>
                ) : null}
              </div>
              <div className="border border-slate-200 rounded-md p-3">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                  Integration
                </div>
                <div className="text-xl font-bold tabular text-emerald-600">
                  {fmtNumber(testSummary.integration_pass)}
                  <span className="text-xs text-slate-500">
                    {" "}
                    /{fmtNumber(testSummary.integration_total)}
                  </span>
                </div>
              </div>
              <div className="border border-slate-200 rounded-md p-3">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                  E2E
                </div>
                <div className="text-xl font-bold tabular text-emerald-600">
                  {fmtNumber(testSummary.e2e_pass)}
                  <span className="text-xs text-slate-500">
                    {" "}
                    /{fmtNumber(testSummary.e2e_total)}
                  </span>
                </div>
              </div>
              <div className="border border-slate-200 rounded-md p-3">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                  Coverage
                </div>
                <div className="text-xl font-bold tabular text-eb-500">
                  {fmtPercent(testSummary.coverage_pct)}
                </div>
                <div className="text-xs text-slate-500">target 70%</div>
              </div>
            </div>
          </section>

          {/* Section 4 — Delivery HTML preview (h2 #4) */}
          <section
            className="bg-white border border-slate-200 rounded-lg p-5 mb-4"
            data-section-id="html-preview"
          >
            <h2 className="text-base font-bold mb-3 flex items-center gap-2">
              <FileText className="w-5 h-5 text-eb-500" aria-hidden />
              {SECTION_H2_TEXTS[3]}
            </h2>
            <div className="bg-slate-50 border border-slate-200 rounded-md p-4 text-sm">
              <h3 className="text-base font-bold border-b border-slate-300 pb-2 mb-2">
                {phaseLabel}
              </h3>
              <p className="text-xs text-slate-700 mb-2">
                {dueDate} / {projectLabel}
              </p>
              <ul className="text-xs space-y-1 list-disc pl-5 text-slate-700">
                {reportItems.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
            <div className="flex gap-2 mt-3">
              <button
                type="button"
                className="border border-slate-200 hover:bg-slate-50 text-xs h-8 px-3 rounded-md flex items-center gap-1"
              >
                <ExternalLink className="w-3 h-3" aria-hidden />
                新規タブで開く
              </button>
              <button
                type="button"
                className="border border-slate-200 hover:bg-slate-50 text-xs h-8 px-3 rounded-md flex items-center gap-1"
              >
                <Download className="w-3 h-3" aria-hidden />
                PDF download
              </button>
            </div>
          </section>

          {/* Section 5 — Client acceptance status (h2 #5) */}
          <section
            className="bg-white border border-slate-200 rounded-lg p-5"
            data-section-id="client-acceptance"
          >
            <h2 className="text-base font-bold mb-3 flex items-center gap-2">
              <UserCheck className="w-5 h-5 text-eb-500" aria-hidden />
              {SECTION_H2_TEXTS[4]}
            </h2>
            <div className="text-sm">
              <div className="flex items-center justify-between p-3 border border-slate-200 rounded-md">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-slate-300 text-slate-700 text-xs font-bold flex items-center justify-center">
                    {delivery?.client_acceptance?.reviewer_label?.[0]?.toUpperCase() ??
                      "M"}
                  </div>
                  <div>
                    <div className="font-medium">
                      {delivery?.client_acceptance?.reviewer_label ??
                        "masato (内部承認)"}
                    </div>
                    <div className="text-xs text-slate-500 mono">
                      {delivery?.client_acceptance?.note ??
                        "Build-Factory dogfood は内製のため client なし"}
                    </div>
                  </div>
                </div>
                <span className="text-[11px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
                  {delivery?.client_acceptance?.state === "approved"
                    ? "Approved"
                    : delivery?.client_acceptance?.state === "pending"
                      ? "Pending"
                      : "N/A"}
                </span>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
