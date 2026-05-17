"use client";

/**
 * S-021 要件エディタ — T-V3-C-47 / F-006 (+ F-025).
 *
 * @screen-id S-021
 * @feature-id F-006
 * @task-ids T-V3-C-47,T-V3-SCR-06
 * @entities E-016,E-021
 * @phase Phase 1 / Wave 1 / Group C
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/spec/S-021-requirements-editor.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-47.md):
 *   structural.AC-S1 (h1 === "要件エディタ")                    -> page heading.
 *   structural.AC-S2 (section h2 set === {"2. 機能要件 (Must)"}) -> editor article.
 *   structural.AC-S3 (Lucide icons exclusively / no emoji)      -> see Lucide imports.
 *   functional.AC-F1 (GET /api/workspaces/{id}/requirements on mount;
 *                     4xx -> inline toast + empty state)         -> useRequirementsEditor.
 *   functional.AC-F2 (UNWANTED: unauthenticated -> /login,
 *                     no workspace data renders)                  -> 401 effect.
 *   functional.AC-F3 (PUT with EARS items -> version+1)           -> save() handler.
 *   functional.AC-F4 (UBIQUITOUS: every AC must match one of the 5 EARS forms
 *                     BEFORE persisting)                          -> validateRequirementItems.
 *
 * Workspace scoping: the page reads ?workspace_id from the search params; in
 * production the (app) layout will supply it from the active workspace. Until
 * that wiring lands we default to "active" (matches T-V3-B-009 / B-006).
 */

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Box,
  CheckCircle2,
  Code,
  Edit3,
  Eye,
  FileText,
  LayoutDashboard,
  List,
  Map as MapIcon,
  Mic,
  Plus,
  Save,
  Sparkles,
  Star,
  UploadCloud,
  Zap,
} from "lucide-react";

import {
  EarsValidationError,
  RequirementsApiError,
  detectEarsForm,
  requirementsListEndpoint,
  requirementsPutEndpoint,
  requirementsVersionsEndpoint,
  type RequirementItem,
} from "@/api/requirements-editor";
import { useRequirementsEditor } from "@/hooks/useRequirementsEditor";

// --------------------------------------------------------------------------
// Mock-derived literals (逐語コピー from screens.json[S-021]).
// AC-S1: h1_text === "要件エディタ"
// AC-S2: section_h2_texts === ["2. 機能要件 (Must)"]
// --------------------------------------------------------------------------

const S021_H1_TEXT = "要件エディタ";
const S021_SECTION_H2: ReadonlyArray<string> = ["2. 機能要件 (Must)"];

const DEFAULT_DRAFT_ITEM: RequirementItem = {
  section: S021_SECTION_H2[0],
  label: "Must",
  body_md: "",
};

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

interface EarsHelperEntry {
  form: ReturnType<typeof detectEarsForm>;
  title: string;
  template: string;
  variant: "default" | "primary" | "warning" | "danger";
}

const EARS_HELPER: ReadonlyArray<EarsHelperEntry> = [
  {
    form: "UBIQUITOUS",
    title: "UBIQUITOUS (常時)",
    template: "The system shall ...",
    variant: "default",
  },
  {
    form: "EVENT-DRIVEN",
    title: "EVENT-DRIVEN",
    template: "When [event], the system shall ...",
    variant: "primary",
  },
  {
    form: "STATE-DRIVEN",
    title: "STATE-DRIVEN",
    template: "While [state], the system shall ...",
    variant: "warning",
  },
  {
    form: "OPTIONAL",
    title: "OPTIONAL",
    template: "Where [feature], the system shall ...",
    variant: "default",
  },
  {
    form: "UNWANTED",
    title: "UNWANTED",
    template: "If [condition], the system shall not ...",
    variant: "danger",
  },
] as const;

function helperVariantClass(variant: EarsHelperEntry["variant"]): string {
  switch (variant) {
    case "primary":
      return "border-eb-200 bg-eb-50";
    case "warning":
      return "border-amber-200 bg-amber-50";
    case "danger":
      return "border-red-200 bg-red-50";
    default:
      return "border-slate-200 bg-white";
  }
}

function countEarsLines(items: RequirementItem[]): {
  total: number;
  byForm: Record<string, number>;
  unmatched: number;
} {
  const byForm: Record<string, number> = {};
  let total = 0;
  let unmatched = 0;
  for (const item of items) {
    const lines = String(item.body_md ?? "")
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => /\bshall\b/i.test(l));
    for (const line of lines) {
      total += 1;
      const normalised = line
        .replace(/^[-*+]\s+/, "")
        .replace(/^\d+\.\s+/, "")
        .replace(/\*\*/g, "")
        .trim();
      const form = detectEarsForm(normalised);
      if (form) {
        byForm[form] = (byForm[form] ?? 0) + 1;
      } else {
        unmatched += 1;
      }
    }
  }
  return { total, byForm, unmatched };
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function RequirementsEditorPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = searchParams?.get("workspace_id") ?? "active";

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    save,
    snapshot,
    isSaving,
    isSnapshotting,
  } = useRequirementsEditor(workspaceId);

  const [draftItems, setDraftItems] = React.useState<RequirementItem[]>([]);
  const [selectedIdx, setSelectedIdx] = React.useState(0);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [savedVersion, setSavedVersion] = React.useState<number | null>(null);

  // --------------------------------------------------------------------
  // AC-F2 (UNWANTED): unauthenticated -> /login. Render nothing else.
  // --------------------------------------------------------------------
  const isUnauthorized =
    isError &&
    error instanceof RequirementsApiError &&
    error.status === 401;

  React.useEffect(() => {
    if (isUnauthorized) {
      router.replace("/login");
    }
  }, [isUnauthorized, router]);

  // --------------------------------------------------------------------
  // AC-F1: surface 4xx as inline error toast (non-technical).
  // --------------------------------------------------------------------
  React.useEffect(() => {
    if (!isError) {
      setErrorMessage(null);
      return;
    }
    if (error instanceof RequirementsApiError) {
      if (error.status === 401) return; // handled by redirect effect.
      setErrorMessage(error.toUserMessage());
    } else if (error) {
      setErrorMessage(
        `通信に失敗しました (${requirementsListEndpoint(workspaceId)})`,
      );
    }
  }, [isError, error, workspaceId]);

  // --------------------------------------------------------------------
  // Sync server data -> editable draft once fetched.
  // --------------------------------------------------------------------
  React.useEffect(() => {
    if (!data) return;
    setDraftItems(
      data.requirements && data.requirements.length > 0
        ? data.requirements.map((r) => ({ ...r }))
        : [{ ...DEFAULT_DRAFT_ITEM }],
    );
    setSelectedIdx(0);
  }, [data]);

  // --------------------------------------------------------------------
  // AC-F3: save via PUT /api/workspaces/{id}/requirements (returns version+1).
  // AC-F4 is enforced inside putRequirements before the wire call.
  // --------------------------------------------------------------------
  const handleSave = React.useCallback(async () => {
    if (isSaving) return;
    setErrorMessage(null);
    try {
      const resp = await save({ items: draftItems });
      setSavedVersion(resp.version);
    } catch (err) {
      if (err instanceof EarsValidationError) {
        setErrorMessage(err.message);
        return;
      }
      if (err instanceof RequirementsApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      if (err instanceof RequirementsApiError) {
        setErrorMessage(err.toUserMessage());
        return;
      }
      setErrorMessage(
        `通信に失敗しました (${requirementsPutEndpoint(workspaceId)})`,
      );
    }
  }, [draftItems, isSaving, router, save, workspaceId]);

  const handlePublish = React.useCallback(async () => {
    if (isSnapshotting) return;
    setErrorMessage(null);
    try {
      // Persist current edits first so the snapshot includes them.
      await save({ items: draftItems });
      await snapshot({ label: "publish" });
    } catch (err) {
      if (err instanceof EarsValidationError) {
        setErrorMessage(err.message);
        return;
      }
      if (err instanceof RequirementsApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      if (err instanceof RequirementsApiError) {
        setErrorMessage(err.toUserMessage());
        return;
      }
      setErrorMessage(
        `通信に失敗しました (${requirementsVersionsEndpoint(workspaceId)})`,
      );
    }
  }, [draftItems, isSnapshotting, router, save, snapshot, workspaceId]);

  const handleAddAcTemplate = React.useCallback((template: string) => {
    setDraftItems((items) => {
      const next = items.length > 0 ? [...items] : [{ ...DEFAULT_DRAFT_ITEM }];
      const idx = Math.min(selectedIdx, next.length - 1);
      const current = next[idx];
      const body = current.body_md ?? "";
      next[idx] = {
        ...current,
        body_md: body
          ? `${body.replace(/\s+$/, "")}\n\n- ${template}`
          : `- ${template}`,
      };
      return next;
    });
  }, [selectedIdx]);

  // Bail out completely on 401 — no workspace data shown.
  if (isUnauthorized) {
    return (
      <div
        data-screen-id="S-021"
        data-feature-id="F-006"
        data-screen-name="requirements_editor"
        data-task-ids="T-V3-C-47,T-V3-SCR-06"
        data-entities="E-016,E-021"
        data-phase="Phase 1"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  const requirements = data?.requirements ?? [];
  const version = savedVersion ?? data?.version ?? 0;
  const stats = countEarsLines(draftItems);
  const draftIsDirty =
    JSON.stringify(draftItems) !== JSON.stringify(requirements);
  const versionBadge = `v${version}${draftIsDirty ? ".draft" : ""}`;

  return (
    <div
      data-screen-id="S-021"
      data-feature-id="F-006"
      data-screen-name="requirements_editor"
      data-task-ids="T-V3-C-47,T-V3-SCR-06"
      data-entities="E-016,E-021"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900 flex font-sans"
    >
      {/* Sidebar — left nav (mock parity) */}
      <aside className="w-[240px] bg-eb-700 text-white flex flex-col shrink-0">
        <div className="px-5 py-4 border-b border-eb-600">
          <div className="text-[11px] tracking-widest text-eb-100 font-bold">
            BUILD-FACTORY
          </div>
          <div className="text-sm font-bold mt-1">Build-Factory dogfood</div>
        </div>
        <nav className="flex-1 px-2 py-3 text-sm space-y-0.5 overflow-y-auto">
          <a
            href="/dashboard"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <LayoutDashboard className="w-4 h-4" aria-hidden />
            ダッシュボード
          </a>
          <div className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold">
            Spec
          </div>
          <a
            href="/spec/hearing"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <Mic className="w-4 h-4" aria-hidden />
            ヒアリング
          </a>
          <span
            aria-current="page"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 bg-eb-600 font-semibold"
          >
            <FileText className="w-4 h-4" aria-hidden />
            要件エディタ
          </span>
          <a
            href="/spec/viewer"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <BookOpen className="w-4 h-4" aria-hidden />
            仕様書
          </a>
          <a
            href="/spec/mock-viewer"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <Box className="w-4 h-4" aria-hidden />
            画面 Mock
          </a>
          <a
            href="/spec/components"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <Box className="w-4 h-4" aria-hidden />
            Components
          </a>
          <a
            href="/spec/flow-map"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <MapIcon className="w-4 h-4" aria-hidden />
            Flow Map
          </a>
          <a
            href="/spec/html-editor"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <Edit3 className="w-4 h-4" aria-hidden />
            HTML エディタ
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

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-3 border-b border-slate-200 bg-white flex items-center justify-between flex-shrink-0">
          <div>
            <h1 className="text-lg font-bold flex items-center gap-2">
              <FileText className="w-5 h-5 text-eb-500" aria-hidden />
              {S021_H1_TEXT}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              EARS notation で受け入れ条件を記述 / Markdown + 構造化エディタ
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span
              data-testid="requirements-version-badge"
              className="text-[11px] bg-amber-50 text-amber-700 border border-amber-200 px-2 py-1 rounded-full mono"
            >
              {versionBadge}
            </span>
            <button
              type="button"
              data-testid="requirements-save-button"
              onClick={handleSave}
              disabled={isSaving || isLoading}
              className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2 disabled:opacity-50"
            >
              <Save className="w-4 h-4" aria-hidden />
              {isSaving ? "保存中…" : "保存"}
            </button>
            <button
              type="button"
              data-testid="requirements-preview-button"
              className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2"
            >
              <Eye className="w-4 h-4" aria-hidden />
              プレビュー
            </button>
            <button
              type="button"
              data-testid="requirements-publish-button"
              onClick={handlePublish}
              disabled={isSnapshotting || isLoading}
              className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md flex items-center gap-2 disabled:opacity-50"
            >
              <UploadCloud className="w-4 h-4" aria-hidden />
              {isSnapshotting ? "公開中…" : "公開 (publish)"}
            </button>
          </div>
        </div>

        {/* AC-F1: inline error toast on 4xx */}
        {errorMessage && (
          <div
            role="alert"
            data-testid="requirements-editor-error"
            className="mx-6 mt-4 p-3 rounded-md bg-amber-50 border border-amber-300 text-amber-800 text-sm flex items-start gap-2"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
            <span>{errorMessage}</span>
            <button
              type="button"
              onClick={() => {
                setErrorMessage(null);
                void refetch();
              }}
              className="ml-auto text-xs underline"
            >
              再読み込み
            </button>
          </div>
        )}

        {/* Body grid: outline + editor + helper */}
        <div className="flex-1 grid grid-cols-[260px_1fr_320px] overflow-hidden">
          {/* TOC sidebar */}
          <aside className="border-r border-slate-200 bg-white overflow-y-auto p-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold px-2 pb-2">
              Outline
            </div>
            <div className="space-y-0.5 text-sm">
              <span className="block px-2 py-1.5 rounded-md text-slate-700">
                1. プロジェクト概要
              </span>
              <span className="block px-2 py-1.5 rounded-md bg-eb-50 text-eb-700 font-semibold">
                {S021_SECTION_H2[0]}
              </span>
              {draftItems.map((item, idx) => (
                <button
                  key={`outline-${idx}`}
                  type="button"
                  data-testid={`outline-item-${idx}`}
                  onClick={() => setSelectedIdx(idx)}
                  className={`block w-full text-left px-2 py-1.5 rounded-md text-slate-700 pl-6 text-xs ${
                    idx === selectedIdx
                      ? "bg-slate-100 font-semibold"
                      : "hover:bg-slate-50"
                  }`}
                >
                  {item.section || `2.${idx + 1}`}
                </button>
              ))}
              <span className="block px-2 py-1.5 rounded-md text-slate-700">
                3. 非機能要件
              </span>
              <span className="block px-2 py-1.5 rounded-md text-slate-700">
                4. 制約条件
              </span>
              <span className="block px-2 py-1.5 rounded-md text-slate-700">
                5. 受け入れ基準 (AC)
              </span>
            </div>

            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold px-2 pt-4 pb-2">
              History
            </div>
            <div
              className="space-y-1 text-xs"
              data-testid="requirements-history"
            >
              <div className="px-2 py-1.5 rounded-md bg-eb-50 mono">
                <span className="font-bold text-eb-700">v{version}</span>
                {" · "}
                {draftIsDirty ? "draft" : "saved"}
              </div>
              {version > 1 && (
                <div className="px-2 py-1.5 rounded-md hover:bg-slate-50 mono cursor-pointer">
                  <span className="font-bold">v{version - 1}</span> · published
                </div>
              )}
            </div>
          </aside>

          {/* Editor */}
          <div className="flex flex-col overflow-hidden bg-white">
            <div className="px-4 py-2 border-b border-slate-200 bg-slate-50 flex items-center gap-2 text-xs">
              <button
                type="button"
                className="px-2 py-1 rounded hover:bg-slate-200 font-bold"
                aria-label="bold"
              >
                B
              </button>
              <button
                type="button"
                className="px-2 py-1 rounded hover:bg-slate-200 italic"
                aria-label="italic"
              >
                I
              </button>
              <button
                type="button"
                className="px-2 py-1 rounded hover:bg-slate-200"
                aria-label="bulleted list"
              >
                <List className="w-3.5 h-3.5" aria-hidden />
              </button>
              <button
                type="button"
                className="px-2 py-1 rounded hover:bg-slate-200"
                aria-label="code"
              >
                <Code className="w-3.5 h-3.5" aria-hidden />
              </button>
              <div className="w-px h-4 bg-slate-300" aria-hidden />
              <button
                type="button"
                data-testid="add-ac-button"
                onClick={() =>
                  handleAddAcTemplate("When [event], the system shall ...")
                }
                className="px-2 py-1 rounded hover:bg-eb-100 text-eb-700 font-semibold text-xs flex items-center gap-1"
              >
                <Plus className="w-3 h-3" aria-hidden />
                AC 追加 (EARS)
              </button>
              <span className="ml-auto text-slate-500 mono">
                Markdown · Auto-save
              </span>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-6">
              <article className="max-w-3xl">
                <h1 className="text-2xl font-bold mb-2">
                  Build-Factory 要件定義 {versionBadge}
                </h1>
                <p className="text-xs text-slate-500 mb-6">
                  masato@engine-base.com
                </p>

                {S021_SECTION_H2.map((heading) => (
                  <h2
                    key={heading}
                    data-testid="requirements-section-h2"
                    className="text-lg font-bold mb-3 mt-6"
                  >
                    {heading}
                  </h2>
                ))}

                {isLoading && (
                  <div
                    role="status"
                    aria-live="polite"
                    data-testid="requirements-loading"
                    className="text-sm text-slate-500"
                  >
                    読み込み中…
                  </div>
                )}

                {!isLoading && draftItems.length === 0 && (
                  <div
                    data-testid="requirements-empty"
                    className="text-sm text-slate-500"
                  >
                    まだ要件が登録されていません。「AC 追加 (EARS)」から始めましょう。
                  </div>
                )}

                {!isLoading &&
                  draftItems.map((item, idx) => (
                    <div
                      key={`item-${idx}`}
                      data-testid={`requirements-item-${idx}`}
                      className={`mb-4 ${
                        idx === selectedIdx
                          ? "ring-2 ring-eb-400 rounded-md"
                          : ""
                      }`}
                    >
                      <label
                        className="block text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1"
                        htmlFor={`item-section-${idx}`}
                      >
                        section
                      </label>
                      <input
                        id={`item-section-${idx}`}
                        type="text"
                        data-testid={`item-section-${idx}`}
                        value={item.section}
                        onChange={(e) =>
                          setDraftItems((items) => {
                            const next = [...items];
                            next[idx] = { ...next[idx], section: e.target.value };
                            return next;
                          })
                        }
                        onFocus={() => setSelectedIdx(idx)}
                        className="w-full mb-2 px-2 py-1 text-sm border border-slate-200 rounded"
                      />
                      <label
                        className="block text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1"
                        htmlFor={`item-body-${idx}`}
                      >
                        body_md (Markdown + EARS AC)
                      </label>
                      <textarea
                        id={`item-body-${idx}`}
                        data-testid={`item-body-${idx}`}
                        value={item.body_md}
                        onFocus={() => setSelectedIdx(idx)}
                        onChange={(e) =>
                          setDraftItems((items) => {
                            const next = [...items];
                            next[idx] = {
                              ...next[idx],
                              body_md: e.target.value,
                            };
                            return next;
                          })
                        }
                        rows={6}
                        className="w-full mono text-sm border border-slate-200 rounded p-2"
                      />
                    </div>
                  ))}

                <p className="text-sm text-slate-600 leading-relaxed mb-3 mt-4">
                  ※ AC は EARS notation (Easy Approach to Requirements Syntax)
                  で書く。5 形式: UBIQUITOUS / EVENT-DRIVEN / STATE-DRIVEN /
                  OPTIONAL / UNWANTED。
                </p>
              </article>
            </div>
          </div>

          {/* EARS helper panel */}
          <aside className="border-l border-slate-200 bg-white overflow-y-auto">
            <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
              <Zap className="w-4 h-4 text-eb-500" aria-hidden />
              <span className="text-sm font-bold">EARS Helper</span>
            </div>
            <div className="p-4 space-y-3 text-xs">
              <button
                type="button"
                data-testid="ai-draft-button"
                className="w-full bg-eb-500 hover:bg-eb-600 text-white font-semibold py-2 rounded-md flex items-center justify-center gap-2"
              >
                <Sparkles className="w-3.5 h-3.5" aria-hidden />
                AI で AC 草案生成
              </button>
              {EARS_HELPER.map((entry) => (
                <button
                  key={entry.title}
                  type="button"
                  data-testid={`ears-helper-${entry.form}`}
                  onClick={() => handleAddAcTemplate(entry.template)}
                  className={`w-full text-left border rounded-md p-2 ${helperVariantClass(entry.variant)}`}
                >
                  <div className="font-bold text-slate-700 mb-1 flex items-center gap-1">
                    {entry.title}
                    {entry.variant === "primary" && (
                      <Star className="w-3 h-3" aria-hidden />
                    )}
                  </div>
                  <code className="block mono text-[11px] text-slate-600">
                    {entry.template}
                  </code>
                </button>
              ))}

              <div className="border-t border-slate-200 pt-3 mt-3">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-2">
                  バリデーション
                </div>
                <div
                  className="text-xs text-slate-700 space-y-1"
                  data-testid="ears-validation"
                >
                  <div className="flex items-center gap-1.5">
                    <CheckCircle2
                      className="w-3 h-3 text-emerald-600"
                      aria-hidden
                    />
                    EARS 形式 OK ({stats.total - stats.unmatched}/{stats.total})
                  </div>
                  {stats.unmatched > 0 && (
                    <div
                      className="flex items-center gap-1.5 text-amber-700"
                      data-testid="ears-validation-warning"
                    >
                      <AlertTriangle className="w-3 h-3" aria-hidden />
                      {stats.unmatched} 件が EARS 形式に一致しません
                    </div>
                  )}
                </div>
              </div>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
