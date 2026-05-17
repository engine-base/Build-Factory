"use client";

/**
 * S-061 仕様書 PDF (Export Spec PDF preview) — T-V3-C-22 / F-031.
 *
 * @screen-id S-061
 * @feature-id F-031
 * @task-ids T-V3-C-22
 * @entities E-014
 * @phase Phase 1B
 *
 * Implements the v3 export preview screen documented at:
 *   docs/mocks/2026-05-15_v3/export/S-061-export-spec-pdf.html
 *
 * Mock parity (逐語 — see screens.json[S-061]):
 *   - h1 text         : "受託 EC 構築 #4— 要件定義書 —" (screens.json[S-061].h1_text)
 *   - h2 sections     : "1. プロジェクト概要" / "2. Must 要件 (34 項目)"
 *   - 状態            : loading / loaded / error (screens.json[S-061].states)
 *   - layout          : A4 page mock (PDF preview frame) with sticky toolbar
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-22.md):
 *   structural.AC-S1 (data-screen-id="S-061")                 — root <div>.
 *   structural.AC-S2 (h1 == "受託 EC 構築 #4— 要件定義書 —") — page heading.
 *   structural.AC-S3 (h2 sections from screens.json)          — A4 page sections.
 *   functional.AC-F1 (4xx/5xx → non-technical toast w/ endpoint, no stack)
 *     — `ExportApiError.toUserMessage()` consumed via local `errorMessage`.
 *   functional.AC-F2 (POST /api/workspaces/{id}/exports → export_id ≤ 1s)
 *     — `queueExport()` invoked from the "PDF ダウンロード" button.
 *   functional.AC-F3 (status queued|running → download_url=null)
 *     — Polling via `getExportById()`; CTA stays disabled when download_url
 *       is null and the status is non-terminal.
 *
 * NOTE: This is a *preview* page. It renders the spec content directly (mock
 * parity) and exposes the export-pipeline backend (POST queue + GET poll) so
 * workspace members can trigger a PDF render and download the artifact when
 * the job finishes. The default workspace id is taken from the route query
 * (`?workspace=<uuid>`) and falls back to a deterministic preview id so the
 * page can be rendered without a real workspace selection.
 */

import * as React from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Download,
  Factory,
  Printer,
  RefreshCw,
} from "lucide-react";

import {
  buildExportByIdEndpoint,
  buildExportsByWorkspaceEndpoint,
  ExportApiError,
  getExportById,
  isExportDownloadable,
  queueExport,
  type ExportStatusResponse,
} from "@/api/exports";

// --------------------------------------------------------------------------
// Constants (mock parity — docs/mocks/2026-05-15_v3/export/S-061-*.html)
// --------------------------------------------------------------------------

const H1_TEXT = "受託 EC 構築 #4— 要件定義書 —";
const SECTION_H2_TEXTS: readonly string[] = [
  "1. プロジェクト概要",
  "2. Must 要件 (34 項目)",
] as const;
const PREVIEW_WORKSPACE_FALLBACK = "preview-workspace-0001";
const DOC_FILENAME = "build-factory-spec-v2.0.pdf";
const DOC_META = `${DOC_FILENAME} · A4 · 24 pages`;
const DOC_VERSION = "v 2.0 · 2026-05-13";
const DOC_AUTHOR = "作成: masato@engine-base.com · 株式会社 ENGINE BASE";

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

type ViewState = "idle" | "queueing" | "polling" | "ready" | "error";

interface PageProps {
  /**
   * Optional workspace id (UUID) to scope the queued export. Falls back to a
   * deterministic preview id so the page renders without a real selection.
   */
  workspaceId?: string;
}

export default function ExportSpecPdfPage(props: PageProps = {}) {
  const workspaceId = props.workspaceId ?? PREVIEW_WORKSPACE_FALLBACK;

  const [viewState, setViewState] = React.useState<ViewState>("idle");
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [exportId, setExportId] = React.useState<string | null>(null);
  const [statusInfo, setStatusInfo] =
    React.useState<ExportStatusResponse | null>(null);

  // ----------------------------------------------------------------------
  // AC-F1 helper: surface a non-technical message referencing the failing
  // endpoint without leaking server stack traces.
  // ----------------------------------------------------------------------
  const surfaceError = React.useCallback(
    (err: unknown, fallbackEndpoint: string) => {
      const msg =
        err instanceof ExportApiError
          ? err.toUserMessage()
          : `通信に失敗しました (${fallbackEndpoint})`;
      setErrorMessage(msg);
      setViewState("error");
    },
    [],
  );

  // ----------------------------------------------------------------------
  // AC-F2: POST /api/workspaces/{id}/exports — queue spec_pdf job.
  // ----------------------------------------------------------------------
  const handleQueueExport = React.useCallback(async () => {
    setErrorMessage(null);
    setViewState("queueing");
    setStatusInfo(null);
    const endpoint = buildExportsByWorkspaceEndpoint(workspaceId);
    try {
      const res = await queueExport(workspaceId, { type: "spec_pdf" });
      if (!res.export_id) {
        throw new ExportApiError(
          "export.empty_export_id",
          "no export_id in response",
          0,
          endpoint,
        );
      }
      setExportId(res.export_id);
      setViewState("polling");
    } catch (err) {
      surfaceError(err, endpoint);
    }
  }, [workspaceId, surfaceError]);

  // ----------------------------------------------------------------------
  // AC-F3: GET /api/exports/{id} — poll status, download when terminal.
  // ----------------------------------------------------------------------
  const handlePollStatus = React.useCallback(async () => {
    if (!exportId) return;
    setErrorMessage(null);
    const endpoint = buildExportByIdEndpoint(exportId);
    try {
      const res = await getExportById(exportId);
      setStatusInfo(res);
      const status = String(res.export?.status ?? "queued");
      if (isExportDownloadable(status) && res.download_url) {
        setViewState("ready");
      } else {
        setViewState("polling");
      }
    } catch (err) {
      surfaceError(err, endpoint);
    }
  }, [exportId, surfaceError]);

  const downloadUrl = statusInfo?.download_url ?? null;
  const exportStatus = String(statusInfo?.export?.status ?? "");
  const downloadDisabled =
    viewState === "queueing" ||
    viewState === "polling" ||
    !downloadUrl ||
    !isExportDownloadable(exportStatus);

  return (
    <div
      data-screen-id="S-061"
      data-feature-id="F-031"
      data-task-ids="T-V3-C-22"
      data-entities="E-014"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-200"
    >
      {/* Back-to-dashboard anchor (mock corner control). */}
      <a
        href="/dashboard"
        data-testid="back-to-dashboard"
        className="fixed top-3 right-3 z-50 inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/95 border border-slate-200 rounded-md text-xs font-semibold text-eb-500 shadow-sm hover:bg-white"
      >
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
        ダッシュボードに戻る
      </a>

      {/* Sticky preview toolbar (mock parity: PDF Preview · Print · Download) */}
      <div
        className="no-print sticky top-0 z-10 bg-slate-900 text-white px-4 py-2 flex items-center gap-3"
        data-testid="pdf-toolbar"
      >
        <span className="text-xs font-semibold">PDF Preview</span>
        <span className="text-xs opacity-70" data-testid="pdf-meta">
          {DOC_META}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            data-testid="pdf-print"
            onClick={() => {
              if (typeof window !== "undefined" && typeof window.print === "function") {
                window.print();
              }
            }}
            className="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1 rounded flex items-center gap-1"
          >
            <Printer className="w-3 h-3" aria-hidden />
            印刷
          </button>
          <button
            type="button"
            data-testid="pdf-queue-export"
            onClick={() => void handleQueueExport()}
            disabled={viewState === "queueing"}
            aria-busy={viewState === "queueing"}
            className="text-xs bg-eb-500 hover:bg-eb-600 px-3 py-1 rounded font-semibold flex items-center gap-1 disabled:opacity-50"
          >
            <Download className="w-3 h-3" aria-hidden />
            {viewState === "queueing" ? "キュー中…" : "PDF ダウンロード"}
          </button>
        </div>
      </div>

      {/* Error toast (AC-F1) */}
      {errorMessage && (
        <div
          role="alert"
          data-testid="export-error"
          className="no-print max-w-[800px] mx-auto mt-4 p-3 rounded-md bg-amber-50 border border-amber-300 text-amber-800 text-xs flex items-start gap-2"
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Polling status banner (AC-F3) */}
      {exportId && viewState !== "error" && (
        <div
          className="no-print max-w-[800px] mx-auto mt-4 p-3 rounded-md bg-slate-50 border border-slate-200 text-slate-700 text-xs flex items-center gap-2"
          data-testid="export-status"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${viewState === "polling" ? "animate-spin" : ""}`}
            aria-hidden
          />
          <span data-testid="export-status-text">
            export_id: <span className="mono">{exportId}</span> · status:{" "}
            <span className="mono">{exportStatus || "queued"}</span> ·
            download_url:{" "}
            <span className="mono">
              {downloadUrl ? "available" : "(null while queued/running)"}
            </span>
          </span>
          <button
            type="button"
            data-testid="export-poll"
            onClick={() => void handlePollStatus()}
            className="ml-auto bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs h-6 px-2 rounded font-semibold"
          >
            状態を更新
          </button>
          {downloadUrl && isExportDownloadable(exportStatus) && (
            <a
              data-testid="export-download-link"
              href={downloadUrl}
              className="bg-eb-500 hover:bg-eb-600 text-white text-xs h-6 px-2.5 rounded font-semibold inline-flex items-center"
              aria-disabled={downloadDisabled ? "true" : "false"}
            >
              ダウンロード
            </a>
          )}
        </div>
      )}

      {/* A4 page (mock parity) */}
      <div
        className="max-w-[800px] mx-auto my-6 bg-white shadow-xl p-12"
        style={{ aspectRatio: "1/1.414", minHeight: "1130px" }}
        data-testid="pdf-a4-page"
      >
        <header className="border-b-2 border-eb-500 pb-4 mb-6">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-md bg-eb-500 flex items-center justify-center">
                <Factory className="w-4 h-4 text-white" aria-hidden />
              </div>
              <span className="text-sm font-bold">Build-Factory</span>
            </div>
            <span className="text-xs mono text-slate-500">{DOC_VERSION}</span>
          </div>
          {/* AC-S2: this is the single <h1> matching screens.json[S-061].h1_text. */}
          <h1 className="text-3xl font-bold" data-testid="doc-h1">
            {H1_TEXT}
          </h1>
          <div className="text-sm text-slate-600 mt-2">{DOC_AUTHOR}</div>
        </header>

        {/* AC-S3: h2 section headings from screens.json[S-061].section_h2_texts */}
        <section className="mb-6">
          <h2
            className="text-xl font-bold border-l-4 border-eb-500 pl-3 mb-3"
            data-testid="doc-section-h2-1"
          >
            {SECTION_H2_TEXTS[0]}
          </h2>
          <p className="text-sm leading-relaxed">
            ABC 社向けの BtoC EC サイト構築。Phase 1 (基盤) → Phase 2
            (機能実装) → Phase 3 (テスト + 納品) の 3 フェーズで進行。
          </p>
          <div className="grid grid-cols-3 gap-3 mt-4">
            <div className="border border-slate-200 rounded p-3">
              <div className="text-[10px] uppercase text-slate-500 font-bold">
                想定 MAU
              </div>
              <div className="text-lg font-bold mono">50,000</div>
            </div>
            <div className="border border-slate-200 rounded p-3">
              <div className="text-[10px] uppercase text-slate-500 font-bold">
                商品数
              </div>
              <div className="text-lg font-bold mono">5,000</div>
            </div>
            <div className="border border-slate-200 rounded p-3">
              <div className="text-[10px] uppercase text-slate-500 font-bold">
                納期
              </div>
              <div className="text-lg font-bold mono">3 ヶ月</div>
            </div>
          </div>
        </section>

        <section className="mb-6">
          <h2
            className="text-xl font-bold border-l-4 border-eb-500 pl-3 mb-3"
            data-testid="doc-section-h2-2"
          >
            {SECTION_H2_TEXTS[1]}
          </h2>
          <h3 className="text-base font-bold mb-2">M-1 商品検索・閲覧</h3>
          <p className="text-sm leading-relaxed mb-2">
            商品カテゴリ / 価格帯 / キーワードによる検索。商品詳細・在庫表示。
          </p>
          <div className="bg-eb-50 border-l-4 border-eb-500 p-3 text-sm mb-3 rounded-r">
            <strong>AC-M1-1 (EVENT-DRIVEN):</strong> When
            キーワード検索が実行された時、the system shall 商品 list を 300ms
            以内に返却する。
          </div>
          <h3 className="text-base font-bold mb-2 mt-4">M-2 カート / 決済</h3>
          <p className="text-sm leading-relaxed">
            Stripe を使った決済 / 商品追加 / 削除 / 数量変更。
          </p>
        </section>

        <footer className="mt-8 border-t border-slate-200 pt-3 flex justify-between text-[10px] text-slate-500 mono">
          <span>build-factory-spec-v2.0</span>
          <span>Page 1 / 24</span>
          <span>© ENGINE BASE</span>
        </footer>
      </div>
    </div>
  );
}
