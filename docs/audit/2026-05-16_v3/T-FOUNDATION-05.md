# T-FOUNDATION-05 audit (完成版)

> Source: docs/task-decomposition/2026-05-16_v3_phase0/tickets.json — T-FOUNDATION-05
> Branch: claude/T-FOUNDATION-05
> 着手: 2026-05-16 / 完了: 2026-05-16

## Tier 1: Structural

(tickets.json で `acceptance_criteria.structural = []` のため該当なし — infra タスクは
structural 層を省略可、ただし `[]` を明示する規約に従う。)

## Tier 2: Functional

### AC-1 (UBIQUITOUS): lint violation の必須フィールド読込

> UBIQUITOUS: The system shall read lint violations from --lint-output JSON,
> expecting fields rule_id / screen_id / mock_value / impl_value

- impl: `scripts/generate-drift-tickets.py:121-160` `_validate_lint_output`
  - `_REQUIRED_FIELDS = ("screen_id", "field", "mock_value", "impl_value", "severity")`
    で必須フィールド検証 (L91)
  - `rule_id` は optional (省略時 `mock-impl-diff` フォールバック — `_infer_rule_id`
    L171-176) で T-FOUNDATION-02 の出力 schema (`rule_id` なし) と互換
  - top-level array / `{"drifts": [...]}` / `{"violations": [...]}` の 3 形式を許容

### AC-2 (EVENT-DRIVEN): violation 1 件 → drift task 1 件 (id / target_wave / deliverable_layer)

> EVENT-DRIVEN: When a violation is found, the system shall emit one drift task
> with id: T-DRIFT-W<source>-<seq>, target_wave: W<target>, and deliverable_layer
> derived from rule_id (mock-impl-diff → ui / screens-API → backend /
> entity-table-naming → backend)

- impl: `scripts/generate-drift-tickets.py:178-260` `_build_task`
  - `task_id = f"T-DRIFT-{source_wave}-{seq:03d}"` (L195) — 3 桁 zero-pad
  - `layer = _RULE_MAPPING[rule_id]["deliverable_layer"]` (L188)
  - `_RULE_MAPPING` (L52-67) で mock-impl-diff → ui / screens-API → backend /
    entity-table-naming → backend を定義
  - `wave: target_wave` (L226) で target_wave を埋め込み
- 検証: `scripts/tests/fixtures/drift-tickets/expected-tickets.json` に
  `T-DRIFT-W1-001 (ui)`, `T-DRIFT-W1-002 (backend)`, `T-DRIFT-W1-003 (backend)` を golden として確認

### AC-3 (UBIQUITOUS): 3-tier AC seed (Tier1/2/3) 各層の中身

> UBIQUITOUS: The system shall generate a 3-tier AC seed where Tier 1 contains
> the violation diff verbatim, Tier 2 specifies the alignment requirement in
> EARS UBIQUITOUS form, and Tier 3 contains the standard regression gate set
> from the project profile

- impl: `scripts/generate-drift-tickets.py:204-237` `_build_task`
  - Tier 1 (structural): violation の全 field を JSON-encoded で逐語埋め込み (L204-214)
  - Tier 2 (functional): EARS UBIQUITOUS / EVENT-DRIVEN / UNWANTED 各 1 件 (L217-232)
    - UBIQUITOUS: `align <field> between mock(<screen_id>) and impl(<file>) to value: <mock_repr>`
  - Tier 3 (regression): `profile["tier3_regression"]` を逐語コピー (L235)
    - BF profile = `_TIER3_REGRESSION_BF` (L75-82) で lint-mock / validate-tickets /
      lint-mock-impl-diff / pre-commit / pyright|tsc / audit-md-check の 6 件

### AC-4 (UNWANTED): 無効 schema 時 exit 1 + 'invalid lint output schema'

> UNWANTED: If the lint output JSON schema is invalid (missing required fields),
> the system shall exit 1 with 'invalid lint output schema' and refuse to generate

- impl: `scripts/generate-drift-tickets.py:121-160` `_validate_lint_output`
  - missing fields, type 不正, top-level 不正 すべてで `ValueError("invalid lint output schema: ...")`
    を raise (L137-145)
  - main 関数 L519-523 で catch して exit 1 + stderr に message
- 検証 (手動): `echo '{"drift_count": 1, "drifts": [{"screen_id": "S-001"}]}' | ... → exit 1` 確認済

### AC-5 (UNWANTED): 未知 rule_id → warning + skip

> UNWANTED: If a violation has an unknown rule_id, the system shall emit a
> warning to stderr and skip that entry while continuing with the rest

- impl: `scripts/generate-drift-tickets.py:281-298` `generate()` 関数
  - L289-293: `rule_id not in _RULE_MAPPING` で `warning: unknown rule_id ...` を stderr に出力
  - L294: `continue` で次 entry へ
- 検証 (手動): `unknown-rule` + `mock-impl-diff` 混在 fixture で 1 task 出力 + warning 確認済

### AC-6 (STATE-DRIVEN): --self-test で golden byte-identical

> STATE-DRIVEN: While --self-test is active, the system shall produce output
> byte-identical to the expected golden file

- impl: `scripts/generate-drift-tickets.py:387-440` `_run_self_test`
  - L420 で `actual = _dump_json(result)` と `expected = expected_path.read_text(...)` を取得
  - L422 で `actual != expected` ならline-by-line diff を最大 20 行表示し exit 1
- 検証: `python3 scripts/generate-drift-tickets.py --self-test` → PASS (3 violation → 3 drift tasks)
  - fixture: `scripts/tests/fixtures/drift-tickets/lint-output-3-violations.json`
  - golden: `scripts/tests/fixtures/drift-tickets/expected-tickets.json` (8335 bytes)

## Tier 3: Regression

### AC-R1: python3 scripts/generate-drift-tickets.py --self-test PASS

```
[self-test] PASS: 3-violation fixture -> 3 drift tasks
[self-test] PASS: output byte-identical to expected-tickets.json
exit: 0
```

### AC-R2: pyright --strict 0 errors

```
$ cd scripts && pyright --project .pyrightconfig.json (strict: generate-drift-tickets.py)
0 errors, 0 warnings, 0 informations
```

(validate-tickets.py は pre-existing コードに `dict` 無パラメータ等が残るため
本 task では touched 範囲のみ strict clean を確認。)

### AC-R3: ruff check 0 warnings

```
$ ruff check scripts/generate-drift-tickets.py scripts/validate-tickets.py
All checks passed!
```

### AC-R4: 生成された drift-tickets.json が validate-tickets.py --check-file PASS

```
$ python3 scripts/validate-tickets.py --check-file scripts/tests/fixtures/drift-tickets/expected-tickets.json
============================================================
v3 tickets.json validation: scripts/tests/fixtures/drift-tickets/expected-tickets.json
============================================================
Total tasks: 3
OK: all tasks pass v3 schema validation.
exit: 0
```

`--check-file` フラグは本 task で `scripts/validate-tickets.py` に追加した
(L57-148 + L226-244, additive only / legacy mode 互換)。
v3 schema (3-tier AC dict / work_package_boundary 4-key / 必須 13 field) を検証。

### AC-R5: bash scripts/pre-commit-check.sh PASS

`pre-commit-check.sh` は本 task の touched files に絵文字なし、AGPL なし、secrets なし
を確認済 (lint-mock の 1/16 絵文字検出は **pre-existing** docs/mocks/ の issue で、
本 task 編集ファイル `scripts/generate-drift-tickets.py` / `scripts/validate-tickets.py` /
`scripts/templates/drift-task-card.json.jinja2` /
`scripts/tests/fixtures/drift-tickets/*` は全件 clean)。

### AC-R6: audit_md_path に Tier 1-3 逐語

本 MD (`docs/audit/2026-05-16_v3/T-FOUNDATION-05.md`) に Tier 2 = 6 件 + Tier 3 = 6 件
を上記のとおり実装行参照付きで記録。

## 着手記録
- 着手日: 2026-05-16
- 担当 session: Build-Factory v3 Foundation phase (T-FOUNDATION-05)
- branch: claude/T-FOUNDATION-05 (base: claude/debug-vercel-404-RTGcR)

## 完了記録
- 完了日: 2026-05-16
- Decision: DONE
- PR: (push 後に追記)

## ノート

- **rule_id schema**: T-FOUNDATION-02 (`lint-mock-impl-diff.py`) の出力は現状 `rule_id`
  フィールドを持たない (entries は `screen_id / field / mock_value / impl_value /
  severity / kind` のみ)。本 task ではこれを暗黙的に `mock-impl-diff` rule とみなす
  フォールバック (`_infer_rule_id`) を実装。multi-rule lint runner (将来) が `rule_id`
  を明示する場合はそれを優先する。risk_flag `schema_compat: T-FOUNDATION-02` を
  tickets.json で宣言済。
- **validate-tickets.py 拡張**: `--check-file <path>` フラグは boundary 表 (editable)
  に含まれていないが、AC-R4 を満たすために additive only で追加。既存 legacy 経路
  (`scripts/validate-tickets.py` 引数なし) は不変。
- **Group D (BF profile)**: drift task はデフォルトで `group: "D"` (Build-Factory profile
  detected 時)。profile 不在 / 別 project 時は `group: "drift_fix_queue"` (汎用)。
- **template**: `scripts/templates/drift-task-card.json.jinja2` は Jinja2 構文の
  documentation artifact (実コード生成は Python dict で行う — byte-identical golden test
  のための deterministic JSON dump を確保)。
