"use client";

/**
 * T-V3-C-02 / S-002: サインアップ (Account creation) page.
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/auth/S-002-signup.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-002
 * @feature-id F-001,F-004
 * @task-ids T-V3-C-02
 * @entities E-001,E-002,E-008,E-043
 * @phase Phase 1B
 *
 * 3-tier AC mapping:
 *   structural.AC-S1 (data-screen-id="S-002")               — root <main> element.
 *   structural.AC-S2 (h1 text "アカウント作成")             — <h1> below the header.
 *   functional.AC-F1 (POST /api/auth/signup via typed client) — onSubmit handler.
 *   functional.AC-F2 (GET  /api/invitations/{token})        — useQuery on mount.
 *   functional.AC-F3 (4xx/5xx → non-technical toast w/ endpoint, no stack) — error handlers.
 *   functional.AC-F4 (post-signup navigation account_dashboard | invite_accept).
 *   functional.AC-F5 (login 200 with tokens — auto-login after signup).
 *   functional.AC-F6 (login 401 generic message, no enumeration).
 */

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowRight,
  Chrome,
  Factory,
  GitBranch,
  Sparkles,
  Ticket,
  UserPlus,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AuthApiError,
  getInvitation,
  login,
  signup,
  type InvitationInfo,
} from "@/api/auth";

// --------------------------------------------------------------------------
// Form helpers
// --------------------------------------------------------------------------

interface FormState {
  name: string;
  email: string;
  password: string;
  tosAgree: boolean;
  privacyAgree: boolean;
}

const INITIAL_FORM: FormState = {
  name: "",
  email: "",
  password: "",
  tosAgree: false,
  privacyAgree: false,
};

/** Lightweight strength estimator that mirrors the mock's "強度: 普通" bar. */
function passwordStrength(pw: string): { score: number; label: string } {
  if (!pw) return { score: 0, label: "未入力" };
  let score = 0;
  if (pw.length >= 8) score += 1;
  if (pw.length >= 12) score += 1;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score += 1;
  if (/\d/.test(pw)) score += 1;
  if (/[^A-Za-z0-9]/.test(pw)) score += 1;
  const labels = ["弱い", "弱い", "普通", "普通", "強い", "強い"] as const;
  return { score, label: labels[Math.min(score, 5)] };
}

function isFormValid(f: FormState): boolean {
  if (!f.name.trim()) return false;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email)) return false;
  if (f.password.length < 8) return false;
  if (!f.tosAgree || !f.privacyAgree) return false;
  return true;
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function SignupPage() {
  const router = useRouter();
  const params = useSearchParams();
  const inviteToken = params?.get("invite") ?? null;

  const [form, setForm] = React.useState<FormState>(INITIAL_FORM);
  const update = React.useCallback(
    <K extends keyof FormState>(key: K, value: FormState[K]) => {
      setForm((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  // AC-F2: GET /api/invitations/{token} — only when ?invite=... is present.
  const invitationQuery = useQuery<InvitationInfo | null>({
    queryKey: ["invitation", inviteToken],
    enabled: !!inviteToken,
    queryFn: ({ signal }) =>
      getInvitation(inviteToken as string, { signal }),
    retry: false,
    staleTime: 60_000,
  });

  // AC-F3: surface non-technical toast referencing the failing endpoint,
  //        without leaking server stack traces.
  const lastInviteToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!invitationQuery.isError) {
      lastInviteToastRef.current = null;
      return;
    }
    const err = invitationQuery.error;
    const userMsg =
      err instanceof AuthApiError
        ? err.toUserMessage()
        : `招待コードを取得できませんでした (/api/invitations)`;
    if (lastInviteToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastInviteToastRef.current = userMsg;
    }
  }, [invitationQuery.isError, invitationQuery.error]);

  // AC-F1 + AC-F5: signup → auto-login → navigate.
  const signupMutation = useMutation({
    mutationFn: async (current: FormState) => {
      await signup({
        email: current.email,
        password: current.password,
        name: current.name,
        invitation_token: inviteToken ?? undefined,
      });
      // AC-F5: auto-login so the user lands signed-in on the next screen.
      const session = await login({
        email: current.email,
        password: current.password,
      });
      return session;
    },
    onSuccess: () => {
      // AC-F4: route to invite-accept screen when a token was used,
      // otherwise to the freshly-created account dashboard.
      if (inviteToken) {
        router.push(
          `/workspaces/invite/accept?token=${encodeURIComponent(inviteToken)}`,
        );
      } else {
        router.push("/dashboard");
      }
    },
    onError: (err: unknown) => {
      // AC-F3 + AC-F6: non-technical message that tags the failing endpoint.
      const userMsg =
        err instanceof AuthApiError
          ? err.toUserMessage()
          : `アカウント作成に失敗しました (/api/auth/signup)`;
      toast.error(userMsg);
    },
  });

  const strength = React.useMemo(
    () => passwordStrength(form.password),
    [form.password],
  );
  const valid = isFormValid(form);

  const onSubmit = React.useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!valid || signupMutation.isPending) return;
      signupMutation.mutate(form);
    },
    [valid, form, signupMutation],
  );

  return (
    <main
      data-screen-id="S-002"
      data-feature-id="F-001,F-004"
      data-task-ids="T-V3-C-02"
      data-entities="E-001,E-002,E-008,E-043"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-50 text-slate-900 flex flex-col"
    >
      <header className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2 max-w-[1400px] mx-auto">
          <div className="w-7 h-7 rounded-md bg-eb-500 flex items-center justify-center">
            <Factory className="w-4 h-4 text-white" aria-hidden />
          </div>
          <div className="text-sm font-bold">Build-Factory</div>
          <span className="text-[11px] text-slate-500 mono">v3</span>
        </div>
      </header>

      <section className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[420px]">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-lg bg-eb-500 mb-4">
              <UserPlus className="w-6 h-6 text-white" aria-hidden />
            </div>
            <h1 className="text-2xl font-bold">アカウント作成</h1>
            <p className="text-sm text-slate-600 mt-1">
              受託 EC 構築から自社 SaaS まで、開発を 1 つの工場に
            </p>
          </div>

          {/* Invite banner (AC-F2 render path) */}
          {inviteToken && invitationQuery.data && (
            <div
              data-testid="invite-banner"
              className="bg-eb-50 border border-eb-100 rounded-md p-3 mb-4 flex items-start gap-2"
            >
              <Ticket
                className="w-4 h-4 text-eb-500 mt-0.5 shrink-0"
                aria-hidden
              />
              <div>
                <div className="text-sm font-medium text-eb-700">
                  招待を受けてサインアップ
                </div>
                <div className="text-xs text-slate-600 mt-0.5">
                  案件「
                  <span className="font-semibold">
                    {invitationQuery.data.workspace_name}
                  </span>
                  」のメンバーとして登録されます
                </div>
              </div>
            </div>
          )}

          <form
            onSubmit={onSubmit}
            className="bg-white border border-slate-200 rounded-lg p-6 space-y-4"
            noValidate
          >
            {/* Display name */}
            <div className="space-y-1.5">
              <label htmlFor="name" className="text-sm font-medium block">
                表示名 <span className="text-red-600">*</span>
              </label>
              <Input
                id="name"
                type="text"
                placeholder="高本 まさと"
                autoComplete="name"
                value={form.name}
                onChange={(e) => update("name", e.target.value)}
                required
              />
            </div>

            {/* Email */}
            <div className="space-y-1.5">
              <label htmlFor="email" className="text-sm font-medium block">
                メールアドレス <span className="text-red-600">*</span>
              </label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                autoComplete="email"
                value={form.email}
                onChange={(e) => update("email", e.target.value)}
                required
              />
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label htmlFor="password" className="text-sm font-medium block">
                パスワード <span className="text-red-600">*</span>
              </label>
              <Input
                id="password"
                type="password"
                placeholder="12 文字以上 / 英大小・数字・記号"
                autoComplete="new-password"
                value={form.password}
                onChange={(e) => update("password", e.target.value)}
                required
                minLength={8}
              />
              <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
                <div
                  data-testid="password-strength-bar"
                  className="h-full bg-eb-400 transition-all"
                  style={{ width: `${(strength.score / 5) * 100}%` }}
                />
              </div>
              <p className="text-xs text-slate-500">
                強度: {strength.label} / 大文字を含めるとより安全
              </p>
            </div>

            {/* Terms */}
            <div className="space-y-2 pt-2">
              <label className="flex items-start gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  className="w-4 h-4 rounded border-slate-300 accent-eb-500 mt-0.5"
                  checked={form.tosAgree}
                  onChange={(e) => update("tosAgree", e.target.checked)}
                />
                <span className="text-slate-700">
                  <a href="#" className="text-eb-500 hover:underline">
                    利用規約
                  </a>{" "}
                  に同意する
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  className="w-4 h-4 rounded border-slate-300 accent-eb-500 mt-0.5"
                  checked={form.privacyAgree}
                  onChange={(e) => update("privacyAgree", e.target.checked)}
                />
                <span className="text-slate-700">
                  <a href="#" className="text-eb-500 hover:underline">
                    プライバシーポリシー
                  </a>{" "}
                  に同意する
                </span>
              </label>
            </div>

            {/* Submit */}
            <Button
              type="submit"
              data-testid="signup-submit"
              disabled={!valid || signupMutation.isPending}
              className="w-full bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-4 rounded-md flex items-center justify-center gap-2 mt-2"
            >
              <span>
                {signupMutation.isPending ? "送信中..." : "アカウント作成"}
              </span>
              <ArrowRight className="w-4 h-4" aria-hidden />
            </Button>

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

            {/* OAuth (display only — handled by F-001 OAuth callback) */}
            <div className="space-y-2">
              <button
                type="button"
                className="w-full bg-white border border-slate-200 hover:bg-slate-50 text-slate-900 text-sm font-medium h-9 px-4 rounded-md flex items-center justify-center gap-2"
              >
                <Sparkles className="w-4 h-4 text-eb-500" aria-hidden />
                <span>Anthropic で続ける</span>
              </button>
              <button
                type="button"
                className="w-full bg-white border border-slate-200 hover:bg-slate-50 text-slate-900 text-sm font-medium h-9 px-4 rounded-md flex items-center justify-center gap-2"
              >
                <Chrome className="w-4 h-4" aria-hidden />
                <span>Google で続ける</span>
              </button>
              <button
                type="button"
                className="w-full bg-white border border-slate-200 hover:bg-slate-50 text-slate-900 text-sm font-medium h-9 px-4 rounded-md flex items-center justify-center gap-2"
              >
                <GitBranch className="w-4 h-4" aria-hidden />
                <span>GitHub で続ける</span>
              </button>
            </div>
          </form>

          <p className="text-center text-sm text-slate-600 mt-6">
            既にアカウントをお持ちの方は{" "}
            <a
              href="/login"
              className="text-eb-500 hover:text-eb-600 hover:underline font-medium"
            >
              ログイン
            </a>
          </p>

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
      </section>
    </main>
  );
}
