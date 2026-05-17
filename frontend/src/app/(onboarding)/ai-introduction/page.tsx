"use client";

/**
 * S-050 AI 社員紹介 — T-V3-C-41 / F-027.
 *
 * @screen-id S-050
 * @feature-id F-027
 * @task-ids T-V3-C-41
 * @entities E-041
 * @phase Phase 1
 *
 * Mock 逐語準拠: docs/mocks/2026-05-15_v3/onboarding/S-050-ai-employee-intro.html
 *   - h1 text          : "AI 社員チームと一緒に"   (screens.json[S-050].h1_text)
 *   - 状態             : loading / loaded / error  (screens.json[S-050].states)
 *   - icons            : Lucide のみ (no emoji)    (design-tokens §8)
 *
 * 3-tier AC mapping (逐語):
 *   structural.AC-S1: STATE-DRIVEN: While the ai_employee_intro page is
 *     rendered, the system shall display an h1 element with the exact text
 *     "AI 社員チームと一緒に".
 *   structural.AC-S2: UBIQUITOUS: The system shall use Lucide icons
 *     exclusively (no emoji) for icon-glyph elements on this page.
 *   functional.AC-F1: UNWANTED: If an unauthenticated visitor navigates to
 *     this page, the system shall redirect to /login (S-001) and shall not
 *     render any workspace-scoped data.
 *   functional.AC-F2: STATE-DRIVEN: While data is being fetched, the system
 *     shall render a skeleton loader with role="status" aria-live="polite";
 *     once data arrives the skeleton shall be replaced atomically.
 */

import * as React from "react";
import { ArrowLeft, Check, Sparkles } from "lucide-react";

import {
  AI_EMPLOYEE_PERSONAS,
  advanceOnboarding,
  type AiEmployeePersonaCard,
} from "@/api/onboarding";
import { useAiEmployeeIntro } from "@/hooks/useAiEmployeeIntro";

const DASHBOARD_HREF = "/dashboard";
const LOGIN_HREF = "/login";
const WORKSPACE_SETUP_HREF = "/workspace-setup";

/**
 * AC-F1 helper: imperatively replace the browser URL with /login. Tests stub
 * `window.location.replace` via vitest spies; SSR safety is preserved by
 * the `typeof window` guard.
 */
function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  try {
    window.location.replace(LOGIN_HREF);
  } catch {
    window.location.assign(LOGIN_HREF);
  }
}

export default function AiEmployeeIntroductionPage(): React.JSX.Element {
  const { view, errorMessage, refetch } = useAiEmployeeIntro();
  const [advancing, setAdvancing] = React.useState(false);
  const [advanceError, setAdvanceError] = React.useState<string | null>(null);

  // AC-F1 (UNWANTED): once the hook signals unauthorized, perform a
  // client-side redirect to /login. Render returns the redirect placeholder
  // *before* this effect runs so no workspace data is ever surfaced.
  React.useEffect(() => {
    if (view === "unauthorized") {
      redirectToLogin();
    }
  }, [view]);

  const onAdvance = React.useCallback(async () => {
    setAdvancing(true);
    setAdvanceError(null);
    try {
      await advanceOnboarding();
      if (typeof window !== "undefined") {
        window.location.assign(DASHBOARD_HREF);
      }
    } catch {
      // Best-effort: advance is server-driven; fall back to client-side
      // navigation so the user is never stuck on S-050.
      setAdvanceError(
        "ダッシュボードへの遷移に失敗しました。再試行してください。",
      );
      if (typeof window !== "undefined") {
        window.location.assign(DASHBOARD_HREF);
      }
    } finally {
      setAdvancing(false);
    }
  }, []);

  // AC-F1 (UNWANTED): zero workspace-scoped data is rendered for unauth visitors.
  if (view === "unauthorized") {
    return (
      <div
        data-screen-id="S-050"
        data-feature-id="F-027"
        data-task-ids="T-V3-C-41"
        data-entities="E-041"
        data-phase="Phase 1"
        data-view-state="unauthorized"
        role="status"
        aria-live="polite"
        className="min-h-screen flex items-center justify-center bg-slate-50 text-sm text-slate-500"
      >
        サインインページへ移動しています…
      </div>
    );
  }

  return (
    <div
      data-screen-id="S-050"
      data-feature-id="F-027"
      data-task-ids="T-V3-C-41"
      data-entities="E-041"
      data-phase="Phase 1"
      data-view-state={view}
      className="min-h-screen bg-slate-50 text-slate-900 flex flex-col"
    >
      <main className="flex-1 flex items-center justify-center px-6 py-8">
        <div className="max-w-[800px] w-full">
          {/* Progress (3 / 3) */}
          <div
            className="flex items-center gap-2 mb-8 max-w-xs mx-auto"
            aria-label="オンボーディング進捗"
            data-testid="onboarding-progress"
          >
            <div className="flex-1 h-1.5 bg-eb-500 rounded-full" />
            <div className="flex-1 h-1.5 bg-eb-500 rounded-full" />
            <div className="flex-1 h-1.5 bg-eb-500 rounded-full" />
          </div>

          <div className="text-center mb-6">
            <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold">
              Step 3 / 3
            </div>
            {/* AC-S1: h1 must read exactly "AI 社員チームと一緒に" */}
            <h1 className="text-2xl font-bold mt-1">AI 社員チームと一緒に</h1>
            <p className="text-sm text-slate-600 mt-2">
              BMAD 10 ペルソナがあなたの案件をサポートします
            </p>
          </div>

          {/* AC-F2 (STATE-DRIVEN): skeleton is shown while loading and is
              replaced atomically once `view === "loaded"`. */}
          {view === "loading" ? (
            <div
              role="status"
              aria-live="polite"
              aria-label="AI 社員紹介を読み込み中"
              data-testid="ai-intro-skeleton"
              className="grid grid-cols-5 gap-3"
            >
              {AI_EMPLOYEE_PERSONAS.map((p) => (
                <div
                  key={`skeleton-${p.id}`}
                  className="bg-white border border-slate-200 rounded-lg p-3 text-center animate-pulse"
                  data-testid={`ai-intro-skeleton-${p.id}`}
                >
                  <div className="w-10 h-10 rounded-full bg-slate-200 mx-auto mb-1.5" />
                  <div className="h-3 w-12 bg-slate-200 rounded mx-auto" />
                  <div className="h-2 w-10 bg-slate-100 rounded mx-auto mt-1" />
                </div>
              ))}
              <span className="sr-only">AI 社員紹介を読み込み中です</span>
            </div>
          ) : view === "error" ? (
            <div
              role="alert"
              data-testid="ai-intro-error"
              className="bg-red-50 border border-red-200 rounded-md p-4 text-sm text-red-700 flex items-start justify-between gap-3"
            >
              <div>
                {errorMessage ?? "通信に失敗しました"}
              </div>
              <button
                type="button"
                onClick={() => {
                  void refetch();
                }}
                className="text-xs font-semibold underline hover:no-underline"
                data-testid="ai-intro-retry"
              >
                再試行
              </button>
            </div>
          ) : (
            <div
              data-testid="ai-intro-loaded"
              className="grid grid-cols-5 gap-3"
            >
              {AI_EMPLOYEE_PERSONAS.map((persona) => (
                <PersonaCard key={persona.id} persona={persona} />
              ))}
            </div>
          )}

          {/* Personal-clone callout (mock parity) */}
          <div className="mt-8 bg-eb-50 border border-eb-200 rounded-md p-4 flex items-start gap-2">
            <Sparkles
              className="w-4 h-4 text-eb-500 mt-0.5"
              aria-hidden="true"
            />
            <div className="text-xs text-eb-700">
              <strong>個人クローン (opt-in)</strong>:
              あなたの判断ログ・コメントを学習させた「あなたのコピー」を AI 社員として登録できます。後でプロフィール設定から有効化可能。
            </div>
          </div>

          {/* Advance error (non-fatal) */}
          {advanceError && (
            <div
              role="alert"
              data-testid="ai-intro-advance-error"
              className="mt-3 bg-amber-50 border border-amber-200 rounded-md p-2 text-xs text-amber-800"
            >
              {advanceError}
            </div>
          )}

          {/* Bottom nav */}
          <div className="mt-6 flex items-center justify-between">
            <a
              href={WORKSPACE_SETUP_HREF}
              className="text-sm text-slate-500 hover:text-slate-900 h-10 px-5 flex items-center gap-1"
              data-testid="ai-intro-back"
            >
              <ArrowLeft className="w-4 h-4" aria-hidden="true" />
              戻る
            </a>
            <button
              type="button"
              onClick={onAdvance}
              disabled={advancing || view !== "loaded"}
              aria-busy={advancing}
              className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-6 rounded-md flex items-center gap-2 disabled:opacity-50"
              data-testid="ai-intro-advance"
            >
              ダッシュボードへ
              <Check className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

// --------------------------------------------------------------------------
// Persona card — internal sub-component (kept simple, mock-aligned).
// --------------------------------------------------------------------------

function PersonaCard({
  persona,
}: {
  persona: AiEmployeePersonaCard;
}): React.JSX.Element {
  return (
    <div
      className="bg-white border border-slate-200 rounded-lg p-3 text-center"
      data-testid={`persona-card-${persona.id}`}
    >
      <div
        className={`w-10 h-10 rounded-full ${persona.colorClass} text-white text-xs font-bold flex items-center justify-center mx-auto mb-1.5 mono`}
        aria-hidden="true"
      >
        {persona.initials}
      </div>
      <div className="text-xs font-bold" data-testid={`persona-name-${persona.id}`}>
        {persona.name}
      </div>
      <div className="text-[10px] text-slate-500">{persona.role}</div>
    </div>
  );
}
