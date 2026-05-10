# T-S0-13: 既存実装インベントリ監査結果

- 走査対象: routers=39, services=54, migrations=7
- 分類サマリ: {'REFACTOR': 35, 'UNDETERMINED': 64, 'REUSE': 1}
- Orphan tickets (listed file 不在): 6 件
- Phase boundary annotation: 2 件

## 分類別ファイル一覧

### REFACTOR (35 件)

- `backend/routers/account_settings.py` — REFACTOR ラベルのチケット T-023-01 (F-023) で参照
- `backend/routers/accounts.py` — REFACTOR ラベルのチケット T-004-01 (F-004) で参照
- `backend/routers/approval.py` — REFACTOR ラベルのチケット T-012-02 (F-012) で参照
- `backend/routers/design_frames.py` — REFACTOR ラベルのチケット T-005b-01 (F-005b) で参照
- `backend/routers/design_mocks.py` — REFACTOR ラベルのチケット T-005b-01 (F-005b) で参照
- `backend/routers/employees.py` — REFACTOR ラベルのチケット T-022-03 (F-022) で参照
- `backend/routers/hearing.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/routers/knowledge_search.py` — REFACTOR ラベルのチケット T-024-02 (F-024) で参照
- `backend/routers/mcp_server.py` — REFACTOR ラベルのチケット T-010a-01 (F-010a) で参照
- `backend/routers/requirements.py` — REFACTOR ラベルのチケット T-005-03 (F-005) で参照
- `backend/routers/reviewer.py` — REFACTOR ラベルのチケット T-011-01 (F-011) で参照
- `backend/routers/skills.py` — REFACTOR ラベルのチケット T-002-01 (F-002) で参照
- `backend/routers/tasks.py` — REFACTOR ラベルのチケット T-006-02 (F-006) で参照
- `backend/routers/threads.py` — REFACTOR ラベルのチケット T-M30-01 (M-30) で参照
- `backend/routers/workspaces.py` — REFACTOR ラベルのチケット T-003-02 (F-003) で参照
- `backend/services/artifact_export.py` — REFACTOR ラベルのチケット T-015-01 (F-015) で参照
- `backend/services/artifact_service.py` — REFACTOR ラベルのチケット T-003-05 (F-003) で参照
- `backend/services/conversation_summarizer.py` — REFACTOR ラベルのチケット T-M30-03 (M-30) で参照
- `backend/services/credentials_store.py` — REFACTOR ラベルのチケット T-023-02 (F-023) で参照
- `backend/services/designer_ai.py` — REFACTOR ラベルのチケット T-005b-02 (F-005b) で参照
- `backend/services/embedding_service.py` — REFACTOR ラベルのチケット T-M28-05 (M-28) で参照
- `backend/services/hearing_service.py` — REFACTOR ラベルのチケット T-005-01 (F-005) で参照
- `backend/services/intent_preprocessor.py` — REFACTOR ラベルのチケット T-M27-02 (M-27) で参照
- `backend/services/long_term_memory.py` — REFACTOR ラベルのチケット T-M30-04 (M-30) で参照
- `backend/services/mode_detector.py` — REFACTOR ラベルのチケット T-M27-02 (M-27) で参照
- `backend/services/observability.py` — REFACTOR ラベルのチケット T-017-02 (F-017) で参照
- `backend/services/obsidian_sync.py` — REFACTOR ラベルのチケット T-M30-04 (M-30) で参照
- `backend/services/output_processor.py` — REFACTOR ラベルのチケット T-015-02 (F-015) で参照
- `backend/services/requirements_service.py` — REFACTOR ラベルのチケット T-005-03 (F-005) で参照
- `backend/services/reviewer_loop.py` — REFACTOR ラベルのチケット T-011-01 (F-011) で参照
- `backend/services/slot_extractor.py` — REFACTOR ラベルのチケット T-005-02 (F-005) で参照
- `backend/services/slot_state.py` — REFACTOR ラベルのチケット T-005-02 (F-005) で参照
- `backend/services/staff_service.py` — REFACTOR ラベルのチケット T-022-03 (F-022) で参照
- `backend/services/user_profile.py` — REFACTOR ラベルのチケット T-023-01 (F-023) で参照
- `backend/services/workspace_service.py` — REFACTOR ラベルのチケット T-BTSTRAP-02 (F-003) で参照

### REUSE (1 件)

- `supabase/migrations/20260501220100_pgvector.sql` — REUSE ラベルのチケット T-001-07 (F-001) で参照

### UNDETERMINED (64 件)

- `backend/routers/ai_system.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/artifacts.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/browser_use.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/chat.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/chatwork.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/dashboard.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/design_pipeline.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/documents.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/estimate.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/knowledge_actions.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/llm.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/llm_providers.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/pricing_design.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/proposal.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/records.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/references.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/secretary.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/secretary_stream.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/skill_creator.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/slot_admin.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/staff.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/template_builder.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/uploads.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/routers/workflows.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/account_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/account_settings_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/auth_middleware.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/briefing_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/browser_queue.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/browser_use_service.py` `[Phase 2]` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/catchup_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/conversation_memory.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/delegation_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/design_pipeline.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/document_ingest_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/document_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/estimate_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/inbox_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/knowledge_curator.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/knowledge_transfer.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/obsidian_vault_sync.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/orchestrator_graph.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/penpot_client.py` `[Phase 1.5]` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/pricing_design_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/proposal_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/rag_context.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/sales_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/scoped_knowledge.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/secretary_chat.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/skill_detector.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/skill_manager.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/slack_history.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/supabase_client.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/template_builder_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/template_render_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/tool_ui_postprocess.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/upload_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `backend/services/workflow_service.py` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `supabase/migrations/20260501220000_initial_schema.sql` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `supabase/migrations/20260501220200_knowledge_scope.sql` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `supabase/migrations/20260501220300_rls_skeleton.sql` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `supabase/migrations/20260501230000_design_frames.sql` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `supabase/migrations/20260501230100_design_mockup_content.sql` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要
- `supabase/migrations/20260502000000_design_mocks.sql` — 個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要

## Orphan: tickets が listed するが disk 不在のファイル

- `backend/routers/auth.py` (T-001-02, label=REFACTOR)
- `backend/services/memory_service.py` (T-020-02, label=REFACTOR)
- `backend/integrations/github_client.py` (T-BTSTRAP-02, label=REFACTOR)
- `backend/cli/project_commands.py` (T-BTSTRAP-04, label=NEW)
- `.github/workflows/template-propagation.yml` (T-BTSTRAP-05, label=NEW)
- `tests/e2e/test_workspace_bootstrap.py` (T-BTSTRAP-06, label=NEW)
