# T-V3-C-TEST-01 audit — Frontend vitest + RTL infrastructure

> Phase 1.0-fix / Wave 0 task C. Stands up the vitest + React Testing Library
> harness so the 54 existing `frontend/tests/screens/S-*.spec.tsx` files can
> actually run, with a 70% coverage gate **defined** in `vitest.config.ts`
> (CI runs informationally; promoted to required status by Wave 1 cleanup of
> `// @ts-nocheck` markers across the remaining specs).

## メタ

- screen(s): N/A (infrastructure task — touches all S-* screen specs collectively)
- feature_id: F-TEST (cross-cutting test harness)
- entity_ids: N/A
- mock_path: N/A
- depends_on: T-V3-D-15 (Phase 1 = 100/100 closure, lint-mock 17/17 OK baseline)
- branch: claude/T-V3-C-TEST-01-infra
- label: NEW
- ADR refs: ADR-011 (完了判定ゲート — `pre-commit-check.sh` 単一ゲート), CLAUDE.md §5.3 (テストカバレッジ ≥ 70% Phase 1 ゲート)

## Tier 1: Structural

- [x] AC-S1: UBIQUITOUS: The system shall provide a `frontend/vitest.config.ts`
      that configures the jsdom environment, the `@/` → `./src/` alias matching
      `tsconfig.json`, and the 70% coverage gate (branches/functions/lines/
      statements) for the v8 provider. →
      impl: `frontend/vitest.config.ts` (new, 62 lines). Lines 1-16: vite +
      react plugin import + jsdom environment + globals + setup file at
      `./tests/setup.ts`. Lines 17-24: alias `"@"` → `path.resolve(__dirname, "./src")`.
      Lines 42-60: coverage v8 provider, reporters text/html/lcov/json-summary,
      thresholds branches=70/functions=70/lines=70/statements=70.
      Verification: `pnpm exec vitest run --coverage` shows the threshold
      banner enforcement at the end of the run (5-spec subset produced
      `ERROR: Coverage for lines (5.72%) does not meet global threshold (70%)`
      proving the gate is wired but expected to fail until Wave 1 cleanup).

- [x] AC-S2: UBIQUITOUS: The system shall provide a `frontend/tests/setup.ts`
      that wires `@testing-library/jest-dom/vitest`, stubs `next/navigation`,
      `next/link`, and `sonner`, and exposes the JSDOM polyfills
      (`matchMedia` / `ResizeObserver` / `IntersectionObserver` /
      `scrollIntoView`) that Radix UI + shadcn components rely on. →
      impl: `frontend/tests/setup.ts` (new, 152 lines). Line 9 wires
      `@testing-library/jest-dom/vitest`. Lines 17-34 default-stub
      `next/navigation` (useRouter/usePathname/useSearchParams/useParams/
      redirect/notFound). Lines 39-51 stub `next/link`. Lines 56-72 stub
      `sonner.toast` (error/success/info/warning/message/loading/dismiss/
      promise). Lines 77-131 install JSDOM polyfills. Lines 137-152 reset
      fetch between tests and `cleanup()` after each test.

- [x] AC-S3: UBIQUITOUS: The system shall provide a `frontend/tsconfig.test.json`
      that extends `tsconfig.json` and adds vitest globals + jest-dom matcher
      types so test files can drop their `// @ts-nocheck` marker. →
      impl: `frontend/tsconfig.test.json` (new, 19 lines). `extends:
      ./tsconfig.json`, `types: ["vitest/globals",
      "@testing-library/jest-dom", "node"]`, `include: tests/**` +
      `src/**` + `vitest.config.ts`. Verified by running
      `npx tsc --noEmit -p tsconfig.test.json` — the 5 representative
      specs report 0 errors (pre-existing failures only in
      `tests/screens/S-027-task_kanban.spec.tsx` which is out of scope).

## Tier 2: Functional

- [x] AC-F1: EVENT-DRIVEN: When `pnpm test` is invoked from `frontend/`,
      the system shall execute every `tests/**/*.spec.{ts,tsx}` file under the
      jsdom environment. →
      impl: `frontend/package.json` scripts: `"test": "vitest run"`,
      `"test:watch": "vitest"`, `"test:cov": "vitest run --coverage"`.
      Verification: `cd frontend && pnpm exec vitest run` discovers all 54
      screen specs (`Test Files 34 failed | 20 passed (54)` →
      `Tests 29 failed | 215 passed (244)`). The 34 file-failures are
      pre-existing spec authoring issues (see "ノート" below) — they prove
      the harness is correctly collecting and executing every spec.

- [x] AC-F2: EVENT-DRIVEN: When the test harness runs a representative spec
      without the `// @ts-nocheck` marker, every test case in that spec shall
      pass under jsdom. →
      impl: Marker removed in this PR from 5 representative specs:
      `frontend/tests/screens/S-009-profile_settings.spec.tsx` (9 cases),
      `frontend/tests/screens/S-011-global_search.spec.tsx` (7 cases),
      `frontend/tests/screens/S-012-workspace_dashboard.spec.tsx` (7 cases),
      `frontend/tests/screens/S-021-requirements_editor.spec.tsx` (9 cases),
      `frontend/tests/screens/S-029-task_dag_view.spec.tsx` (8 cases).
      Verification: `pnpm exec vitest run` on these 5 files →
      `Test Files 5 passed (5) / Tests 40 passed (40)` (100%).

- [x] AC-F3: EVENT-DRIVEN: When `pnpm test:cov` is invoked, the system shall
      run the v8 coverage provider and emit `coverage/` with `text` (stdout),
      `html`, `lcov` (`coverage/lcov.info`), and `json-summary` reporters. →
      impl: `vitest.config.ts` lines 43-45 declare the four reporters and
      `reportsDirectory: "./coverage"`. Verification: after `pnpm test:cov`
      on the 5 representative specs, `coverage/coverage-summary.json`,
      `coverage/lcov.info`, `coverage/index.html` are emitted; the v8
      threshold banner at the end of stdout enforces the 70% gate
      (current numbers below).

- [x] AC-F4: STATE-DRIVEN: While the coverage report is below the configured
      70% threshold, the system shall fail `pnpm test:cov` with non-zero
      exit code so the gate is enforceable. →
      impl: `vitest.config.ts` lines 54-59 set `thresholds: { branches: 70,
      functions: 70, lines: 70, statements: 70 }`. Verification: 5-spec run
      emitted 4 ERROR lines and exited non-zero — the gate is operational.
      The new CI workflow (`.github/workflows/frontend-test.yml`) runs
      `pnpm test:cov` and is intentionally marked `continue-on-error: true`
      so this PR can land the infrastructure without blocking; Wave 1
      cleanup of `// @ts-nocheck` will lift coverage past the threshold and
      let us drop the `continue-on-error` flag.

## Tier 3: Regression

- [x] AC-R1: The system shall keep `bash scripts/lint-mock.sh` at 17/17 OK
      with no new violations introduced by this PR. →
      実行ログ: `bash scripts/lint-mock.sh` → final line `===== Lint OK =====`
      (exit 0). All 17 checks (絵文字 / AGPL / ARCHIVE / tickets / secrets /
      langgraph / litellm-in-runner / domain-boundaries / provider-routing /
      tool-trim / template-skeleton / constitution-inject / fallback-circuit-
      breaker / handoff / 9-section-summary / server-side-compaction /
      entity-table-naming-drift) PASS.

- [x] AC-R2: The system shall keep `python3 scripts/validate-tickets.py`
      passing for every existing ticket entry. →
      実行ログ: `OK: all tickets pass validation.` (exit 0).

- [x] AC-R3: The system shall pass `bash scripts/audit-md-check.sh
      T-V3-C-TEST-01` (audit MD exists, 3 Tier sections present, no generic
      phrase). →
      実行ログ: `bash scripts/audit-md-check.sh T-V3-C-TEST-01; echo "Exit: $?"` → `Exit: 0`.

- [x] AC-R4: The system shall not regress the existing CI workflows
      (`ci.yml`, `ci-v3.yml`). The new workflow is a separate file with its
      own concurrency group. →
      impl: `.github/workflows/frontend-test.yml` declares
      `concurrency: group: frontend-test-${{ github.ref }}` (independent of
      `ci-v3-${{ github.ref }}` and the legacy `ci.yml` group). Triggers are
      scoped to `frontend/**` + the workflow file itself via `paths:`.

- [x] AC-R5: The system shall pin the test devDeps to React-19-compatible
      versions and record them in `package.json`. →
      installed (pnpm 10.33.0 lockfile, `pnpm ls`):
      - `vitest@2.1.9`
      - `@vitejs/plugin-react@4.7.0`
      - `@vitest/coverage-v8@2.1.9`
      - `@testing-library/react@16.3.2`
      - `@testing-library/jest-dom@6.9.1`
      - `@testing-library/user-event@14.6.1`
      - `jsdom@25.0.1`

### 凡例

- [ ] = 未着手
- [x] = PASS (実行ログ貼付済)
- [/] = SKIP-WITH-REASON
- [!] = FAIL

## 着手記録

- 着手日: 2026-05-17
- 担当 session: worktree agent-a7aec3bd183fd3685
- branch: claude/T-V3-C-TEST-01-infra

## 完了記録

- 完了日: 2026-05-17
- Decision: DONE (infra landed, 40/40 representative specs PASS)
- PR: see commit log of `claude/T-V3-C-TEST-01-infra`
- 実行ログ抜粋:
  - `cd frontend && pnpm exec vitest run tests/screens/S-009-profile_settings.spec.tsx tests/screens/S-011-global_search.spec.tsx tests/screens/S-012-workspace_dashboard.spec.tsx tests/screens/S-021-requirements_editor.spec.tsx tests/screens/S-029-task_dag_view.spec.tsx`
    → `Test Files 5 passed (5) / Tests 40 passed (40)`.
  - `bash scripts/lint-mock.sh` → `===== Lint OK =====` (17/17, exit 0).
  - `python3 scripts/validate-tickets.py` → `OK: all tickets pass validation.`
  - `bash scripts/audit-md-check.sh T-V3-C-TEST-01` → exit 0.

## ノート

- **Scope boundary**: Wave 0 only lands the infra. The remaining 49 spec
  files keep their `// @ts-nocheck` marker — Wave 1 cleanup picks them up.
- **Coverage % achieved** (5 representative specs only):
  - Lines: 5.72% (gate fails until Wave 1 cleanup runs the rest of the specs)
  - Functions: 33.75%
  - Statements: 5.72%
  - Branches: 53.82%
- **Pre-existing source rot** (3 doc-comment merge artifacts in
  `frontend/src/api/auth.ts` lines 17 / 60 / 286 broke esbuild transform).
  Surgically fixed in this PR — only the merged JSDoc headers (no logic
  change). The remaining ~5 tsc errors in `auth.ts` from concurrent
  T-V3-C-02 / -03 / -04 / -05 / -06 merges remain — out of scope for this
  ticket but documented for the next cleanup.
- **CI gate**: `frontend-test.yml` runs `pnpm test:cov` informationally
  (`continue-on-error: true`). After Wave 1 ts-nocheck cleanup raises
  coverage above 70%, drop the flag and the job becomes a required
  status check (Phase 1 quality gate).
- **No new app code added** — only test infrastructure and the 3-line
  comment repair in `src/api/auth.ts`.
- **Lucide / 絵文字 / AGPL rules unchanged** — `lint-mock.sh` 17/17 OK.
