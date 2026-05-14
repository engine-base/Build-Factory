# Pre-flight AC Audit (retroactive) — T-AI-01 (Anthropic Memory API 統合 (memory_facts.write_fact + extract_facts_from_session + )

- **Task**: T-AI-01 (Anthropic Memory API 統合 (memory_facts.write_fact + extract_facts_from_session + recall_facts + request_deletion + proces)
- **Sprint**: S2 / **Feature**: F-AI / **Layer**: L2
- **Slice**: S2 / **Wave**: 2.2
- **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-AI-01`
- **Deps**: T-S0-08
- **Status**: ✅ VERIFIED (retroactive — 実装+test 共に既存, post-hoc 検証で全 PASS 確認)

> **retroactive audit**: 本タスクは 2026-05-13 の pre-flight audit workflow 制定**前**に
> 既に実装+test ともに完了していた (bootstrap または初期実装フェーズで)。
> commit message に明示的な task ID 記載が無かったため `done_status='pending'` 扱いだったが、
> existing_files の実在確認 + 全 test PASS で **機能的に done と確定**。
> 本 audit MD はその retroactive 検証記録。

---

## 既存実装 (existing_files)

- ✅ `backend/services/memory_facts.py`

## 既存 test ファイル

- `backend/tests/test_t_ai_01_memory_api_spec_invariants.py` (27 test 関数)

## AC × test 1:1 対応 (post-hoc mapping)

### AC-1 UBIQUITOUS

> backend/services/memory_facts.py shall expose write_fact(*, user_id, fact_text, source_session_id=None, workspace_id=None, confidence_score=0.7, kind='durable') / extract_facts_from_session(session_id, user_id, *, workspace_id=None, confidence_score=0.7) / recall_facts(user_id, query, *, top_k=5) / request_deletion(fact_id, user_id) / process_retry_queue(*, max_items=50) / process_pending_deletions(*, dry_run=False) / FactRecord dataclass (14 fields including memory_api_id / mem0_id / fingerprint / status / retry_count / last_error / synced_at / deleted_at) / fingerprint(text) SHA-256 head 16-hex helper (ADR-010: Anthropic-native, no langgraph / langchain / litellm in this module).

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 1.1 | `test_ac1_module_exists` | `test_t_ai_01_memory_api_spec_invariants.py` | 45 | ✅ VERIFIED |
| 1.2 | `test_ac1_six_public_apis_callable` | `test_t_ai_01_memory_api_spec_invariants.py` | 49 | ✅ VERIFIED |
| 1.3 | `test_ac1_write_fact_signature` | `test_t_ai_01_memory_api_spec_invariants.py` | 60 | ✅ VERIFIED |
| 1.4 | `test_ac1_recall_facts_top_k_default` | `test_t_ai_01_memory_api_spec_invariants.py` | 72 | ✅ VERIFIED |
| 1.5 | `test_ac1_fact_record_14_fields` | `test_t_ai_01_memory_api_spec_invariants.py` | 78 | ✅ VERIFIED |
| 1.6 | `test_ac1_fingerprint_sha256_head_16` | `test_t_ai_01_memory_api_spec_invariants.py` | 90 | ✅ VERIFIED |
| 1.7 | `test_ac1_no_langgraph_langchain_litellm_imports` | `test_t_ai_01_memory_api_spec_invariants.py` | 102 | ✅ VERIFIED |

### AC-2 EVENT-DRIVEN

> When extract_facts_from_session is called, the system shall read chat_messages WHERE thread_id = ?, scan each row.content with _FACT_RE = `^[ \t]*(?:#+|\*+|-)?[ \t]*\*{0,2}([DPC]-\d{2,4})\*{0,2}[ \t]*[:：．。\-—]?[ \t]*(.+?)[ \t]*$` (MULTILINE) capturing D-XXX / P-XXX / C-XXX prefixes, and pass each (prefix, body) tuple to write_fact(); when write_fact is called the system shall (a) INSERT OR IGNORE into memory_facts with status='pending' using fingerprint(fact_text), (b) wrap _memory_api_write_with_retry via services.anthropic_retry.with_retry(idempotency_key=fp, label='memory_api.append'), (c) on success call _mark_synced + set memory_api_id + synced_at, (d) on RetryExhaustedError call _mark_failed + emit 'memory_api_write_failed' audit, (e) on non-retryable Exception emit 'memory_api_write_error' audit.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 2.1 | `test_ac2_fact_regex_captures_dpc_prefixes` | `test_t_ai_01_memory_api_spec_invariants.py` | 118 | ✅ VERIFIED |
| 2.2 | `test_ac2_write_fact_uses_with_retry_and_idempotency` | `test_t_ai_01_memory_api_spec_invariants.py` | 133 | ✅ VERIFIED |
| 2.3 | `test_ac2_insert_pending_status_in_write_fact` | `test_t_ai_01_memory_api_spec_invariants.py` | 149 | ✅ VERIFIED |
| 2.4 | `test_ac2_retry_exhausted_audit_event` | `test_t_ai_01_memory_api_spec_invariants.py` | 162 | ✅ VERIFIED |
| 2.5 | `test_ac2_extract_reads_chat_messages_by_thread` | `test_t_ai_01_memory_api_spec_invariants.py` | 172 | ✅ VERIFIED |

### AC-3 STATE-DRIVEN

> While storing a fact, write_fact shall persist source_session_id + confidence_score (float 0.0–1.0) on every row (DB column NOT NULL after migration); while ANTHROPIC_API_KEY env is unset, _memory_api_write_with_retry shall raise RuntimeError('ANTHROPIC_API_KEY not set') so callers know to skip the network call gracefully; while the SDK lacks client.beta.memory_stores (older anthropic versions), the call shall raise RuntimeError('anthropic Memory API not available in this SDK') instead of returning silently; while memory_stores exposes neither append nor create, the call shall raise RuntimeError('memory_stores has neither append nor create').

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 3.1 | `test_ac3_api_key_unset_raises_runtime_error` | `test_t_ai_01_memory_api_spec_invariants.py` | 191 | ✅ VERIFIED |
| 3.2 | `test_ac3_memory_stores_availability_guarded` | `test_t_ai_01_memory_api_spec_invariants.py` | 206 | ✅ VERIFIED |
| 3.3 | `test_ac3_uses_client_beta_memory_stores` | `test_t_ai_01_memory_api_spec_invariants.py` | 215 | ✅ VERIFIED |

### AC-4 OPTIONAL

> Where the user invokes request_deletion(fact_id, user_id), memory_facts.status shall be UPDATEd to 'deleted' + deleted_at = datetime('now','localtime') and emit 'memory_fact_deletion_requested' audit; where process_pending_deletions(dry_run=False) runs (cron hourly), _physical_delete_fact shall call client.beta.memory_stores.delete(store_id=f'bf_user_{user_id}', id=memory_api_id) best-effort + services.long_term_memory.delete_user_memories(user_id, ids=[mem0_id]) best-effort + DELETE FROM memory_facts WHERE id=?, emitting 'memory_facts_deleted_batch' audit with the deleted ids.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 4.1 | `test_ac4_request_deletion_soft_marks_and_audits` | `test_t_ai_01_memory_api_spec_invariants.py` | 229 | ✅ VERIFIED |
| 4.2 | `test_ac4_physical_delete_cascades_memory_api_mem0_db` | `test_t_ai_01_memory_api_spec_invariants.py` | 242 | ✅ VERIFIED |
| 4.3 | `test_ac4_process_pending_emits_batch_audit` | `test_t_ai_01_memory_api_spec_invariants.py` | 260 | ✅ VERIFIED |
| 4.4 | `test_ac4_dry_run_returns_would_delete` | `test_t_ai_01_memory_api_spec_invariants.py` | 265 | ✅ VERIFIED |

### AC-5 UNWANTED

> If Memory API write fails with RetryExhaustedError, the system shall keep the DB row (status='failed', retry_count=retry_count+1, last_error=str(e.last_exc)[:300]) so process_retry_queue(max_items=50) can resend it (LIMIT max_items, retry_count < 5, ORDER BY created_at ASC) — no data loss; if fact_text is empty or whitespace-only, write_fact shall return None without touching the DB; if the DB INSERT raises, write_fact shall logger.warning + return None; the module shall not import langgraph / langchain / litellm (ADR-010) and shall not contain hardcoded Supabase / Anthropic credentials.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 5.1 | `test_ac5_retry_queue_limits_to_5_attempts` | `test_t_ai_01_memory_api_spec_invariants.py` | 282 | ✅ VERIFIED |
| 5.2 | `test_ac5_mark_failed_increments_retry_count` | `test_t_ai_01_memory_api_spec_invariants.py` | 298 | ✅ VERIFIED |
| 5.3 | `test_ac5_empty_fact_text_returns_none` | `test_t_ai_01_memory_api_spec_invariants.py` | 311 | ✅ VERIFIED |
| 5.4 | `test_ac5_db_insert_failure_logs_and_returns_none` | `test_t_ai_01_memory_api_spec_invariants.py` | 326 | ✅ VERIFIED |
| 5.5 | `test_ac5_no_hardcoded_supabase_or_anthropic_key` | `test_t_ai_01_memory_api_spec_invariants.py` | 339 | ✅ VERIFIED |

## AC 未紐付 test (cross-cutting / regression)

- `test_tickets_t_ai_01_canonical_ears` (`test_t_ai_01_memory_api_spec_invariants.py:350`)
- `test_tickets_t_ai_01_has_adr_link_and_files` (`test_t_ai_01_memory_api_spec_invariants.py:362`)
- `test_tickets_t_ai_01_ac_mentions_concrete_symbols` (`test_t_ai_01_memory_api_spec_invariants.py:370`)

## 完了判定 (ADR-011 単一ゲート)

- [x] existing_files 全件が repo に実在
- [x] test ファイル (1 件) 全 PASS (post-hoc 一括実行で確認)
- [x] AC 5 件すべてに test 関数または cross-cutting カバレッジが対応
- [x] `bash scripts/lint-mock.sh` 16/16 OK (repo 全体)
- [x] `python3 scripts/verify-slice.py T-AI-01` PASS

---

_自動生成 by `scripts/generate-audit-mds.py` (2026-05-14)_