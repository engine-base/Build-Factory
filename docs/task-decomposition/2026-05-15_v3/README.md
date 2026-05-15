# v3 Task Decomposition — Build-Factory

> **作成日**: 2026-05-15
> **目的**: v1 (2026-05-09) / v2 (2026-05-14) の 187 task 完走宣言で見落とされた **画面 drift 21 件 / API gap 8 件 / RLS 不足 28 件 / 確定 gap 4 件 / 怪しい 63 件 / audit MD 不在 36 件** を完全に潰す
> **方針**: 7 つの判断は最厳格 (spec 徹底) 側に固定。形式 done ではなく **mock 一致 + API 200 + RLS 適用 + test pass の 3-tier 全部 pass で初めて done**

## 何を変えたか (v1 / v2 → v3)

| 項目 | v1 / v2 | v3 |
|---|---|---|
| Done 定義 | test pass + lint pass (= regression のみ) | **structural + functional + regression の 3-tier 全部 pass** |
| AC schema | EARS 5 形式 のフラット配列 | EARS 5 形式を **structural / functional / regression に分類** |
| AUTH 方針 | 不明確 (Supabase Auth 丸投げが暗黙) | **REST API として `/api/auth/*` 実装** (ADR-013) |
| 命名 | `bf_` prefix と PascalCase 混在 | **PascalCase 対応 snake_case に統一** (ADR-014) |
| 既存 22 画面 | 「実装済」扱いで触らず | **全件 REFACTOR** (R-1〜R-4 適用) |
| RLS | 宣言 43 / 実装 15 | **43+ 必須 / 1 entity = 1 RLS policy task** |
| lint check | 16 件 (lint-mock.sh) | **19 件** (#17 mock-impl diff / #18 screens-API / #19 entity-table naming 追加) |
| 並列実行 | Slice × Wave 固定 8 群 | **依存 DAG から動的計算** |
| audit MD | 自動生成 116 件 + 手動 30 件 (内容ばらつき) | **全 task 手動執筆 / 3-tier 逐語マッピング必須** |

## 構成ファイル

| ファイル | 内容 |
|---|---|
| `README.md` (このファイル) | v3 全体の趣旨 |
| `ACCEPTANCE_CRITERIA_SCHEMA.md` | 3-tier AC の定義 (structural / functional / regression) |
| `tickets.json` | v3 全タスクのフラット配列 (約 120 件) |
| `DEPENDENCIES.md` | 依存 DAG / 並列グループ / Phase 1-2 分け |
| `decision_log.json` | 7 つの判断の根拠ログ |
| `migration_from_v1.md` | v1 187 task と v3 のマッピング (REUSE/REFACTOR/ARCHIVE/NEW 判定) |

## タスクグループ (10 群)

| Group | 内容 | 概算件数 |
|---|---|---:|
| **A. Infrastructure (Phase 0)** | lint #17-19 追加 / AC 3-tier validator / pyright strict 設定 / coverage 70% gate / ADR-013 (AUTH) / ADR-014 (命名) | 8 |
| **B. AUTH 完全実装** | S-001〜S-005 + API 5 endpoint + middleware + e2e tests (REST API として実装) | 15 |
| **C. DB スキーマ完成 + RLS** | PhaseGate / ScreenComponent / ArtifactVersion / UserKnowledgeNamespace 新規 + 28 件 RLS policy | 28 |
| **D. 重大 drift 修正** | S-006 root rewrite + S-036/040 h1 統一 + GET /api/accounts/{id}/dashboard 実装 | 5 |
| **E. 未実装 20 画面** | S-008/010/011/015/020/021/022/023/024/025/030/033/037/042/043 + 6 endpoint | 20 |
| **F. 既存 22 画面 REFACTOR** | R-1〜R-4 適用 (3-tier AC / mock-impl 一致 / RLS / pyright strict) | 22 |
| **G. 確定 gap 4 件** | T-008-04 / T-013-04b / T-007-03b / T-BTSTRAP-04 完了 | 4 |
| **H. 怪しい 63 件 検証 + audit retrofit 36 件** | v1 で done フラグが立った疑惑タスクの再検証 + audit MD 手動執筆 | 12 (集約) |
| **I. 余剰整理** | ai_employee_config / projects (legacy) / threads (legacy) / bf_features / bf_mocks の整理 | 5 |
| **J. 命名 migration** | bf_ prefix 廃止 (10 件のテーブル rename + ORM 修正) | 10 |
| 合計 | | **約 129** |

## Phase 分け

| Phase | 内容 | 必須 task |
|---|---|---|
| **Phase 0** | Infrastructure (新 lint / AC validator / ADR 起票) | Group A 全 8 件 |
| **Phase 1 (dogfood)** | 1 ユーザー 1 案件で運用開始できる最小セット | A + B + (C のうち重要 10) + D + E のうち 7 件 + F のうち 10 件 = 約 50 件 |
| **Phase 1.5** | Phase 1 の REFACTOR 完成 + 残り未実装画面 | F の残り + E の残り = 約 25 件 |
| **Phase 2 (公開)** | 全 RLS 完成 + 命名統一 + 余剰整理 + 全 audit MD 厳密化 | C の残り + I + J + H = 約 50 件 |

## 実装プロトコル (v3 版)

各 task 着手前に必ず以下を実施:

1. **Pre-flight**: `docs/audit/2026-05-15_v3/<TASK_ID>.md` を template から作成し、3-tier AC を埋める
2. **Implementation**: AC の各項目に対する impl 行範囲を audit MD に記録しながら実装
3. **Verification**:
   - `bash scripts/lint-mock.sh` (19/19 PASS)
   - `bash scripts/lint-mock-impl-diff.sh <SCREEN_ID>` (該当 screen の structural 一致)
   - `pytest backend/tests/test_<TASK_ID>*.py` (regression)
   - `pyright --strict` (regression)
4. **Audit completion**: audit MD の 3-tier 全項目を `[x]` に
5. **PR**: commit メッセージに 3-tier AC 該当行範囲を記載

## v3 リリース要件

- 全 ~129 task が 3-tier AC で done フラグ
- 全 task に手動 audit MD あり (auto-generated 禁止)
- 全 lint #1-19 PASS
- 全 screen で mock h1 == impl h1 (structural)
- 全 entity に RLS policy (functional)
- pyright strict 0 errors / coverage ≥ 70%

## 旧 docs との関係

- v1 (`docs/task-decomposition/2026-05-09_v1/`): legacy 参照用に保持
- v2 (`docs/task-decomposition/2026-05-14_v2/`): 縦スライス試行版、保持
- 既存 audit MD (`docs/audit/2026-05-13_v2/`): legacy 参照用に保持。v3 は `docs/audit/2026-05-15_v3/` に新設
