"use client";

/**
 * T-V3-C-05 / S-005: OAuth コールバック page.
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/auth/S-005-oauth-callback.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-005
 * @feature-id F-001
 * @task-ids T-V3-C-05,T-V3-AUTH-12,T-V3-AUTH-06
 * @entities E-001,E-040
 * @phase Phase 1B
 *
 * 3-tier AC mapping:
 *   structural.AC-S1 (data-screen-id="S-005") — root element.
 *   structural.AC-S2 (h1 == "ログイン中...") — loading state primary heading.
 *   functional.AC-F1 (GET /api/auth/oauth/{provider}/callback via typed client)
 *     — `completeOAuthCallback()` called from a one-shot React effect.
 *   functional.AC-F2 (4xx/5xx -> non-technical toast referencing endpoint)
 *     — `toast.error(err.toUserMessage())`, never embeds stack trace.
 *   functional.AC-F3 (valid state token -> access_token + refresh_token returned)
 *     — backend (T-V3-B-02). UI persists both tokens to localStorage and
 *     redirects to /dashboard on success.
 */

import * as React from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { toast } from "sonner";
import {
  CheckCircle2,
  Circle,
  Factory,
  Loader2,
  ArrowLeft,
  X,
} from "lucide-react";

import {
  completeOAuthCallback,
  oauthCallbackEndpoint,
  OAuthCallbackApiError,
  OAUTH_PROVIDERS,
  type OAuthCallbackResponse,
} from "@/api/auth";

/**
 * Default provider used when the URL does not carry a `provider` query param
 * (e.g. /oauth-callback?code=...&state=...). The mock copy assumes
 * "Anthropic アカウントで認証しています" — keep that wording aligned.
 */
const DEFAULT_PROVIDER = "anthropic";

type CallbackState =
  | { kind: "loading" }
  | { kind: "success"; data: OAuthCallbackResponse }
  | { kind: "error_csrf"; endpoint: string }
  | { kind: "error_generic"; endpoint: string; userMessage: string };

function providerFromQuery(
  searchParams: ReturnType<typeof useSearchParams>,
  pathname: string | null
): string {
  const explicit = searchParams?.get("provider");
  if (explicit) return explicit;
  // Some OAuth providers redirect to /oauth-callback/<provider> instead of
  // a query param. Fall back to the last URL segment when it is one of the
  // supported providers.
  if (pathname) {
    const seg = pathname.split("/").filter(Boolean).pop() ?? "";
    if ((OAUTH_PROVIDERS as readonly string[]).includes(seg)) return seg;
  }
  return DEFAULT_PROVIDER;
}

function ProviderLabel({ provider }: { provider: string }) {
  const label =
    provider === "anthropic"
      ? "Anthropic"
      : provider === "github"
        ? "GitHub"
        : provider === "slack"
          ? "Slack"
          : provider === "google"
            ? "Google"
            : provider;
  return <>{label}</>;
}

export default function OAuthCallbackPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = React.useState<CallbackState>({ kind: "loading" });
  const ranRef = React.useRef(false);

  const provider = providerFromQuery(searchParams, pathname);
  const code = searchParams?.get("code") ?? "";
  const stateParam = searchParams?.get("state") ?? "";
  const endpoint = oauthCallbackEndpoint(provider);

  React.useEffect(() => {
    // Guard against React 19 strict-mode double-mount: only the first run
    // performs the OAuth handshake. AbortController would also work but we
    // intentionally avoid aborting an in-flight token exchange.
    if (ranRef.current) return;
    ranRef.current = true;

    if (!code || !stateParam) {
      // Treat missing code/state as a generic OAuth error.
      const msg = `OAuth のリクエストパラメータが不正です。 (${endpoint})`;
      setState({ kind: "error_generic", endpoint, userMessage: msg });
      toast.error(msg);
      return;
    }

    let cancelled = false;
    completeOAuthCallback({ provider, code, state: stateParam })
      .then((data) => {
        if (cancelled) return;
        // AC-F3: persist tokens so the rest of the app can authenticate.
        try {
          if (typeof window !== "undefined") {
            window.localStorage.setItem("bf.access_token", data.access_token);
            window.localStorage.setItem(
              "bf.refresh_token",
              data.refresh_token
            );
            window.localStorage.setItem("bf.user_id", data.user_id);
          }
        } catch {
          // Quota / private-mode: tokens are still returned; downstream
          // requests can re-issue via /refresh.
        }
        setState({ kind: "success", data });
        // Mirror the mock: brief "ログイン成功" pause then forward to dashboard.
        window.setTimeout(() => {
          if (!cancelled) router.replace("/dashboard");
        }, 800);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof OAuthCallbackApiError) {
          const userMsg = err.toUserMessage();
          // 401 == CSRF / state mismatch / code expired (backend contract).
          if (err.status === 401) {
            setState({ kind: "error_csrf", endpoint: err.endpoint });
          } else {
            setState({
              kind: "error_generic",
              endpoint: err.endpoint,
              userMessage: userMsg,
            });
          }
          toast.error(userMsg);
        } else {
          const fallback = `認証中にエラーが発生しました。 (${endpoint})`;
          setState({
            kind: "error_generic",
            endpoint,
            userMessage: fallback,
          });
          toast.error(fallback);
        }
      });

    return () => {
      cancelled = true;
    };
    // Intentionally omit `router` from deps — the handshake is one-shot per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider, code, stateParam, endpoint]);

  return (
    <div
      data-screen-id="S-005"
      data-feature-id="F-001"
      data-task-ids="T-V3-C-05,T-V3-AUTH-12,T-V3-AUTH-06"
      data-entities="E-001,E-040"
      data-phase="Phase 1B"
      className="min-h-screen flex flex-col bg-slate-50 text-slate-900"
    >
      <header className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2 max-w-[1400px] mx-auto">
          <div className="w-7 h-7 rounded-md bg-eb-500 flex items-center justify-center">
            <Factory className="w-4 h-4 text-white" aria-hidden />
          </div>
          <div className="text-sm font-bold">Build-Factory</div>
          <span className="text-[11px] text-slate-500 font-mono">v3</span>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[420px]">
          {state.kind === "loading" && (
            <LoadingCard provider={provider} />
          )}
          {state.kind === "success" && <SuccessCard />}
          {state.kind === "error_csrf" && <ErrorCsrfCard />}
          {state.kind === "error_generic" && (
            <ErrorGenericCard
              endpoint={state.endpoint}
              userMessage={state.userMessage}
            />
          )}

          <p className="text-center text-[11px] text-slate-400 mt-8 font-mono">
            © ENGINE BASE
          </p>
        </div>
      </main>
    </div>
  );
}

function LoadingCard({ provider }: { provider: string }) {
  return (
    <div
      data-state="loading"
      className="bg-white border border-slate-200 rounded-lg p-8 text-center"
    >
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-eb-100 mb-6">
        <Loader2
          className="w-8 h-8 text-eb-500 animate-spin"
          aria-hidden
        />
      </div>
      <h1 className="text-2xl font-bold mb-2">ログイン中...</h1>
      <p className="text-sm text-slate-600">
        <ProviderLabel provider={provider} /> アカウントで認証しています
      </p>

      <div className="mt-8 flex items-center justify-center gap-2 text-xs text-slate-500">
        <span className="w-1.5 h-1.5 rounded-full bg-eb-500 animate-pulse" />
        <span className="font-mono">connecting to {provider}</span>
      </div>

      <div className="mt-6 space-y-2 text-left max-w-xs mx-auto">
        <div className="flex items-center gap-2 text-xs">
          <CheckCircle2
            className="w-4 h-4 text-eb-500 shrink-0"
            aria-hidden
          />
          <span className="text-slate-700">OAuth トークン受信</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <Loader2
            className="w-4 h-4 text-eb-500 animate-spin shrink-0"
            aria-hidden
          />
          <span className="text-slate-700">ユーザー情報取得</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <Circle className="w-4 h-4 text-slate-300 shrink-0" aria-hidden />
          <span className="text-slate-500">セッション作成</span>
        </div>
      </div>
    </div>
  );
}

function SuccessCard() {
  return (
    <div
      data-state="success"
      className="bg-white border border-eb-200 rounded-lg p-8 text-center"
    >
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-eb-100 mb-6">
        <CheckCircle2 className="w-8 h-8 text-eb-500" aria-hidden />
      </div>
      <h2 className="text-2xl font-bold mb-2">ログイン成功</h2>
      <p className="text-sm text-slate-600">ダッシュボードへ移動します...</p>
      <div className="mt-4 h-1 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full bg-eb-500 w-full" />
      </div>
    </div>
  );
}

function ErrorCsrfCard() {
  return (
    <div
      data-state="error_csrf"
      className="bg-white border border-red-200 rounded-lg p-8 text-center"
    >
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-50 mb-6">
        <X className="w-8 h-8 text-red-600" aria-hidden />
      </div>
      <h2 className="text-2xl font-bold mb-2">認証エラー</h2>
      <p className="text-sm text-slate-600 mb-1">
        セキュリティ検証に失敗しました
      </p>
      <p className="text-xs text-slate-500 font-mono mb-6">
        error: oauth_csrf_check_failed
      </p>

      <div className="text-left bg-slate-50 border border-slate-200 rounded-md p-3 mb-6">
        <p className="text-xs text-slate-700 leading-relaxed">
          ブラウザの cookie 設定または 5 分以上経過した可能性があります。
          <br />
          ログイン画面から再度お試しください。
        </p>
      </div>

      <a
        href="/login"
        className="inline-flex items-center gap-2 bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-6 rounded-md transition-colors"
      >
        <ArrowLeft className="w-4 h-4" aria-hidden />
        ログインに戻る
      </a>
    </div>
  );
}

function ErrorGenericCard({
  endpoint,
  userMessage,
}: {
  endpoint: string;
  userMessage: string;
}) {
  return (
    <div
      data-state="error"
      className="bg-white border border-red-200 rounded-lg p-8 text-center"
    >
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-50 mb-6">
        <X className="w-8 h-8 text-red-600" aria-hidden />
      </div>
      <h2 className="text-2xl font-bold mb-2">認証エラー</h2>
      <p className="text-sm text-slate-600 mb-1">{userMessage}</p>
      <p className="text-xs text-slate-500 font-mono mb-6">
        endpoint: {endpoint}
      </p>

      <a
        href="/login"
        className="inline-flex items-center gap-2 bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-6 rounded-md transition-colors"
      >
        <ArrowLeft className="w-4 h-4" aria-hidden />
        ログインに戻る
      </a>
    </div>
  );
}
