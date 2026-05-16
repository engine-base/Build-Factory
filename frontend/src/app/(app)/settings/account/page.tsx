"use client";

/**
 * S-007 アカウント設定 — T-V3-C-07 / F-004.
 *
 * @screen-id S-007
 * @feature-id F-004
 * @task-ids T-V3-C-07,T-V3-B-05
 * @entities E-008,E-001
 * @phase Phase 1B
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/account/S-007-account-settings.html
 *
 * Bundled dialog patterns:
 *   - docs/mocks/2026-05-15_v3/dialog/S-052-unsaved-changes.html  (dirty-form guard)
 *   - docs/mocks/2026-05-15_v3/dialog/S-055-danger-zone.html       (typed-name confirm)
 *
 * 3-tier AC mapping (逐語):
 *   structural.AC-S1 (data-screen-id="S-007")              — root <div>.
 *   structural.AC-S2 (h1 == "アカウント設定")               — page heading.
 *   structural.AC-S3 (h2: 基本情報 / プラン / 課金 / 所有者 / Danger Zone)
 *     — section_h2_texts from screens.json[S-007].
 *   functional.AC-F1 (GET /api/accounts/{id} typed client)   — useEffect on mount.
 *   functional.AC-F2 (PUT /api/accounts/{id} typed client)   — Save button.
 *   functional.AC-F3 (POST /api/accounts/{id}/transfer-owner typed client)
 *   functional.AC-F4 (DELETE /api/accounts/{id} typed client) — Danger Zone confirm.
 *   functional.AC-F5 (4xx/5xx -> non-technical toast referencing endpoint)
 *     — `AccountsApiError.toUserMessage()` consumed via local error state.
 *   functional.AC-F6 (owner valid plan upgrade -> emits account_updated audit log)
 *     — backend (T-V3-B-05). UI emits PATCH on dirty plan + name; audit_log emit
 *     is a backend responsibility (REUSE).
 *   functional.AC-F7 (transfer-owner non-member -> 409)      — surface 409 toast.
 *   functional.AC-F8 (invitations > 20/hour/account -> 429)  — surface 429 toast.
 *   functional.AC-F9 (dirty form navigation guard via S-052 dialog).
 *   functional.AC-F10 (Danger Zone irreversible action requires typed-name confirm — S-055).
 */

import * as React from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronRight,
  CreditCard,
  Skull,
  X,
} from "lucide-react";

import {
  ACCOUNT_DELETE_ENDPOINT,
  ACCOUNT_GET_ENDPOINT,
  ACCOUNT_TRANSFER_OWNER_ENDPOINT,
  ACCOUNT_UPDATE_ENDPOINT,
  AccountsApiError,
  deleteAccount,
  getAccount,
  transferAccountOwner,
  updateAccount,
  type Account,
  type AccountUpdatePayload,
} from "@/api/accounts";

// Single-account dogfood account_id; replaced by router context post-T-V3-AUTH wave.
const DEFAULT_ACCOUNT_ID = 1;

type FormState = {
  name: string;
  account_type: string;
  plan: string;
};

function snapshot(account: Account | null): FormState {
  return {
    name: (account?.name as string) ?? "",
    account_type: (account?.account_type as string) ?? "",
    plan: (account?.plan as string) ?? "",
  };
}

function diffOf(original: FormState, draft: FormState): AccountUpdatePayload {
  const patch: AccountUpdatePayload = {};
  if (draft.name !== original.name) patch.name = draft.name;
  if (draft.account_type !== original.account_type)
    patch.account_type = draft.account_type;
  if (draft.plan !== original.plan) patch.plan = draft.plan;
  return patch;
}

export default function AccountSettingsPage({
  accountId = DEFAULT_ACCOUNT_ID,
}: {
  accountId?: number | string;
}) {
  const [account, setAccount] = React.useState<Account | null>(null);
  const [draft, setDraft] = React.useState<FormState>({
    name: "",
    account_type: "",
    plan: "",
  });
  const [original, setOriginal] = React.useState<FormState>({
    name: "",
    account_type: "",
    plan: "",
  });
  const [loading, setLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [savingState, setSavingState] = React.useState<
    "idle" | "saving" | "saved"
  >("idle");

  // S-055 Danger Zone dialog state
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [confirmName, setConfirmName] = React.useState("");
  const [confirmAcknowledged, setConfirmAcknowledged] = React.useState(false);
  const [confirmBusy, setConfirmBusy] = React.useState(false);

  // S-052 unsaved-changes guard state
  const [navGuardOpen, setNavGuardOpen] = React.useState(false);
  const [pendingHref, setPendingHref] = React.useState<string | null>(null);

  // Transfer-owner inline form
  const [transferOpen, setTransferOpen] = React.useState(false);
  const [transferTarget, setTransferTarget] = React.useState("");
  const [transferBusy, setTransferBusy] = React.useState(false);

  const dirty = React.useMemo(
    () => Object.keys(diffOf(original, draft)).length > 0,
    [original, draft],
  );

  // AC-F1: GET /api/accounts/{id} on mount.
  React.useEffect(() => {
    const ctrl = new AbortController();
    let alive = true;
    (async () => {
      try {
        const data = await getAccount(accountId, { signal: ctrl.signal });
        if (!alive) return;
        setAccount(data);
        const snap = snapshot(data);
        setOriginal(snap);
        setDraft(snap);
        setLoading(false);
      } catch (err) {
        if ((err as { name?: string }).name === "AbortError") return;
        if (!alive) return;
        const userMsg =
          err instanceof AccountsApiError
            ? err.toUserMessage()
            : `${ACCOUNT_GET_ENDPOINT(accountId)}: 通信に失敗しました`;
        setErrorMessage(userMsg);
        setLoading(false);
      }
    })();
    return () => {
      alive = false;
      ctrl.abort();
    };
  }, [accountId]);

  // AC-F9: beforeunload guard while dirty.
  React.useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  // AC-F2: PATCH /api/accounts/{id} (verb alias for PUT in spec).
  const onSave = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const patch = diffOf(original, draft);
    if (Object.keys(patch).length === 0) return;
    setSavingState("saving");
    setErrorMessage(null);
    try {
      const next = await updateAccount(accountId, patch);
      setAccount(next);
      const snap = snapshot(next);
      setOriginal(snap);
      setDraft(snap);
      setSavingState("saved");
      window.setTimeout(() => setSavingState("idle"), 1500);
    } catch (err) {
      const userMsg =
        err instanceof AccountsApiError
          ? err.toUserMessage()
          : `${ACCOUNT_UPDATE_ENDPOINT(accountId)}: 通信に失敗しました`;
      setErrorMessage(userMsg);
      setSavingState("idle");
    }
  };

  // AC-F3 + AC-F7: POST /api/accounts/{id}/transfer-owner (409 on non-member).
  const onTransfer = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const target = transferTarget.trim();
    if (!target) return;
    setTransferBusy(true);
    setErrorMessage(null);
    try {
      await transferAccountOwner(accountId, { new_owner_user_id: target });
      setTransferOpen(false);
      setTransferTarget("");
      // Refresh owner display.
      const refreshed = await getAccount(accountId);
      setAccount(refreshed);
    } catch (err) {
      const userMsg =
        err instanceof AccountsApiError
          ? err.toUserMessage()
          : `${ACCOUNT_TRANSFER_OWNER_ENDPOINT(accountId)}: 通信に失敗しました`;
      setErrorMessage(userMsg);
    } finally {
      setTransferBusy(false);
    }
  };

  // AC-F4 + AC-F10: DELETE /api/accounts/{id} — typed-name confirm gate.
  const accountName = (account?.name as string) ?? "";
  const confirmReady =
    confirmAcknowledged && confirmName.trim() === accountName && !confirmBusy;

  const onConfirmDelete = async () => {
    if (!confirmReady) return;
    setConfirmBusy(true);
    setErrorMessage(null);
    try {
      await deleteAccount(accountId);
      setConfirmOpen(false);
      // After successful delete, send the user to the dashboard root.
      // Use replace so the back button does not return to a defunct account.
      if (typeof window !== "undefined") window.location.replace("/dashboard");
    } catch (err) {
      const userMsg =
        err instanceof AccountsApiError
          ? err.toUserMessage()
          : `${ACCOUNT_DELETE_ENDPOINT(accountId)}: 通信に失敗しました`;
      setErrorMessage(userMsg);
      setConfirmBusy(false);
    }
  };

  // AC-F9: intercept link navigation while dirty.
  const guardedNavigate = (href: string) => {
    if (dirty) {
      setPendingHref(href);
      setNavGuardOpen(true);
      return;
    }
    if (typeof window !== "undefined") window.location.href = href;
  };

  return (
    <div
      data-screen-id="S-007"
      data-feature-id="F-004"
      data-task-ids="T-V3-C-07,T-V3-B-05"
      data-entities="E-008,E-001"
      data-phase="Phase 1B"
      data-dirty={dirty ? "true" : "false"}
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <main className="max-w-[800px] mx-auto px-6 py-8">
        {/* Breadcrumb */}
        <div className="text-xs text-slate-500 flex items-center gap-1.5 mb-2">
          <a
            href="/dashboard"
            onClick={(e) => {
              if (dirty) {
                e.preventDefault();
                guardedNavigate("/dashboard");
              }
            }}
            className="hover:text-slate-900 inline-flex items-center gap-1"
            data-testid="breadcrumb-back"
          >
            <ArrowLeft className="w-3 h-3" /> Account
          </a>
          <ChevronRight className="w-3 h-3" />
          <span className="text-slate-900 font-medium">アカウント設定</span>
        </div>

        <header className="mb-6">
          <h1 className="text-2xl font-bold">アカウント設定</h1>
          <p className="text-sm text-slate-600 mt-1">
            アカウント全体の設定 / プラン / オーナー権限
          </p>
        </header>

        {errorMessage && (
          <div
            role="alert"
            data-testid="error-toast"
            className="mb-4 text-xs rounded-md border border-red-200 bg-red-50 text-red-700 px-3 py-2"
          >
            {errorMessage}
          </div>
        )}

        {loading ? (
          <div
            className="bg-white border border-slate-200 rounded-lg p-6 text-sm text-slate-500"
            data-testid="loading"
          >
            読み込み中…
          </div>
        ) : (
          <form onSubmit={onSave} noValidate>
            {/* AC-S3: h2 #1 — 基本情報 */}
            <section className="bg-white border border-slate-200 rounded-lg p-6 mb-4">
              <h2 className="text-base font-bold mb-4">基本情報</h2>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label
                    htmlFor="account-name"
                    className="text-sm font-medium block"
                  >
                    アカウント名
                  </label>
                  <input
                    id="account-name"
                    type="text"
                    value={draft.name}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, name: e.target.value }))
                    }
                    className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label
                      htmlFor="account-type"
                      className="text-sm font-medium block"
                    >
                      アカウント種別
                    </label>
                    <select
                      id="account-type"
                      value={draft.account_type}
                      onChange={(e) =>
                        setDraft((d) => ({
                          ...d,
                          account_type: e.target.value,
                        }))
                      }
                      className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
                    >
                      <option value="agency">受託会社</option>
                      <option value="inhouse">社内開発チーム</option>
                      <option value="freelance">フリーランス</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium block">
                      Account ID
                    </label>
                    <div
                      data-testid="account-id"
                      className="border border-slate-200 bg-slate-50 text-sm h-9 px-3 rounded-md w-full flex items-center font-mono text-slate-700"
                    >
                      {String(account?.id ?? accountId)}
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-end gap-2 pt-2">
                  {savingState === "saved" && (
                    <span
                      className="text-xs text-eb-500 font-semibold"
                      data-testid="saved-indicator"
                    >
                      保存しました
                    </span>
                  )}
                  <button
                    type="submit"
                    disabled={!dirty || savingState === "saving"}
                    aria-busy={savingState === "saving"}
                    className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md disabled:opacity-50"
                    data-testid="save-button"
                  >
                    {savingState === "saving" ? "保存中…" : "保存"}
                  </button>
                </div>
              </div>
            </section>

            {/* AC-S3: h2 #2 — プラン / 課金 */}
            <section className="bg-white border border-slate-200 rounded-lg p-6 mb-4">
              <h2 className="text-base font-bold mb-4">プラン / 課金</h2>
              <div className="border border-eb-200 bg-eb-50 rounded-md p-4 mb-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-bold">
                    {draft.plan || "—"} プラン
                  </span>
                  <span className="text-[11px] bg-eb-500 text-white px-2 py-0.5 rounded-full font-semibold">
                    CURRENT
                  </span>
                </div>
                <label
                  htmlFor="plan-select"
                  className="text-xs text-slate-600 block mb-1"
                >
                  プラン変更
                </label>
                <select
                  id="plan-select"
                  value={draft.plan}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, plan: e.target.value }))
                  }
                  className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-48"
                >
                  <option value="Free">Free</option>
                  <option value="Pro">Pro</option>
                  <option value="Business">Business</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium block">支払い方法</label>
                <div className="border border-slate-200 rounded-md p-3 flex items-center gap-3">
                  <CreditCard className="w-5 h-5 text-slate-500" />
                  <div className="flex-1">
                    <div className="text-sm font-medium font-mono">
                      **** **** **** 4242
                    </div>
                    <div className="text-xs text-slate-500">
                      Visa · 有効期限 12/26
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* AC-S3: h2 #3 — 所有者 (Account Owner) */}
            <section className="bg-white border border-slate-200 rounded-lg p-6 mb-4">
              <h2 className="text-base font-bold mb-4">所有者 (Account Owner)</h2>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-eb-500 text-white flex items-center justify-center text-sm font-bold">
                  {(account?.owner_user_id ?? "?").toString().slice(0, 1).toUpperCase()}
                </div>
                <div className="flex-1">
                  <div
                    className="text-sm font-medium"
                    data-testid="owner-user-id"
                  >
                    {account?.owner_user_id ?? "(未設定)"}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setTransferOpen((v) => !v)}
                  className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-4 rounded-md"
                  data-testid="transfer-owner-toggle"
                >
                  他メンバーに移譲
                </button>
              </div>
              {transferOpen && (
                <form
                  onSubmit={onTransfer}
                  className="mt-4 flex items-center gap-2"
                  data-testid="transfer-owner-form"
                >
                  <input
                    type="text"
                    value={transferTarget}
                    onChange={(e) => setTransferTarget(e.target.value)}
                    placeholder="新オーナーの user_id"
                    className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md flex-1"
                    data-testid="transfer-owner-input"
                  />
                  <button
                    type="submit"
                    disabled={transferBusy || transferTarget.trim().length === 0}
                    aria-busy={transferBusy}
                    className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md disabled:opacity-50"
                    data-testid="transfer-owner-submit"
                  >
                    移譲する
                  </button>
                </form>
              )}
            </section>

            {/* AC-S3: h2 #4 — Danger Zone */}
            <section className="bg-white border border-red-200 rounded-lg p-6">
              <h2 className="text-base font-bold text-red-600 mb-3 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> Danger Zone
              </h2>
              <p className="text-xs text-slate-600 mb-4">
                不可逆な操作です。慎重に実行してください。
              </p>
              <div className="flex items-center justify-between p-3 border border-red-200 rounded-md">
                <div>
                  <div className="text-sm font-semibold text-red-600">
                    アカウントを削除
                  </div>
                  <div className="text-xs text-slate-500">
                    全 workspace / メンバー / データを完全削除
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setConfirmName("");
                    setConfirmAcknowledged(false);
                    setConfirmOpen(true);
                  }}
                  className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold h-9 px-4 rounded-md"
                  data-testid="open-danger-zone"
                >
                  削除する
                </button>
              </div>
            </section>
          </form>
        )}
      </main>

      {/* S-052 unsaved-changes dialog (AC-F9) */}
      {navGuardOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="未保存の変更があります"
          data-testid="unsaved-changes-dialog"
          data-dialog="S-052"
          className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center px-6"
        >
          <div className="bg-white rounded-xl shadow-2xl max-w-[440px] w-full p-6">
            <div className="flex items-start gap-4 mb-5">
              <div className="w-10 h-10 rounded-full bg-amber-50 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <h2 className="text-base font-bold">
                  変更が保存されていません
                </h2>
                <p className="text-sm text-slate-600 mt-1.5 leading-relaxed">
                  編集中の内容が未保存です。このページを離れますか?
                </p>
              </div>
            </div>
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setNavGuardOpen(false);
                  setPendingHref(null);
                }}
                className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-4 rounded-md"
                data-testid="nav-guard-stay"
              >
                編集を続ける
              </button>
              <button
                type="button"
                onClick={() => {
                  setNavGuardOpen(false);
                  setDraft(original);
                  const href = pendingHref;
                  setPendingHref(null);
                  if (href && typeof window !== "undefined")
                    window.location.href = href;
                }}
                className="border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 text-sm h-9 px-4 rounded-md font-semibold"
                data-testid="nav-guard-discard"
              >
                変更を破棄して離脱
              </button>
            </div>
          </div>
        </div>
      )}

      {/* S-055 Danger Zone dialog (AC-F4 + AC-F10) */}
      {confirmOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="アカウントを完全削除"
          data-testid="danger-zone-dialog"
          data-dialog="S-055"
          className="fixed inset-0 z-50 bg-slate-900/60 flex items-center justify-center px-6"
        >
          <div className="bg-white rounded-xl shadow-2xl max-w-[480px] w-full p-6 border-2 border-red-200">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center shrink-0">
                <Skull className="w-5 h-5 text-red-700" />
              </div>
              <div>
                <h2 className="text-base font-bold text-red-700">
                  アカウントを完全削除
                </h2>
                <p className="text-sm text-slate-700 mt-1.5 leading-relaxed font-semibold">
                  この操作は
                  <strong className="text-red-700">完全に取り消し不能</strong>
                  です。
                </p>
              </div>
            </div>

            <div className="bg-red-50 border-2 border-red-300 rounded-md p-3 mb-4 space-y-1.5 text-xs text-red-900">
              <div className="flex gap-1.5">
                <X className="w-3 h-3 mt-0.5 shrink-0" />
                <span>全 workspace / メンバー / データを完全削除</span>
              </div>
              <div className="flex gap-1.5">
                <X className="w-3 h-3 mt-0.5 shrink-0" />
                <span>請求は当月末に最終決済</span>
              </div>
              <div className="flex gap-1.5">
                <X className="w-3 h-3 mt-0.5 shrink-0" />
                <span>30 日後に物理削除 (バックアップも削除)</span>
              </div>
            </div>

            <div className="space-y-2 mb-4">
              <label
                htmlFor="confirm-name"
                className="text-sm font-medium block"
              >
                アカウント名{" "}
                <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded">
                  {accountName || "—"}
                </span>{" "}
                を入力
              </label>
              <input
                id="confirm-name"
                type="text"
                value={confirmName}
                onChange={(e) => setConfirmName(e.target.value)}
                placeholder={accountName}
                className="border border-red-300 text-sm h-10 px-3 rounded-md w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
                data-testid="danger-zone-name-input"
              />
              <label className="flex items-start gap-2 text-xs cursor-pointer pt-1">
                <input
                  type="checkbox"
                  checked={confirmAcknowledged}
                  onChange={(e) => setConfirmAcknowledged(e.target.checked)}
                  className="w-4 h-4 mt-0.5 accent-red-600"
                  data-testid="danger-zone-ack"
                />
                <span className="text-slate-700">
                  不可逆な削除であることを理解し、データを全てエクスポート済みです
                </span>
              </label>
            </div>

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                className="border border-slate-200 hover:bg-slate-50 text-sm h-10 px-5 rounded-md font-semibold"
                data-testid="danger-zone-cancel"
              >
                キャンセル
              </button>
              <button
                type="button"
                onClick={onConfirmDelete}
                disabled={!confirmReady}
                aria-busy={confirmBusy}
                className="bg-red-600 hover:bg-red-700 text-white text-sm h-10 px-5 rounded-md font-bold disabled:opacity-50"
                data-testid="danger-zone-confirm"
              >
                {confirmBusy ? "削除中…" : "完全削除する"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
