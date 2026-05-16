"use client";

/**
 * T-V3-C-01 / S-001 — ログイン (Login) screen + S-053 MFA challenge dialog.
 *
 * - Lucide icons only (CLAUDE.md §5.1, no emojis).
 * - Tailwind eb-* palette (CLAUDE.md §5.2: ENGINE BASE green #1a6648).
 * - shadcn/ui primitives (Dialog / Input / Button / sonner) as per design tokens.
 * - data-screen-id="S-001" / "S-053" for mock-impl-diff lint (AC-S1, Gate #8).
 *
 * Backend contracts:
 *   - POST /api/auth/login    (loginWithPassword, AC-F1 / AC-F5 / AC-F6)
 *   - POST /api/auth/mfa/verify (verifyMfaCode, AC-F2 / AC-F7 / AC-F8)
 *
 * Mock-impl source of truth: docs/mocks/2026-05-15_v3/auth/S-001-login.html +
 *                            docs/mocks/2026-05-15_v3/dialog/S-053-mfa-challenge.html
 * Spec source of truth: docs/functional-breakdown/2026-05-16_v3/screens.json (S-001, S-053)
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowRight,
  AlertCircle,
  Eye,
  EyeOff,
  Factory,
  GitBranch,
  Globe,
  Loader2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AuthApiError,
  LAST_VISITED_STORAGE_KEY,
  POST_LOGIN_FALLBACK_PATH,
  loginWithPassword,
  resolvePostLoginPath,
  verifyMfaCode,
  type LoginResponse,
} from "@/api/auth";

// ---------------------------------------------------------------------------
// Mock-derived screen literals —逐語コピー (h1_text / section_h2_texts).
// screens.json[S-001].h1_text === "ログイン" (AC-S2)
// screens.json[S-053].section_h2_texts === ["2 段階認証"]
// ---------------------------------------------------------------------------
const S001_H1_TEXT = "ログイン";
const S001_SUBTITLE = "Build-Factory にサインインして案件を管理";
const S053_H2_TEXT = "2 段階認証";
const S053_SUBTITLE = "認証アプリに表示された 6 桁コードを入力";

const TOTP_LENGTH = 6;

// ---------------------------------------------------------------------------
// MFA challenge dialog (S-053 pattern, AC-F8).
// ---------------------------------------------------------------------------
function MfaChallengeDialog({
  open,
  onOpenChange,
  pendingUserId,
  onVerified,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  pendingUserId: string | null;
  onVerified: () => void;
}) {
  const [code, setCode] = React.useState("");

  const handleOpenChange = React.useCallback(
    (next: boolean) => {
      if (!next) {
        setCode("");
      }
      onOpenChange(next);
    },
    [onOpenChange],
  );

  const verifyMutation = useMutation({
    mutationFn: async (totp: string) => {
      if (!pendingUserId) {
        throw new AuthApiError(
          "auth.client_state_error",
          "missing pending user_id",
          0,
          "/api/auth/mfa/verify",
        );
      }
      return verifyMfaCode({ user_id: pendingUserId, totp_code: totp });
    },
    onError: (err: unknown) => {
      // AC-F3: surface a non-technical, endpoint-tagged toast — never raw stack.
      if (err instanceof AuthApiError) {
        toast.error(err.toUserMessage());
      } else {
        toast.error("検証に失敗しました (/api/auth/mfa/verify)");
      }
    },
    onSuccess: () => {
      onVerified();
    },
  });

  const submit = () => {
    if (code.length !== TOTP_LENGTH || !/^[0-9]{6}$/.test(code)) {
      toast.error("6 桁の数字を入力してください");
      return;
    }
    verifyMutation.mutate(code);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        data-screen-id="S-053"
        data-feature-id="F-001"
        className="max-w-[420px]"
      >
        <DialogHeader>
          <div className="mx-auto inline-flex w-14 h-14 rounded-full bg-eb-100 items-center justify-center mb-2">
            <ShieldCheck className="w-7 h-7 text-eb-500" aria-hidden />
          </div>
          <DialogTitle className="text-center text-xl font-bold">
            {S053_H2_TEXT}
          </DialogTitle>
          <DialogDescription className="text-center text-sm text-slate-600">
            {S053_SUBTITLE}
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="mt-2 space-y-4"
        >
          <Input
            data-testid="mfa-code-input"
            inputMode="numeric"
            pattern="[0-9]{6}"
            maxLength={TOTP_LENGTH}
            autoComplete="one-time-code"
            placeholder="123456"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ""))}
            className="mono tabular tracking-widest text-center h-12 text-2xl font-bold"
            aria-label="2FA コード"
            disabled={verifyMutation.isPending}
          />
          <Button
            type="submit"
            data-testid="mfa-verify-button"
            className="w-full bg-eb-500 hover:bg-eb-600 text-white h-10"
            disabled={verifyMutation.isPending}
          >
            {verifyMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
            ) : null}
            <span>検証する</span>
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// S-001 — Login page.
// ---------------------------------------------------------------------------
export default function LoginPage() {
  const router = useRouter();

  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [remember, setRemember] = React.useState(false);
  const [mfaOpen, setMfaOpen] = React.useState(false);
  const [pendingUserId, setPendingUserId] = React.useState<string | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const navigatePostLogin = React.useCallback(() => {
    // AC-F4: account_dashboard or workspace_dashboard (last visited).
    let lastVisited: string | null = null;
    if (typeof window !== "undefined") {
      try {
        lastVisited = window.localStorage.getItem(LAST_VISITED_STORAGE_KEY);
      } catch {
        lastVisited = null;
      }
    }
    const next = resolvePostLoginPath(lastVisited);
    router.push(next || POST_LOGIN_FALLBACK_PATH);
  }, [router]);

  const loginMutation = useMutation({
    mutationFn: async () =>
      loginWithPassword({ email, password }),
    onError: (err: unknown) => {
      // AC-F3 / AC-F6: generic, endpoint-tagged toast — never leak stack.
      if (err instanceof AuthApiError) {
        const userMsg = err.toUserMessage();
        setErrorMessage(userMsg);
        toast.error(userMsg);
      } else {
        const fallback = "サインインに失敗しました (/api/auth/login)";
        setErrorMessage(fallback);
        toast.error(fallback);
      }
    },
    onSuccess: (resp: LoginResponse) => {
      setErrorMessage(null);
      // AC-F8: mfa_required=true → show S-053 dialog before completing login.
      if (resp.mfa_required) {
        setPendingUserId(resp.user_id);
        setMfaOpen(true);
        return;
      }
      navigatePostLogin();
    },
  });

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMessage(null);
    if (!email || !password) {
      const msg = "メールアドレスとパスワードを入力してください";
      setErrorMessage(msg);
      toast.error(msg);
      return;
    }
    loginMutation.mutate();
  };

  const isSubmitting = loginMutation.isPending;

  return (
    <div
      data-screen-id="S-001"
      data-feature-id="F-001"
      data-screen-name="login"
      className="min-h-screen flex flex-col bg-slate-50 text-slate-900"
    >
      {/* Header (minimal logo bar) */}
      <header className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2 max-w-[1400px] mx-auto">
          <div className="w-7 h-7 rounded-md bg-eb-500 flex items-center justify-center">
            <Factory className="w-4 h-4 text-white" aria-hidden />
          </div>
          <div className="text-sm font-bold text-slate-900">Build-Factory</div>
          <span className="text-[11px] text-slate-500 mono">v3</span>
        </div>
      </header>

      {/* Main centered login card */}
      <main className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[420px]">
          {/* Title block */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-lg bg-eb-500 mb-4">
              <Factory className="w-6 h-6 text-white" aria-hidden />
            </div>
            <h1 className="text-2xl font-bold text-slate-900">
              {S001_H1_TEXT}
            </h1>
            <p className="text-sm text-slate-600 mt-1">{S001_SUBTITLE}</p>
          </div>

          {/* Login card */}
          <form
            onSubmit={submit}
            className="bg-white border border-slate-200 rounded-lg p-6 space-y-4"
            aria-label="login-form"
          >
            {/* Email */}
            <div className="space-y-1.5">
              <label
                htmlFor="email"
                className="text-sm font-medium text-slate-900 block"
              >
                メールアドレス
              </label>
              <Input
                id="email"
                data-testid="login-email-input"
                type="email"
                placeholder="you@example.com"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={isSubmitting}
              />
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label
                  htmlFor="password"
                  className="text-sm font-medium text-slate-900"
                >
                  パスワード
                </label>
                <a
                  href="/forgot-password"
                  className="text-xs text-eb-500 hover:text-eb-600 hover:underline"
                >
                  パスワードを忘れた
                </a>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  data-testid="login-password-input"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••••"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={isSubmitting}
                  className="pr-9"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((p) => !p)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-1"
                  aria-label={
                    showPassword ? "パスワードを隠す" : "パスワードを表示"
                  }
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" aria-hidden />
                  ) : (
                    <Eye className="w-4 h-4" aria-hidden />
                  )}
                </button>
              </div>
            </div>

            {/* Remember me */}
            <div className="flex items-center gap-2 pt-1">
              <input
                id="remember"
                data-testid="login-remember-checkbox"
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="w-4 h-4 rounded border-slate-300 accent-eb-500"
              />
              <label
                htmlFor="remember"
                className="text-sm text-slate-600"
              >
                この端末を記憶する
              </label>
            </div>

            {/* Submit button */}
            <Button
              type="submit"
              data-testid="login-submit-button"
              className="w-full bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-4 rounded-md"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <Loader2
                  className="w-4 h-4 animate-spin"
                  aria-hidden
                />
              ) : null}
              <span>ログイン</span>
              {!isSubmitting ? (
                <ArrowRight className="w-4 h-4" aria-hidden />
              ) : null}
            </Button>

            {/* Error message (AC-F3 / AC-F6) */}
            {errorMessage ? (
              <div
                data-testid="login-error-banner"
                role="alert"
                className="bg-red-50 border border-red-200 text-red-700 text-xs px-3 py-2 rounded-md flex items-center gap-2"
              >
                <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden />
                <span>{errorMessage}</span>
              </div>
            ) : null}

            {/* Divider */}
            <div className="relative py-2">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200" />
              </div>
              <div className="relative flex justify-center">
                <span className="bg-white px-2 text-xs text-slate-500">
                  または
                </span>
              </div>
            </div>

            {/* OAuth buttons */}
            <div className="space-y-2">
              <button
                type="button"
                data-testid="oauth-anthropic"
                className="w-full bg-white border border-slate-200 hover:bg-slate-50 text-slate-900 text-sm font-medium h-9 px-4 rounded-md transition-colors flex items-center justify-center gap-2"
              >
                <Sparkles className="w-4 h-4 text-eb-500" aria-hidden />
                <span>Anthropic で続ける</span>
              </button>
              <button
                type="button"
                data-testid="oauth-google"
                className="w-full bg-white border border-slate-200 hover:bg-slate-50 text-slate-900 text-sm font-medium h-9 px-4 rounded-md transition-colors flex items-center justify-center gap-2"
              >
                <Globe
                  className="w-4 h-4 text-slate-700"
                  aria-hidden
                />
                <span>Google で続ける</span>
              </button>
              <button
                type="button"
                data-testid="oauth-github"
                className="w-full bg-white border border-slate-200 hover:bg-slate-50 text-slate-900 text-sm font-medium h-9 px-4 rounded-md transition-colors flex items-center justify-center gap-2"
              >
                <GitBranch
                  className="w-4 h-4 text-slate-700"
                  aria-hidden
                />
                <span>GitHub で続ける</span>
              </button>
            </div>
          </form>

          {/* Sign up link */}
          <p className="text-center text-sm text-slate-600 mt-6">
            アカウントをお持ちでない方は
            <a
              href="/signup"
              className="text-eb-500 hover:text-eb-600 hover:underline font-medium ml-1"
            >
              サインアップ
            </a>
          </p>

          {/* Footer info */}
          <div className="text-center text-[11px] text-slate-400 mt-8 space-x-3">
            <a href="#" className="hover:text-slate-600">
              利用規約
            </a>
            <span>·</span>
            <a href="#" className="hover:text-slate-600">
              プライバシーポリシー
            </a>
            <span>·</span>
            <span className="mono">© ENGINE BASE</span>
          </div>
        </div>
      </main>

      {/* AC-F8: MFA challenge dialog (S-053 pattern). */}
      <MfaChallengeDialog
        open={mfaOpen}
        onOpenChange={(next) => {
          setMfaOpen(next);
          if (!next) {
            setPendingUserId(null);
          }
        }}
        pendingUserId={pendingUserId}
        onVerified={() => {
          setMfaOpen(false);
          setPendingUserId(null);
          navigatePostLogin();
        }}
      />
    </div>
  );
}
