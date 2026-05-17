/**
 * T-V3-C-48 / F-005 / S-022 — useSpecViewer hook.
 *
 * Encapsulates the spec list + comments fetch + comment POST flow used by
 * `frontend/src/app/(app)/spec/viewer/[id]/page.tsx` (the S-022 page).
 *
 * Returns a tuple of {state, actions} so the page can stay focused on render.
 */
"use client";

import * as React from "react";

import {
  createSpecComment,
  getSpecComments,
  getSpecs,
  SpecsApiError,
  workspaceSpecCommentsEndpoint,
  workspaceSpecsEndpoint,
  type Spec,
  type SpecComment,
} from "@/api/specs";

export type SpecViewerStatus = "idle" | "loading" | "loaded" | "error";

export interface SpecViewerState {
  status: SpecViewerStatus;
  specs: Spec[];
  activeSpecId: string | null;
  comments: SpecComment[];
  errorMessage: string | null;
  posting: boolean;
}

export interface UseSpecViewerOptions {
  workspaceId: string | null;
  authToken: string | null;
  /** Initial spec id to focus on (e.g. from /spec/viewer/[id]). */
  initialSpecId?: string | null;
}

export interface UseSpecViewerResult {
  state: SpecViewerState;
  refresh: () => Promise<void>;
  selectSpec: (specId: string) => void;
  postComment: (body: string) => Promise<SpecComment | null>;
}

/**
 * useSpecViewer — fetches the spec list, the active spec's comments, and
 * exposes a postComment action.
 *
 * AC-F1: on mount with auth+workspace -> GET specs; 4xx surfaces inline.
 * AC-F2 is enforced by the *page* (redirect to /login when no auth token).
 */
export function useSpecViewer(opts: UseSpecViewerOptions): UseSpecViewerResult {
  const { workspaceId, authToken, initialSpecId } = opts;

  const [status, setStatus] = React.useState<SpecViewerStatus>("idle");
  const [specs, setSpecs] = React.useState<Spec[]>([]);
  const [activeSpecId, setActiveSpecId] = React.useState<string | null>(
    initialSpecId ?? null,
  );
  const [comments, setComments] = React.useState<SpecComment[]>([]);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [posting, setPosting] = React.useState(false);

  const surfaceError = React.useCallback(
    (err: unknown, fallbackEndpoint: string): string => {
      const userMsg =
        err instanceof SpecsApiError
          ? err.toUserMessage()
          : `通信に失敗しました (${fallbackEndpoint})`;
      setErrorMessage(userMsg);
      return userMsg;
    },
    [],
  );

  const refresh = React.useCallback(async () => {
    if (!workspaceId || !authToken) return;
    setStatus("loading");
    setErrorMessage(null);
    try {
      const body = await getSpecs(workspaceId, { authToken });
      const list = Array.isArray(body.specs) ? body.specs : [];
      setSpecs(list);
      // Auto-select first spec if none active.
      const nextActive =
        activeSpecId && list.some((s) => s.id === activeSpecId)
          ? activeSpecId
          : (list[0]?.id ?? null);
      setActiveSpecId(nextActive);

      if (nextActive) {
        try {
          const cBody = await getSpecComments(workspaceId, nextActive, {
            authToken,
          });
          setComments(Array.isArray(cBody.comments) ? cBody.comments : []);
        } catch (err) {
          setComments([]);
          surfaceError(
            err,
            workspaceSpecCommentsEndpoint(workspaceId, nextActive),
          );
        }
      } else {
        setComments([]);
      }
      setStatus("loaded");
    } catch (err) {
      setSpecs([]);
      setComments([]);
      setStatus("error");
      surfaceError(err, workspaceSpecsEndpoint(workspaceId));
    }
  }, [workspaceId, authToken, activeSpecId, surfaceError]);

  // Initial + auth/workspace changes drive the refetch.
  React.useEffect(() => {
    if (!workspaceId || !authToken) return;
    void refresh();
    // We intentionally exclude refresh from deps — refresh closes over activeSpecId
    // and re-creates each render which would trigger an infinite loop. The refetch
    // is driven by auth/workspace changes only; subsequent refetches use the
    // returned `refresh` action.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, authToken]);

  const selectSpec = React.useCallback(
    (specId: string) => {
      if (!workspaceId || !authToken) return;
      setActiveSpecId(specId);
      setErrorMessage(null);
      void (async () => {
        try {
          const body = await getSpecComments(workspaceId, specId, {
            authToken,
          });
          setComments(Array.isArray(body.comments) ? body.comments : []);
        } catch (err) {
          setComments([]);
          surfaceError(
            err,
            workspaceSpecCommentsEndpoint(workspaceId, specId),
          );
        }
      })();
    },
    [workspaceId, authToken, surfaceError],
  );

  const postComment = React.useCallback(
    async (body: string): Promise<SpecComment | null> => {
      if (!workspaceId || !authToken || !activeSpecId) return null;
      const trimmed = body.trim();
      if (trimmed.length === 0) return null;
      setPosting(true);
      try {
        const resp = await createSpecComment(
          workspaceId,
          activeSpecId,
          { body: trimmed },
          { authToken },
        );
        // Optimistic append; server is source of truth on next refresh.
        const newComment: SpecComment = {
          id: resp.comment_id,
          body: trimmed,
          created_at: resp.created_at,
        };
        setComments((prev) => [...prev, newComment]);
        setErrorMessage(null);
        return newComment;
      } catch (err) {
        surfaceError(
          err,
          workspaceSpecCommentsEndpoint(workspaceId, activeSpecId),
        );
        return null;
      } finally {
        setPosting(false);
      }
    },
    [workspaceId, authToken, activeSpecId, surfaceError],
  );

  const state: SpecViewerState = React.useMemo(
    () => ({
      status,
      specs,
      activeSpecId,
      comments,
      errorMessage,
      posting,
    }),
    [status, specs, activeSpecId, comments, errorMessage, posting],
  );

  return { state, refresh, selectSpec, postComment };
}
