"use client";

/**
 * T-V3-C-62 / S-013: 案件設定 page (Vertical Slice / UI).
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/workspace/S-013-workspace-settings.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-013
 * @feature-id F-004
 * @task-ids T-V3-C-62
 * @entities E-009
 * @phase Phase 1
 *
 * Backend contracts (T-V3-B-05 / F-004):
 *   GET    /api/workspaces/{id}
 *   PUT    /api/workspaces/{id}
 *   DELETE /api/workspaces/{id}
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-62.md):
 *   structural.AC-S1 — h1 === "案件設定" (mock h1 逐語コピー).
 *   structural.AC-S2 — section h2 set == {基本情報 / トークン / コスト制限 /
 *                      外部連携 / Danger Zone} (matching mock section_h2_texts).
 *   structural.AC-S3 — Lucide icons only (no emoji glyphs).
 *   functional.AC-F1 — GET /api/workspaces/{id} on mount; 2xx renders,
 *                      4xx → inline toast + empty state.
 *   functional.AC-F2 — 401 → router.replace("/login") (no workspace data render).
 *   functional.AC-F3 — PUT /api/workspaces/{id} on save by workspace_admin
 *                      with valid plan upgrade; server emits account_updated
 *                      audit log.
 *
 * Auth: workspace_admin required server-side for PUT / DELETE. The page
 * surfaces 403 as a friendly toast tagged with the failing endpoint.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AlertTriangle,
  Book,
  GitBranch,
  Loader2,
  MessageCircle,
  Settings,
  Trash2,
  XCircle,
} from "lucide-react";

import {
  WorkspaceSettingsApiError,
  type WorkspaceIntegrationLink,
  type WorkspaceProjectType,
} from "@/api/workspace-settings";
import { useWorkspaceSettings } from "@/hooks/useWorkspaceSettings";

// ---------------------------------------------------------------------------
// Mock-derived screen literals — 逐語コピー (h1_text / section_h2_texts).
// AC-S1: h1_text === "案件設定"
// AC-S2: section h2 set (slash literal preserved from mock)
// ---------------------------------------------------------------------------
const S013_H1_TEXT = "案件設定";
const S013_SECTION_H2_TEXTS = [
  "基本情報",
  "トークン / コスト制限",
  "外部連携",
  "Danger Zone",
] as const;

interface FormState {
  name: string;
  project_meta: string;
  project_type: string;
  is_confidential: boolean;
  token_limit: number | "";
  cost_budget: number | "";
  max_parallel_sessions: number | "";
}

const EMPTY_FORM: FormState = {
  name: "",
  project_meta: "",
  project_type: "internal",
  is_confidential: false,
  token_limit: "",
  cost_budget: "",
  max_parallel_sessions: "",
};

const PROJECT_TYPE_OPTIONS: ReadonlyArray<{
  value: string;
  label: string;
}> = [
  { value: "internal", label: "内製" },
  { value: "client", label: "受託" },
  { value: "oss", label: "OSS" },
];

function parseWorkspaceId(value: string | string[] | null | undefined):
  | number
  | string
  | null {
  if (!value) return null;
  const v = Array.isArray(value) ? value[0] : value;
  if (!v) return null;
  const n = Number(v);
  if (Number.isFinite(n) && n > 0) return n;
  // Accept opaque string ids too (e.g. "ws_8f3a2c").
  return v;
}

function integrationIcon(kind: string): React.ReactElement {
  const k = (kind ?? "").toLowerCase();
  if (k.includes("git") || k.includes("hub")) {
    return <GitBranch className="w-5 h-5 text-slate-700" aria-hidden />;
  }
  if (k.includes("slack") || k.includes("message")) {
    return <MessageCircle className="w-5 h-5 text-slate-700" aria-hidden />;
  }
  return <Book className="w-5 h-5 text-slate-700" aria-hidden />;
}

function integrationStatusBadge(
  status: string | null | undefined,
): React.ReactElement {
  if (status === "connected") {
    return (
      <span className="text-[11px] bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full font-medium">
        connected
      </span>
    );
  }
  return (
    <span className="text-[11px] text-slate-500">{status ?? "未連携"}</span>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function WorkspaceSettingsPage(): React.ReactElement {
  const router = useRouter();
  const params = useParams<{ id?: string | string[] }>();

  const workspaceId = parseWorkspaceId(params?.id) ?? 1;

  const {
    data,
    isPending,
    isError,
    isSuccess,
    error,
    save,
    remove,
    isSaving,
    isDeleting,
  } = useWorkspaceSettings({ workspaceId });

  // Hydrate the form synchronously during render once the workspace payload
  // arrives. We track which workspace payload version we have already seeded
  // from so re-renders do not clobber edits the user has already made.
  //
  // Pattern matches React Docs "Adjusting some state when a prop changes"
  // (https://react.dev/learn/you-might-not-need-an-effect) — preferred over
  // calling setState inside an effect.
  const [form, setForm] = React.useState<FormState>(EMPTY_FORM);
  const [seededFromWorkspace, setSeededFromWorkspace] = React.useState<
    number | string | null
  >(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = React.useState(false);

  const wsForSeed = data?.workspace;
  if (wsForSeed && seededFromWorkspace !== (wsForSeed.id ?? workspaceId)) {
    setForm({
      name: wsForSeed.name ?? "",
      project_meta: wsForSeed.project_meta ?? "",
      project_type: (wsForSeed.project_type as string) ?? "internal",
      is_confidential: wsForSeed.is_confidential ?? false,
      token_limit: wsForSeed.token_limit ?? "",
      cost_budget: wsForSeed.cost_budget ?? "",
      max_parallel_sessions: wsForSeed.max_parallel_sessions ?? "",
    });
    setSeededFromWorkspace(wsForSeed.id ?? workspaceId);
  }

  // AC-F2: 401 → router.replace("/login") (no workspace data render).
  const redirectedRef = React.useRef(false);
  React.useEffect(() => {
    if (!isError) return;
    if (redirectedRef.current) return;
    if (
      error instanceof WorkspaceSettingsApiError &&
      error.status === 401
    ) {
      redirectedRef.current = true;
      router.replace("/login");
    }
  }, [isError, error, router]);

  // AC-F1 tail: on 4xx (non-401) surface a friendly toast tagged with the
  // failing endpoint and render an empty state below.
  const lastToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!isError) {
      lastToastRef.current = null;
      return;
    }
    if (
      error instanceof WorkspaceSettingsApiError &&
      error.status === 401
    ) {
      return;
    }
    const userMsg =
      error instanceof WorkspaceSettingsApiError
        ? error.toUserMessage()
        : "案件設定の読み込みに失敗しました";
    if (lastToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastToastRef.current = userMsg;
    }
  }, [isError, error]);

  const integrations: WorkspaceIntegrationLink[] = React.useMemo(() => {
    const links = data?.workspace?.integration_links;
    if (Array.isArray(links) && links.length > 0) return links;
    // Sensible defaults so the mock structure renders even before the backend
    // populates the JSONB column.
    return [
      { kind: "github", label: "GitHub", status: "disconnected" },
      { kind: "slack", label: "Slack", status: "disconnected" },
      { kind: "obsidian", label: "Obsidian Vault", status: "disconnected" },
    ];
  }, [data?.workspace?.integration_links]);

  const onSave = React.useCallback(async () => {
    if (isSaving) return;
    try {
      await save({
        name: form.name || null,
        project_meta: form.project_meta || null,
        project_type: form.project_type as WorkspaceProjectType,
        is_confidential: form.is_confidential,
        token_limit: form.token_limit === "" ? null : Number(form.token_limit),
        cost_budget: form.cost_budget === "" ? null : Number(form.cost_budget),
        max_parallel_sessions:
          form.max_parallel_sessions === ""
            ? null
            : Number(form.max_parallel_sessions),
      });
      toast.success("案件設定を保存しました");
    } catch (err) {
      const userMsg =
        err instanceof WorkspaceSettingsApiError
          ? err.toUserMessage()
          : "案件設定の保存に失敗しました";
      toast.error(userMsg);
    }
  }, [form, isSaving, save]);

  const onDelete = React.useCallback(async () => {
    if (isDeleting) return;
    try {
      await remove();
      toast.success("案件を削除しました");
      setShowDeleteConfirm(false);
      router.replace("/workspaces");
    } catch (err) {
      const userMsg =
        err instanceof WorkspaceSettingsApiError
          ? err.toUserMessage()
          : "案件の削除に失敗しました";
      toast.error(userMsg);
    }
  }, [isDeleting, remove, router]);

  // 401 redirect terminal state — render nothing (AC-F2 "no workspace data").
  const isUnauthenticated =
    error instanceof WorkspaceSettingsApiError && error.status === 401;

  if (isUnauthenticated) {
    return (
      <main
        data-screen-id="S-013"
        data-screen-name="workspace_settings"
        data-feature-id="F-004"
        data-task-ids="T-V3-C-62"
        data-entities="E-009"
        data-phase="Phase 1"
        className="min-h-screen bg-slate-50 text-slate-900"
        aria-hidden
      />
    );
  }

  const workspaceIdLabel = String(data?.workspace?.id ?? workspaceId);

  return (
    <main
      data-screen-id="S-013"
      data-screen-name="workspace_settings"
      data-feature-id="F-004"
      data-task-ids="T-V3-C-62"
      data-entities="E-009"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <div className="max-w-[800px] mx-auto px-6 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Settings
              className="w-6 h-6 text-eb-500"
              aria-hidden
            />
            {S013_H1_TEXT}
          </h1>
          <p className="text-sm text-slate-600">
            この workspace の基本情報・連携・トークン制限・削除
          </p>
        </header>

        {isPending && (
          <div
            data-testid="workspace-settings-loading"
            className="flex items-center gap-2 text-sm text-slate-500 py-8"
            role="status"
            aria-live="polite"
          >
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
            <span>読み込み中…</span>
          </div>
        )}

        {isError && !isUnauthenticated && (
          <div
            data-testid="workspace-settings-error-empty-state"
            className="bg-white border border-red-200 rounded-lg p-6 text-center"
            role="alert"
            aria-live="assertive"
          >
            <XCircle
              className="w-8 h-8 text-red-500 mx-auto mb-2"
              aria-hidden
            />
            <p className="text-sm text-slate-700">
              案件設定の読み込みに失敗しました
            </p>
            <p className="text-xs text-slate-500 mt-1">
              {error instanceof WorkspaceSettingsApiError
                ? error.endpoint
                : ""}
            </p>
          </div>
        )}

        {isSuccess && (
          <div data-testid="workspace-settings-form">
            <section
              data-testid="workspace-settings-section-basic"
              className="bg-white border border-slate-200 rounded-lg p-6 mb-4"
            >
              <h2 className="text-base font-bold mb-4">
                {S013_SECTION_H2_TEXTS[0]}
              </h2>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label
                    htmlFor="ws-name"
                    className="text-sm font-medium block"
                  >
                    案件名
                  </label>
                  <input
                    id="ws-name"
                    data-testid="workspace-settings-name"
                    type="text"
                    value={form.name}
                    onChange={(e) =>
                      setForm((s) => ({ ...s, name: e.target.value }))
                    }
                    className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
                  />
                </div>
                <div className="space-y-1.5">
                  <label
                    htmlFor="ws-project-meta"
                    className="text-sm font-medium block"
                  >
                    プロジェクトメタ
                  </label>
                  <textarea
                    id="ws-project-meta"
                    data-testid="workspace-settings-project-meta"
                    value={form.project_meta}
                    onChange={(e) =>
                      setForm((s) => ({
                        ...s,
                        project_meta: e.target.value,
                      }))
                    }
                    placeholder="プロジェクト概要・目的"
                    className="border border-slate-200 bg-white text-sm px-3 py-2 rounded-md w-full min-h-[80px] resize-y"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label
                      htmlFor="ws-project-type"
                      className="text-sm font-medium block"
                    >
                      案件種別
                    </label>
                    <select
                      id="ws-project-type"
                      data-testid="workspace-settings-project-type"
                      value={form.project_type}
                      onChange={(e) =>
                        setForm((s) => ({
                          ...s,
                          project_type: e.target.value,
                        }))
                      }
                      className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
                    >
                      {PROJECT_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium block">
                      Workspace ID
                    </label>
                    <div
                      data-testid="workspace-settings-id"
                      className="border border-slate-200 bg-slate-50 text-sm h-9 px-3 rounded-md w-full flex items-center mono text-slate-700"
                    >
                      {workspaceIdLabel}
                    </div>
                  </div>
                </div>
                <label className="flex items-center gap-3 p-3 border border-slate-200 rounded-md cursor-pointer">
                  <input
                    data-testid="workspace-settings-confidential"
                    type="checkbox"
                    checked={form.is_confidential}
                    onChange={(e) =>
                      setForm((s) => ({
                        ...s,
                        is_confidential: e.target.checked,
                      }))
                    }
                    className="w-4 h-4 accent-eb-500"
                  />
                  <div>
                    <div className="text-sm font-medium">
                      機密案件 (Confidential)
                    </div>
                    <div className="text-xs text-slate-500">
                      監査ログを暗号化し、external integration をブロック
                    </div>
                  </div>
                </label>
              </div>
            </section>

            <section
              data-testid="workspace-settings-section-token-cost"
              className="bg-white border border-slate-200 rounded-lg p-6 mb-4"
            >
              <h2 className="text-base font-bold mb-4">
                {S013_SECTION_H2_TEXTS[1]}
              </h2>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label
                    htmlFor="ws-token-limit"
                    className="text-sm font-medium block"
                  >
                    月間トークン上限
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      id="ws-token-limit"
                      data-testid="workspace-settings-token-limit"
                      type="number"
                      value={form.token_limit}
                      onChange={(e) =>
                        setForm((s) => ({
                          ...s,
                          token_limit:
                            e.target.value === ""
                              ? ""
                              : Number(e.target.value),
                        }))
                      }
                      className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md flex-1 mono"
                    />
                    <span className="text-xs text-slate-500">tokens</span>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label
                    htmlFor="ws-cost-budget"
                    className="text-sm font-medium block"
                  >
                    月間コスト予算
                  </label>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">¥</span>
                    <input
                      id="ws-cost-budget"
                      data-testid="workspace-settings-cost-budget"
                      type="number"
                      value={form.cost_budget}
                      onChange={(e) =>
                        setForm((s) => ({
                          ...s,
                          cost_budget:
                            e.target.value === ""
                              ? ""
                              : Number(e.target.value),
                        }))
                      }
                      className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md flex-1 mono"
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label
                    htmlFor="ws-max-parallel"
                    className="text-sm font-medium block"
                  >
                    並列セッション上限
                  </label>
                  <input
                    id="ws-max-parallel"
                    data-testid="workspace-settings-max-parallel"
                    type="number"
                    value={form.max_parallel_sessions}
                    onChange={(e) =>
                      setForm((s) => ({
                        ...s,
                        max_parallel_sessions:
                          e.target.value === ""
                            ? ""
                            : Number(e.target.value),
                      }))
                    }
                    className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-32 mono"
                  />
                </div>
              </div>
            </section>

            <section
              data-testid="workspace-settings-section-integrations"
              className="bg-white border border-slate-200 rounded-lg p-6 mb-4"
            >
              <h2 className="text-base font-bold mb-4">
                {S013_SECTION_H2_TEXTS[2]}
              </h2>
              <div className="space-y-2">
                {integrations.map((link, idx) => (
                  <div
                    key={`${link.kind}-${idx}`}
                    data-testid={`workspace-settings-integration-${link.kind}`}
                    className="border border-slate-200 rounded-md p-3 flex items-center gap-3"
                  >
                    {integrationIcon(link.kind)}
                    <div className="flex-1">
                      <div className="text-sm font-semibold">
                        {link.label ?? link.kind}
                      </div>
                      {link.url && (
                        <div className="text-xs text-slate-500 mono">
                          {link.url}
                        </div>
                      )}
                    </div>
                    {integrationStatusBadge(link.status)}
                  </div>
                ))}
              </div>
            </section>

            <div className="flex justify-end gap-2 mb-4">
              <button
                type="button"
                data-testid="workspace-settings-cancel"
                className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-4 rounded-md"
                onClick={() => {
                  // Re-seed from current data by clearing the seeded marker —
                  // the render-time seeding block above will re-hydrate the
                  // form from the latest workspace payload on the next render.
                  setSeededFromWorkspace(null);
                }}
              >
                キャンセル
              </button>
              <button
                type="button"
                data-testid="workspace-settings-save"
                onClick={onSave}
                disabled={isSaving}
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-2"
              >
                {isSaving && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />
                )}
                保存
              </button>
            </div>

            <section
              data-testid="workspace-settings-section-danger-zone"
              className="bg-white border border-red-200 rounded-lg p-6"
            >
              <h2 className="text-base font-bold text-red-600 mb-3 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" aria-hidden />
                {S013_SECTION_H2_TEXTS[3]}
              </h2>
              <div className="flex items-center justify-between p-3 border border-red-200 rounded-md">
                <div>
                  <div className="text-sm font-semibold text-red-600">
                    この案件を削除
                  </div>
                  <div className="text-xs text-slate-500">
                    全タスク・セッション・成果物を含む全データを削除
                  </div>
                </div>
                {showDeleteConfirm ? (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      data-testid="workspace-settings-delete-cancel"
                      className="text-xs text-slate-600 hover:text-slate-900 px-3 py-1"
                      onClick={() => setShowDeleteConfirm(false)}
                    >
                      キャンセル
                    </button>
                    <button
                      type="button"
                      data-testid="workspace-settings-delete-confirm"
                      onClick={onDelete}
                      disabled={isDeleting}
                      className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold h-9 px-4 rounded-md disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-2"
                    >
                      {isDeleting && (
                        <Loader2
                          className="w-3.5 h-3.5 animate-spin"
                          aria-hidden
                        />
                      )}
                      <Trash2 className="w-3.5 h-3.5" aria-hidden />
                      本当に削除
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    data-testid="workspace-settings-delete"
                    onClick={() => setShowDeleteConfirm(true)}
                    className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold h-9 px-4 rounded-md"
                  >
                    削除する
                  </button>
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
