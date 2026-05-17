/**
 * T-V3-C-52 / S-026 — `useDesignHtmlEditor` hook.
 *
 * Encapsulates the data-fetching state machine for the HTML エディタ page:
 *   1. GET  /api/workspaces/{id}/mocks/{screen_id}/html      — on mount (AC-F1/F3)
 *   2. POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit   — natural-language edit
 *   3. PUT  /api/workspaces/{id}/mocks/{screen_id}/html      — "新バージョン保存"
 *
 * The hook only handles state. The page owns layout + redirect. Side effects
 * (fetch / redirect) stay testable because all network calls flow through
 * `globalThis.fetch` (mockable from vitest) via the @/api/design-html-editor
 * helpers.
 *
 * AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-52.md):
 *   AC-F1 (S-026) — GET on mount; 4xx surfaces toast + empty state.
 *   AC-F2 (S-026) — 401 propagated via DesignHtmlEditorApiError.status === 401
 *                   so the page can router.replace("/login") before any
 *                   workspace-scoped UI is committed.
 *   AC-F3 (S-026) — GET returns the latest version of the mock HTML.
 */

"use client";

import * as React from "react";

import {
  aiEditDesignHtml,
  DesignHtmlEditorApiError,
  type DesignHtmlEditorAiEditResponse,
  type DesignHtmlEditorSaveResponse,
  getDesignHtml,
  saveDesignHtml,
} from "@/api/design-html-editor";

export type EditorState = "idle" | "loading" | "loaded" | "error";

export interface UseDesignHtmlEditorOptions {
  workspaceId: string | null;
  screenId: string | null;
  /** Bearer token; null disables network calls. */
  authToken?: string | null;
  /** Test seam — defaults to global fetch via the API helpers. */
  fetchImpl?: typeof fetch;
}

export interface UseDesignHtmlEditorResult {
  /** GET state machine. */
  state: EditorState;
  /** Latest fetched HTML body (AC-F3). */
  html: string | null;
  /** The error returned by the most recent network call, or null. */
  error: DesignHtmlEditorApiError | null;
  /** True while a PUT save is in flight. */
  saving: boolean;
  /** True while a POST ai-edit is in flight. */
  aiEditing: boolean;
  /** Refetch GET /mocks/{screen_id}/html. */
  reload: () => Promise<void>;
  /** PUT /mocks/{screen_id}/html — returns server response or throws. */
  save: (html: string) => Promise<DesignHtmlEditorSaveResponse>;
  /** POST /mocks/{screen_id}/ai-edit — returns diff/new_html or throws. */
  aiEdit: (prompt: string) => Promise<DesignHtmlEditorAiEditResponse>;
}

/**
 * Single GET on mount + on (workspaceId, screenId) change. The hook is
 * intentionally provider-independent (no QueryClientProvider required) so the
 * vitest harness can drive 200 / 401 / 4xx branches via `globalThis.fetch`.
 */
export function useDesignHtmlEditor(
  options: UseDesignHtmlEditorOptions,
): UseDesignHtmlEditorResult {
  const { workspaceId, screenId, authToken, fetchImpl } = options;

  const [state, setState] = React.useState<EditorState>("idle");
  const [html, setHtml] = React.useState<string | null>(null);
  const [error, setError] = React.useState<DesignHtmlEditorApiError | null>(
    null,
  );
  const [saving, setSaving] = React.useState(false);
  const [aiEditing, setAiEditing] = React.useState(false);

  const reload = React.useCallback(async (): Promise<void> => {
    if (!workspaceId || !screenId) return;
    setState("loading");
    setError(null);
    try {
      const payload = await getDesignHtml(workspaceId, screenId, {
        authToken: authToken ?? null,
        fetchImpl,
      });
      setHtml(typeof payload.html === "string" ? payload.html : "");
      setState("loaded");
    } catch (err) {
      if (err instanceof DesignHtmlEditorApiError) {
        setError(err);
        setHtml(null);
        setState("error");
      } else {
        throw err;
      }
    }
  }, [workspaceId, screenId, authToken, fetchImpl]);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  const save = React.useCallback(
    async (htmlBody: string): Promise<DesignHtmlEditorSaveResponse> => {
      if (!workspaceId || !screenId) {
        throw new DesignHtmlEditorApiError(
          "design_html_editor.no_workspace",
          "workspaceId or screenId is null",
          0,
          "/api/workspaces/<missing>/mocks/<missing>/html",
        );
      }
      setSaving(true);
      try {
        const resp = await saveDesignHtml(
          workspaceId,
          screenId,
          { html: htmlBody },
          { authToken: authToken ?? null, fetchImpl },
        );
        // Keep local html in sync so the page's editor reflects what was just
        // persisted (avoids a follow-up GET round-trip).
        setHtml(htmlBody);
        return resp;
      } catch (err) {
        if (err instanceof DesignHtmlEditorApiError) setError(err);
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [workspaceId, screenId, authToken, fetchImpl],
  );

  const aiEdit = React.useCallback(
    async (prompt: string): Promise<DesignHtmlEditorAiEditResponse> => {
      if (!workspaceId || !screenId) {
        throw new DesignHtmlEditorApiError(
          "design_html_editor.no_workspace",
          "workspaceId or screenId is null",
          0,
          "/api/workspaces/<missing>/mocks/<missing>/ai-edit",
        );
      }
      setAiEditing(true);
      try {
        const resp = await aiEditDesignHtml(
          workspaceId,
          screenId,
          { prompt },
          { authToken: authToken ?? null, fetchImpl },
        );
        // When the AI returns a new_html body, treat it as a preview but do
        // not auto-commit — the page exposes 「適用」/「プレビュー」 buttons
        // and the user opts in via save().
        return resp;
      } catch (err) {
        if (err instanceof DesignHtmlEditorApiError) setError(err);
        throw err;
      } finally {
        setAiEditing(false);
      }
    },
    [workspaceId, screenId, authToken, fetchImpl],
  );

  return {
    state,
    html,
    error,
    saving,
    aiEditing,
    reload,
    save,
    aiEdit,
  };
}
