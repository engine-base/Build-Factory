"use client";

/**
 * T-V3-C-23 / S-062: 納品レポート page (Vertical Slice / UI).
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/export/S-062-export-delivery-report.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-062
 * @feature-id F-031
 * @task-ids T-V3-C-23
 * @entities E-034
 * @phase Phase 1B
 *
 * Auth model: bearerAuth (workspace member). The workspace_id is supplied via
 * `?workspace_id=...` query string. POSTing a spec_pdf export queue job and
 * polling the resulting /api/exports/{id} record both require the same bearer
 * scope; 4xx/5xx surfaces as a friendly toast tagged with the failing
 * endpoint (never leaking server stack traces).
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-23.md):
 *   structural.AC-S1 (data-screen-id="S-062")            — root <main> element.
 *   structural.AC-S2 (h1 == screens.json[S-062].h1_text) — page heading verbatim.
 *   structural.AC-S3 (h2 section list == section_h2_texts)
 *                                                        — 4 numbered sections.
 *   functional.AC-F1 (4xx/5xx → non-technical toast tagged endpoint, no stack)
 *                                                        — query + mutation handlers.
 *   functional.AC-F2 (POST /api/workspaces/{id}/exports type=spec_pdf →
 *                     export_id within 1s)
 *                                                        — "PDF ダウンロード" button.
 *   functional.AC-F3 (GET /api/exports/{id} returns download_url=null while
 *                     status ∈ {queued, running})
 *                                                        — polled until ready.
 *
 * NOTE on path:
 *   The ticket card lists `frontend/src/app/(app)/exports/delivery/[exportId]/page.tsx`
 *   as the canonical file, but the worktree instructions for this session
 *   explicitly directed this page to live at
 *   `frontend/src/app/export/delivery/page.tsx` (workspace_id-keyed, not
 *   export_id-keyed). Both paths render the same Next.js App Router page; this
 *   one matches the GET /api/workspaces/{id}/delivery contract the page hits
 *   on mount. If the (app)/exports/delivery/[exportId] route ships later, it
 *   can re-export this default component verbatim.
 */

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  Factory,
  Loader2,
  Mail,
} from "lucide-react";

import {
  EXPORT_BY_ID_ENDPOINT_PATTERN,
  ExportsApiError,
  exportByIdEndpoint,
  getExport,
  getWorkspaceDelivery,
  requestSpecPdfExport,
  workspaceDeliveryEndpoint,
  workspaceExportsEndpoint,
  type Delivery,
  type DeliverySummary,
  type ExportRecord,
  type VerificationRow,
  type WorkspaceDeliveryResponse,
} from "@/api/exports";

// --------------------------------------------------------------------------
// Static copy — must match docs/functional-breakdown/2026-05-16_v3/screens.json
// [S-062].h1_text verbatim (Tier 1 AC-S2) and section_h2_texts (Tier 1 AC-S3).
// Keeping them top-level so the lint-mock-impl-diff Gate #8 can grep straight
// out of the source.
// --------------------------------------------------------------------------

const SCREEN_H1_TEXT =
  "Phase 1 納品レポート— 受託 EC 構築 #4 / 基盤実装フェーズ —";

const SECTION_H2_TEXTS: readonly string[] = [
  "1. 納品物サマリー",
  "2. 実装内容",
  "3. 検証結果",
  "4. 受入確認",
];

// --------------------------------------------------------------------------
// Fallback content — mirrors the static mock. The page renders this while the
// backend payload is still empty (e.g. before the server-side `summary` field
// lands). Once the backend supplies a `delivery.summary`, the page uses that
// instead, but the static fallback keeps the design-review experience intact.
// --------------------------------------------------------------------------

const FALLBACK_IMPLEMENTATION_ITEMS: readonly string[] = [
  "Supabase 基盤 + 8 migrations (RLS policy 43 件全実装)",
  "認証フロー: signup / login / MFA (TOTP) / OAuth (Google / GitHub)",
  "商品管理 schema (商品 / カテゴリ / 在庫 / 画像)",
  "カート + 決済 (Stripe 連携 / Webhook)",
  "管理画面 (admin / 出荷管理 / 在庫管理)",
];

const FALLBACK_VERIFICATION_ROWS: readonly VerificationRow[] = [
  {
    label: "unit test",
    result: "8000 / 8010 PASS",
    note: "10 件 skipped (numpy 互換)",
  },
  { label: "integration test", result: "187 / 187 PASS", note: null },
  { label: "E2E (Playwright)", result: "42 / 42 PASS", note: null },
  { label: "Coverage", result: "84%", note: "target 70% 達成" },
];

const FALLBACK_KPI = {
  completed_tasks: 23,
  tests_passed: 8000,
  coverage_pct: 84,
  redline_breaches: 0,
} as const;

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

function isExportComplete(record: ExportRecord | undefined): boolean {
  if (!record) return false;
  if (record.status === "queued" || record.status === "running") return false;
  return !!record.download_url;
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function DeliveryReportPage() {
  const search = useSearchParams();
  // workspace_id is supplied via query string. When missing, we still render
  // the skeleton + static fallback content so design review can proceed; the
  // delivery fetch is simply skipped (enabled: !!workspaceId).
  const workspaceId = search?.get("workspace_id") ?? "";

  const queryClient = useQueryClient();

  // AC-F1: GET /api/workspaces/{id}/delivery on mount.
  const deliveryQuery = useQuery<WorkspaceDeliveryResponse, ExportsApiError>({
    queryKey: ["delivery", workspaceId],
    enabled: !!workspaceId,
    queryFn: ({ signal }) => getWorkspaceDelivery(workspaceId, { signal }),
    retry: false,
    staleTime: 30_000,
  });

  // AC-F1: surface non-technical toast tagged with the failing endpoint and
  // never leak server stack traces.
  const lastDeliveryToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!deliveryQuery.isError) {
      lastDeliveryToastRef.current = null;
      return;
    }
    const err = deliveryQuery.error;
    const endpoint = workspaceDeliveryEndpoint(workspaceId || "{id}");
    const userMsg =
      err instanceof ExportsApiError
        ? err.toUserMessage()
        : `納品レポートの取得に失敗しました (${endpoint})`;
    if (lastDeliveryToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastDeliveryToastRef.current = userMsg;
    }
  }, [deliveryQuery.isError, deliveryQuery.error, workspaceId]);

  // AC-F2: POST /api/workspaces/{id}/exports (type=spec_pdf) → export_id.
  const [pendingExportId, setPendingExportId] = React.useState<string | null>(
    null,
  );
  const queueExportMutation = useMutation({
    mutationFn: () => requestSpecPdfExport(workspaceId),
    onSuccess: (data) => {
      setPendingExportId(data.export_id);
      toast.success("PDF 生成ジョブをキューに登録しました");
    },
    onError: (err: unknown) => {
      const endpoint = workspaceExportsEndpoint(workspaceId || "{id}");
      const userMsg =
        err instanceof ExportsApiError
          ? err.toUserMessage()
          : `PDF 生成のリクエストに失敗しました (${endpoint})`;
      toast.error(userMsg);
    },
  });

  // AC-F3: poll GET /api/exports/{id} while status ∈ {queued, running}. The
  // backend contract says download_url=null in those states; once a non-null
  // URL appears we enable the download button.
  const exportQuery = useQuery<ExportRecord, ExportsApiError>({
    queryKey: ["export", pendingExportId],
    enabled: !!pendingExportId,
    queryFn: ({ signal }) =>
      getExport(pendingExportId as string, { signal }),
    retry: false,
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return 2_000;
      if (data.status === "queued" || data.status === "running") return 2_000;
      return false;
    },
  });

  const lastExportToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!exportQuery.isError) {
      lastExportToastRef.current = null;
      return;
    }
    const err = exportQuery.error;
    const endpoint = pendingExportId
      ? exportByIdEndpoint(pendingExportId)
      : EXPORT_BY_ID_ENDPOINT_PATTERN;
    const userMsg =
      err instanceof ExportsApiError
        ? err.toUserMessage()
        : `生成状況の取得に失敗しました (${endpoint})`;
    if (lastExportToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastExportToastRef.current = userMsg;
    }
  }, [exportQuery.isError, exportQuery.error, pendingExportId]);

  // Surface a success toast + invalidate the delivery cache once the export
  // is ready, so the artifact_urls list refreshes.
  React.useEffect(() => {
    if (!exportQuery.data) return;
    if (isExportComplete(exportQuery.data)) {
      toast.success("PDF の生成が完了しました");
      queryClient.invalidateQueries({ queryKey: ["delivery", workspaceId] });
    }
  }, [exportQuery.data, queryClient, workspaceId]);

  const onClickGeneratePdf = React.useCallback(() => {
    if (!workspaceId || queueExportMutation.isPending) return;
    queueExportMutation.mutate();
  }, [workspaceId, queueExportMutation]);

  const delivery: Delivery | undefined = deliveryQuery.data?.delivery;
  const summary: DeliverySummary | null | undefined = delivery?.summary;

  const kpi = summary?.kpi ?? FALLBACK_KPI;
  const implementationItems =
    (summary?.implementation_items && summary.implementation_items.length > 0
      ? summary.implementation_items
      : FALLBACK_IMPLEMENTATION_ITEMS) as readonly string[];
  const verificationRows =
    (summary?.verification_rows && summary.verification_rows.length > 0
      ? summary.verification_rows
      : FALLBACK_VERIFICATION_ROWS) as readonly VerificationRow[];

  const downloadReady = isExportComplete(exportQuery.data);
  const downloadUrl = downloadReady ? exportQuery.data?.download_url ?? null : null;
  const downloadButtonLabel = queueExportMutation.isPending
    ? "送信中..."
    : pendingExportId && !downloadReady
      ? "生成中..."
      : downloadReady
        ? "PDF を開く"
        : "PDF ダウンロード";

  return (
    <main
      data-screen-id="S-062"
      data-feature-id="F-031"
      data-task-ids="T-V3-C-23"
      data-entities="E-034"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-200 text-slate-900"
    >
      {/* Top action bar — mirrors the mock no-print sticky bar. */}
      <div className="bg-slate-900 text-white px-4 py-2 flex items-center gap-3 sticky top-0 z-10">
        <a
          href="/"
          className="text-xs inline-flex items-center gap-1 text-slate-200 hover:text-white"
        >
          <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
          <span>戻る</span>
        </a>
        <div className="flex items-center gap-2 ml-2">
          <span className="text-xs font-semibold">納品レポート Preview</span>
          <span className="text-xs opacity-70 mono">
            delivery-report-phase1.pdf
          </span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            data-testid="send-client-button"
            className="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1 rounded flex items-center gap-1"
          >
            <Mail className="w-3 h-3" aria-hidden />
            クライアントに送付
          </button>
          {downloadReady && downloadUrl ? (
            <a
              data-testid="download-pdf-link"
              href={downloadUrl}
              className="text-xs bg-eb-500 hover:bg-eb-600 px-3 py-1 rounded font-semibold flex items-center gap-1 text-white"
            >
              <Download className="w-3 h-3" aria-hidden />
              {downloadButtonLabel}
            </a>
          ) : (
            <button
              type="button"
              data-testid="download-pdf-button"
              onClick={onClickGeneratePdf}
              disabled={
                !workspaceId ||
                queueExportMutation.isPending ||
                (!!pendingExportId && !downloadReady)
              }
              className="text-xs bg-eb-500 hover:bg-eb-600 disabled:opacity-60 disabled:cursor-not-allowed px-3 py-1 rounded font-semibold flex items-center gap-1 text-white"
            >
              {queueExportMutation.isPending ||
              (pendingExportId && !downloadReady) ? (
                <Loader2 className="w-3 h-3 animate-spin" aria-hidden />
              ) : (
                <Download className="w-3 h-3" aria-hidden />
              )}
              {downloadButtonLabel}
            </button>
          )}
        </div>
      </div>

      {/* Loading skeleton — keeps the page accessible while the delivery
          payload is in flight. */}
      {deliveryQuery.isPending && !!workspaceId && (
        <div
          data-state="loading"
          role="status"
          aria-live="polite"
          className="flex items-center justify-center py-16 text-slate-500 gap-2"
        >
          <Loader2
            className="w-5 h-5 animate-spin text-eb-500"
            aria-hidden
          />
          <span className="text-sm">納品レポートを読み込み中...</span>
        </div>
      )}

      <article
        className="max-w-[800px] mx-auto my-6 bg-white shadow-xl p-12"
        style={{ minHeight: 1130 }}
      >
        {/* Header */}
        <header className="border-b-2 border-eb-500 pb-4 mb-6">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-md bg-eb-500 flex items-center justify-center">
                <Factory className="w-4 h-4 text-white" aria-hidden />
              </div>
              <span className="text-sm font-bold">Build-Factory</span>
            </div>
            <span className="text-xs mono text-slate-500">
              納品 ID: {summary?.delivery_id_label ?? "del_5f8a2c"} ·{" "}
              {summary?.delivery_date ?? "2026-05-15"}
            </span>
          </div>
          <h1 className="text-3xl font-bold whitespace-pre-line">
            {SCREEN_H1_TEXT}
          </h1>
          <div className="text-sm text-slate-600 mt-2">
            納品先: {summary?.client_email ?? "ceo@abc.co.jp"} · 担当:{" "}
            {summary?.assignee_email ?? "masato@engine-base.com"}
          </div>
        </header>

        {/* Section 1: 納品物サマリー (AC-S3 #1) */}
        <section className="mb-6" data-section-id="summary">
          <h2 className="text-xl font-bold border-l-4 border-eb-500 pl-3 mb-3">
            {SECTION_H2_TEXTS[0]}
          </h2>
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-emerald-50 border border-emerald-200 rounded-md p-3 text-center">
              <div className="text-[10px] uppercase text-emerald-700 font-bold">
                完了タスク
              </div>
              <div className="text-2xl font-bold tabular text-emerald-600">
                {fmtNumber(kpi.completed_tasks)}
              </div>
            </div>
            <div className="bg-emerald-50 border border-emerald-200 rounded-md p-3 text-center">
              <div className="text-[10px] uppercase text-emerald-700 font-bold">
                Test PASS
              </div>
              <div className="text-2xl font-bold tabular text-emerald-600">
                {fmtNumber(kpi.tests_passed)}
              </div>
            </div>
            <div className="bg-emerald-50 border border-emerald-200 rounded-md p-3 text-center">
              <div className="text-[10px] uppercase text-emerald-700 font-bold">
                Coverage
              </div>
              <div className="text-2xl font-bold tabular text-emerald-600">
                {fmtPercent(kpi.coverage_pct)}
              </div>
            </div>
            <div className="bg-emerald-50 border border-emerald-200 rounded-md p-3 text-center">
              <div className="text-[10px] uppercase text-emerald-700 font-bold">
                赤線抵触
              </div>
              <div className="text-2xl font-bold tabular text-emerald-600">
                {fmtNumber(kpi.redline_breaches)}
              </div>
            </div>
          </div>
        </section>

        {/* Section 2: 実装内容 (AC-S3 #2) */}
        <section className="mb-6" data-section-id="implementation">
          <h2 className="text-xl font-bold border-l-4 border-eb-500 pl-3 mb-3">
            {SECTION_H2_TEXTS[1]}
          </h2>
          <ul className="text-sm space-y-2 list-disc pl-5">
            {implementationItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>

        {/* Section 3: 検証結果 (AC-S3 #3) */}
        <section className="mb-6" data-section-id="verification">
          <h2 className="text-xl font-bold border-l-4 border-eb-500 pl-3 mb-3">
            {SECTION_H2_TEXTS[2]}
          </h2>
          <table className="w-full text-sm border border-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-bold">項目</th>
                <th className="px-3 py-2 text-right text-xs font-bold">
                  結果
                </th>
                <th className="px-3 py-2 text-left text-xs font-bold">備考</th>
              </tr>
            </thead>
            <tbody>
              {verificationRows.map((row) => (
                <tr key={row.label} className="border-t border-slate-200">
                  <td className="px-3 py-2">{row.label}</td>
                  <td className="px-3 py-2 text-right mono tabular">
                    {row.result}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-500">
                    {row.note ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {/* Section 4: 受入確認 (AC-S3 #4) */}
        <section className="mb-6" data-section-id="acceptance">
          <h2 className="text-xl font-bold border-l-4 border-eb-500 pl-3 mb-3">
            {SECTION_H2_TEXTS[3]}
          </h2>
          <div className="border-2 border-eb-500 bg-eb-50 rounded-md p-5 text-center">
            <div className="text-sm text-slate-600 mb-2 inline-flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5 text-eb-500" aria-hidden />
              クライアント受入署名
            </div>
            <div
              className="h-20 border-b-2 border-slate-300 mb-1"
              aria-hidden
            />
            <div className="text-xs text-slate-500">
              日付: ____________ 氏名: ____________
            </div>
          </div>
        </section>

        <footer className="mt-12 pt-4 border-t border-slate-200 text-[10px] text-slate-500 mono flex justify-between">
          <span>delivery-report-phase1</span>
          <span>Page 1 / 8</span>
          <span>© ENGINE BASE</span>
        </footer>
      </article>
    </main>
  );
}
