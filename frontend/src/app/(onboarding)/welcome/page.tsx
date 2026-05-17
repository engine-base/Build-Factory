"use client";

/**
 * T-V3-C-39 / S-048 — ようこそ (welcome_first_login) onboarding page.
 *
 * Backend contract (T-V3-B-29 ONBOARDING 実装済):
 *   GET   /api/me/onboarding          (state / current_step / completed)
 *   POST  /api/me/onboarding/advance  (step + payload → next_step / completed)
 *   POST  /api/me/onboarding/skip     (skipped_at)
 *
 * Mock-impl source of truth:
 *   docs/mocks/2026-05-15_v3/onboarding/S-048-welcome-first-login.html
 * Spec source of truth:
 *   docs/functional-breakdown/2026-05-16_v3/screens.json#S-048
 *
 * 3-tier AC mapping (T-V3-C-39):
 *   - Tier 1 / AC-S1: h1 === "Build-Factory へようこそ"   (mock h1 逐語コピー)
 *   - Tier 1 / AC-S2: Lucide icons only, no emojis        (design-tokens.md §8)
 *   - Tier 2 / AC-F1: 401 → router.replace("/login")      (no workspace data render)
 *   - Tier 2 / AC-F2: skeleton role="status" aria-live="polite" while loading
 *
 * Design system: ENGINE BASE green (#1a6648 = eb-500), Noto Sans JP, shadcn/ui.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Factory,
  Loader2,
  Mic,
  PackageCheck,
  Zap,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { OnboardingApiError } from "@/api/onboarding";
import { useWelcomeFirstLogin } from "@/hooks/useWelcomeFirstLogin";

// ---------------------------------------------------------------------------
// Mock-derived screen literals — 逐語コピー (h1_text from screens.json[S-048]).
// AC-S1: h1_text === "Build-Factory へようこそ"
// ---------------------------------------------------------------------------
const S048_H1_TEXT = "Build-Factory へようこそ";
const S048_SUBTITLE_LEAD =
  "受託会社 / 中小企業の社内開発チーム / フリーランス PM が、";
const S048_SUBTITLE_STRONG = "1 人で 10 案件を並列開発できる";
const S048_SUBTITLE_TAIL = " SaaS 型の開発工場 OS。";

const SKIP_LABEL = "スキップして始める";
const NEXT_LABEL = "最初の案件を作成する";

const NEXT_STEP_PATH = "/onboarding/workspace-setup"; // → S-049

interface PillarCard {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  desc: string;
}

const PILLARS: ReadonlyArray<PillarCard> = [
  {
    icon: Mic,
    title: "ヒアリング",
    desc: "AI 社員と対話で要件抽出",
  },
  {
    icon: Zap,
    title: "Swarm 並列実行",
    desc: "最大 50 セッション並列",
  },
  {
    icon: PackageCheck,
    title: "納品まで一気通貫",
    desc: "仕様 → 実装 → テスト → 納品",
  },
] as const;

// ---------------------------------------------------------------------------
// Skeleton loader — AC-F2: role="status" aria-live="polite" while loading.
// ---------------------------------------------------------------------------
function WelcomeSkeleton() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="読み込み中"
      data-testid="welcome-skeleton"
      className="max-w-[640px] w-full"
    >
      <div className="flex items-center gap-2 mb-8 max-w-xs mx-auto">
        <div className="flex-1 h-1.5 bg-slate-200 rounded-full animate-pulse" />
        <div className="flex-1 h-1.5 bg-slate-200 rounded-full animate-pulse" />
        <div className="flex-1 h-1.5 bg-slate-200 rounded-full animate-pulse" />
      </div>
      <div className="flex flex-col items-center gap-3">
        <div className="w-16 h-16 rounded-2xl bg-slate-200 animate-pulse" />
        <div className="h-8 w-2/3 bg-slate-200 rounded animate-pulse" />
        <div className="h-4 w-3/4 bg-slate-200 rounded animate-pulse" />
      </div>
      <div className="grid grid-cols-3 gap-4 mt-8">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="bg-white border border-slate-200 rounded-lg p-4 h-28 animate-pulse"
          />
        ))}
      </div>
      <span className="sr-only">読み込み中…</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// S-048 — Welcome (first login) page.
// ---------------------------------------------------------------------------
export default function WelcomeFirstLoginPage() {
  const router = useRouter();
  const {
    data,
    isLoading,
    isError,
    error,
    advance,
    skip,
    isAdvancing,
    isSkipping,
  } = useWelcomeFirstLogin();

  // AC-F1: UNWANTED — unauthenticated visitor → redirect to /login (S-001).
  // We do this in an effect so the redirect runs after render commit and
  // server components don't see partially-rendered workspace data.
  React.useEffect(() => {
    if (!isError) return;
    if (error instanceof OnboardingApiError && error.status === 401) {
      router.replace("/login");
    }
  }, [isError, error, router]);

  // If we already know we're unauthorised, render nothing so no workspace-
  // scoped UI ever appears — AC-F1 second-half guarantee.
  if (isError && error instanceof OnboardingApiError && error.status === 401) {
    return (
      <div
        data-screen-id="S-048"
        data-feature-id="F-027"
        data-screen-name="welcome_first_login"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  const handleAdvance = async () => {
    try {
      await advance({ step: "welcome", payload: {} });
      router.push(NEXT_STEP_PATH);
    } catch (err) {
      if (err instanceof OnboardingApiError && err.status === 401) {
        router.replace("/login");
      }
    }
  };

  const handleSkip = async () => {
    try {
      await skip({ step: "welcome" });
      router.push(NEXT_STEP_PATH);
    } catch (err) {
      if (err instanceof OnboardingApiError && err.status === 401) {
        router.replace("/login");
      }
    }
  };

  return (
    <div
      data-screen-id="S-048"
      data-feature-id="F-027"
      data-screen-name="welcome_first_login"
      className="min-h-screen flex flex-col bg-slate-50 text-slate-900 font-sans"
    >
      <main className="flex-1 flex items-center justify-center px-6 py-8">
        {isLoading ? (
          <WelcomeSkeleton />
        ) : (
          <div className="max-w-[640px] w-full" data-testid="welcome-content">
            {/* Stepper — 1/3 active (welcome) */}
            <div
              className="flex items-center gap-2 mb-8 max-w-xs mx-auto"
              aria-label="onboarding-stepper"
              data-testid="welcome-stepper"
            >
              <div
                className="flex-1 h-1.5 bg-eb-500 rounded-full"
                aria-current="step"
              />
              <div className="flex-1 h-1.5 bg-slate-200 rounded-full" />
              <div className="flex-1 h-1.5 bg-slate-200 rounded-full" />
            </div>

            <div className="text-center">
              <div className="inline-flex w-16 h-16 rounded-2xl bg-eb-500 items-center justify-center mb-4">
                <Factory className="w-8 h-8 text-white" aria-hidden />
              </div>
              <h1 className="text-3xl font-bold">{S048_H1_TEXT}</h1>
              <p className="text-base text-slate-600 mt-3 leading-relaxed">
                {S048_SUBTITLE_LEAD}
                <br />
                <strong>{S048_SUBTITLE_STRONG}</strong>
                {S048_SUBTITLE_TAIL}
              </p>
              {data?.current_step ? (
                <p className="sr-only" data-testid="welcome-current-step">
                  current step: {data.current_step}
                </p>
              ) : null}
            </div>

            <div className="grid grid-cols-3 gap-4 mt-8">
              {PILLARS.map((p) => {
                const Icon = p.icon;
                return (
                  <div
                    key={p.title}
                    className="bg-white border border-slate-200 rounded-lg p-4 text-center"
                  >
                    <div className="w-10 h-10 rounded-full bg-eb-50 flex items-center justify-center mx-auto mb-2">
                      <Icon className="w-5 h-5 text-eb-500" aria-hidden />
                    </div>
                    <div className="text-sm font-bold">{p.title}</div>
                    <div className="text-xs text-slate-500 mt-1">{p.desc}</div>
                  </div>
                );
              })}
            </div>

            <div className="mt-8 flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={handleSkip}
                disabled={isSkipping || isAdvancing}
                data-testid="welcome-skip-button"
                className="text-sm text-slate-500 hover:text-slate-900 h-10 px-5 disabled:opacity-50"
              >
                {SKIP_LABEL}
              </button>
              <Button
                type="button"
                onClick={handleAdvance}
                disabled={isAdvancing || isSkipping}
                data-testid="welcome-advance-button"
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-6 rounded-md flex items-center gap-2"
              >
                {isAdvancing ? (
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
                ) : null}
                <span>{NEXT_LABEL}</span>
                <ArrowRight className="w-4 h-4" aria-hidden />
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
