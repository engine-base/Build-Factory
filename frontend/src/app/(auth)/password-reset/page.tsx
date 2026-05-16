"use client";

/**
 * S-003 パスワード再設定 — T-V3-C-03 / F-001.
 *
 * @screen-id S-003
 * @feature-id F-001
 * @task-ids T-V3-C-03,T-V3-AUTH-10,T-V3-AUTH-03
 * @entities E-001,E-039
 * @phase Phase 1B
 *
 * Mock 逐語準拠: docs/mocks/2026-05-15_v3/auth/S-003-password-reset.html
 *   - h1 text       : "パスワード再設定"            (screens.json[S-003].h1_text)
 *   - 主要アクション : POST /api/auth/password-reset (T-V3-B-01 実装済)
 *   - 状態         : loading / loaded / error      (screens.json[S-003].states)
 *
 * EARS AC:
 *   - STATE-DRIVEN: While S-003 page is rendered, the system shall include a
 *     `data-screen-id="S-003"` attribute on the root element.
 *   - STATE-DRIVEN: While S-003 page is rendered, the system shall display an
 *     h1 element with text "パスワード再設定".
 *   - EVENT-DRIVEN: When the page performs its primary action, the system shall
 *     call POST /api/auth/password-reset via the typed API client.
 *   - UNWANTED: If a backing API call returns 4xx or 5xx, the system shall
 *     surface a non-technical error toast referencing the failing endpoint
 *     without leaking server stack traces.
 *   - EVENT-DRIVEN: When POST /api/auth/password-reset is called with an email,
 *     the system shall always return 2xx (no account enumeration) and send
 *     reset email only if the account exists. (backend-side; UI assumes 2xx
 *     regardless and shows the same success state.)
 */

import { useState, type FormEvent } from "react";
import { ApiError, requestPasswordReset } from "@/api/auth";

type ViewState = "idle" | "loading" | "loaded" | "error";

export default function PasswordResetPage() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<ViewState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [sentToEmail, setSentToEmail] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("loading");
    setErrorMessage(null);
    try {
      await requestPasswordReset({ email });
      // 2xx: account enumeration を避けるため成功画面を常に表示する.
      setSentToEmail(email);
      setState("loaded");
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "POST /api/auth/password-reset: 予期しないエラーが発生しました";
      setErrorMessage(msg);
      setState("error");
    }
  }

  return (
    <div
      data-screen-id="S-003"
      data-feature-id="F-001"
      data-task-ids="T-V3-C-03,T-V3-AUTH-10,T-V3-AUTH-03"
      data-entities="E-001,E-039"
      data-phase="Phase 1B"
      className="min-h-screen flex flex-col bg-slate-50 text-slate-900"
    >
      <header className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2 max-w-[1400px] mx-auto">
          <div className="w-7 h-7 rounded-md bg-eb-500 flex items-center justify-center text-white text-xs font-bold">
            BF
          </div>
          <div className="text-sm font-bold">Build-Factory</div>
          <span className="text-[11px] text-slate-500 font-mono">v3</span>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[420px]">
          <a
            href="/login"
            className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900 mb-6"
            data-testid="back-to-login"
          >
            ログインに戻る
          </a>

          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-lg bg-eb-100 mb-4">
              <span aria-hidden="true" className="text-eb-500 font-semibold">
                {/* lucide: key-round (mock parity) */}
                key
              </span>
            </div>
            <h1 className="text-2xl font-bold">パスワード再設定</h1>
            <p className="text-sm text-slate-600 mt-1">
              登録メールアドレスに再設定リンクを送ります
            </p>
          </div>

          {state !== "loaded" && (
            <form
              onSubmit={onSubmit}
              className="bg-white border border-slate-200 rounded-lg p-6 space-y-4"
              data-state="request_reset"
              noValidate
            >
              <div className="space-y-1.5">
                <label htmlFor="email" className="text-sm font-medium block">
                  メールアドレス
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  required
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={state === "loading"}
                  className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full focus-visible:outline-none focus-visible:border-eb-500 focus-visible:ring-2 focus-visible:ring-eb-100"
                />
                <p className="text-xs text-slate-500">
                  登録時のメールアドレスを入力してください
                </p>
              </div>

              {state === "error" && errorMessage && (
                <div
                  role="alert"
                  data-testid="error-toast"
                  className="text-xs rounded-md border border-red-200 bg-red-50 text-red-700 px-3 py-2"
                >
                  {errorMessage}
                </div>
              )}

              <button
                type="submit"
                disabled={state === "loading" || email.trim().length === 0}
                aria-busy={state === "loading"}
                className="w-full bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-4 rounded-md transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {state === "loading" ? "送信中…" : "再設定リンクを送る"}
              </button>
            </form>
          )}

          {state === "loaded" && (
            <div
              className="bg-white border border-eb-200 rounded-lg p-6 space-y-3"
              data-state="email_sent"
              role="status"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-eb-100 flex items-center justify-center shrink-0 text-eb-500 font-bold">
                  ok
                </div>
                <div>
                  <div className="text-sm font-semibold">メールを送信しました</div>
                  <div className="text-xs text-slate-600 mt-0.5">
                    {sentToEmail
                      ? `${sentToEmail} 宛に再設定リンクを送りました。受信トレイをご確認ください`
                      : "受信トレイをご確認ください"}
                  </div>
                </div>
              </div>
              <div className="text-xs text-slate-500 leading-relaxed pt-3 border-t border-slate-200">
                メールが届かない場合:
                <br />
                ・迷惑メールフォルダを確認
                <br />
                ・メールアドレスの入力ミスを確認
                <br />
                ・5 分待ってから再送信
              </div>
            </div>
          )}

          <div className="text-center text-[11px] text-slate-400 mt-8 font-mono">
            © ENGINE BASE
          </div>
        </div>
      </main>
    </div>
  );
}
