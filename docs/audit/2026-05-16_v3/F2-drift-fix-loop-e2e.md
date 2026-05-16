# F2 audit — scripts/tests/test-drift-fix-loop-e2e.sh (drift fix loop end-to-end integration test)

> Source: Build-Factory v3 Phase 0 follow-up F2 (drift fix loop end-to-end 動作確認)
> Phase: Foundation follow-up / Group: C (integration test) / Label: NEW
> 3-tier AC を Tier 1 (structural: step 順序) / Tier 2 (functional: 異常系) /
> Tier 3 (regression: self-contained + shellcheck + fixture 互換) で記述する.
> ADR-011 完了判定ゲート (pre-commit-check.sh PASS) を最終ゲートとして遵守.

---

## 概要

T-02 (`scripts/lint-mock-impl-diff.py`) と T-05 (`scripts/generate-drift-tickets.py`) は
それぞれ self-test で fixture 検証済みだが、**両者を artificial drift で連結した
end-to-end 動作確認** (T-02 output schema == T-05 input schema, T-05 output が
v3 tickets.json として `validate-tickets.py --check-file` を通る) は本 task が初出.

主軸 3 (drift fix → drift fix queue 流し込み)
(`skills/integration/references/v3-core.md` 210-237 行) の汎用フローを
Build-Factory profile (Group D / BF tier3 regression set) 配下で 1 回通し、
output → input 互換性が崩れていないことを **CI から bash 1 発で検証可能** にする.

---

## Tier 1: Structural

> tickets.json `acceptance_criteria.structural` 相当 — integration test の **step 順序**
> を spec から逐語化 (改変禁止). 5 step の順序遵守を AC 化する.

### S-1: step 順序 (Setup → 1 → 2 → 3 → 4 → 5)

> UBIQUITOUS: The end-to-end test shall execute exactly 5 ordered steps:
> Setup (3 artificial drift fixtures) → Step 1 (lint-mock-impl-diff.py
> --output drift.json) → Step 2 (generate-drift-tickets.py --source-wave W1
> --target-wave W2 --output drift-tickets-W1.json) → Step 3
> (validate-tickets.py --check-file drift-tickets-W1.json) → Step 4
> (generated drift task field assertions) → Step 5 (cleanup via trap EXIT).

- impl: `scripts/tests/test-drift-fix-loop-e2e.sh`
  - Setup: L72-152 (3 fixture を `${MOCK_DIR}` / `${IMPL_DIR}/screens` に配置)
  - Step 1: L158-202 (`python3 scripts/lint-mock-impl-diff.py --mock-dir ... --output ...`)
  - Step 2: L208-242 (`python3 scripts/generate-drift-tickets.py --lint-output ... --output ...`)
  - Step 3: L248-264 (`python3 scripts/validate-tickets.py --check-file ...`)
  - Step 4: L274-330 (drift task field assertions: deliverable_layer / group / 3-tier AC)
  - Step 5: L336-339 (`trap cleanup EXIT` が L32-37 で登録)

### S-2: 3 artificial drift fixture の網羅 3 kind

> UBIQUITOUS: The Setup step shall produce exactly 3 drift kinds covering
> value_mismatch (drift A), missing_in_impl (drift B), missing_field_in_mock
> (drift C) so that each branch of `diff_one_screen()` in T-02 is exercised.

- impl:
  - drift A: mock S-001 (screen-id=S-001) + impl S-001.tsx (data-screen-id=S-002, 他 4 field 一致)
    → 1 件 `value_mismatch` on field `screen-id` (T-02 L257-266)
  - drift B: mock S-002 のみ (`${IMPL_DIR}/screens/S-002.tsx` 不存在)
    → 1 件 `missing_in_impl` on field `*` severity=error (T-02 L199-209)
  - drift C: mock S-003 (`phase` meta 欠落 / 他 4 meta あり) + impl S-003.tsx (全 5 meta)
    → 1 件 `missing_field_in_mock` on field `phase` severity=error (T-02 L230-241)
- 検証: Step 1 assertion (L181-200) で 3 件の `screen_id` / `field` / `kind` / `severity` を
  field-wise に検査.

---

## Tier 2: Functional

> 異常系 (drift 0 件 / schema invalid / validate-tickets fail) で integration test も
> 適切に fail することを保証する EARS AC.

### F-1 (UBIQUITOUS): output / input schema 互換性

> UBIQUITOUS: The end-to-end test shall consume T-02 output as T-05 input
> without any intermediate transformation, asserting that `drift_count: 3` in
> `drift.json` becomes `summary.total_tasks: 3` in `drift-tickets-W1.json`
> (one drift entry -> one drift task, sequential ids T-DRIFT-W1-001..003).

- impl: Step 2 assertion (L223-242):
  - `summary.total_tasks == 3` 検証
  - `ids == ["T-DRIFT-W1-001", "T-DRIFT-W1-002", "T-DRIFT-W1-003"]` 検証
  - `version == "v3"` / `source_wave == "W1"` / `target_wave == "W2"` 検証
- T-02 output schema (`{drift_count, drifts:[...]}`) と T-05 input schema
  (`_validate_lint_output()`: `drifts` key + 必須 5 field) が一致することを e2e で証明.

### F-2 (EVENT-DRIVEN): drift task field の整合性

> EVENT-DRIVEN: When the BF profile is detected, the generated drift task
> shall satisfy: deliverable_layer="ui", group="D", wave="W2",
> phase="Foundation", label="FIX", category="infra".

- impl: Step 4 assertion (L283-294):
  - `project == "Build-Factory"` (BF profile detection)
  - 各 task に対し `deliverable_layer == "ui"` (mock-impl-diff rule の既定 layer)
  - `group == "D"` (BF profile 既定)
  - `wave == "W2"` (target_wave 反映)
  - `phase == "Foundation"` / `label == "FIX"` / `category == "infra"`

### F-3 (UBIQUITOUS): 3-tier AC seed の存在

> UBIQUITOUS: Each generated drift task shall expose acceptance_criteria with
> >= 1 structural entry, >= 3 functional entries (UBIQUITOUS/EVENT-DRIVEN/
> UNWANTED), and >= 6 regression entries (BF tier3 regression set).

- impl: Step 4 assertion (L296-304):
  - `acceptance_criteria.structural` >= 1 件 (violation 逐語埋め込み)
  - `acceptance_criteria.functional` >= 3 件 (UBIQUITOUS/EVENT-DRIVEN/UNWANTED の 3 EARS form)
  - `acceptance_criteria.regression` >= 6 件 (`_TIER3_REGRESSION_BF` 全件)

### F-4 (UBIQUITOUS): 補助 field の整合 (files_changed / boundary / audit_md / branch)

> UBIQUITOUS: Each drift task shall include
> "frontend/src/screens/<screen_id>.tsx" in files_changed and
> work_package_boundary.editable, and shall declare
> audit_md_path="docs/audit/2026-05-16_v3/T-DRIFT-W1-NNN.md" and
> branch="claude/T-DRIFT-W1-NNN".

- impl: Step 4 assertion (L306-321)

### F-5 (UNWANTED): drift 0 件時の挙動

> UNWANTED: If the lint-mock-impl-diff step reports 0 drifts, the e2e test
> shall exit 1 from Step 1 with "drift_count expected 3, got 0".

- impl: Step 1 assertion (L174-179) で `drift_count != 3` なら `fail` 関数経由で
  `exit 1`. drift 0 件は drift_count=0 で trap し、`fail` が stderr に drift.json を
  ダンプして即 exit.

### F-6 (UNWANTED): schema invalid 時の挙動

> UNWANTED: If generate-drift-tickets.py rejects the drift.json with schema
> errors (e.g. missing required fields), the e2e test shall exit 1 from
> Step 2 via `set -euo pipefail` propagating the python3 non-zero exit.

- impl: L17 `set -euo pipefail` + Step 2 (L211-217) で `python3 ... || fail "..."`.
  `generate-drift-tickets.py` の `_validate_lint_output` (L121-160) が `ValueError`
  を raise → main の except (L568-570) で exit 1 を返し、`fail` が補足エラーで止める.

### F-7 (UNWANTED): validate-tickets fail 時の挙動

> UNWANTED: If validate-tickets.py --check-file does not print "OK: all tasks
> pass v3 schema validation.", the e2e test shall exit 1 from Step 3 and
> dump the validator log to stderr for diagnosis.

- impl: Step 3 assertion (L252-263):
  - `python3 ... --check-file ...` exit が非 0 → `fail` で log を stderr に流す
  - exit 0 でも `grep -q "OK: all tasks pass v3 schema validation."` で
    成功メッセージを再確認 → 不在なら `fail`

---

## Tier 3: Regression

> bash script として self-contained / shellcheck 0 warnings / 既存 fixture と互換.

### R-1: shellcheck 0 warnings

```
$ shellcheck scripts/tests/test-drift-fix-loop-e2e.sh
(no output)
$ echo $?
0
```

- 唯一の suppress 指示は L29 の `# shellcheck disable=SC2317` (trap で間接起動される
  `cleanup` 関数を unreachable と誤検出する false positive のみ).

### R-2: self-contained (依存ゼロで bash + python3 stdlib のみ)

- 使用コマンド: `bash`, `python3`, `mktemp`, `cat`, `mkdir`, `rm`, `cd`, `grep`, `chmod`, `trap`
- 全て POSIX / GNU coreutils 標準. 追加 install 不要.
- python3 は stdlib `json` のみ使用 (heredoc 内インライン).
- 既存 script (`scripts/lint-mock-impl-diff.py` / `scripts/generate-drift-tickets.py` /
  `scripts/validate-tickets.py`) を CLI 経由で呼び出すため、それらの依存条件
  (stdlib only) を継承.

### R-3: 既存 fixture 互換 (artificial drift と既存 self-test fixture が無干渉)

- 本 test は `mktemp -d` で `/tmp/drift-e2e-XXXXXX` に作業ディレクトリを作成し、
  `scripts/tests/fixtures/mock-impl-diff/` / `scripts/tests/fixtures/drift-tickets/`
  の既存 fixture には一切触れない.
- `trap cleanup EXIT` で正常 / 異常 / SIGINT いずれの終了でも tmp dir を削除
  (L32-37).
- 既存 self-test (`--self-test` 2 件) の結果に影響しない:
  ```
  $ python3 scripts/lint-mock-impl-diff.py --self-test  # 4 cases PASS
  $ python3 scripts/generate-drift-tickets.py --self-test  # 3-violation byte-identical PASS
  ```

### R-4: e2e test 自身が exit 0

```
$ bash scripts/tests/test-drift-fix-loop-e2e.sh
[drift-e2e] PASS: Fixtures created (3 drift scenarios)
[drift-e2e] step1 assertions: 3/3 PASS
[drift-e2e] PASS: Step 1: drift.json = 3 drifts (A=value_mismatch / B=missing_in_impl / C=missing_field_in_mock)
generated 3 drift task(s) -> /tmp/drift-e2e-XXXXXX/drift-tickets-W1.json (violations=3)
[drift-e2e] step2 id sequence: 3/3 PASS
[drift-e2e] PASS: Step 2: drift-tickets-W1.json = 3 drift tasks (T-DRIFT-W1-001..003)
[drift-e2e] PASS: Step 3: validate-tickets.py --check-file PASS (v3 schema valid)
[drift-e2e] step4 assertions: all PASS for 3 drift tasks
[drift-e2e] PASS: Step 4: drift task field assertions (Group D / target_wave W2 / 3-tier AC / boundaries)
[drift-e2e] tmp dir will be removed: /tmp/drift-e2e-XXXXXX

============================================================
[drift-e2e] ALL 5 STEPS PASS — drift fix loop end-to-end OK
============================================================
$ echo $?
0
```

### R-5: CI 組込みは別 task

`.github/workflows/ci-v3.yml` への `drift-loop-e2e` job 追加は **本 task の範囲外**
(T-07 で merged 済の ci-v3.yml に対し別 task で `continue-on-error: true` + 5 min
timeout 設定で追加予定). 本 task では bash script 本体のみ実装し、CI 配線は
追跡 task に委譲する.

---

## 設計判断ログ

### D-1: 3 drift シナリオの kind を意図的にずらす

`diff_one_screen()` の 3 main branch (missing_in_impl / value_mismatch /
missing_field_in_mock) を 1 fixture / 1 kind の対応で網羅. 各 fixture は
**1 件のみの drift** を生成するように meta を組み立てる:
- drift A: screen-id 1 field のみ divergent (他 4 field は impl と一致)
- drift B: impl tsx ファイル不存在 (field=`*` の 1 件のみ)
- drift C: mock の `phase` meta のみ欠落 (他 4 meta は両側存在 & 一致)

これにより `drift_count == 3` を厳密に assert でき、過剰 drift / 不足 drift
の双方を検出可能.

### D-2: BF profile auto-detection に依存

`generate-drift-tickets.py` の `--profile` 引数は default で
`skills/integration/references/profiles/build-factory.md` を指す.
本 test は default profile を使うことで Group D / project="Build-Factory" /
tier3_regression_BF を pull する経路を **本番と同じ条件** で検証する.

### D-3: heredoc 内 python での assertion (jq 不依存)

CI 環境で jq が常用可能とは限らないため、JSON 検査は `python3 - <<PY ... PY` で
heredoc inline 実行する. これにより:
- stdlib のみで完結 (jq の install 不要)
- error message を python の `f"..."` で柔軟に組み立てられる
- exit code (`sys.exit(1)`) と `set -e` 経由で `fail` 関数に確実に伝播

---

## 着手記録
- 着手日: 2026-05-16
- 担当 session: Build-Factory v3 Phase 0 follow-up F2 session
- branch: `claude/phase-0-follow-up-F2`
- base: main

## 完了記録
- 完了日: 2026-05-16
- Decision: **DONE**
- 主成果物: `scripts/tests/test-drift-fix-loop-e2e.sh` (single bash file)
- 補助: 本 audit MD (Tier 1-3 AC)
- PR: (push 後に追記)

## ノート

- **CI 配線 (drift-loop-e2e job)** は別 task. 本 task では bash 本体 + audit MD のみ.
  追跡 task は `drift-loop-e2e` job を `.github/workflows/ci-v3.yml` の
  `gate-summary` の後に `continue-on-error: true` で追加し、`pull_request` event 限定
  + 5 min timeout で動かす (regression に対する warn 扱い).
- **artificial drift 3 種は最小構成**. 将来 `screens-API` / `entity-table-naming`
  rule_id が T-02 出力に含まれるようになったら本 test を拡張して各 rule_id ごとに
  1 drift シナリオを追加する (現状 T-02 は `mock-impl-diff` rule のみ).
- **既存 self-test は不変**. 本 test は新規ファイル 1 件追加のみで、`scripts/`
  既存ファイルへの変更は 0.
