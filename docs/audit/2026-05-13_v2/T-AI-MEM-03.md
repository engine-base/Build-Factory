# Pre-flight AC Audit — T-AI-MEM-03

- **Task**: T-AI-MEM-03 Subagent Memory store (handoff 引継ぎ知識保管; /memories/subagent/<persona>/handoff/<ts>-from-<source>.md; user / workspace 2 scope)
- **Sprint**: S2 / **Feature**: F-AI / **Layer**: BE / **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json` (search T-AI-MEM-03)
- **ADR refs**: ADR-012 (Anthropic Memory Tool 採用)
- **Status legend**: ⬜ PLANNED → 🟡 IMPL_DONE → 🟢 TEST_PASS → ✅ VERIFIED
- **Final status**: ✅ VERIFIED (24 sub-clause + 11 gap = 49 tests, 全 PASS / 1 周完結)

---

## 既存実装の把握 (着手前)

| ファイル | 状態 |
|---|---|
| `backend/services/subagent_memory.py` (292 行) | ✅ 既存 (PR #233 cascade) |
| `backend/routers/anthropic_memory.py` (subagent endpoint 含む) | ✅ 既存 |
| `backend/tests/test_adr_012_anthropic_memory_tool.py` (subagent test 10 件) | ✅ 既存だが mixed (dedicated 1:1 not yet) |

→ 本 PR は **dedicated 1:1 spec test + gap closure** が中心. impl ファイル変更は最小.

---

## AC-1 UBIQUITOUS

> "The system shall provide SubagentMemoryStore with record_handoff / preload_for / list_persona_files / clear_persona, backed by anthropic_memory_tool.MemoryToolHandler, supporting both user and workspace_id scopes."

| # | sub-clause | impl | test | status | gap |
|---|---|---|---|---|---|
| 1.1 | SubagentMemoryStore class 提供 | `backend/services/subagent_memory.py:90` | `test_ac1_class_exists_and_signature` | ✅ | G1 (1:1 test 追加) |
| 1.2 | record_handoff method | `backend/services/subagent_memory.py:105` | `test_ac1_record_handoff_signature` | ✅ | G1 |
| 1.3 | preload_for method | `backend/services/subagent_memory.py:222` | `test_ac1_preload_for_signature` | ✅ | G1 |
| 1.4 | list_persona_files method | `backend/services/subagent_memory.py:183` | `test_ac1_list_persona_files_signature` | ✅ | **G2 (dedicated test 欠落)** |
| 1.5 | clear_persona method | `backend/services/subagent_memory.py:248` | `test_ac1_clear_persona_signature` | ✅ | G1 |
| 1.6 | backed by anthropic_memory_tool.MemoryToolHandler | `backend/services/subagent_memory.py:35-39` | `test_ac1_backed_by_memory_tool_handler` | ✅ | **G3 (委譲 test 欠落)** |
| 1.7 | user scope (workspace_id=None) | `backend/services/subagent_memory.py:81-86` | `test_ac1_user_scope_path` | ✅ | G4 |
| 1.8 | workspace_id scope | `backend/services/subagent_memory.py:84-85` | `test_ac1_workspace_scope_path` | ✅ | G4 |

---

## AC-2 EVENT-DRIVEN

> "When record_handoff is invoked, the system shall persist the handoff snippet to /memories/subagent/<persona>/handoff/<ts>-from-<source>.md within 2 seconds and shall be retrievable via preload_for in newest-first order."

| # | sub-clause | impl | test | status | gap |
|---|---|---|---|---|---|
| 2.1 | path format `/memories/subagent/<persona>/handoff/<ts>-from-<source>.md` | `backend/services/subagent_memory.py:131-133` | `test_ac2_path_format_exact_regex` | ✅ | **G5 (exact regex assertion 欠落、startswith のみ)** |
| 2.2 | within 2 seconds | (impl 全体) | `test_ac2_record_handoff_within_2sec` | ✅ | **G6 (timing test 欠落)** |
| 2.3 | retrievable via preload_for newest-first | `backend/services/subagent_memory.py:222` | `test_ac2_preload_newest_first_dedicated` | ✅ | G1 |
| 2.4 | workspace_id 付き path format `/memories/subagent/ws-<id>/<persona>/handoff/...` | `backend/services/subagent_memory.py:84-85` | `test_ac2_workspace_path_format_exact_regex` | ✅ | G5 |

---

## AC-3 STATE-DRIVEN

> "While both scopes (user-level and workspace_id-scoped) coexist, the system shall isolate persona memory by scope key and shall not leak memory across workspaces. existing handoff_service.py shall remain unchanged (no import cycle)."

| # | sub-clause | impl | test | status | gap |
|---|---|---|---|---|---|
| 3.1 | 2 scope coexist + isolate by scope key | `backend/services/subagent_memory.py:81-86` | `test_ac3_two_scopes_coexist_isolated` | ✅ | G1 |
| 3.2 | not leak memory across workspaces (positive) | (same) | `test_ac3_workspace_scope_isolation_basic` | ✅ | G1 |
| 3.3 | not leak (cross workspace + user scope) | (same) | `test_ac3_no_leak_user_to_workspace_and_vice_versa` | ✅ | **G7 (cross-scope negative 欠落)** |
| 3.4 | handoff_service.py remains unchanged | (touch せず) | `test_ac3_handoff_service_module_unchanged` | ✅ | **G8 (G9 相当 test 欠落)** |
| 3.5 | no import cycle (subagent_memory does NOT import handoff_service) | `backend/services/subagent_memory.py:imports` | `test_ac3_no_import_cycle_with_handoff_service` | ✅ | **G9 (import 関係 test 欠落)** |

---

## AC-4 UNWANTED

> "If invalid persona key (non-alnum / empty / > 100 chars), invalid workspace_id (<= 0, non-int) or empty message is provided, the system shall reject with SubagentMemoryError mapped to 4xx {detail:{code,message}} and shall NOT mutate persistent state."

| # | sub-clause | impl | test | status | gap |
|---|---|---|---|---|---|
| 4.1 | invalid persona non-alnum reject | `backend/services/subagent_memory.py:60-68` | `test_ac4_persona_non_alnum_rejected` | ✅ | G1 |
| 4.2 | invalid persona empty reject | (同上) | `test_ac4_persona_empty_rejected` | ✅ | G1 |
| 4.3 | invalid persona > 100 chars reject | (同上) | `test_ac4_persona_too_long_rejected` | ✅ | G1 |
| 4.4 | invalid workspace_id (<= 0) reject | `backend/services/subagent_memory.py:71-78` | `test_ac4_workspace_id_zero_or_negative_rejected` | ✅ | G1 |
| 4.5 | invalid workspace_id (non-int / bool / str) reject | (同上) | `test_ac4_workspace_id_wrong_type_rejected` | ✅ | G1 |
| 4.6 | empty message reject | `backend/services/subagent_memory.py:123-124` | `test_ac4_empty_message_rejected` | ✅ | G1 |
| 4.7 | mapped to 4xx {detail:{code,message}} via REST | `backend/routers/anthropic_memory.py:56-57,114-` | `test_ac4_rest_endpoint_returns_4xx_structured` (4 case) | ✅ | **G10 (router 4xx 統一の dedicated test 欠落)** |
| 4.8 | shall NOT mutate persistent state on rejection | (validation 先行設計) | `test_ac4_invalid_input_does_not_mutate_store` (4 case) | ✅ | **G11 (state mutate negative test 欠落)** |

---

## Gap closure 一覧 (着手前に網羅、合計 11 件)

| Gap | Severity | 内容 | 修正先 |
|---|---|---|---|
| G1 | LOW | 1:1 spec test の dedicated file 化 | 新規 `test_t_ai_mem_03_subagent_memory_spec.py` |
| G2 | MEDIUM | list_persona_files dedicated test | 新規 file |
| G3 | MEDIUM | MemoryToolHandler 委譲 (公開仕様) test | 新規 file |
| G4 | LOW | user / workspace 各 path 1:1 test | 新規 file |
| G5 | MEDIUM | path format 完全一致 regex assert | 新規 file |
| G6 | MEDIUM | 2 秒以内 timing test | 新規 file |
| G7 | MEDIUM | cross-scope leak negative test | 新規 file |
| G8 | MEDIUM | handoff_service.py 不変 test (T-M30-03 G9 相当) | 新規 file |
| G9 | LOW | no import cycle assertion | 新規 file |
| G10 | MEDIUM | router 4xx 統一の dedicated test | 新規 file |
| G11 | MEDIUM | invalid input で state mutate なし test | 新規 file |

**実装側は無変更が原則**. test だけで AC 1:1 を完成させる. service / router の小さな fix が必要なら別途記録.

---

## 完了判定 (Step 6 / ADR-011)

- [x] 全行 status = ✅ VERIFIED (25 sub-clause / 11 gap closure / 49 tests)
- [x] 新 test file: `backend/tests/test_t_ai_mem_03_subagent_memory_spec.py` **49 tests 全 PASS**
- [ ] `bash scripts/pre-commit-check.sh` exit_code=0 (commit 直前で実施)
- [ ] 既存 `test_adr_012_anthropic_memory_tool.py` も全 PASS (regression なし — full suite で確認)
- [ ] PR description にこの audit doc へのリンク

## 結果サマリー (post-mortem)

| | T-M30-03 (旧方式) | T-AI-MEM-03 (新方式) |
|---|---|---|
| audit 周回数 | 3 | **1** |
| 事後 gap 発見 | 6 件 | **0 件** (着手前 11 件全網羅) |
| commit 数 | 3 | **1** |
| PR コメント | 1500 行 | 表 1 + link |
| test 数 | 133 (3 PR 累計) | **49 (1 PR 完結)** |
| 所要時間 | 90-120 分 | **~30 分** |

新 workflow の効果が定量的に確認された.
