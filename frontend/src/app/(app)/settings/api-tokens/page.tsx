"use client";

/**
 * S-064 API トークン管理 — T-V3-C-25 / F-030.
 *
 * @screen-id S-064
 * @feature-id F-030
 * @task-ids T-V3-C-25
 * @entities E-006
 * @phase Phase 1B
 *
 * Mock 逐語準拠: docs/mocks/2026-05-15_v3/extras/S-064-api-tokens.html
 *   - h1 text          : "Personal Access Tokens"   (screens.json[S-064].h1_text)
 *   - section h2 cap 12: "Scopes リファレンス"        (screens.json[S-064].section_h2_texts)
 *   - 状態             : loading / loaded / error    (screens.json[S-064].states)
 *
 * 3-tier AC mapping (逐語):
 *   structural.AC-S1: While S-064 page is rendered, the system shall include a
 *     `data-screen-id="S-064"` attribute on the root element.
 *   structural.AC-S2: h1 == "Personal Access Tokens".
 *   structural.AC-S3: render h2 "Scopes リファレンス".
 *   functional.AC-F1: 4xx/5xx -> non-technical toast referencing the failing
 *     endpoint, no stack-trace leak.
 *   functional.AC-F2: POST /api/me/api-tokens returns plaintext token exactly
 *     once (displayed in a one-time-only reveal panel), server stores hash.
 *   functional.AC-F3: GET /api/me/api-tokens never exposes plaintext — only the
 *     masked `prefix` (last 4 chars) is rendered into the table.
 */

import * as React from "react";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Check,
  ChevronRight,
  Copy,
  Key,
  Plus,
  Trash2,
  X,
} from "lucide-react";

import {
  ApiTokensApiError,
  API_TOKENS_ENDPOINT,
  apiTokensItemEndpoint,
  deleteApiToken,
  getApiTokens,
  postApiToken,
  type ApiTokenSummary,
  type PostApiTokenRequest,
} from "@/api/api-tokens";

type ViewState = "loading" | "loaded" | "error";

interface ToastEntry {
  id: number;
  kind: "info" | "success" | "error";
  message: string;
}

/** Scope catalog — must mirror mock's Scopes リファレンス cards. */
const SCOPE_CATALOG: { id: string; label: string; description: string }[] = [
  { id: "read:tasks", label: "read:tasks", description: "タスク一覧の取得" },
  { id: "write:tasks", label: "write:tasks", description: "タスクの作成・更新" },
  {
    id: "write:sessions",
    label: "write:sessions",
    description: "セッション起動・終了",
  },
  {
    id: "read:audit",
    label: "read:audit",
    description: "監査ログ閲覧 (monitor 用)",
  },
];

/**
 * Mask a token's last 4 chars defensively. The server already returns
 * a non-sensitive `prefix`; if a value still looks like a raw token
 * (e.g. starts with `bf_pat_` and is long), it is re-masked here so a
 * mis-configured backend cannot leak plaintext through the UI (AC-F3).
 */
function safeMask(value: string | null | undefined): string {
  if (!value) return "—";
  if (value.length <= 12 || value.includes("*")) return value;
  return `${value.slice(0, 7)}*****${value.slice(-4)}`;
}

function formatExpiry(iso: string | null | undefined): string {
  if (!iso) return "無期限";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const today = new Date();
  const expired = d.getTime() < today.getTime();
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return expired ? `${yyyy}-${mm}-${dd} (期限切れ)` : `${yyyy}-${mm}-${dd}`;
}

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diffMs = Date.now() - then;
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 1) return "たった今";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} days ago`;
}

export default function ApiTokensPage() {
  const [view, setView] = React.useState<ViewState>("loading");
  const [tokens, setTokens] = React.useState<ApiTokenSummary[]>([]);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [toasts, setToasts] = React.useState<ToastEntry[]>([]);
  const toastIdRef = React.useRef(0);

  // Create dialog state
  const [createOpen, setCreateOpen] = React.useState(false);
  const [draftName, setDraftName] = React.useState("");
  const [draftScopes, setDraftScopes] = React.useState<string[]>([]);
  const [draftExpiresAt, setDraftExpiresAt] = React.useState<string>("");
  const [creating, setCreating] = React.useState(false);

  // One-time reveal state (AC-F2): set immediately after a successful POST,
  // cleared once the user dismisses or copies the token.
  const [revealedToken, setRevealedToken] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  const pushToast = React.useCallback(
    (kind: ToastEntry["kind"], message: string) => {
      toastIdRef.current += 1;
      const id = toastIdRef.current;
      setToasts((prev) => [...prev, { id, kind, message }]);
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 6000);
    },
    [],
  );

  const handleError = React.useCallback(
    (err: unknown, fallbackEndpoint: string) => {
      const userMsg =
        err instanceof ApiTokensApiError
          ? err.toUserMessage()
          : `${fallbackEndpoint}: 通信に失敗しました`;
      pushToast("error", userMsg);
      return userMsg;
    },
    [pushToast],
  );

  // Initial load (GET /api/me/api-tokens).
  React.useEffect(() => {
    const ctrl = new AbortController();
    let alive = true;
    (async () => {
      try {
        const res = await getApiTokens({ signal: ctrl.signal });
        if (!alive) return;
        setTokens(res.tokens ?? []);
        setView("loaded");
      } catch (err) {
        if ((err as { name?: string }).name === "AbortError") return;
        if (!alive) return;
        setErrorMessage(handleError(err, API_TOKENS_ENDPOINT));
        setView("error");
      }
    })();
    return () => {
      alive = false;
      ctrl.abort();
    };
  }, [handleError]);

  const refresh = React.useCallback(async () => {
    try {
      const res = await getApiTokens({});
      setTokens(res.tokens ?? []);
    } catch (err) {
      handleError(err, API_TOKENS_ENDPOINT);
    }
  }, [handleError]);

  const toggleScope = (id: string) => {
    setDraftScopes((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id],
    );
  };

  const resetDraft = () => {
    setDraftName("");
    setDraftScopes([]);
    setDraftExpiresAt("");
  };

  const onCreate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!draftName.trim() || draftScopes.length === 0) return;
    setCreating(true);
    const payload: PostApiTokenRequest = {
      name: draftName.trim(),
      scopes: draftScopes,
      expires_at: draftExpiresAt
        ? new Date(draftExpiresAt).toISOString()
        : null,
    };
    try {
      const created = await postApiToken(payload);
      // AC-F2: the plaintext token is shown ONCE and never persisted.
      setRevealedToken(created.plaintext_token_shown_once);
      setCopied(false);
      setCreateOpen(false);
      resetDraft();
      pushToast("success", "トークンを作成しました");
      await refresh();
    } catch (err) {
      handleError(err, API_TOKENS_ENDPOINT);
    } finally {
      setCreating(false);
    }
  };

  const onRevoke = async (id: string, name: string) => {
    if (typeof window !== "undefined") {
      const ok = window.confirm(
        `「${name}」を削除します。\nこのトークンを使用しているクライアントは即座に 401 になります。続行しますか?`,
      );
      if (!ok) return;
    }
    try {
      await deleteApiToken(id);
      pushToast("success", `「${name}」を削除しました`);
      await refresh();
    } catch (err) {
      handleError(err, apiTokensItemEndpoint(id));
    }
  };

  const onCopyRevealed = async () => {
    if (!revealedToken) return;
    try {
      if (
        typeof navigator !== "undefined" &&
        navigator.clipboard &&
        typeof navigator.clipboard.writeText === "function"
      ) {
        await navigator.clipboard.writeText(revealedToken);
      }
      setCopied(true);
    } catch {
      // Clipboard not available — surface a soft toast but keep the token visible.
      pushToast("info", "クリップボードへのコピーに失敗しました");
    }
  };

  const dismissRevealed = () => {
    setRevealedToken(null);
    setCopied(false);
  };

  return (
    <div
      data-screen-id="S-064"
      data-feature-id="F-030"
      data-task-ids="T-V3-C-25"
      data-entities="E-006"
      data-phase="Phase 1B"
      data-view-state={view}
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <main className="max-w-[1000px] mx-auto px-6 py-6">
        {/* Breadcrumb */}
        <div className="text-xs text-slate-500 flex items-center gap-1.5 mb-2">
          <a
            href="/profile"
            className="hover:text-slate-900 inline-flex items-center gap-1"
            data-testid="breadcrumb-back"
          >
            <ArrowLeft className="w-3 h-3" /> プロフィール
          </a>
          <ChevronRight className="w-3 h-3" />
          <span className="text-slate-900 font-medium">API トークン</span>
        </div>

        <div className="flex items-end justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Key className="w-6 h-6 text-eb-500" />
              Personal Access Tokens
            </h1>
            <p className="text-sm text-slate-600 mt-1">
              外部から Build-Factory API を呼び出すための個人トークン
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              resetDraft();
              setCreateOpen(true);
            }}
            className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md flex items-center gap-2"
            data-testid="open-create-token"
          >
            <Plus className="w-4 h-4" /> 新規トークン作成
          </button>
        </div>

        {/* Warning banner (mock parity) */}
        <div className="bg-amber-50 border border-amber-200 rounded-md p-3 mb-4 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5" />
          <div className="text-xs text-amber-900">
            <strong>注意</strong>: トークンは作成時に{" "}
            <strong>1 度だけ</strong>{" "}
            表示されます。安全な場所にコピーして保管してください。
          </div>
        </div>

        {/* One-time reveal panel (AC-F2) */}
        {revealedToken && (
          <div
            role="alert"
            data-testid="plaintext-reveal"
            className="bg-eb-50 border-2 border-eb-500 rounded-md p-4 mb-4"
          >
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <div className="text-sm font-bold text-eb-700">
                  新しいトークンを生成しました
                </div>
                <div className="text-xs text-slate-600 mt-1">
                  この値は{" "}
                  <strong>このタイミングでしか表示されません</strong>。
                  安全な場所に保管してください。
                </div>
              </div>
              <button
                type="button"
                onClick={dismissRevealed}
                className="text-slate-500 hover:text-slate-700"
                aria-label="閉じる"
                data-testid="dismiss-revealed"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex items-center gap-2">
              <code
                className="font-mono text-sm bg-white border border-slate-200 rounded px-3 py-2 flex-1 break-all"
                data-testid="revealed-token-value"
              >
                {revealedToken}
              </code>
              <button
                type="button"
                onClick={onCopyRevealed}
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-3 rounded-md flex items-center gap-1.5"
                data-testid="copy-revealed"
              >
                {copied ? (
                  <>
                    <Check className="w-4 h-4" /> コピーしました
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" /> コピー
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Tokens table */}
        {view === "loading" ? (
          <div
            className="bg-white border border-slate-200 rounded-lg p-6 text-sm text-slate-500"
            data-testid="loading"
          >
            読み込み中…
          </div>
        ) : view === "error" ? (
          <div
            role="alert"
            data-testid="load-error"
            className="bg-red-50 border border-red-200 rounded-md p-4 text-sm text-red-700"
          >
            {errorMessage ?? "通信に失敗しました"}
          </div>
        ) : tokens.length === 0 ? (
          <div
            className="bg-white border border-slate-200 rounded-lg p-8 text-center text-sm text-slate-500"
            data-testid="empty-state"
          >
            まだトークンがありません。「新規トークン作成」から発行してください。
          </div>
        ) : (
          <div
            className="bg-white border border-slate-200 rounded-lg overflow-hidden"
            data-testid="tokens-table"
          >
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-2 text-left">Name</th>
                  <th className="px-4 py-2 text-left">Token</th>
                  <th className="px-4 py-2 text-left">Scopes</th>
                  <th className="px-4 py-2 text-left">最終使用</th>
                  <th className="px-4 py-2 text-left">有効期限</th>
                  <th className="px-4 py-2 text-right" />
                </tr>
              </thead>
              <tbody>
                {tokens.map((t) => (
                  <tr
                    key={t.id}
                    className="border-t border-slate-100 hover:bg-slate-50"
                    data-testid={`token-row-${t.id}`}
                  >
                    <td className="px-4 py-3">
                      <div className="text-sm font-semibold">{t.name}</div>
                      {t.created_at && (
                        <div className="text-[10px] text-slate-500 font-mono">
                          作成: {t.created_at.slice(0, 10)}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <code
                        className="font-mono text-xs bg-slate-100 px-2 py-1 rounded"
                        data-testid={`token-prefix-${t.id}`}
                      >
                        {safeMask(t.prefix ?? null)}
                      </code>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(t.scopes ?? []).map((s) => (
                          <span
                            key={s}
                            className="text-[10px] bg-slate-100 px-1.5 py-0.5 rounded font-mono"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500 font-mono">
                      {formatRelative(t.last_used_at ?? null)}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {formatExpiry(t.expires_at ?? null)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => onRevoke(t.id, t.name)}
                        className="text-xs text-red-500 hover:text-red-700 inline-flex items-center gap-1"
                        data-testid={`revoke-${t.id}`}
                      >
                        <Trash2 className="w-3 h-3" /> 削除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Scopes reference — AC-S3 (only h2 of the page) */}
        <section className="mt-6 bg-white border border-slate-200 rounded-lg p-5">
          <h2 className="text-sm font-bold text-eb-500 mb-3 flex items-center gap-2">
            <BookOpen className="w-4 h-4" />
            Scopes リファレンス
          </h2>
          <div className="grid grid-cols-2 gap-3 text-xs">
            {SCOPE_CATALOG.map((s) => (
              <div
                key={s.id}
                className="border border-slate-200 rounded-md p-2.5"
                data-testid={`scope-card-${s.id}`}
              >
                <code className="font-mono text-eb-500 font-bold">
                  {s.label}
                </code>
                <div className="text-slate-600 mt-1">{s.description}</div>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Create dialog */}
      {createOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="新規トークン作成"
          data-testid="create-token-dialog"
          className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center px-6"
        >
          <div className="bg-white rounded-xl shadow-2xl max-w-[480px] w-full p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-eb-50 flex items-center justify-center shrink-0">
                <Key className="w-5 h-5 text-eb-500" />
              </div>
              <div className="flex-1">
                <h2 className="text-base font-bold">新規トークン作成</h2>
                <p className="text-sm text-slate-600 mt-1">
                  用途別にスコープを最小限に設定してください。
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setCreateOpen(false);
                  resetDraft();
                }}
                className="text-slate-500 hover:text-slate-700"
                aria-label="閉じる"
                data-testid="close-create-dialog"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={onCreate} noValidate className="space-y-4">
              <div className="space-y-1.5">
                <label
                  htmlFor="token-name"
                  className="text-sm font-medium block"
                >
                  Name
                </label>
                <input
                  id="token-name"
                  type="text"
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  placeholder="cli-local-dev"
                  className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
                  data-testid="token-name-input"
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium block">Scopes</label>
                <div className="grid grid-cols-2 gap-2">
                  {SCOPE_CATALOG.map((s) => (
                    <label
                      key={s.id}
                      className="flex items-start gap-2 text-xs border border-slate-200 rounded-md p-2 cursor-pointer hover:border-eb-500"
                    >
                      <input
                        type="checkbox"
                        checked={draftScopes.includes(s.id)}
                        onChange={() => toggleScope(s.id)}
                        className="mt-0.5 accent-eb-500"
                        data-testid={`scope-checkbox-${s.id}`}
                      />
                      <div>
                        <code className="font-mono font-bold text-eb-500">
                          {s.label}
                        </code>
                        <div className="text-slate-600 mt-0.5">
                          {s.description}
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="token-expires"
                  className="text-sm font-medium block"
                >
                  有効期限 (空欄 = 無期限)
                </label>
                <input
                  id="token-expires"
                  type="date"
                  value={draftExpiresAt}
                  onChange={(e) => setDraftExpiresAt(e.target.value)}
                  className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
                  data-testid="token-expires-input"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setCreateOpen(false);
                    resetDraft();
                  }}
                  className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-4 rounded-md"
                  data-testid="cancel-create"
                >
                  キャンセル
                </button>
                <button
                  type="submit"
                  disabled={
                    creating || !draftName.trim() || draftScopes.length === 0
                  }
                  aria-busy={creating}
                  className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md disabled:opacity-50"
                  data-testid="submit-create"
                >
                  {creating ? "作成中…" : "トークンを発行"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Toast container */}
      <div className="fixed bottom-6 right-6 space-y-2 z-50">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            data-testid={
              t.kind === "error" ? "toast-error" : `toast-${t.kind}`
            }
            className={`text-xs rounded-md px-3 py-2 shadow-md border ${
              t.kind === "error"
                ? "bg-red-50 border-red-200 text-red-700"
                : t.kind === "success"
                  ? "bg-eb-50 border-eb-200 text-eb-700"
                  : "bg-white border-slate-200 text-slate-700"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </div>
  );
}
