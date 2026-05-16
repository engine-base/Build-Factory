# T-FOUNDATION-02 audit — scripts/lint-mock-impl-diff.py (Gate #8 / lint #17 mock-impl-diff)

> Source: `docs/task-decomposition/2026-05-16_v3_phase0/tickets.json#T-FOUNDATION-02`
> Phase: Foundation / Wave: 0a / Group: A-1 / Label: NEW
> 3-tier AC を逐語コピー + impl line 記録. ADR-011 完了判定ゲート準拠.

---

## 概要

v3 Foundation Phase の **Gate #8 (UI gate / lint #17 mock-impl-diff)** を実装する.
mock HTML (`docs/mocks/2026-05-09_v1/*.html`) に埋め込まれた machine-readable meta
(`<meta name="screen-id|feature-id|task-ids|entities|phase">`) と、
対応する React 実装 (`frontend/src/screens/<screen-id>.tsx`) の JSDoc / `data-*` 属性 /
`?meta` import から抽出した meta を field-wise に diff し、drift をレポートする
スタンドアロン Python script.

依存ゼロ (stdlib `html.parser` のみ) で、`--self-test` で 4 fixture cases を一括検証.

---

## Tier 1: Structural

(tickets.json `acceptance_criteria.structural` 空配列 — Foundation lint script のため UI/mock 整合 AC は無し)

---

## Tier 2: Functional

### AC-1 (UBIQUITOUS)
> The system shall extract 5 meta fields (screen-id / feature-id / task-ids / entities / phase) from each mock HTML in --mock-dir

- impl: `scripts/lint-mock-impl-diff.py:51-113` (`META_FIELDS` 定数 L51 + `_MetaTagCollector` HTMLParser L86 + `extract_mock_meta()` L105)
- test: `scripts/tests/test-lint-mock-impl-diff.py::test_aligned_yields_no_drift` (`sorted(mock.keys()) == sorted(META_FIELDS)` で 5 件抽出を検証)

### AC-2 (EVENT-DRIVEN)
> When the impl file at <impl-dir>/screens/<screen-id>.tsx does not exist, the system shall record a drift entry with error: 'missing_in_impl' and severity: 'error'

- impl: `scripts/lint-mock-impl-diff.py:199-209` (`diff_one_screen()` 冒頭の `impl_meta is None` 分岐 → `kind="missing_in_impl"` / `severity="error"`) + `scripts/lint-mock-impl-diff.py:295-296` (scan 内で `impl_path.exists()` 判定)
- test: `scripts/tests/test-lint-mock-impl-diff.py::test_missing_impl_yields_error`

### AC-3 (EVENT-DRIVEN)
> When the meta value differs between mock and impl, the system shall record a drift entry {screen_id, field, mock_value, impl_value, severity: 'warning'}

- impl: `scripts/lint-mock-impl-diff.py:255-266` (`_normalize()` 比較で `value_mismatch` → `severity="warning"`)
- test: `scripts/tests/test-lint-mock-impl-diff.py::test_value_mismatch_yields_warning` (4 件 value_mismatch / 全て warning)

### AC-4 (OPTIONAL)
> Where the --strict flag is provided and drift count > 0, the system shall exit with code 1

- impl: `scripts/lint-mock-impl-diff.py:455-459` (`if args.strict and drifts: return 1`)
- test: `scripts/tests/test-lint-mock-impl-diff.py::test_strict_mode_exits_nonzero_on_drift` (subprocess で実 CLI を起動 / `returncode == 1` 検証)

### AC-5 (UNWANTED)
> If the mock HTML lacks a required meta field, the system shall record {screen_id, field, error: 'missing_in_mock'} and exit 1 (strict mode)

- impl: `scripts/lint-mock-impl-diff.py:212-240` (`diff_one_screen()` 内 `mock_v is None` 分岐 → `kind="missing_field_in_mock"` / `severity="error"`) — strict 時 `main()` L455-459 で exit 1
- test: `scripts/tests/test-lint-mock-impl-diff.py::test_missing_meta_in_mock_yields_error` (5 件 missing_field_in_mock / 全て error severity)

### AC-6 (STATE-DRIVEN)
> While --self-test is active, the system shall run 4 fixture cases (aligned / drifted / missing_impl / missing_meta) and exit 0 only if all match expectation

- impl: `scripts/lint-mock-impl-diff.py:310-378` (`_run_self_test()`) + `scripts/lint-mock-impl-diff.py:433-434` (`main()` の `args.self_test` 分岐)
- test: `scripts/tests/test-lint-mock-impl-diff.py::test_self_test_flag_runs_4_cases` (subprocess で `--self-test` を起動 / "ALL 4 CASES PASS" 文字列を確認)

---

## Tier 3: Regression

### R-1: python3 scripts/lint-mock-impl-diff.py --self-test PASS (4 fixture cases)
- 実行: `python3 scripts/lint-mock-impl-diff.py --self-test`
- 結果: **PASS** (exit 0)
  ```
  [self-test] aligned: PASS (0 drift)
  [self-test] drifted: PASS (4 value_mismatch drifts)
  [self-test] missing_impl: PASS (1 missing_in_impl error)
  [self-test] missing_meta: PASS (5 missing_field_in_mock error)

  [self-test] ALL 4 CASES PASS
  ```

### R-2: pyright --strict scripts/lint-mock-impl-diff.py 0 errors
- 実行: `pyrightconfig.tmp.json` で `strict: ["scripts/lint-mock-impl-diff.py"]` を指定し `pyright --project pyrightconfig.tmp.json`
- 結果: **PASS** (`0 errors, 0 warnings, 0 informations`)

### R-3: ruff check scripts/lint-mock-impl-diff.py 0 warnings
- 実行: `ruff check scripts/lint-mock-impl-diff.py scripts/tests/test-lint-mock-impl-diff.py`
- 結果: **PASS** (`All checks passed!`)

### R-4: bash scripts/pre-commit-check.sh PASS
- 実行: `bash scripts/pre-commit-check.sh --quick`
- 結果: 本タスク由来は全 **PASS**.
  - `lint-agpl` PASS / `lint-archive` PASS / `lint-secrets` PASS / `lint-no-langgraph` PASS
  - `lint-tickets` PASS (0 <= baseline 0)
  - `python-syntax` PASS (578 files)
  - `backend-smoke` SKIP (依存未インストール: `python-dotenv` — 本タスク非関連 / 環境問題)
  - `frontend-tsc` SKIP (`--quick` 指定)
  - `lint-emoji` 既存 baseline drift (44 件 / 全て `docs/mocks/2026-05-15_v3/` 配下 — 別タスク `b6d1ca6 v3 mocks B-09` 由来 / 本タスクのファイルは 0 件で `grep -E "lint-mock-impl-diff|fixtures/mock-impl-diff" => no violations in my files`)

### R-5: python3 scripts/validate-tickets.py PASS for this task entry
- 実行: `python3 scripts/validate-tickets.py`
- 結果: **PASS** (`Compliant tickets : 187 / OK: all tickets pass validation.`)
  - 本タスク (T-FOUNDATION-02) はまだ既存 `2026-05-09_v1/tickets.json` に存在しないが、`2026-05-16_v3_phase0/tickets.json` 側 schema (3-tier AC) で文法整合確認済み.

### R-6: audit_md_path に Tier 1-3 逐語
- 本ファイル (`docs/audit/2026-05-16_v3/T-FOUNDATION-02.md`) に Tier 1 / Tier 2 (AC-1〜AC-6 全 6 件) / Tier 3 (R-1〜R-6 全 6 件) を逐語コピー + impl line / 実行結果記載済.

---

## 設計判断ログ

### D-1: bs4 不採用 → stdlib `html.parser`
- 理由: `backend/pyproject.toml` に bs4 未収録. Foundation script は依存ゼロが望ましい (ADR-011 の単一ゲート性).
- 実装: `_MetaTagCollector(HTMLParser)` で `<meta name=... content=...>` のみ収集. 50 行未満.

### D-2: impl meta 抽出は JSDoc + data-attr の union (JSDoc 優先)
- 理由: 既存 `frontend/src/` には現状 meta 規約が無い → tsx 着手時に「JSDoc / data-attr のどちらでも書けば pass」と緩く運用開始. 将来 `?meta` vite plugin を導入したときも import 検出で互換.
- 実装: `_JSDOC_RE` (`* @screen-id S-001` 行末) + `_DATA_ATTR_RE` (`data-screen-id="S-001"`) + `_META_IMPORT_RE` (detect only).

### D-3: CSV 値の比較は順序非依存 (set 比較相当)
- 理由: `task-ids="T-001,T-002"` と `task-ids="T-002,T-001"` は意味的同等. 順序差を drift 扱いするとノイズ多発.
- 実装: `_normalize()` でカンマ含み値を sort + rejoin.

### D-4: drift kind = 6 種類
- `missing_in_impl` (impl ファイル不在 / error)
- `missing_field_in_impl` (impl にメタ無し / warning)
- `missing_field_in_mock` (mock にメタ無し / error — AC-5 直接対応)
- `value_mismatch` (両方ある値が異なる / warning — AC-3 直接対応)
- (将来用) `value_normalized_match` は対象外

---

## 着手記録
- 着手日: 2026-05-16
- 担当 session: subagent (T-FOUNDATION-02)
- branch: claude/T-FOUNDATION-02
- base: claude/debug-vercel-404-RTGcR

## 完了記録
- 完了日: 2026-05-16
- Decision: **DONE**
- 主成果物: `scripts/lint-mock-impl-diff.py` (463 行 / 0 lint warning / 0 pyright strict error)
- fixture: 4 件 (mock-aligned.html / mock-drifted.html / impl-aligned.tsx / impl-drifted.tsx)
- 補助: `scripts/tests/test-lint-mock-impl-diff.py` (6 pytest 関数 + standalone runner)

## ノート
- 既存 `frontend/src/screens/` ディレクトリは現状未存在 (43 mock に対し screen tsx 0 件). real-scan で 36 drift が検出されるが、これは Foundation phase 時点で想定どおりの drift であり、後続 task が UI 実装するときに段階解消される.
- Gate #8 (`ui-mock-impl-diff`) は本 script を CI workflow から `python3 scripts/lint-mock-impl-diff.py --strict` で呼ぶ. workflow 配線は別 task で実施.
