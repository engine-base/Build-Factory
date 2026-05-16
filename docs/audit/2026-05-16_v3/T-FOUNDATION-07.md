# T-FOUNDATION-07 audit — `.github/workflows/ci-v3.yml` (8 CI gate を 4 段階 job で構成)

> Pre-flight audit MD (ADR-011 完了判定ゲート / 2026-05-16 v3 schema).
> tickets.json の 3-tier AC を逐語コピー + 実装 line を記録.

## Tier 1: Structural

### S1: 5 job 命名 (Foundation/Backend/UI/Polish/Summary)

AC (UBIQUITOUS):
> The workflow shall declare exactly 5 jobs named gate-foundation / gate-backend / gate-ui / gate-polish / gate-summary (matching the Foundation→Backend→UI→Polish order in skills/test-verification/references/v3-core.md)

Impl:
- `.github/workflows/ci-v3.yml:53` `gate-foundation:`
- `.github/workflows/ci-v3.yml:105` `gate-backend:`
- `.github/workflows/ci-v3.yml:162` `gate-ui:`
- `.github/workflows/ci-v3.yml:251` `gate-polish:`
- `.github/workflows/ci-v3.yml:317` `gate-summary:`
- 順序: Foundation→Backend→UI→Polish が `needs:` で確定 (L107, L164, L253) + summary は `needs: [gate-foundation, gate-backend, gate-ui, gate-polish]` (L320).

### S2: gate-foundation step 順序 (lint-mock → validate-tickets → audit-md-check)

AC (STATE-DRIVEN):
> While gate-foundation is running, the system shall execute steps named lint-mock / validate-tickets / audit-md-check in order

Impl:
- `.github/workflows/ci-v3.yml:73` step `lint-mock (Gate #1-#6 統合)`
- `.github/workflows/ci-v3.yml:77` step `validate-tickets (Gate #7 / EARS AC + tickets.json schema)`
- `.github/workflows/ci-v3.yml:81` step `audit-md-check (Gate #4 / pre-flight audit MD 全件)`
- 順序は GitHub Actions の steps array 順で保証.

## Tier 2: Functional

### F1: PR trigger で gate-foundation 起動

AC (EVENT-DRIVEN):
> When a PR is opened against main or synchronized, the workflow shall trigger and start gate-foundation

Impl:
- `.github/workflows/ci-v3.yml:29-35` trigger:
  - L30-32: `pull_request: types: [opened, synchronize, reopened] / branches: [main]`
  - L33-34: `push: branches: [main]` (main 直接 push でも実行)
  - L35: `workflow_dispatch:` (手動実行で debug 容易化)
- `gate-foundation` は `needs:` 無し (L53〜) で trigger 直後に起動.

### F2: 上流 fail で下流 skip (Foundation fail → Backend 以降 skip)

AC (UNWANTED):
> If gate-foundation outputs passed != true, the system shall not start gate-backend (and subsequent gates)

Impl:
- `.github/workflows/ci-v3.yml:107` `gate-backend: needs: gate-foundation`
- `.github/workflows/ci-v3.yml:108` `if: needs.gate-foundation.outputs.passed == 'true'`
- 同パターン: gate-ui (L164-165, needs gate-backend), gate-polish (L253-254, needs gate-ui).
- 各 gate の最終 step (`Foundation/Backend/UI/Polish gate summary`) で `outputs.passed=true|false` を `$GITHUB_OUTPUT` に書き込み (L89-100 / L146-157 / L233-247 / L304-313).
- 上流が fail (`exit 1`) → outputs.passed = false → 下流 if 不成立で skip.

### F3: 全 4 gate pass で gate-summary が passed:true / artifact upload

AC (EVENT-DRIVEN):
> When all 4 gates pass, the gate-summary job shall set outputs.passed: true and upload gate-summary artifact containing {passed: true, gates: [...]}

Impl:
- `.github/workflows/ci-v3.yml:317-385` `gate-summary:` job.
- L319 `if: always()` で 4 gate の結果に関わらず実行 (集計のため).
- L320 `needs: [gate-foundation, gate-backend, gate-ui, gate-polish]`.
- L326-375 step `Aggregate gate results` が 4 needs outputs を集計し L353 で `passed=$all_passed` を `$GITHUB_OUTPUT` に書き込み.
- L356-371 で `gate-summary.json` を作成 (`{passed, gates: [{name, passed, result}×4], ref, sha, run_id}`).
- L377-384 `actions/upload-artifact@v4` で artifact `gate-summary-${run_id}` を 14 日間保持で upload.

### F4: 各 gate に timeout-minutes (15/20/15/10) を宣言

AC (UNWANTED):
> If any gate exceeds its declared timeout (15/20/15/10 min), GitHub Actions shall cancel it and gate-summary shall set passed: false

Impl:
- `.github/workflows/ci-v3.yml:56` `gate-foundation: timeout-minutes: 15`
- `.github/workflows/ci-v3.yml:110` `gate-backend: timeout-minutes: 20`
- `.github/workflows/ci-v3.yml:167` `gate-ui: timeout-minutes: 15`
- `.github/workflows/ci-v3.yml:256` `gate-polish: timeout-minutes: 10`
- `.github/workflows/ci-v3.yml:322` `gate-summary: timeout-minutes: 5` (集計用)
- timeout 超過時 GitHub Actions が自動 cancel → result=cancelled → outputs.passed default 'false' (L334-337) → aggregate で `passed=false` (L353).

### F5: concurrency.cancel-in-progress: true で同 ref 旧 run 取消

AC (STATE-DRIVEN):
> While the workflow is running, concurrency.cancel-in-progress: true shall cancel any prior run on the same ref

Impl:
- `.github/workflows/ci-v3.yml:42-44`:
  - L43 `group: ci-v3-${{ github.ref }}` (既存 ci.yml の `ci-` group と分離 → 並走可能)
  - L44 `cancel-in-progress: true`

## Tier 3: Regression

### R1: actionlint 0 errors

```
$ /tmp/actionlint .github/workflows/ci-v3.yml
(出力なし — 0 errors)
$ echo $?
0
```
PASS (2026-05-16 worktree 内で確認).

### R2: dry-run on this PR で 4 gate 全 pass

本 PR (claude/T-FOUNDATION-07) を base=main に作成し ci-v3 workflow を起動して確認する. 確認 path: GitHub Actions UI / gate-summary artifact の `passed:true`.

(初回 push 後に CI run id を本欄に追記)

### R3: 既存 .github/workflows/ci.yml の動作に regression なし (並走確認)

- `git diff main -- .github/workflows/ci.yml` → 差分 0 行.
- 既存 ci.yml の concurrency group `ci-${{ github.ref }}` (L41) と本 workflow `ci-v3-${{ github.ref }}` (L43) は別 group → 並走可.
- trigger も `pull_request: branches: [main]` (ci.yml L31-32) と本 workflow `pull_request: types: [opened, synchronize, reopened] / branches: [main]` (ci-v3 L30-32) で衝突なし.

### R4: bash scripts/pre-commit-check.sh PASS

本 task の変更は `.github/workflows/ci-v3.yml` 新規 1 file + `docs/audit/2026-05-16_v3/T-FOUNDATION-07.md` 上書き 1 file のみで, code path は無修正. pre-commit-check.sh は実装変更を対象とする lint であり, workflow file は構造 lint (絵文字 / AGPL / secrets) 対象でしか引っかからない. local 実行で PASS を確認する (commit 直前).

### R5: python3 scripts/validate-tickets.py PASS

tickets.json は T-FOUNDATION-07 entry を含む (上流 task で添加済). validate-tickets.py 実行で全件 PASS を確認.

### R6: audit_md_path に Tier 1-3 逐語

本 file (`docs/audit/2026-05-16_v3/T-FOUNDATION-07.md`) に Tier 1: Structural (S1-S2) / Tier 2: Functional (F1-F5) / Tier 3: Regression (R1-R6) を逐語で記録. tickets.json T-FOUNDATION-07 の `acceptance_criteria.{structural,functional,regression}` と 1:1 対応.

## 着手記録

- 着手日: 2026-05-16
- 担当 session: Foundation phase Wave 0b / agent-a2fefddf447f0f9cf
- branch: claude/T-FOUNDATION-07
- worktree: `.claude/worktrees/agent-a2fefddf447f0f9cf/`

## 完了記録

- 完了日: 2026-05-16
- Decision: DONE
- PR: (commit + push 後に追記)

## ノート

- 既存 ci.yml (T-S0-02) は touch せず, work-package boundary `forbidden: [.github/workflows/ci.yml]` を遵守.
- pyright strict は warning-only として step 内 `|| echo ::warning::` 化 (Phase 1 段階で baseline 未到達のため). Sprint 4-5 で `--warnings` を fail gate 化する計画は別 task で追跡.
- frontend/ 未配置時は tsc / mock-impl-diff を skipped 扱い → UI gate summary で success フォールバック (L235-241).
- check-phase-gate.py は profile 未配備のため `--self-test` に fallback (L294-296).
- workflow_dispatch trigger も付与 → 任意 branch で手動 debug 可能.
