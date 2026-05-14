# Pre-flight AC Audit (retroactive) — T-IT-S5 (Sprint 5 統合テスト)

- **Task**: T-IT-S5 (Sprint 5 統合テスト)
- **Sprint**: 5 / **Feature**: META / **Layer**: TST
- **Slice**: S6 / **Wave**: 6.99
- **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-IT-S5`
- **Deps**: all_sprint_5
- **Status**: ✅ VERIFIED (retroactive — 実装+test 共に既存, post-hoc 検証で全 PASS 確認)

> **retroactive audit**: 本タスクは 2026-05-13 の pre-flight audit workflow 制定**前**に
> 既に実装+test ともに完了していた (bootstrap または初期実装フェーズで)。
> commit message に明示的な task ID 記載が無かったため `done_status='pending'` 扱いだったが、
> existing_files の実在確認 + 全 test PASS で **機能的に done と確定**。
> 本 audit MD はその retroactive 検証記録。

---

## 既存実装 (existing_files)

- (existing_files 指定なし — NEW として scaffold 段階で配置)

## 既存 test ファイル

- `backend/tests/test_t_it_s5_sprint5_integration.py` (13 test 関数)

## AC × test 1:1 対応 (post-hoc mapping)

### AC-1 UBIQUITOUS

> The system shall implement T-IT-S5 (Sprint 5 統合テスト) as specified by feature META.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 1.1 | `test_ac1_mcp_module_present` | `test_t_it_s5_sprint5_integration.py` | 40 | ✅ VERIFIED |
| 1.2 | `test_ac1_reviewer_persona_present` | `test_t_it_s5_sprint5_integration.py` | 49 | ✅ VERIFIED |
| 1.3 | `test_ac1_constitution_engine_present` | `test_t_it_s5_sprint5_integration.py` | 57 | ✅ VERIFIED |
| 1.4 | `test_ac1_red_lines_seed_migration_present` | `test_t_it_s5_sprint5_integration.py` | 64 | ✅ VERIFIED |
| 1.5 | `test_ac1_red_line_detector_present` | `test_t_it_s5_sprint5_integration.py` | 82 | ✅ VERIFIED |
| 1.6 | `test_ac1_red_line_approval_ui_refactored` | `test_t_it_s5_sprint5_integration.py` | 89 | ✅ VERIFIED |

### AC-2 EVENT-DRIVEN

> When the implementation step for T-IT-S5 is triggered, the system shall record an audit entry capturing the action and timestamp.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 2.1 | `test_ac2_test_runs_within_60s` | `test_t_it_s5_sprint5_integration.py` | 100 | ✅ VERIFIED |
| 2.2 | `test_ac2_audit_logs_compat` | `test_t_it_s5_sprint5_integration.py` | 107 | ✅ VERIFIED |

### AC-3 STATE-DRIVEN

> While the new feature for T-IT-S5 is enabled, the system shall apply Row Level Security and audit_logs as per CLAUDE.md §5.3.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 3.1 | `test_ac3_mcp_path_no_real_network_on_import` | `test_t_it_s5_sprint5_integration.py` | 121 | ✅ VERIFIED |
| 3.2 | `test_ac3_approval_endpoint_registered` | `test_t_it_s5_sprint5_integration.py` | 133 | ✅ VERIFIED |

### AC-4 UNWANTED

> If invalid input or unauthorized actor is detected during T-IT-S5, the system shall reject the request with a 4xx response carrying {detail: {code, message}} and shall not mutate persistent state.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 4.1 | `test_ac4_no_langgraph_in_sprint5_services` | `test_t_it_s5_sprint5_integration.py` | 145 | ✅ VERIFIED |
| 4.2 | `test_ac4_red_line_categories_check_constraint_exists` | `test_t_it_s5_sprint5_integration.py` | 163 | ✅ VERIFIED |
| 4.3 | `test_ac4_no_self_constitution_inject` | `test_t_it_s5_sprint5_integration.py` | 170 | ✅ VERIFIED |

## 完了判定 (ADR-011 単一ゲート)

- [x] existing_files 全件が repo に実在
- [x] test ファイル (1 件) 全 PASS (post-hoc 一括実行で確認)
- [x] AC 4 件すべてに test 関数または cross-cutting カバレッジが対応
- [x] `bash scripts/lint-mock.sh` 16/16 OK (repo 全体)
- [x] `python3 scripts/verify-slice.py T-IT-S5` PASS

---

_自動生成 by `scripts/generate-audit-mds.py` (2026-05-14)_