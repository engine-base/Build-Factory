# Build-Factory Phase 0 (Foundation) タスク分解結果

> 作成日: 2026-05-16
> profile: `skills/task-decomposition/references/profiles/build-factory.md`
> output: `docs/task-decomposition/2026-05-16_v3_phase0/`

## サマリー

| metric | 値 |
|---|---|
| 総 task 数 | 8 |
| Group | A-1: 2 / A-2: 4 / A-3: 2 |
| カテゴリ | infra 8 |
| ラベル | NEW 8 |
| deliverable_layer | foundation 8 / backend 0 / ui 0 / polish 0 |
| 推定総工数 | 18h |
| 並列実時間 | ~7.5h (1 営業日内) |
| Wave 数 | 3 (0a / 0b / 0c) |
| Phase | Foundation 8 |

## Group 別タスク一覧

### Group A-1: Single-purpose scripts

| ID | タイトル | category | label | layer | est_hr | wave | depends_on |
|---|---|---|---|---|---:|---|---|
| T-FOUNDATION-01 | scripts/audit-md-check.sh (Gate #4) | infra | NEW | foundation | 1.5 | 0a-First | [] |
| T-FOUNDATION-02 | scripts/lint-mock-impl-diff.py (Gate #8) | infra | NEW | foundation | 2.5 | 0a-First | [] |

### Group A-2: Wave/Phase tooling scripts

| ID | タイトル | category | label | layer | est_hr | wave | depends_on |
|---|---|---|---|---|---:|---|---|
| T-FOUNDATION-03 | scripts/check-wave-mutex.py | infra | NEW | foundation | 2 | 0a-Second | [] |
| T-FOUNDATION-04 | scripts/wave-integration-report.py | infra | NEW | foundation | 2.5 | 0a-Second | [] |
| T-FOUNDATION-05 | scripts/generate-drift-tickets.py | infra | NEW | foundation | 2 | 0a-Second | [] |
| T-FOUNDATION-06 | scripts/check-phase-gate.py | infra | NEW | foundation | 2.5 | 0a-First | [] |

### Group A-3: CI workflows

| ID | タイトル | category | label | layer | est_hr | wave | depends_on |
|---|---|---|---|---|---:|---|---|
| T-FOUNDATION-07 | .github/workflows/ci-v3.yml | infra | NEW | foundation | 3 | 0b | [T-01, T-02, T-06] |
| T-FOUNDATION-08 | .github/workflows/auto-merge.yml | infra | NEW | foundation | 2 | 0c | [T-07] |

## 各タスクカード詳細

STEP 4 で出力済の 8 タスクカード全文を本ファイル末尾の `## タスクカード詳細` 配下に記載 (本リポジトリでは `docs/task-decomposition/2026-05-16_v3_phase0/tickets.json` に構造化 JSON として格納)。

### 着手前チェックリスト

各 task の着手前に以下を実行:

1. `cp docs/audit/2026-05-13_v2/_template.md docs/audit/2026-05-16_v3/T-FOUNDATION-NN.md`
2. tickets.json から該当 task の 3-tier AC を逐語コピーして `T-FOUNDATION-NN.md` に貼り付け
3. branch 作成: `git checkout -b claude/T-FOUNDATION-NN`
4. work_package_boundary.editable 配下のみ編集 (forbidden / readonly を尊重)
5. 実装完了後、3-tier AC を 1 つずつ確認しながら audit MD に impl line を記録
6. `bash scripts/<script>.sh --self-test` などで Tier 3 AC 全件 PASS 確認
7. PR 作成 → 既存 ci.yml 経由で merge (Phase 0 中は手動 / T-08 完成後は auto-merge)

### Wave 起動順序

1. **Wave 0a First (3 並列)**: T-FOUNDATION-01 / -02 / -06
2. **Wave 0a Second (3 並列)**: T-FOUNDATION-03 / -04 / -05
3. **Wave 0b (1 task)**: T-FOUNDATION-07 (Wave 0a 完了後)
4. **Wave 0c (1 task)**: T-FOUNDATION-08 (T-07 完了後)

## 関連ファイル

- 構造化 JSON: `tickets.json`
- 依存 DAG: `DEPENDENCIES.md`
- 判断ログ: `decision-log.json`
- audit MD templates: `docs/audit/2026-05-16_v3/T-FOUNDATION-01.md` 〜 `T-FOUNDATION-08.md`
