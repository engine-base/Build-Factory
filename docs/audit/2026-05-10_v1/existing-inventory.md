# T-S0-13: 既存実装インベントリ監査結果

- 走査対象: routers=39, services=54, migrations=7
- 分類サマリ: {'REFACTOR': 91, 'UNDETERMINED': 5, 'REUSE': 4}
- Orphan tickets (listed file 不在): 4 件
- Phase boundary annotation: 5 件

## 分類別ファイル一覧

### REFACTOR (91 件)

- `backend/routers/account_settings.py` — REFACTOR ラベルのチケット T-023-01 (F-023) で参照
- `backend/routers/accounts.py` — REFACTOR ラベルのチケット T-004-01 (F-004) で参照
- `backend/routers/ai_system.py` — REFACTOR ラベルのチケット T-022-03 (F-022) で参照
- `backend/routers/approval.py` — REFACTOR ラベルのチケット T-012-02 (F-012) で参照
- `backend/routers/artifacts.py` — REFACTOR ラベルのチケット T-003-05 (F-003) で参照
- `backend/routers/chat.py` — REFACTOR ラベルのチケット T-M30-01 (M-30) で参照
- `backend/routers/dashboard.py` — REFACTOR ラベルのチケット T-008-01 (F-008) で参照
- `backend/routers/design_frames.py` — REFACTOR ラベルのチケット T-005b-01 (F-005b) で参照
- `backend/routers/design_mocks.py` — REFACTOR ラベルのチケット T-005b-01 (F-005b) で参照
- `backend/routers/design_pipeline.py` — REFACTOR ラベルのチケット T-005b-02 (F-005b) で参照
- `backend/routers/documents.py` — REFACTOR ラベルのチケット T-016-01 (F-016) で参照
- `backend/routers/employees.py` — REFACTOR ラベルのチケット T-022-03 (F-022) で参照
- `backend/routers/estimate.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/routers/hearing.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/routers/knowledge_actions.py` — REFACTOR ラベルのチケット T-024-02 (F-024) で参照
- `backend/routers/knowledge_search.py` — REFACTOR ラベルのチケット T-024-02 (F-024) で参照
- `backend/routers/llm.py` — REFACTOR ラベルのチケット T-020-02 (F-020) で参照
- `backend/routers/llm_providers.py` — REFACTOR ラベルのチケット T-020-02 (F-020) で参照
- `backend/routers/mcp_server.py` — REFACTOR ラベルのチケット T-010a-01 (F-010a) で参照
- `backend/routers/pricing_design.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/routers/proposal.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/routers/records.py` — REFACTOR ラベルのチケット T-016-01 (F-016) で参照
- `backend/routers/references.py` — REFACTOR ラベルのチケット T-024-02 (F-024) で参照
- `backend/routers/requirements.py` — REFACTOR ラベルのチケット T-005-03 (F-005) で参照
- `backend/routers/reviewer.py` — REFACTOR ラベルのチケット T-011-01 (F-011) で参照
- `backend/routers/secretary.py` — REFACTOR ラベルのチケット T-003-02 (F-003) で参照
- `backend/routers/secretary_stream.py` — REFACTOR ラベルのチケット T-003-02 (F-003) で参照
- `backend/routers/skill_creator.py` — REFACTOR ラベルのチケット T-002-01 (F-002) で参照
- `backend/routers/skills.py` — REFACTOR ラベルのチケット T-002-01 (F-002) で参照
- `backend/routers/slot_admin.py` — REFACTOR ラベルのチケット T-005-02 (F-005) で参照
- `backend/routers/staff.py` — REFACTOR ラベルのチケット T-022-03 (F-022) で参照
- `backend/routers/tasks.py` — REFACTOR ラベルのチケット T-006-02 (F-006) で参照
- `backend/routers/template_builder.py` — REFACTOR ラベルのチケット T-015-01 (F-015) で参照
- `backend/routers/threads.py` — REFACTOR ラベルのチケット T-M30-01 (M-30) で参照
- `backend/routers/uploads.py` — REFACTOR ラベルのチケット T-016-01 (F-016) で参照
- `backend/routers/workflows.py` — REFACTOR ラベルのチケット T-010c-01 (F-010c) で参照
- `backend/routers/workspaces.py` — REFACTOR ラベルのチケット T-003-02 (F-003) で参照
- `backend/services/account_service.py` — REFACTOR ラベルのチケット T-004-01 (F-004) で参照
- `backend/services/account_settings_service.py` — REFACTOR ラベルのチケット T-004-01 (F-004) で参照
- `backend/services/artifact_export.py` — REFACTOR ラベルのチケット T-015-01 (F-015) で参照
- `backend/services/artifact_service.py` — REFACTOR ラベルのチケット T-003-05 (F-003) で参照
- `backend/services/auth_middleware.py` — REFACTOR ラベルのチケット T-S0-09 (META) で参照
- `backend/services/briefing_service.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/services/catchup_service.py` — REFACTOR ラベルのチケット T-008-01 (F-008) で参照
- `backend/services/conversation_memory.py` — REFACTOR ラベルのチケット T-020-02 (F-020) で参照
- `backend/services/conversation_summarizer.py` — REFACTOR ラベルのチケット T-M30-03 (M-30) で参照
- `backend/services/credentials_store.py` — REFACTOR ラベルのチケット T-023-02 (F-023) で参照
- `backend/services/delegation_service.py` — REFACTOR ラベルのチケット T-003-02 (F-003) で参照
- `backend/services/design_pipeline.py` — REFACTOR ラベルのチケット T-005b-02 (F-005b) で参照
- `backend/services/designer_ai.py` — REFACTOR ラベルのチケット T-005b-02 (F-005b) で参照
- `backend/services/document_ingest_service.py` — REFACTOR ラベルのチケット T-016-01 (F-016) で参照
- `backend/services/document_service.py` — REFACTOR ラベルのチケット T-016-01 (F-016) で参照
- `backend/services/embedding_service.py` — REFACTOR ラベルのチケット T-M28-05 (M-28) で参照
- `backend/services/estimate_service.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/services/hearing_service.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/services/intent_preprocessor.py` — REFACTOR ラベルのチケット T-M27-02 (M-27) で参照
- `backend/services/knowledge_curator.py` — REFACTOR ラベルのチケット T-M28-05 (M-28) で参照
- `backend/services/knowledge_transfer.py` — REFACTOR ラベルのチケット T-M28-05 (M-28) で参照
- `backend/services/long_term_memory.py` — REFACTOR ラベルのチケット T-M30-04 (M-30) で参照
- `backend/services/mode_detector.py` — REFACTOR ラベルのチケット T-M27-02 (M-27) で参照
- `backend/services/observability.py` — REFACTOR ラベルのチケット T-017-02 (F-017) で参照
- `backend/services/obsidian_sync.py` — REFACTOR ラベルのチケット T-M30-04 (M-30) で参照
- `backend/services/obsidian_vault_sync.py` — REFACTOR ラベルのチケット T-M30-04 (M-30) で参照
- `backend/services/orchestrator_graph.py` — REFACTOR ラベルのチケット T-010b-01 (F-010b) で参照
- `backend/services/output_processor.py` — REFACTOR ラベルのチケット T-015-02 (F-015) で参照
- `backend/services/pricing_design_service.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/services/proposal_service.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/services/rag_context.py` — REFACTOR ラベルのチケット T-M28-05 (M-28) で参照
- `backend/services/requirements_service.py` — REFACTOR ラベルのチケット T-005-03 (F-005) で参照
- `backend/services/reviewer_loop.py` — REFACTOR ラベルのチケット T-011-01 (F-011) で参照
- `backend/services/sales_service.py` — REFACTOR ラベルのチケット T-008-01 (F-008) で参照
- `backend/services/scoped_knowledge.py` — REFACTOR ラベルのチケット T-024-02 (F-024) で参照
- `backend/services/secretary_chat.py` — REFACTOR ラベルのチケット T-003-02 (F-003) で参照
- `backend/services/skill_detector.py` — REFACTOR ラベルのチケット T-M27-02 (M-27) で参照
- `backend/services/skill_manager.py` — REFACTOR ラベルのチケット T-002-02 (F-002) で参照
- `backend/services/slot_extractor.py` — REFACTOR ラベルのチケット T-005-02 (F-005) で参照
- `backend/services/slot_state.py` — REFACTOR ラベルのチケット T-005-02 (F-005) で参照
- `backend/services/staff_service.py` — REFACTOR ラベルのチケット T-022-03 (F-022) で参照
- `backend/services/supabase_client.py` — REFACTOR ラベルのチケット T-S0-08 (META) で参照
- `backend/services/template_builder_service.py` — REFACTOR ラベルのチケット T-015-01 (F-015) で参照
- `backend/services/template_render_service.py` — REFACTOR ラベルのチケット T-015-01 (F-015) で参照
- `backend/services/upload_service.py` — REFACTOR ラベルのチケット T-016-01 (F-016) で参照
- `backend/services/user_profile.py` — REFACTOR ラベルのチケット T-023-01 (F-023) で参照
- `backend/services/workflow_service.py` — REFACTOR ラベルのチケット T-010c-01 (F-010c) で参照
- `backend/services/workspace_service.py` — REFACTOR ラベルのチケット T-BTSTRAP-02 (F-003) で参照
- `supabase/migrations/20260501220000_initial_schema.sql` — REFACTOR ラベルのチケット T-001-02 (F-001) で参照
- `supabase/migrations/20260501220200_knowledge_scope.sql` — REFACTOR ラベルのチケット T-024-02 (F-024) で参照
- `supabase/migrations/20260501220300_rls_skeleton.sql` — REFACTOR ラベルのチケット T-001-02 (F-001) で参照
- `supabase/migrations/20260501230000_design_frames.sql` — REFACTOR ラベルのチケット T-005b-01 (F-005b) で参照
- `supabase/migrations/20260501230100_design_mockup_content.sql` — REFACTOR ラベルのチケット T-005b-01 (F-005b) で参照
- `supabase/migrations/20260502000000_design_mocks.sql` — REFACTOR ラベルのチケット T-005b-01 (F-005b) で参照

### REUSE (4 件)

- `backend/routers/chatwork.py` — REUSE ラベルのチケット T-014-01 (F-014) で参照
- `backend/services/inbox_service.py` — REUSE ラベルのチケット T-014-01 (F-014) で参照
- `backend/services/slack_history.py` — REUSE ラベルのチケット T-014-01 (F-014) で参照
- `supabase/migrations/20260501220100_pgvector.sql` — REUSE ラベルのチケット T-001-07 (F-001) で参照

### UNDETERMINED (5 件)

- `backend/routers/browser_use.py` `[Phase 2]` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/browser_queue.py` `[Phase 2]` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/browser_use_service.py` `[Phase 2]` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/penpot_client.py` `[Phase 1.5]` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/tool_ui_postprocess.py` `[Phase 1.5]` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要

## Orphan: tickets が listed するが disk 不在のファイル

- `backend/integrations/github_client.py` (T-BTSTRAP-02, label=REFACTOR)
- `backend/cli/project_commands.py` (T-BTSTRAP-04, label=NEW)
- `.github/workflows/template-propagation.yml` (T-BTSTRAP-05, label=NEW)
- `tests/e2e/test_workspace_bootstrap.py` (T-BTSTRAP-06, label=NEW)
