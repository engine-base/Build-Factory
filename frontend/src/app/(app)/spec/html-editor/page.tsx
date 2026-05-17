"use client";

/**
 * S-026 HTML エディタ — T-V3-C-52 / F-005b.
 *
 * @screen-id S-026
 * @feature-id F-005b
 * @task-ids T-V3-C-52,T-V3-RF-10
 * @entities E-022,E-021
 * @phase Phase 1
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/spec/S-026-design-html-editor.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-52.md):
 *   structural.AC-S1: h1 == "HTML エディタ" (mock h1 逐語) inside
 *     data-screen-id="S-026" root.
 *   structural.AC-S2: Lucide icons exclusively — see imports below; no emoji
 *     glyphs in this file.
 *
 *   functional.AC-F1: On mount for an authenticated workspace member, GET
 *     /api/workspaces/{id}/mocks/{screen_id}/html. The 2xx body is dropped
 *     into the editor textarea + preview iframe (AC-F3 same call returns the
 *     latest version). 4xx surfaces a non-technical, endpoint-tagged toast
 *     and an empty state.
 *   functional.AC-F2: 401 from GET → router.replace("/login") and the page
 *     renders an aria-hidden shell instead of any workspace-scoped data.
 *   functional.AC-F3: GET html returns the latest version of the mock HTML —
 *     same call as AC-F1; the typed client / hook treat the 2xx body as
 *     authoritative.
 *
 * Backend contract (T-V3-B-08 list / T-V3-B-09 ai-edit + html GET/PUT):
 *   GET    /api/workspaces/{id}/mocks/{screen_id}/html        (member)
 *   PUT    /api/workspaces/{id}/mocks/{screen_id}/html        (workspace_admin)
 *   POST   /api/workspaces/{id}/mocks/{screen_id}/ai-edit     (member)
 *
 * Workspace + screen scoping: the page reads `?workspace=<id>` and
 * `?screen_id=<S-XXX>` from the search params. Defaults: `active` workspace
 * sentinel (accepted by the backend) and `S-006` (the screen displayed in the
 * v3 mock). The (app) layout will eventually supply the active workspace
 * automatically (see ROADMAP T-V3-RF-10).
 *
 * Editor surfaces: Three modes (GUI / AI / HTML) mirror the v3 mock toolbar.
 * GrapesJS core (BSD-3) is intentionally NOT loaded at runtime here — the
 * lightweight HTML textarea is the contract surface for T-V3-C-52 (4h budget).
 * A follow-up vertical slice (T-V3-RF-10) will swap the textarea for the
 * full GrapesJS canvas; that swap is feature-flagged via `editorMode` so the
 * AC-F1/F2/F3 wiring tested here remains the source of truth.
 */

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Badge,
  BarChart3,
  Bot,
  Box,
  Code,
  Copy,
  Edit3,
  Image as ImageIcon,
  Layout,
  LayoutDashboard,
  Redo2,
  Save,
  Sparkles,
  Square,
  Table as TableIcon,
  TextCursorInput,
  Type,
  Undo2,
} from "lucide-react";

import {
  DesignHtmlEditorApiError,
  htmlEditorAiEditEndpoint,
  htmlEditorGetEndpoint,
} from "@/api/design-html-editor";
import { useDesignHtmlEditor } from "@/hooks/use-design-html-editor";

// --------------------------------------------------------------------------
// Mock-derived literals — 逐語 from docs/mocks/2026-05-15_v3/spec/S-026-*.html
// --------------------------------------------------------------------------

const S026_H1_TEXT = "HTML エディタ";
const DEFAULT_SCREEN_ID = "S-006";

interface ComponentChip {
  label: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  group: "base" | "bf";
}

// Lucide-icon-only component palette (AC-S2).
const COMPONENT_PALETTE: ComponentChip[] = [
  { label: "Container", icon: Box, group: "base" },
  { label: "Heading", icon: Type, group: "base" },
  { label: "Button", icon: Square, group: "base" },
  { label: "Input", icon: TextCursorInput, group: "base" },
  { label: "Image", icon: ImageIcon, group: "base" },
  { label: "Table", icon: TableIcon, group: "base" },
  { label: "KPI Card", icon: BarChart3, group: "bf" },
  { label: "AI Chip", icon: Bot, group: "bf" },
  { label: "Badge", icon: Badge, group: "bf" },
];

type EditorMode = "gui" | "ai" | "html";

interface ChatTurn {
  who: "designer" | "user";
  text: string;
  ts: string;
}

// --------------------------------------------------------------------------
// Page component
// --------------------------------------------------------------------------

export default function DesignHtmlEditorPage(): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = searchParams?.get("workspace") ?? "active";
  const screenId = searchParams?.get("screen_id") ?? DEFAULT_SCREEN_ID;

  const editor = useDesignHtmlEditor({
    workspaceId,
    screenId,
    authToken: null,
  });

  const [mode, setMode] = React.useState<EditorMode>("gui");
  const [draftHtml, setDraftHtml] = React.useState<string>("");
  const [prompt, setPrompt] = React.useState<string>("");
  const [chat, setChat] = React.useState<ChatTurn[]>([
    {
      who: "designer",
      text: "こんにちは、自然言語で編集指示してください。",
      ts: "14:30",
    },
  ]);
  const [aiError, setAiError] = React.useState<string | null>(null);
  const [saveBanner, setSaveBanner] = React.useState<string | null>(null);

  // Sync the fetched HTML into the local draft when GET resolves so the
  // textarea / preview iframe always reflect the latest server version.
  React.useEffect(() => {
    if (editor.state === "loaded" && typeof editor.html === "string") {
      setDraftHtml(editor.html);
    }
  }, [editor.state, editor.html]);

  // ----------------------------------------------------------------------
  // AC-F2: 401 from GET html → router.replace("/login") and never render
  // any workspace-scoped data.
  // ----------------------------------------------------------------------
  React.useEffect(() => {
    if (editor.error && editor.error.status === 401) {
      router.replace("/login");
    }
  }, [editor.error, router]);

  if (editor.error && editor.error.status === 401) {
    return (
      <div
        data-screen-id="S-026"
        data-feature-id="F-005b"
        data-task-ids="T-V3-C-52,T-V3-RF-10"
        data-entities="E-022,E-021"
        data-phase="Phase 1"
        data-screen-name="design_html_editor"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  const surfacedErrorMessage =
    editor.error && editor.error.status !== 401
      ? editor.error.toUserMessage()
      : null;

  // ----------------------------------------------------------------------
  // Handlers
  // ----------------------------------------------------------------------

  const handleSave = async () => {
    setSaveBanner(null);
    try {
      const resp = await editor.save(draftHtml);
      setSaveBanner(
        resp.new_version != null
          ? `v${resp.new_version} を保存しました`
          : "新バージョンを保存しました",
      );
    } catch (err) {
      if (err instanceof DesignHtmlEditorApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      // Non-401 errors will surface via editor.error / surfacedErrorMessage.
    }
  };

  const handleAiSubmit = async () => {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    setAiError(null);
    const now = new Date();
    const ts = `${String(now.getHours()).padStart(2, "0")}:${String(
      now.getMinutes(),
    ).padStart(2, "0")}`;
    setChat((prev) => [...prev, { who: "user", text: trimmed, ts }]);
    setPrompt("");
    try {
      const resp = await editor.aiEdit(trimmed);
      const responseText =
        resp.diff && resp.diff.length > 0
          ? resp.diff
          : "プロンプトを受信しました。プレビューで確認してください。";
      setChat((prev) => [
        ...prev,
        { who: "designer", text: responseText, ts },
      ]);
      if (typeof resp.new_html === "string" && resp.new_html.length > 0) {
        setDraftHtml(resp.new_html);
      }
    } catch (err) {
      if (err instanceof DesignHtmlEditorApiError) {
        if (err.status === 401) {
          router.replace("/login");
          return;
        }
        setAiError(err.toUserMessage());
      } else {
        setAiError(
          `通信に失敗しました (${htmlEditorAiEditEndpoint(
            workspaceId,
            screenId,
          )})`,
        );
      }
    }
  };

  const copyPrompt = async () => {
    if (typeof navigator === "undefined" || !navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(draftHtml ?? "");
    } catch {
      // Clipboard blocked — non-fatal, no AC-S* impact.
    }
  };

  // ----------------------------------------------------------------------
  // Render
  // ----------------------------------------------------------------------

  return (
    <div
      data-screen-id="S-026"
      data-feature-id="F-005b"
      data-task-ids="T-V3-C-52,T-V3-RF-10"
      data-entities="E-022,E-021"
      data-phase="Phase 1"
      data-screen-name="design_html_editor"
      className="min-h-screen bg-slate-50 text-slate-900 flex"
    >
      {/* Left rail — matches mock S-026 sidebar */}
      <aside className="w-[200px] bg-eb-700 text-white flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-eb-600">
          <div className="text-[10px] tracking-widest text-eb-100 font-bold">
            BUILD-FACTORY
          </div>
          <div className="text-xs font-bold mt-1">dogfood</div>
        </div>
        <nav className="flex-1 px-2 py-3 text-sm space-y-0.5 overflow-y-auto">
          <a
            href="/dashboard"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100 text-xs"
          >
            <LayoutDashboard className="w-3.5 h-3.5" aria-hidden />
            ダッシュ
          </a>
          <div className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold">
            Spec
          </div>
          <a
            href="/spec/mocks"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100 text-xs"
          >
            <Layout className="w-3.5 h-3.5" aria-hidden />
            画面 Mock
          </a>
          <a
            href="/spec/components"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100 text-xs"
          >
            <Box className="w-3.5 h-3.5" aria-hidden />
            Components
          </a>
          <span
            aria-current="page"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 bg-eb-600 font-semibold text-xs"
          >
            <Edit3 className="w-3.5 h-3.5" aria-hidden />
            HTML エディタ
          </span>
        </nav>
        <a
          href="/dashboard"
          className="px-3 py-2 border-t border-eb-600 text-[11px] text-eb-100 inline-flex items-center gap-1 hover:text-white"
        >
          <ArrowLeft className="w-3 h-3" aria-hidden />
          ダッシュボードへ戻る
        </a>
      </aside>

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar — h1 + mode tabs + save action */}
        <div className="px-4 py-2 border-b border-slate-200 bg-white flex items-center gap-3 flex-shrink-0">
          <h1 className="text-sm font-bold flex items-center gap-2">
            <Edit3 className="w-4 h-4 text-eb-500" aria-hidden />
            {S026_H1_TEXT}
          </h1>
          <span
            className="text-[11px] mono text-slate-500"
            data-testid="editor-active-screen"
          >
            editing: {screenId}
          </span>
          <div className="ml-auto flex items-center gap-1.5 text-xs">
            <button
              type="button"
              data-testid="mode-gui"
              onClick={() => setMode("gui")}
              className={`px-3 py-1 rounded-md flex items-center gap-1 ${
                mode === "gui"
                  ? "bg-white border border-eb-500 text-eb-500 font-semibold"
                  : "hover:bg-slate-50 text-slate-600 border border-transparent"
              }`}
            >
              <Layout className="w-3 h-3" aria-hidden />
              GUI
            </button>
            <button
              type="button"
              data-testid="mode-ai"
              onClick={() => setMode("ai")}
              className={`px-3 py-1 rounded-md flex items-center gap-1 ${
                mode === "ai"
                  ? "bg-white border border-eb-500 text-eb-500 font-semibold"
                  : "hover:bg-slate-50 text-slate-600 border border-transparent"
              }`}
            >
              <Sparkles className="w-3 h-3" aria-hidden />
              AI
            </button>
            <button
              type="button"
              data-testid="mode-html"
              onClick={() => setMode("html")}
              className={`px-3 py-1 rounded-md flex items-center gap-1 ${
                mode === "html"
                  ? "bg-white border border-eb-500 text-eb-500 font-semibold"
                  : "hover:bg-slate-50 text-slate-600 border border-transparent"
              }`}
            >
              <Code className="w-3 h-3" aria-hidden />
              HTML
            </button>
            <div className="w-px h-5 bg-slate-200 mx-2" />
            <button
              type="button"
              aria-label="Undo"
              className="border border-slate-200 hover:bg-slate-50 h-8 px-3 rounded-md flex items-center gap-1"
            >
              <Undo2 className="w-3.5 h-3.5" aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Redo"
              className="border border-slate-200 hover:bg-slate-50 h-8 px-3 rounded-md flex items-center gap-1"
            >
              <Redo2 className="w-3.5 h-3.5" aria-hidden />
            </button>
            <button
              type="button"
              data-testid="copy-as-prompt"
              onClick={() => void copyPrompt()}
              className="border border-slate-200 hover:bg-slate-50 h-8 px-3 rounded-md flex items-center gap-1"
            >
              <Copy className="w-3.5 h-3.5" aria-hidden />
              Copy as Prompt
            </button>
            <button
              type="button"
              data-testid="editor-save"
              onClick={() => void handleSave()}
              disabled={editor.saving}
              className="bg-eb-500 hover:bg-eb-600 text-white h-8 px-3 rounded-md font-semibold flex items-center gap-1 disabled:opacity-60"
            >
              <Save className="w-3.5 h-3.5" aria-hidden />
              新バージョン保存
            </button>
          </div>
        </div>

        {/* AC-F1 error toast — non-technical, endpoint-tagged. */}
        {surfacedErrorMessage ? (
          <div
            role="alert"
            data-testid="editor-error"
            className="mx-4 mt-3 rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-sm px-3 py-2 flex items-start gap-2"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
            <span>{surfacedErrorMessage}</span>
          </div>
        ) : null}

        {saveBanner ? (
          <div
            role="status"
            data-testid="editor-save-banner"
            className="mx-4 mt-3 rounded-md border border-emerald-200 bg-emerald-50 text-emerald-700 text-xs px-3 py-2"
          >
            {saveBanner}
          </div>
        ) : null}

        {/* Body: 4-pane grid mirroring the mock layout. */}
        <div className="flex-1 grid grid-cols-[200px_1fr_240px_280px] overflow-hidden">
          {/* Component palette */}
          <aside className="border-r border-slate-200 bg-white overflow-y-auto">
            <div className="px-3 py-2 border-b border-slate-200">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                Components
              </div>
            </div>
            <div className="p-2 space-y-1" data-testid="component-palette">
              {COMPONENT_PALETTE.filter((c) => c.group === "base").map((c) => {
                const Icon = c.icon;
                return (
                  <button
                    type="button"
                    key={c.label}
                    data-testid={`palette-${c.label.toLowerCase()}`}
                    className="w-full border border-slate-200 hover:border-eb-500 rounded-md p-2 text-left flex items-center gap-2 text-xs cursor-grab"
                  >
                    <Icon className="w-3.5 h-3.5" aria-hidden />
                    {c.label}
                  </button>
                );
              })}
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold pt-3 pb-1 px-1">
                Build-Factory
              </div>
              {COMPONENT_PALETTE.filter((c) => c.group === "bf").map((c) => {
                const Icon = c.icon;
                return (
                  <button
                    type="button"
                    key={c.label}
                    data-testid={`palette-bf-${c.label.toLowerCase().replace(/\s+/g, "-")}`}
                    className="w-full border border-eb-200 bg-eb-50 hover:bg-eb-100 rounded-md p-2 text-left flex items-center gap-2 text-xs cursor-grab"
                  >
                    <Icon className="w-3.5 h-3.5" aria-hidden />
                    {c.label}
                  </button>
                );
              })}
            </div>
          </aside>

          {/* Canvas / textarea pane (mode-switched) */}
          <div className="bg-slate-100 overflow-auto flex flex-col">
            {editor.state === "loading" ? (
              <div
                role="status"
                aria-live="polite"
                data-testid="editor-loading"
                className="flex-1 flex items-center justify-center text-sm text-slate-500"
              >
                読み込み中…
              </div>
            ) : editor.state === "error" || draftHtml === "" ? (
              <div
                role="status"
                data-testid="editor-empty"
                className="flex-1 flex items-center justify-center text-sm text-slate-500"
              >
                {editor.state === "error"
                  ? "モックを読み込めませんでした。"
                  : `モックは未生成です (${htmlEditorGetEndpoint(workspaceId, screenId)})`}
              </div>
            ) : mode === "html" ? (
              <textarea
                data-testid="editor-textarea"
                aria-label="HTML エディタ"
                value={draftHtml}
                onChange={(e) => setDraftHtml(e.target.value)}
                className="flex-1 w-full h-full bg-slate-900 text-slate-50 font-mono text-xs p-4 outline-none"
              />
            ) : (
              <div className="flex-1 p-4 overflow-auto flex items-start justify-center">
                <iframe
                  data-testid="editor-preview"
                  title={`design html editor preview ${screenId}`}
                  srcDoc={draftHtml}
                  sandbox="allow-same-origin"
                  className="w-full max-w-[900px] h-full min-h-[480px] bg-white rounded shadow border border-slate-200"
                />
              </div>
            )}
          </div>

          {/* Style panel (placeholder — wired in T-V3-RF-10 with GrapesJS) */}
          <aside className="border-l border-slate-200 bg-white overflow-y-auto">
            <div className="px-3 py-2 border-b border-slate-200">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                Style
              </div>
            </div>
            <div className="p-3 space-y-3 text-xs" data-testid="style-panel">
              <div>
                <div className="font-bold mb-1">Text</div>
                <input
                  type="text"
                  defaultValue=""
                  placeholder="text"
                  aria-label="text style value"
                  className="border border-slate-200 px-2 py-1 rounded text-xs w-full"
                />
              </div>
              <div>
                <div className="font-bold mb-1">Color</div>
                <div className="flex items-center gap-1.5">
                  <span
                    aria-label="eb-500 swatch"
                    className="w-6 h-6 rounded border-2 border-eb-500 bg-eb-500"
                  />
                  <span
                    aria-label="slate-900 swatch"
                    className="w-6 h-6 rounded border border-slate-200 bg-slate-900"
                  />
                  <span
                    aria-label="slate-600 swatch"
                    className="w-6 h-6 rounded border border-slate-200 bg-slate-600"
                  />
                  <span
                    aria-label="red-600 swatch"
                    className="w-6 h-6 rounded border border-slate-200 bg-red-600"
                  />
                </div>
              </div>
            </div>
          </aside>

          {/* AI chat panel */}
          <aside className="border-l border-slate-200 bg-white overflow-y-auto flex flex-col">
            <div className="px-3 py-2 border-b border-slate-200 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-eb-500" aria-hidden />
              <span className="text-sm font-bold">AI 編集 (designer)</span>
            </div>
            <div
              className="flex-1 overflow-y-auto p-3 space-y-3 text-xs"
              data-testid="ai-chat-log"
            >
              {chat.map((turn, idx) => (
                <div
                  key={idx}
                  data-testid={`ai-chat-turn-${turn.who}`}
                  className={
                    turn.who === "designer"
                      ? "bg-slate-50 border border-slate-200 rounded-md p-2"
                      : "bg-eb-50 border border-eb-200 rounded-md p-2 ml-4"
                  }
                >
                  <div className="text-[10px] text-slate-500 mb-0.5">
                    {turn.who} · {turn.ts}
                  </div>
                  <p>{turn.text}</p>
                </div>
              ))}
              {aiError ? (
                <div
                  role="alert"
                  data-testid="ai-error"
                  className="rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-[11px] px-2 py-1.5 flex items-start gap-1"
                >
                  <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" aria-hidden />
                  <span>{aiError}</span>
                </div>
              ) : null}
            </div>
            <div className="border-t border-slate-200 p-2">
              <textarea
                data-testid="ai-prompt"
                aria-label="編集指示を入力"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="編集指示を入力..."
                className="border border-slate-200 bg-white text-xs px-2 py-1.5 rounded-md w-full min-h-[40px]"
              />
              <button
                type="button"
                data-testid="ai-submit"
                onClick={() => void handleAiSubmit()}
                disabled={editor.aiEditing || prompt.trim().length === 0}
                className="w-full bg-eb-500 hover:bg-eb-600 text-white text-xs font-semibold h-7 rounded-md mt-1 disabled:opacity-60"
              >
                送信
              </button>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
