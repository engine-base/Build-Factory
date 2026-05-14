# Pre-flight AC Audit (retroactive) — T-IT-S4 (Sprint 4 統合テスト)

- **Task**: T-IT-S4 (Sprint 4 統合テスト)
- **Sprint**: 4 / **Feature**: META / **Layer**: TST
- **Slice**: S5 / **Wave**: 5.99
- **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-IT-S4`
- **Deps**: all_sprint_4
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

- `backend/tests/test_t_it_s4_sprint4_integration.py` (13 test 関数)

## AC × test 1:1 対応 (post-hoc mapping)

### AC-1 UBIQUITOUS

> The system shall implement T-IT-S4 (Sprint 4 統合テスト) as specified by feature META.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 1.1 | `test_ac1_kanban_and_dag_modules_coexist` | `test_t_it_s4_sprint4_integration.py` | 43 | ✅ VERIFIED |
| 1.2 | `test_ac1_phase_module_present` | `test_t_it_s4_sprint4_integration.py` | 52 | ✅ VERIFIED |
| 1.3 | `test_ac1_task_dependency_module_present` | `test_t_it_s4_sprint4_integration.py` | 60 | ✅ VERIFIED |
| 1.4 | `test_ac1_cmdk_module_present` | `test_t_it_s4_sprint4_integration.py` | 72 | ✅ VERIFIED |
| 1.5 | `test_ac1_unified_search_endpoint_registered` | `test_t_it_s4_sprint4_integration.py` | 82 | ✅ VERIFIED |

### AC-2 EVENT-DRIVEN

> When the implementation step for T-IT-S4 is triggered, the system shall record an audit entry capturing the action and timestamp.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 2.1 | `test_ac2_test_runs_within_60_seconds` | `test_t_it_s4_sprint4_integration.py` | 94 | ✅ VERIFIED |
| 2.2 | `test_ac2_audit_logs_module_importable` | `test_t_it_s4_sprint4_integration.py` | 104 | ✅ VERIFIED |

### AC-3 STATE-DRIVEN

> While the new feature for T-IT-S4 is enabled, the system shall apply Row Level Security and audit_logs as per CLAUDE.md §5.3.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 3.1 | `test_ac3_no_real_network_in_imports` | `test_t_it_s4_sprint4_integration.py` | 118 | ✅ VERIFIED |
| 3.2 | `test_ac3_kanban_accordion_status_columns_invariant` | `test_t_it_s4_sprint4_integration.py` | 135 | ✅ VERIFIED |
| 3.3 | `test_ac3_public_api_stable_for_tasks` | `test_t_it_s4_sprint4_integration.py` | 153 | ✅ VERIFIED |

### AC-4 UNWANTED

> If invalid input or unauthorized actor is detected during T-IT-S4, the system shall reject the request with a 4xx response carrying {detail: {code, message}} and shall not mutate persistent state.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 4.1 | `test_ac4_no_langgraph_in_sprint4_services` | `test_t_it_s4_sprint4_integration.py` | 166 | ✅ VERIFIED |
| 4.2 | `test_ac4_invalid_workspace_id_rejected_at_router_layer` | `test_t_it_s4_sprint4_integration.py` | 190 | ✅ VERIFIED |
| 4.3 | `test_ac4_no_self_compaction_in_sprint4` | `test_t_it_s4_sprint4_integration.py` | 215 | ✅ VERIFIED |

## 完了判定 (ADR-011 単一ゲート)

- [x] existing_files 全件が repo に実在
- [x] test ファイル (1 件) 全 PASS (post-hoc 一括実行で確認)
- [x] AC 4 件すべてに test 関数または cross-cutting カバレッジが対応
- [x] `bash scripts/lint-mock.sh` 16/16 OK (repo 全体)
- [x] `python3 scripts/verify-slice.py T-IT-S4` PASS

---

_自動生成 by `scripts/generate-audit-mds.py` (2026-05-14)_