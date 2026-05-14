# Pre-flight AC Audit (retroactive) — T-AI-02 (Mem0 ベクトル検索 + Anthropic Memory API ブリッジ (mem0_bridge.mirror_fact_to_mem0 + searc)

- **Task**: T-AI-02 (Mem0 ベクトル検索 + Anthropic Memory API ブリッジ (mem0_bridge.mirror_fact_to_mem0 + search_with_rerank + preload_secretary_facts )
- **Sprint**: S2 / **Feature**: F-AI / **Layer**: L2
- **Slice**: S2 / **Wave**: 2.3
- **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-AI-02`
- **Deps**: T-AI-01
- **Status**: ✅ VERIFIED (retroactive — 実装+test 共に既存, post-hoc 検証で全 PASS 確認)

> **retroactive audit**: 本タスクは 2026-05-13 の pre-flight audit workflow 制定**前**に
> 既に実装+test ともに完了していた (bootstrap または初期実装フェーズで)。
> commit message に明示的な task ID 記載が無かったため `done_status='pending'` 扱いだったが、
> existing_files の実在確認 + 全 test PASS で **機能的に done と確定**。
> 本 audit MD はその retroactive 検証記録。

---

## 既存実装 (existing_files)

- ✅ `backend/services/mem0_bridge.py`
- ✅ `backend/services/long_term_memory.py`

## 既存 test ファイル

- `backend/tests/test_t_ai_02_mem0_bridge_spec_invariants.py` (23 test 関数)

## AC × test 1:1 対応 (post-hoc mapping)

### AC-1 UBIQUITOUS

> backend/services/mem0_bridge.py shall expose async mirror_fact_to_mem0(fact: FactRecord) -> Optional[str] / search_with_rerank(user_id, query, *, top_k=5) -> list[ScoredFact] / preload_secretary_facts(user_id, *, top_n=50) -> list[FactRecord] / detect_divergence(user_id, *, sample=100) -> dict; ScoredFact dataclass shall hold (fact: FactRecord, vector_score: float, confidence: float, final_score: float); FactRecord and _row_to_fact shall be reused from services.memory_facts (no schema drift); ADR-010 compliance — no langgraph / langchain / litellm IMPORT in this module.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 1.1 | `test_ac1_module_exists` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 44 | ✅ VERIFIED |
| 1.2 | `test_ac1_four_public_apis_callable` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 48 | ✅ VERIFIED |
| 1.3 | `test_ac1_scored_fact_four_fields` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 58 | ✅ VERIFIED |
| 1.4 | `test_ac1_reuses_fact_record_and_row_to_fact` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 65 | ✅ VERIFIED |
| 1.5 | `test_ac1_search_with_rerank_top_k_default` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 77 | ✅ VERIFIED |
| 1.6 | `test_ac1_preload_secretary_facts_top_n_default` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 83 | ✅ VERIFIED |
| 1.7 | `test_ac1_no_langgraph_langchain_litellm_imports` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 89 | ✅ VERIFIED |

### AC-2 EVENT-DRIVEN

> When mirror_fact_to_mem0(fact) is called, the system shall call services.long_term_memory.add_conversation(user_id=fact.user_id, conversation=[{'role': 'system', 'content': fact.fact_text}], metadata={kind, fingerprint, source_session_id, confidence_score}) and on success UPDATE memory_facts SET mem0_id = f'mem0:{fact.fingerprint}' WHERE id = fact.id, returning the new mem0_id; when search_with_rerank(user_id, query, top_k=5) is called the system shall (a) call services.long_term_memory.search_relevant_memories(user_id, query, limit=top_k), (b) compute fingerprint() per returned text, (c) DB-join with memory_facts on fingerprint IN (...), (d) compute vector_score = 1.0/(rank+1) MRR, (e) final_score = 0.6 * vector_score + 0.4 * confidence_score, (f) sort by final_score DESC and return scored[:top_k].

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 2.1 | `test_ac2_mirror_calls_add_conversation` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 105 | ✅ VERIFIED |
| 2.2 | `test_ac2_mirror_updates_mem0_id_with_fp_prefix` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 120 | ✅ VERIFIED |
| 2.3 | `test_ac2_rerank_formula_0_6_vector_0_4_confidence` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 132 | ✅ VERIFIED |
| 2.4 | `test_ac2_rerank_uses_mrr_score_1_over_rank_plus_1` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 140 | ✅ VERIFIED |
| 2.5 | `test_ac2_rerank_calls_search_relevant_memories_and_sorts` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 148 | ✅ VERIFIED |

### AC-3 STATE-DRIVEN

> While invoked for the secretary AI session start, preload_secretary_facts shall execute SELECT * FROM memory_facts WHERE user_id = ? AND deleted_at IS NULL AND status = 'synced' ORDER BY confidence_score DESC, created_at DESC LIMIT top_n (default 50), returning FactRecord rows for system prompt injection; while a fact is found in Mem0 but missing from the DB (deleted / not yet synced), search_with_rerank shall construct a synthetic FactRecord(id=None, fact_text=text, kind='durable', confidence_score=0.5, fingerprint=fp, status='pending') so the caller still gets a hit (graceful degradation, not silent drop).

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 3.1 | `test_ac3_preload_secretary_query_order` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 169 | ✅ VERIFIED |
| 3.2 | `test_ac3_synthetic_fact_record_for_mem0_only` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 186 | ✅ VERIFIED |

### AC-4 OPTIONAL

> Where Mem0 search returns an empty list, search_with_rerank shall short-circuit and return [] without attempting the DB join (cost-saving); where services.long_term_memory is unavailable or raises (ImportError / runtime), mirror_fact_to_mem0 shall logger.warning and return None and search_with_rerank shall treat mem0_texts as [] so the caller still receives a deterministic empty result (no exception propagation to HTTP).

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 4.1 | `test_ac4_empty_mem0_returns_empty_list` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 204 | ✅ VERIFIED |
| 4.2 | `test_ac4_import_error_treated_as_empty` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 215 | ✅ VERIFIED |
| 4.3 | `test_ac4_mirror_logs_and_returns_none_on_failure` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 226 | ✅ VERIFIED |

### AC-5 UNWANTED

> If detect_divergence(user_id, sample=100) finds memory_facts rows with status='synced' AND deleted_at IS NULL AND mem0_id IS NULL (sample size SELECT ORDER BY id DESC LIMIT sample), the function shall emit a 'memory_divergence_detected' audit via services.memory_service.emit_event with detail={'missing_in_mem0': len(missing), 'sample_ids': missing[:20]} and return a dict {checked, missing_in_mem0, missing_ids: missing[:50]} so the divergence cannot be silently hidden; the module shall not import langgraph / langchain / litellm (ADR-010) and shall not contain hardcoded Supabase / Anthropic credentials.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 5.1 | `test_ac5_detect_divergence_emits_audit` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 243 | ✅ VERIFIED |
| 5.2 | `test_ac5_detect_divergence_query_filters` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 257 | ✅ VERIFIED |
| 5.3 | `test_ac5_no_hardcoded_supabase_or_anthropic_key` | `test_t_ai_02_mem0_bridge_spec_invariants.py` | 269 | ✅ VERIFIED |

## AC 未紐付 test (cross-cutting / regression)

- `test_tickets_t_ai_02_canonical_ears` (`test_t_ai_02_mem0_bridge_spec_invariants.py:280`)
- `test_tickets_t_ai_02_has_adr_link_and_files` (`test_t_ai_02_mem0_bridge_spec_invariants.py:292`)
- `test_tickets_t_ai_02_ac_mentions_concrete_symbols` (`test_t_ai_02_mem0_bridge_spec_invariants.py:301`)

## 完了判定 (ADR-011 単一ゲート)

- [x] existing_files 全件が repo に実在
- [x] test ファイル (1 件) 全 PASS (post-hoc 一括実行で確認)
- [x] AC 5 件すべてに test 関数または cross-cutting カバレッジが対応
- [x] `bash scripts/lint-mock.sh` 16/16 OK (repo 全体)
- [x] `python3 scripts/verify-slice.py T-AI-02` PASS

---

_自動生成 by `scripts/generate-audit-mds.py` (2026-05-14)_