# Phase 0 (Foundation) Dependencies / Wave Plan

> Build-Factory v3 Foundation 整備 / 8 CI gate + auto-merge 基盤を 8 task に分解。BF profile 適用。

## 物量

| 指標 | 値 |
|---|---|
| 総 task 数 | 8 |
| 総工数 | 18 時間 |
| 並列セッション換算 | 8 |
| 並列実行時の実時間 | ~7.5 時間 (1 営業日内) |
| 並列度 (Wave 0a) | 6 |
| 並列度 (Wave 0b, 0c) | 1 |

## Wave 構成

| Wave | 内容 | Group | deliverable_layer | 並列度 | 所要 |
|---|---|---|---|---:|---|
| 0a | A-1 + A-2 single-purpose & tooling scripts | A-1, A-2 | foundation | 6 | 2.5h |
| 0b | A-3a CI workflow (ci-v3.yml) | A-3 | foundation | 1 | 3h |
| 0c | A-3b auto-merge workflow | A-3 | foundation | 1 | 2h |

## Wave 0a 内 priority (起動順序)

オーケストレータが session を起動する順:

1. **First wave (3 並列)**: T-01 / T-02 / T-06 — T-07 が依存する 3 件、最優先
2. **Second wave (3 並列)**: T-03 / T-04 / T-05 — T-07 は依存しないが Phase 1 開始時に必要

T-07 開始までの待ち時間を最小化 (T-01/02/06 完成 → 即 T-07 start)。

## 依存 DAG (簡略)

```
[Wave 0a: A-1 + A-2 / 6 並列]
  T-FOUNDATION-01 (audit-md-check.sh)       ─┐  (First, T-07 ブロッカー)
  T-FOUNDATION-02 (lint-mock-impl-diff.py)  ─┤  (First, T-07 ブロッカー)
  T-FOUNDATION-06 (check-phase-gate.py)     ─┤  (First, T-07 ブロッカー)
  T-FOUNDATION-03 (check-wave-mutex.py)     ─┤  (Second)
  T-FOUNDATION-04 (wave-integration-report) ─┤  (Second)
  T-FOUNDATION-05 (generate-drift-tickets)  ─┘  (Second)
                                             │
                                             ↓
[Wave 0b: A-3a / 1 task]                    │
  T-FOUNDATION-07 (ci-v3.yml)               │  depends_on: T-01, T-02, T-06
                                             │
                                             ↓
[Wave 0c: A-3b / 1 task]                    │
  T-FOUNDATION-08 (auto-merge.yml)          │  depends_on: T-07
                                             │
                                             ↓
                            [Phase 0 完成 / Phase 1 解禁]
```

## ブロッキングタスク

| タスクID | タスク名 | ブロックする範囲 |
|---|---|---|
| T-FOUNDATION-01 | audit-md-check.sh | T-07 (gate-foundation step) |
| T-FOUNDATION-02 | lint-mock-impl-diff.py | T-07 (gate-ui step) |
| T-FOUNDATION-06 | check-phase-gate.py | T-07 (gate-polish step) |
| T-FOUNDATION-07 | ci-v3.yml | T-08 (gate-summary artifact 依存) |
| T-FOUNDATION-08 | auto-merge.yml | Phase 1 全 task (auto-merge 本体) |

T-03/T-04/T-05 は本 Phase 0 段階では誰もブロックしない。Phase 1 開始前に完成必要。

## 互換性チェックポイント

| 関係 | 確認内容 |
|---|---|
| T-04 ↔ T-05 | drift entry の field 名 (`rule_id` / `screen_id` / `mock_value` / `impl_value` / `count`) が両 script で一致 |
| T-02 ↔ T-05 | T-02 出力 (drift.json) を T-05 が消費するため schema 完全一致 |
| T-06 ↔ T-04 | T-04 出力 (Wave Integration Report MD) を T-06 が evidence として参照可能 |
| T-07 ↔ T-01/02/06 | ci-v3.yml の各 step が呼び出す script の引数仕様一致 |
| T-08 ↔ T-07 | auto-merge.yml が download する artifact 名 (`gate-summary`) が一致 |

## file-level mutex (全 Wave 通し / 衝突ゼロ)

| Wave | task | editable boundary |
|---|---|---|
| 0a | T-01 | `scripts/audit-md-check.sh` + `scripts/tests/fixtures/audit-md-*.md` |
| 0a | T-02 | `scripts/lint-mock-impl-diff.py` + `scripts/tests/fixtures/mock-impl-diff/*` |
| 0a | T-03 | `scripts/check-wave-mutex.py` + `scripts/tests/fixtures/wave-mutex/*` |
| 0a | T-04 | `scripts/wave-integration-report.py` + `scripts/templates/wave-integration-report.md.jinja2` + `scripts/tests/fixtures/wave-report/*` |
| 0a | T-05 | `scripts/generate-drift-tickets.py` + `scripts/templates/drift-task-card.json.jinja2` + `scripts/tests/fixtures/drift-tickets/*` |
| 0a | T-06 | `scripts/check-phase-gate.py` + `scripts/templates/phase-gate-decision.json.jinja2` + `scripts/tests/fixtures/phase-gate/*` |
| 0b | T-07 | `.github/workflows/ci-v3.yml` |
| 0c | T-08 | `.github/workflows/auto-merge.yml` |

全 8 task の editable boundary が完全分離 → conflict 事前防止 OK。`scripts/check-wave-mutex.py --self-test` 本 Phase 0 を 1 fixture として使える (self-validation)。

## CI gate (Phase 0 中の暫定運用)

T-07 (ci-v3.yml) 完成まで **既存 ci.yml + license-check.yml + scripts/pre-commit-check.sh** で守る:

| 暫定 Gate | 実行 | 該当 task の Tier 3 AC |
|---|---|---|
| existing ci.yml (pytest cov + smoke) | 既存 | AC-R5 (pre-commit-check) |
| license-check.yml (AGPL + ADR-010) | 既存 | (該当なし、本 task 群は全 MIT/BSD) |
| pyright strict (touched files) | 既存 | AC-R2 |
| ruff check (touched files) | 既存 | AC-R3 |
| ShellCheck (sh files) | T-01 のみ手動 | AC-R2 (T-01) |
| actionlint (workflow files) | T-07/T-08 のみ手動 | AC-R1 (T-07/T-08) |
| validate-tickets.py | 既存 | AC-R5 |
| self-test (per script) | 各 task 内 | AC-R1 |

T-07 完成後は **ci-v3.yml + ci.yml 並走**、T-08 完成後は **Phase 1 から auto-merge 発動**。

## 失敗時の retry プロトコル

1. CI が PR コメントに失敗内容を貼る (既存 ci.yml or 完成後の ci-v3.yml)
2. orchestrator (Phase 0 = human / Phase 1 から = 自動) が retry session 起動
3. **連続 3 失敗で human エスカ** (BF profile 既定 / T-08 完成後は label `needs-human-review` で自動付与)

Phase 0 段階では T-08 がまだ存在しないため、human エスカは手動。

## Phase 0 完了判定

- 8 task 全件 merge 済 (Phase 0 PR は既存 ci.yml で merge / T-08 完成後の Phase 1 から auto-merge)
- `python3 scripts/check-phase-gate.py --phase foundation` exit 0
- `phase-gate-decision.json` に `Foundation → Backend: OPEN_GATE` が記録される
