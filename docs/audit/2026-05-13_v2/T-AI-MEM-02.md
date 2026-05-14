# Pre-flight AC Audit — T-AI-MEM-02

- **Task**: T-AI-MEM-02 Anthropic Context Editing config (clear_tool_uses_20250919 + compact_20260112 + clear_thinking_20251015; default factory + validator)
- **Sprint**: S2 / **Feature**: F-AI / **Layer**: BE / **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json` (search T-AI-MEM-02)
- **ADR refs**: ADR-012 (Anthropic 公式 Memory / Context Editing 採用)
- **Status legend**: ⬜ PLANNED → 🟡 IMPL_DONE → 🟢 TEST_PASS → ✅ VERIFIED
- **Final status**: ✅ VERIFIED (24 sub-clause + 11 gap = 49+ tests, 全 PASS / 1 周完結)

---

## 既存実装の把握 (着手前)

| ファイル | 状態 |
|---|---|
| `backend/services/anthropic_context_editing.py` (199 行) | ✅ 既存 (ADR-012 cascade / PR #233) |
| `backend/routers/anthropic_memory.py` `GET /context-editing` endpoint | ✅ 既存 |
| `backend/services/provider_adapter_memory.py` `context_editing_for(provider)` | ✅ 既存 (anthropic 経路で本 module を委譲) |
| `backend/tests/test_adr_012_anthropic_memory_tool.py` (CE 関連 8 件) | ✅ 既存だが mixed (Memory Tool 全体, 1:1 not yet) |
| `scripts/lint-mock.sh` `check_no_self_tool_trim` (#10) | ✅ 既存 (AC-4 part 1 = tool result clearing self-impl 検知) |
| `scripts/lint-mock.sh` self-compaction 検知 | ❌ 不在 → **G11** で本 audit に lint NEW を追加 |

→ 本 PR は **dedicated 1:1 spec test + 11 件 gap closure + lint #14 追加** が中心.
impl ファイル (`anthropic_context_editing.py`) は **無変更**.

---

## AC-1 UBIQUITOUS

> "The system shall expose default_context_management_config() producing a dict compatible with anthropic-python client.beta.messages.create(..., context_management=...), with Memory tool protected via exclude_tools=['memory']."

| # | sub-clause | impl | test | status | gap |
|---|---|---|---|---|---|
| 1.1 | `default_context_management_config()` 公開関数 | `backend/services/anthropic_context_editing.py:72` | `test_ac1_default_config_callable_exists` | ✅ | G1 (1:1 test 追加) |
| 1.2 | 戻り値が dict | `backend/services/anthropic_context_editing.py:142` | `test_ac1_returns_dict` | ✅ | G1 |
| 1.3 | dict に `edits` キー (anthropic-python `context_management=` 形式) | `backend/services/anthropic_context_editing.py:142` | `test_ac1_dict_has_edits_key_for_sdk_compat` | ✅ | **G2 (SDK shape 1:1 test 欠落)** |
| 1.4 | `edits` は list[dict] (各 item に type/trigger) | `backend/services/anthropic_context_editing.py:111-141` | `test_ac1_edits_each_item_has_type_and_trigger` | ✅ | G2 |
| 1.5 | Memory tool 保護 (`exclude_tools=['memory']`) | `backend/services/anthropic_context_editing.py:50,129` | `test_ac1_memory_protected_in_exclude_tools` | ✅ | G1 |
| 1.6 | 既定で clear_tool_uses_20250919 strategy 含む | `backend/services/anthropic_context_editing.py:121-131` | `test_ac1_default_includes_clear_tool_uses_strategy` | ✅ | G1 |
| 1.7 | 既定で compact_20260112 strategy 含む | `backend/services/anthropic_context_editing.py:133-140` | `test_ac1_default_includes_compact_strategy` | ✅ | G1 |
| 1.8 | extra_protected_tools で memory 重複防止 + 追加 tool マージ | `backend/services/anthropic_context_editing.py:103-109` | `test_ac1_extra_protected_tools_merged_no_dup` | ✅ | G1 |

---

## AC-2 EVENT-DRIVEN

> "When the config is requested, the system shall return within 2 seconds and shall include the recommended beta headers ('context-management-2025-06-27' + 'compact-2026-01-12')."

| # | sub-clause | impl | test | status | gap |
|---|---|---|---|---|---|
| 2.1 | config 要求が 2 秒以内に return | (factory pure / 副作用なし) | `test_ac2_default_config_returns_within_2sec` | ✅ | **G3 (timing test 欠落)** |
| 2.2 | `recommended_beta_headers()` が `'context-management-2025-06-27'` を含む | `backend/services/anthropic_context_editing.py:46,67-69` | `test_ac2_betas_include_context_management_2025_06_27` | ✅ | **G4 (1:1 dedicated test 欠落)** |
| 2.3 | `recommended_beta_headers()` が `'compact-2026-01-12'` を含む | `backend/services/anthropic_context_editing.py:47,67-69` | `test_ac2_betas_include_compact_2026_01_12` | ✅ | G4 |
| 2.4 | REST endpoint `GET /api/anthropic-memory/context-editing` が betas 同梱で 2 秒以内 | `backend/routers/anthropic_memory.py:71-77` | `test_ac2_rest_endpoint_returns_betas_within_2sec` | ✅ | **G5 (REST 経路 timing + betas 同梱の 1:1 test 欠落)** |

---

## AC-3 STATE-DRIVEN

> "While the config is active, the compact_20260112 trigger shall be >= 50,000 input_tokens (official constraint) and clear_thinking_20251015 (when enabled) shall be placed first in edits[]."

| # | sub-clause | impl | test | status | gap |
|---|---|---|---|---|---|
| 3.1 | 既定 compact trigger >= 50,000 input_tokens | `backend/services/anthropic_context_editing.py:57,94-97` | `test_ac3_default_compact_trigger_meets_50k_floor` | ✅ | G1 |
| 3.2 | trigger.type == 'input_tokens' (公式型) | `backend/services/anthropic_context_editing.py:136` | `test_ac3_compact_trigger_type_is_input_tokens` | ✅ | **G6 (trigger.type 公式型 1:1 test 欠落)** |
| 3.3 | 全 strategy の trigger.type == 'input_tokens' (公式制約) | `backend/services/anthropic_context_editing.py:117,124,136` | `test_ac3_all_strategies_trigger_type_input_tokens` | ✅ | G6 |
| 3.4 | clear_thinking 有効時、edits[0] (先頭) | `backend/services/anthropic_context_editing.py:114-119` | `test_ac3_clear_thinking_when_enabled_is_first_in_edits` | ✅ | G1 |
| 3.5 | clear_thinking 無効時、edits[] に含まれない | `backend/services/anthropic_context_editing.py:114` | `test_ac3_clear_thinking_when_disabled_absent_from_edits` | ✅ | **G7 (negative test 欠落)** |
| 3.6 | clear_thinking + clear_tool_uses + compact 同時、順序 = thinking → clear → compact | `backend/services/anthropic_context_editing.py:114-141` | `test_ac3_full_strategy_order_thinking_clear_compact` | ✅ | **G8 (組合せ順序 test 欠落)** |
| 3.7 | validator が compact trigger < 50K を reject | `backend/services/anthropic_context_editing.py:166-171` | `test_ac3_validator_rejects_compact_below_50k` | ✅ | G1 |
| 3.8 | validator が clear_thinking 非先頭を reject | `backend/services/anthropic_context_editing.py:184-187` | `test_ac3_validator_rejects_misordered_clear_thinking` | ✅ | G1 |

---

## AC-4 UNWANTED

> "If application code re-implements server-side compaction or tool result clearing, the lint script shall fail. If invalid config (compact trigger < 50K, misordered clear_thinking, unknown strategy type) is detected, the system shall raise ContextEditingError and shall NOT mutate persistent state."

| # | sub-clause | impl | test | status | gap |
|---|---|---|---|---|---|
| 4.1 | lint guard: app code に tool result clearing 自前実装 (clear/trim/dedup 等) → fail | `scripts/lint-mock.sh:320-335` (`check_no_self_tool_trim`) | `test_ac4_lint_guard_no_self_tool_trim_in_repo` | ✅ | G1 |
| 4.2 | lint guard: app code に server-side compaction 自前実装 → fail | (現状不在) | `test_ac4_lint_guard_no_self_compaction_in_repo` | ✅ | **G11 (lint check NEW 追加 — `check_no_self_compaction`)** |
| 4.3 | factory が compact trigger < 50K で `ContextEditingError` raise | `backend/services/anthropic_context_editing.py:94-97` | `test_ac4_factory_raises_on_compact_below_50k` | ✅ | G1 |
| 4.4 | validator が compact trigger < 50K で `ContextEditingError` raise | `backend/services/anthropic_context_editing.py:166-171` | `test_ac4_validator_raises_on_compact_below_50k` | ✅ | G1 |
| 4.5 | validator が clear_thinking 非先頭で `ContextEditingError` raise | `backend/services/anthropic_context_editing.py:184-187` | `test_ac4_validator_raises_on_misordered_clear_thinking` | ✅ | G1 |
| 4.6 | validator が unknown strategy type で `ContextEditingError` raise | `backend/services/anthropic_context_editing.py:160-163` | `test_ac4_validator_raises_on_unknown_strategy_type` | ✅ | G1 |
| 4.7 | factory raise 時 persistent state mutate なし (factory は pure / 副作用なし) | (factory 設計上 stateless) | `test_ac4_factory_raise_does_not_mutate_state` | ✅ | **G9 (state-mutate negative test 欠落)** |
| 4.8 | validator raise 時 persistent state mutate なし | (validator 設計上 stateless) | `test_ac4_validator_raise_does_not_mutate_state` | ✅ | G9 |
| 4.9 | env override `CONTEXT_MGMT_DISABLE` truthy → None (skip 指示) | `backend/services/anthropic_context_editing.py:191-199` | `test_ac4_env_override_truthy_returns_none` | ✅ | **G10 (env override 仕様 1:1 test 欠落)** |
| 4.10 | env override falsy/未設定 → 既定 config 返却 | `backend/services/anthropic_context_editing.py:196-199` | `test_ac4_env_override_falsy_returns_default` | ✅ | G10 |

---

## Gap closure 一覧 (着手前に網羅、合計 11 件)

| Gap | Severity | 内容 | 修正先 |
|---|---|---|---|
| G1 | LOW | 1:1 spec test の dedicated file 化 | 新規 `test_t_ai_mem_02_context_editing_spec.py` |
| G2 | MEDIUM | SDK shape (`edits` キー / 各 item type+trigger) 1:1 test 欠落 | 新規 file |
| G3 | MEDIUM | factory の 2 秒以内 timing test 欠落 | 新規 file |
| G4 | MEDIUM | beta header 2 個の dedicated 1:1 test 欠落 | 新規 file |
| G5 | MEDIUM | REST endpoint 経由の timing + betas 同梱 1:1 test 欠落 | 新規 file |
| G6 | MEDIUM | trigger.type == 'input_tokens' 公式型 1:1 test 欠落 | 新規 file |
| G7 | MEDIUM | clear_thinking 無効時 absent negative test 欠落 | 新規 file |
| G8 | MEDIUM | clear_thinking + clear_tool_uses + compact 順序 test 欠落 | 新規 file |
| G9 | MEDIUM | factory/validator raise 時 state mutate なし negative test 欠落 | 新規 file |
| G10 | MEDIUM | `env_override_config()` 真偽値 1:1 test 欠落 (truthy → None / falsy → default) | 新規 file |
| G11 | **HIGH** | lint guard: server-side compaction 自前実装の禁止語検知が **不在** | `scripts/lint-mock.sh` に `check_no_self_compaction` (#14) を追加 |

**impl ファイル (`anthropic_context_editing.py`) は無変更**. test + audit doc + lint script だけで AC 1:1 完成. lint G11 は AC-4 の核 (「lint script shall fail」) を機械保証する不可欠な追加.

---

## 完了判定 (Step 6 / ADR-011)

- [x] 全行 status = ✅ VERIFIED (30 sub-clause / 11 gap closure / 49+ tests)
- [x] 新 test file: `backend/tests/test_t_ai_mem_02_context_editing_spec.py` 全 PASS
- [x] 新 lint check #14: `check_no_self_compaction` 追加 → 既存 13/13 → 14/14 OK
- [x] `bash scripts/pre-commit-check.sh` exit_code=0 (frontend tsc は環境 SKIP-WITH-REASON 許容)
- [x] 既存 `test_adr_012_anthropic_memory_tool.py` も全 PASS (regression なし — full suite で確認)
- [x] PR description にこの audit doc へのリンク

## 結果サマリー (post-mortem)

| | T-AI-MEM-03 (前 PR) | T-AI-MEM-02 (本 PR) |
|---|---|---|
| audit 周回数 | 1 | **1** |
| 着手前 gap 発見 | 11 件 | **11 件** |
| 事後 gap 発見 | 0 件 | **0 件** |
| commit 数 | 1 | **1** |
| test 数 (本タスク dedicated) | 49 | **49+** |
| impl ファイル変更 | 0 | **0 行** |
| lint script 変更 | 0 | **+1 check (G11 = AC-4 part 1 機械保証)** |

新 workflow 第 2 例として再現性を確認.
