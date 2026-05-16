# T-FOUNDATION-04 audit

> tickets.json (`docs/task-decomposition/2026-05-16_v3_phase0/tickets.json`) の 3-tier AC を逐語コピーし、implementation line / 実行結果を付記。

## Tier 1: Structural

- **STATE-DRIVEN: While rendering Markdown, the system shall include the sections defined in skills/integration/references/v3-core.md Wave Integration Report スキーマ (概要 / auto-merge 集計 / 連続失敗の原因分析 / drift 検出 / 統合先 git state)**
  - impl: `scripts/templates/wave-integration-report.md.jinja2` で 5 セクションを順序固定で出力。`# Wave Integration Report` H1 / `## 概要` / `## auto-merge 集計 (4 カテゴリ × deliverable category)` (4 行 table) / `## 連続失敗の原因分析` / `## drift 検出 (drift fix queue 行き)` / `## 統合先 git state` を v3-core.md §119 スキーマと文字列レベルで一致 (golden で固定化)。
  - evidence: `scripts/tests/fixtures/wave-report/expected-small.md` (30 行) / `scripts/tests/fixtures/wave-report/expected-large.md` (41 行) の grep PASS。

## Tier 2: Functional

- **UBIQUITOUS: The system shall categorize each task into exactly one of {auto-merged / retried / escalated / rolled-back} based on branch-package.json.final_state**
  - impl: `scripts/wave-integration-report.py::_normalize_task` で `final_state` を `VALID_STATES = ("auto-merged", "retried", "escalated", "rolled-back")` に正規化。alias map で旧 `merged` / `rolled_back` も吸収。未知値は escalated 扱い + stderr warning。
  - evidence: `large-30task.json` で 4 状態混在 (auto-merged=23 / retried=4 / escalated=2 / rolled-back=1) を golden 一致で確認。

- **UBIQUITOUS: The system shall sum task counts by deliverable_layer field (foundation / backend / ui / polish)**
  - impl: `aggregate()` で `layer_counts` (Foundation / Backend / UI / Polish / Drift fix) を集計。`drift-fix` alias も吸収。
  - evidence: large fixture の Foundation=2 / Backend=12 / UI=10 / Polish=4 / Drift fix=2 を golden で固定。

- **EVENT-DRIVEN: When a task has failure_count >= 3, the system shall include it in the failure analysis section with gate ID and error reason**
  - impl: `aggregate()` で `task.failure_count >= FAILURE_THRESHOLD (=3)` の task を `failure_analysis` リストに収集。template が gate ID と reason を逐語出力。
  - evidence: large fixture の T-B-08 (4) / T-U-06 (3) / T-B-11 (5) が 3 件として失敗分析 section に出る (golden line 21-26 で固定)。

- **EVENT-DRIVEN: When drift entries exist in <branch-packages>/_drift.json, the system shall include drift count by rule_id; when the file is absent, the system shall report drift = 0 with a stderr warning**
  - impl: directory mode では `<dir>/_drift.json` を別読み。file mode では wrapper の `drift` field を使う。`aggregate()` で `rule_counts` を集計し、無ければ `print(..., file=sys.stderr)` で warning。
  - evidence: large fixture: 3 rule_id (lint-mock-1-emoji=3 / lint-mock-8-domain-boundaries=1 / ears-ac-missing-unwanted=1) を golden 化。small fixture: `drift = null` → stderr warning + 「drift 検出無し」表示を golden で固定。

- **OPTIONAL: Where --format json is provided, the system shall emit the same data as JSON instead of Markdown**
  - impl: `render_json(ctx)` で同 context を indent=2 / ensure_ascii=False の JSON dump。15 keys 含む (`version` / `skill` / `wave_id` / `layer_counts` / `state_layer` / `failure_analysis` / `drift_rows` 等)。
  - evidence: `python3 scripts/wave-integration-report.py --wave W0a --branch-packages scripts/tests/fixtures/wave-report/small-3task.json --format json | jq keys` で 15 key 確認 (手動 smoke)。

- **STATE-DRIVEN: While --self-test is active, the system shall verify 2 fixture cases produce reports byte-identical to expected goldens**
  - impl: `run_self_test()` で fixture 2 件 (`small-3task.json` / `large-30task.json`) を順に render → `expected-small.md` / `expected-large.md` と `str ==` 比較。差分時は `_show_diff` で expected/actual の最初の 20 行を表示し exit 1。
  - evidence: `python3 scripts/wave-integration-report.py --self-test` → `self-test: OK (2/2)` (byte-identical 856B / 1476B)。

## Tier 3: Regression

- **python3 scripts/wave-integration-report.py --self-test PASS (2 fixtures)** — PASS (`self-test: OK (2/2)`、small=856 bytes / large=1476 bytes)
- **pyright --strict 0 errors** — PASS (`pyright -p pyrightconfig_wave.json` で `0 errors, 0 warnings, 0 informations`)
- **ruff check 0 warnings** — PASS (`ruff check scripts/wave-integration-report.py` → `All checks passed!`)
- **bash scripts/pre-commit-check.sh PASS** — SKIP-WITH-REASON: lint-emoji baseline (0 → 44) が base branch (`claude/debug-vercel-404-RTGcR` および main) 時点で既に違反しており本 task 範囲外。他項目 (lint-agpl / lint-archive / lint-secrets / lint-no-langgraph / lint-tickets / python-syntax) は PASS、backend-smoke / frontend-tsc は依存未インストールで SKIP。
- **python3 scripts/validate-tickets.py PASS** — PASS (`Total tickets : 187 / Tickets with issues : 0 / Compliant tickets : 187 / OK: all tickets pass validation.`)
- **audit_md_path に Tier 1-3 逐語** — PASS (本 file)

## 着手記録
- 着手日: 2026-05-16
- 担当 session: Build-Factory v3 Foundation phase / T-FOUNDATION-04
- branch: claude/T-FOUNDATION-04

## 完了記録
- 完了日: 2026-05-16
- Decision: DONE
- PR: (base = `claude/debug-vercel-404-RTGcR`, push 後 URL を記録)

## ノート
- Jinja2 (`jinja2==3.1.6`) を採用。既存 `scripts/templates/phase-gate-decision.json.jinja2` で先行例があり、依存追加コスト無し。
- branch-package.json schema は柔軟対応:
  - directory mode (`<dir>/*.json` glob, `_drift.json` 任意) と consolidated wrapper file mode の両方をサポート。
  - `final_state` 欠落 / 旧 alias (`merged` / `rolled_back`) も吸収。
- `--self-test` golden は `str ==` の byte-identical 比較。template / aggregate ロジック修正時は golden の再生成が必要 (`python3 scripts/wave-integration-report.py --wave <id> --branch-packages <fixture> --output <golden>`)。
- T-FOUNDATION-05 (`scripts/generate-drift-tickets.py`) との schema interlock: `_drift.json` の `entries[]` には `rule_id` (str) を必須とし、`fix_task` (str) を任意で持つ。T-05 側で出力構造が確定したら本 script の `aggregate()` 互換性を再確認すること (risk_flag に明記済み)。
- `_infer_next_wave()` の alphabetic 末尾 increment は `W0a → W0b` / `W1 → W2` を期待した heuristic。fixture の wrapper に `next_wave` field を明示すれば override 可能。
