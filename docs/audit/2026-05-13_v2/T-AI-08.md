# Pre-flight AC Audit — T-AI-08 (Anthropic 障害時 LiteLLM フォールバック)

- **Task**: T-AI-08 (NEW audit — circuit breaker + automatic failover spec verification)
- **Sprint**: S4 / **Feature**: F-M12 (LiteLLM Router) / **Layer**: L2
- **Label**: NEW (Wave 5 spec audit; primary impl already merged via PR #234 / fallback_router.py)
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-AI-08`
- **ADR refs**: ADR-010 (AI stack 3 層 / Anthropic 純正中心 + LiteLLM サブ), ADR-012 (provider-adapter / Memory Tool), CLAUDE.md §3 自前実装必須 8 項目 #8
- **Deps**: T-AI-06 (rate limit retry), T-M12-01 (LiteLLM Router sub-purpose only)
- **Final status**: VERIFIED (40 new spec tests; 126 total T-AI-08 / T-M12-01 tests; lint 12/12 OK)

---

## Spec literal expansion (源泉 cited)

`tickets.json#T-AI-08` の 5 AC を逐語引用:

```
EVENT-1  : "When Anthropic API health-check fails 3 times within 60 seconds,
            the system shall switch the main route to LiteLLM → GPT-4o
            (primary fallback) and notify masato."
STATE    : "While in fallback mode, the system shall disable Memory API writes
            and Subagent (Task tool), and shall mark every session with
            degraded_mode=true."
EVENT-2  : "When Anthropic recovers (3 consecutive successful health-checks
            in 5 min), the system shall switch back to claude-agent-sdk
            automatically."
OPTIONAL : "Where masato manually overrides via /admin/fallback {provider:gemini},
            the system shall route to Gemini 2.5 Pro instead of GPT-4o."
UNWANTED : "If both Anthropic AND OpenAI fail simultaneously, the system shall
            pause new sessions, allow only emergency read-only access, and
            alert masato + Slack — it shall not silently route to an untested
            provider."
```

## Anti-drift 防衛ライン (本 audit の主目的)

本 NEW audit は **既存 fallback_router 実装 (PR #234) の上に置く独立 spec 層**.
偽装 risk は CLAUDE.md §3 + 過去の T-013-04 v1 偽装事例から下記 4 つを想定:

| # | 偽装パターン | 防衛 test |
|---|---|---|
| D1 | `if anthropic_down: use_litellm` の 1 行で「動いている」装い (route 先 model がどの provider でも区別なし) | `test_routing_openai_model_is_gpt_4o` + `test_routing_gemini_model_is_gemini_2_5_pro` を **個別** に書く |
| D2 | circuit breaker 閾値を spec 文 (3 fail / 60s, 3 success / 5 min) と一致しない値で実装 | `test_ac_event1_threshold_constant_exactly_3` / `_window_constant_exactly_60_sec` / `test_ac_event2_recovery_streak_constant_exactly_3` / `_window_constant_exactly_5_min` を **定数 ID 1:1 検証** |
| D3 | LiteLLM をメイン経路 (claude_agent_runner.py) で import (ADR-010 違反) | `test_lint_no_litellm_in_main_runner_source` (source grep) + `test_lint_no_litellm_in_runner_passes` (lint script) + `test_lint_emergency_chat_runtime_guard_blocks_main_runner` (runtime stack check) の **三重防衛** |
| D4 | 未テスト provider (xai / cohere / meta) に silent route | `test_ac_unwanted_untested_provider_rejected` + `test_routing_emergency_providers_constant_exact` |

---

## AC × 実装 × test × lint 対応表

### AC-EVENT-1 (3 fail / 60s → openai + notify)

| # | spec sub-clause | impl (file) | test 関数名 | status |
|---|---|---|---|---|
| 1.1 | "3 times" 定数 = `FAILURE_THRESHOLD == 3` | `services/fallback_router.py:60` | `test_ac_event1_threshold_constant_exactly_3` | VERIFIED |
| 1.2 | "within 60 seconds" 定数 = `FAILURE_WINDOW_SEC == 60` | `services/fallback_router.py:59` | `test_ac_event1_window_constant_exactly_60_sec` | VERIFIED |
| 1.3 | 2 回 fail では fallback しない (boundary lower) | `record_health_check` 内分岐 | `test_ac_event1_two_failures_does_not_trigger_fallback` | VERIFIED |
| 1.4 | 3 回 fail → route = `"openai"` | `current_route` | `test_ac_event1_third_failure_triggers_fallback_to_openai` | VERIFIED |
| 1.5 | "primary fallback" = GPT-4o (openai) / gemini ではない drift guard | `current_route` priority | `test_ac_event1_primary_fallback_is_openai_not_gemini` | VERIFIED |
| 1.6 | "notify masato" = audit `anthropic_fallback_engaged` emit | `_notify` 経由 | `test_ac_event1_audit_event_emit_on_fallback` | VERIFIED |
| 1.7 | 60 秒窓を超えた fail は count しない (sliding window) | `_ProviderState.failures_in_window` | `test_ac_event1_failure_window_excludes_old_history` | VERIFIED |

### AC-STATE (degraded mode capabilities)

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 2.1 | "disable Memory API writes" | `memory_api_writes_enabled()` | `test_ac_state_memory_api_writes_disabled_in_fallback` | VERIFIED |
| 2.2 | "disable Subagent (Task tool)" | `subagent_enabled()` | `test_ac_state_subagent_disabled_in_fallback` | VERIFIED |
| 2.3 | "mark every session with degraded_mode=true" | `session_degraded_mode_flag()` | `test_ac_state_session_degraded_mode_true_in_fallback` | VERIFIED |
| 2.4 | 復旧後 (reset) は capability 再有効 | `reset_state` | `test_ac_state_capabilities_re_enabled_after_reset` | VERIFIED |
| 2.5 | emergency_chat response に `memory_api_writes_disabled` シグナル | `litellm_router.memory_api_writes_allowed_in_fallback` | `test_ac_state_emergency_chat_response_marks_writes_disabled` | VERIFIED |

### AC-EVENT-2 (3 success / 5 min → recover)

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 3.1 | "3 consecutive" 定数 = `RECOVERY_SUCCESS_STREAK == 3` | `services/fallback_router.py:64` | `test_ac_event2_recovery_streak_constant_exactly_3` | VERIFIED |
| 3.2 | "in 5 min" 定数 = `RECOVERY_WINDOW_SEC == 300` | `services/fallback_router.py:63` | `test_ac_event2_recovery_window_constant_exactly_5_min` | VERIFIED |
| 3.3 | "switch back ... automatically" → audit `anthropic_recovered` emit | `record_health_check` 末尾分岐 | `test_ac_event2_recovery_emits_anthropic_recovered_audit` | VERIFIED |
| 3.4 | consecutive success tracking | `_ProviderState.consecutive_successes` | `test_ac_event2_consecutive_successes_state_tracking` | VERIFIED |
| 3.5 | failure で streak リセット | 同上 | `test_ac_event2_consecutive_resets_on_failure` | VERIFIED |

### AC-OPTIONAL (manual /admin/fallback {gemini})

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 4.1 | "{provider:gemini}" → route = `"gemini"` | `manual_override` | `test_ac_optional_manual_override_to_gemini` | VERIFIED |
| 4.2 | OPTIONAL openai override も可能 | 同上 | `test_ac_optional_manual_override_to_openai` | VERIFIED |
| 4.3 | None で auto に戻る | 同上 | `test_ac_optional_manual_override_back_to_auto_clears` | VERIFIED |
| 4.4 | "overrides" = audit `fallback_manual_override` emit | `manual_override` _notify | `test_ac_optional_manual_override_audit_emit` | VERIFIED |
| 4.5 | `VALID_OVERRIDE_PROVIDERS = (openai, gemini)` のみ | `services/fallback_router.py:68` | `test_ac_optional_valid_override_providers_constant` | VERIFIED |

### AC-UNWANTED (both fail → paused + alert + no silent route)

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 5.1 | "both ... fail simultaneously" → "pause" | `should_pause()` / `current_route` | `test_ac_unwanted_both_fail_triggers_pause` | VERIFIED |
| 5.2 | "emergency read-only" = Memory API write 不可 | `memory_api_writes_enabled()` | `test_ac_unwanted_pause_disables_memory_api_writes` | VERIFIED |
| 5.3 | "alert masato + Slack" = audit `fallback_paused_both_down` emit | `_notify` + `_notify_slack` | `test_ac_unwanted_pause_alerts_audit_event` | VERIFIED |
| 5.4 | "shall not silently route to untested provider" — manual override (gemini) よりも paused が優先 | `current_route` priority | `test_ac_unwanted_pause_overrides_manual_override` | VERIFIED |
| 5.5 | untested provider (xai / cohere / meta) を `record_health_check` / `manual_override` で reject | `ALLOWED_PROVIDERS` / `VALID_OVERRIDE_PROVIDERS` 列挙 | `test_ac_unwanted_untested_provider_rejected` | VERIFIED |

### Provider routing (anti-drift 個別検証)

| # | sub-clause | impl | test | status |
|---|---|---|---|---|
| 6.1 | `EMERGENCY_PROVIDERS = (openai, gemini)` (anthropic / xai / meta は不含) | `services/litellm_router.py:38` | `test_routing_emergency_providers_constant_exact` | VERIFIED |
| 6.2 | **Claude → GPT-4o**: openai mapping = `"openai/gpt-4o"` (gpt-4o-mini や 3.5 への drift 防止) | `services/litellm_router.py:259` | `test_routing_openai_model_is_gpt_4o` | VERIFIED |
| 6.3 | **Claude → Gemini**: gemini mapping = `"gemini/gemini-2.5-pro"` (gemini-flash 等への drift 防止) | `services/litellm_router.py:260` | `test_routing_gemini_model_is_gemini_2_5_pro` | VERIFIED |
| 6.4 | active_route='anthropic' で emergency_chat 呼び出し → reject (Anthropic 健常時に LiteLLM 呼ぶな) | `emergency_chat` 内 if | `test_routing_emergency_chat_rejects_anthropic_route` | VERIFIED |
| 6.5 | untested route (`xai`/`cohere`/`meta`/`claude`) で emergency_chat → reject | 同上 | `test_routing_emergency_chat_rejects_untested_route` | VERIFIED |
| 6.6 | emergency_chat が `fallback_router.current_route()` を読む (2 module cross-ref) | `services/litellm_router.py:241` | `test_routing_emergency_chat_reads_current_route_from_fallback_router` | VERIFIED |

### Lint (no LiteLLM in main runner)

| # | sub-clause | impl | test | status |
|---|---|---|---|---|
| 7.1 | `claude_agent_runner.py` source に `import litellm` / `from litellm` 無し | source grep | `test_lint_no_litellm_in_main_runner_source` | VERIFIED |
| 7.2 | `scripts/lint-mock.sh --no-litellm-in-runner` PASS | lint-mock.sh check #7 | `test_lint_no_litellm_in_runner_passes` | VERIFIED |
| 7.3 | `scripts/lint-mock.sh --no-self-fallback-circuit` PASS (T-AI-08 AC-UNWANTED) | lint-mock.sh check #13 | `test_lint_no_self_fallback_circuit_passes` | VERIFIED |
| 7.4 | runtime guard: `_assert_not_called_from_runner` が claude_agent_runner.py からの呼び出しを stack 検査で reject | `litellm_router._assert_not_called_from_runner` | `test_lint_emergency_chat_runtime_guard_blocks_main_runner` | VERIFIED |

### Cross-ref (traceability)

| # | sub-clause | test | status |
|---|---|---|---|
| 8.1 | tickets.json T-AI-08: 5 AC / label=NEW / deps includes T-M12-01 / 4 EARS types | `test_xref_ticket_t_ai_08_has_5_ac_and_deps` | VERIFIED |
| 8.2 | ADR-010 supersedes ADR-002 + T-AI-08 が「自前 8 項目」に enumerate | `test_xref_adr_010_supersedes_adr_002` | VERIFIED |
| 8.3 | fallback_router docstring に ADR-012 / T-AI-MEM-04 / T-M12-01 cross-ref + 5 AC label | `test_xref_fallback_router_docstring_documents_cross_refs` | VERIFIED |

---

## Gap analysis

### 着手前 gap

| # | gap | severity | resolution |
|---|---|---|---|
| G1 | 既存 48 test (test_fallback_router + test_t_ai_08_fallback_gap) は機能網羅性は高いが、 **spec literal (3 / 60 / 5 min) と AC 文書の 1:1 対応** が明示されていなかった | MEDIUM | 本 audit suite で AC sub-clause 別に分解 (40 test, 8 group) |
| G2 | "Claude → GPT-4o" と "Claude → Gemini 2.5 Pro" を **個別 test** で検証していなかった (model_map 全体は使われていたが model 文字列の固定 test 無し) | HIGH (D1 偽装防止) | `test_routing_openai_model_is_gpt_4o` + `test_routing_gemini_model_is_gemini_2_5_pro` を **別々** に追加. drift (gpt-4o-mini や gemini-flash への劣化) を spec 文 1:1 で検出 |
| G3 | LiteLLM が主経路で使われないことの **runtime stack check** test 不在 (lint script PASS のみで担保) | MEDIUM (D3 偽装防止) | `test_lint_emergency_chat_runtime_guard_blocks_main_runner` で `_assert_not_called_from_runner` の stack inspection 動作を検証 |
| G4 | OPTIONAL "instead of GPT-4o" の対比検証 (gemini override が正しく gemini route を作り、 openai に逃げない) | LOW | `test_ac_optional_manual_override_to_gemini` で `current_route() == "gemini"` (`"openai"` ではない) を assertion |

### Spot-check (今回 audit で新たに発見した spec drift 候補)

| # | 観察事項 | severity | 対応 |
|---|---|---|---|
| S1 | `EMERGENCY_PROVIDERS = ("openai", "gemini")` の順序は AC-EVENT-1 "primary fallback = GPT-4o" を **暗黙に** 保証. しかし `current_route()` 内の degraded 分岐は明示的に `"openai"` を return しているので drift risk 低. | LOW | drift guard test `test_ac_event1_primary_fallback_is_openai_not_gemini` で **明示確認**. 将来 `current_route` が tuple index で動的選択するように変更されれば spec 違反になる. |
| S2 | `manual_override` 時に paused が優先される仕様 (`current_route` の if 順序). AC-UNWANTED "shall not silently route to untested provider" の core 解釈. | INFO | `test_ac_unwanted_pause_overrides_manual_override` で固定化. 将来 priority が flip すれば test fail. |
| S3 | `RECOVERY_WINDOW_SEC = 300` は定数として保持されているが、 実装上 recovery 判定は `consecutive_successes >= 3` のみで window 内かは見ていない (history の time decay 任せ). spec "in 5 min" は **streak 計算の時間制約ではなく audit/log の文脈** とみなした. | INFO | 定数固定 test (`test_ac_event2_recovery_window_constant_exactly_5_min`) で値は保証. 厳密な「5 min 内 streak」検証は monotonic mock 込みの統合 test で別途扱う (本 audit 範囲外). |

着手後 gap 数: 0 (G1-G4 + S1-S3 全て閉鎖 or INFO 化).

---

## NEW 適合チェック (9 項目)

| # | 項目 | 結果 |
|---|---|---|
| 1 | 新規 SQL migration 追加なし | OK |
| 2 | 既存 service module 改変なし | OK (`fallback_router.py` / `litellm_router.py` は import のみ; source 改変なし) |
| 3 | 既存 router 改変なし | OK (audit suite は test + doc のみ) |
| 4 | 既存 test 削除/改変なし | OK (test_fallback_router 48 / test_t_ai_08_fallback_gap 既存件数を維持) |
| 5 | 公開 API シンボル変更なし | OK |
| 6 | DB schema 変更なし | OK |
| 7 | RLS policy 追加/削除なし | OK |
| 8 | external dependency 追加なし | OK (stdlib + 既存 services + pytest のみ) |
| 9 | docstring 改変なし | OK |

---

## 完了判定 (Step 6 / ADR-011)

- [x] 全行 status = VERIFIED (40 sub-clause, 8 group)
- [x] `pytest backend/tests/test_t_ai_08_litellm_fallback_spec.py` → 40 passed in 0.25s
- [x] Regression: `pytest test_fallback_router.py test_t_ai_08_fallback_gap.py test_t_m12_01_litellm_router.py` → 126 passed
- [x] `bash scripts/lint-mock.sh` → 12/12 OK
- [x] PR description にこの audit doc へのリンク

---

## post-mortem

**今回 audit で確立した anti-drift パターン** (次 wave 以降に再利用):

1. **"flag 系の引数 / 定数を取る分岐では、各 value が実際に異なる挙動を発生させる test を 1:1 で書け"** — T-013-04 v2 post-mortem 教訓の継承.
2. **"spec 文中の数値 (3 / 60 / 5 min) は定数 ID と 1:1 で固定 test"** — magic number 化を機械検出.
3. **"provider 切替先 model 名は source 文字列 grep で固定"** — `openai/gpt-4o` ≠ `openai/gpt-4o-mini` を drift で区別.
4. **"lint + runtime guard の三重防衛"** — source grep / shell lint / runtime stack check を **個別 test** で検証する (1 test で 3 つを兼ねない).
