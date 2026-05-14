# Pre-flight AC Audit (retroactive) — T-IT-S2 (Sprint 2 統合テスト (M-27 chain x M-30 chain x 4 層 observability x Layer 2b cross-fea)

- **Task**: T-IT-S2 (Sprint 2 統合テスト (M-27 chain x M-30 chain x 4 層 observability x Layer 2b cross-feature))
- **Sprint**: 2 / **Feature**: META / **Layer**: TST
- **Slice**: S2 / **Wave**: 2.99
- **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-IT-S2`
- **Deps**: all_sprint_2
- **Status**: ✅ VERIFIED (retroactive — 実装+test 共に既存, post-hoc 検証で全 PASS 確認)

> **retroactive audit**: 本タスクは 2026-05-13 の pre-flight audit workflow 制定**前**に
> 既に実装+test ともに完了していた (bootstrap または初期実装フェーズで)。
> commit message に明示的な task ID 記載が無かったため `done_status='pending'` 扱いだったが、
> existing_files の実在確認 + 全 test PASS で **機能的に done と確定**。
> 本 audit MD はその retroactive 検証記録。

---

## 既存実装 (existing_files)

- ✅ `backend/services/intent_classifier.py`
- ✅ `backend/services/handoff_service.py`
- ✅ `backend/services/mid_term_layer.py`
- ✅ `backend/services/memory_pipeline.py`
- ✅ `backend/logging_config.py`
- ✅ `backend/sentry_config.py`
- ✅ `backend/uptime_heartbeat.py`

## 既存 test ファイル

- `backend/tests/test_t_it_s2_sprint2_integration.py` (20 test 関数)

## AC × test 1:1 対応 (post-hoc mapping)

### AC-1 UBIQUITOUS

> The system shall provide `backend/tests/test_t_it_s2_sprint2_integration.py` verifying cross-feature integration of Sprint 2 deliverables: (a) M-27 chain (intent_classifier → handoff_service), (b) M-30 chain (mid_term_layer ↔ memory_pipeline), (c) 4-layer observability coexistence (logging_config + sentry_config + uptime_heartbeat without conflicts), (d) Layer 2b LiteLLM config integrity. Existing unit tests SHALL NOT be modified (REUSE).

| # | note | status |
|---|---|---|
| 1.1 | この AC 専用の test 関数は明示的に名付けられていない (汎用 test 群でカバー) | 🟡 IMPLICIT |

### AC-2 EVENT-DRIVEN

> When the integration test runs, it shall execute scenarios that span 2+ modules per assertion, simulating real call sequences (classify → handoff / record_summary → latest_summary / configure_structlog while sentry init in same process). Each scenario shall complete within 2 seconds.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 2.1 | `test_m27_chain_classify_then_handoff_emits_two_audit_events` | `test_t_it_s2_sprint2_integration.py` | 119 | ✅ VERIFIED |

### AC-3 STATE-DRIVEN

> While the integration test runs, the system shall NOT make real network calls (all external IO must be mocked via monkeypatch), shall NOT write to the audit_logs DB (capture via fake_emit), and shall preserve module state via pytest fixtures (reset_for_tests / clear_context after each test).

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 3.1 | `test_m30_chain_section_keys_invariant_holds_cross_module` | `test_t_it_s2_sprint2_integration.py` | 214 | ✅ VERIFIED |

### AC-4 UNWANTED

> If any Sprint 2 module's public API breaks (function signature change / removed symbol), the integration test shall fail with a clear error message identifying the broken contract. The test SHALL NOT depend on external services (LiteLLM container / Sentry SaaS / Better Stack) and SHALL NOT contain hardcoded secrets.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 4.1 | `test_no_real_http_calls_in_session` | `test_t_it_s2_sprint2_integration.py` | 399 | ✅ VERIFIED |
| 4.2 | `test_no_audit_logs_db_write_during_observability_init` | `test_t_it_s2_sprint2_integration.py` | 411 | ✅ VERIFIED |
| 4.3 | `test_no_external_service_dependency_in_tests` | `test_t_it_s2_sprint2_integration.py` | 452 | ✅ VERIFIED |

## AC 未紐付 test (cross-cutting / regression)

- `test_m27_chain_classify_top_signal_can_drive_handoff_target` (`test_t_it_s2_sprint2_integration.py:156`)
- `test_m27_chain_handoff_unknown_persona_does_not_break_classify` (`test_t_it_s2_sprint2_integration.py:175`)
- `test_m30_chain_modules_import_without_error` (`test_t_it_s2_sprint2_integration.py:203`)
- `test_observability_4_layers_coexist_without_conflict` (`test_t_it_s2_sprint2_integration.py:243`)
- `test_observability_logger_does_not_call_sentry_or_audit` (`test_t_it_s2_sprint2_integration.py:260`)
- `test_observability_sentry_does_not_call_logger_or_audit` (`test_t_it_s2_sprint2_integration.py:271`)
- `test_observability_uptime_does_not_call_logger_or_audit` (`test_t_it_s2_sprint2_integration.py:281`)
- `test_observability_audit_emit_still_works_after_init` (`test_t_it_s2_sprint2_integration.py:318`)
- `test_litellm_config_yaml_loads` (`test_t_it_s2_sprint2_integration.py:346`)
- `test_litellm_in_docker_compose_uses_profile` (`test_t_it_s2_sprint2_integration.py:356`)
- `test_main_path_does_not_import_litellm_proxy` (`test_t_it_s2_sprint2_integration.py:365`)
- `test_each_scenario_completes_within_2_seconds` (`test_t_it_s2_sprint2_integration.py:377`)
- `test_sprint2_public_api_surface_stable` (`test_t_it_s2_sprint2_integration.py:434`)
- `test_tickets_t_it_s2_ac_concretized` (`test_t_it_s2_sprint2_integration.py:471`)
- `test_tickets_t_it_s2_has_adr_link_and_existing_files` (`test_t_it_s2_sprint2_integration.py:490`)

## 完了判定 (ADR-011 単一ゲート)

- [x] existing_files 全件が repo に実在
- [x] test ファイル (1 件) 全 PASS (post-hoc 一括実行で確認)
- [x] AC 4 件すべてに test 関数または cross-cutting カバレッジが対応
- [x] `bash scripts/lint-mock.sh` 16/16 OK (repo 全体)
- [x] `python3 scripts/verify-slice.py T-IT-S2` PASS

---

_自動生成 by `scripts/generate-audit-mds.py` (2026-05-14)_