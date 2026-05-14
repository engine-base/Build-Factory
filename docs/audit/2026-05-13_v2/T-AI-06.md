# Pre-flight AC Audit (retroactive) — T-AI-06 (Rate limit 自動 retry (anthropic_retry.with_retry + retryable_anthropic_call decor)

- **Task**: T-AI-06 (Rate limit 自動 retry (anthropic_retry.with_retry + retryable_anthropic_call decorator + tenacity AsyncRetrying + StopByEx)
- **Sprint**: S2 / **Feature**: F-AI / **Layer**: L2
- **Slice**: S2 / **Wave**: 2.2
- **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-AI-06`
- **Deps**: T-S0-08
- **Status**: ✅ VERIFIED (retroactive — 実装+test 共に既存, post-hoc 検証で全 PASS 確認)

> **retroactive audit**: 本タスクは 2026-05-13 の pre-flight audit workflow 制定**前**に
> 既に実装+test ともに完了していた (bootstrap または初期実装フェーズで)。
> commit message に明示的な task ID 記載が無かったため `done_status='pending'` 扱いだったが、
> existing_files の実在確認 + 全 test PASS で **機能的に done と確定**。
> 本 audit MD はその retroactive 検証記録。

---

## 既存実装 (existing_files)

- ✅ `backend/services/anthropic_retry.py`

## 既存 test ファイル

- `backend/tests/test_t_ai_06_retry_spec_invariants.py` (25 test 関数)

## AC × test 1:1 対応 (post-hoc mapping)

### AC-1 UBIQUITOUS

> backend/services/anthropic_retry.py shall expose with_retry(coro_factory, *, idempotency_key=None, session_id=None, user_id=None, label='anthropic_call') and retryable_anthropic_call(*, label='anthropic_call') decorator + RetryExhaustedError(RuntimeError) + is_retryable(exc) helper; the retry engine shall use tenacity.AsyncRetrying with retry=retry_if_exception(is_retryable), reraise=True (ADR-010: anthropic SDK 0.52+ main path, no langgraph / langchain / litellm in this module).

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 1.1 | `test_ac1_module_exists` | `test_t_ai_06_retry_spec_invariants.py` | 46 | ✅ VERIFIED |
| 1.2 | `test_ac1_with_retry_callable` | `test_t_ai_06_retry_spec_invariants.py` | 50 | ✅ VERIFIED |
| 1.3 | `test_ac1_with_retry_signature` | `test_t_ai_06_retry_spec_invariants.py` | 56 | ✅ VERIFIED |
| 1.4 | `test_ac1_retryable_decorator_signature` | `test_t_ai_06_retry_spec_invariants.py` | 66 | ✅ VERIFIED |
| 1.5 | `test_ac1_retry_exhausted_error_is_runtime_error` | `test_t_ai_06_retry_spec_invariants.py` | 75 | ✅ VERIFIED |
| 1.6 | `test_ac1_is_retryable_helper_exists` | `test_t_ai_06_retry_spec_invariants.py` | 80 | ✅ VERIFIED |
| 1.7 | `test_ac1_uses_async_retrying_with_reraise_true` | `test_t_ai_06_retry_spec_invariants.py` | 85 | ✅ VERIFIED |
| 1.8 | `test_ac1_no_langgraph_langchain_litellm` | `test_t_ai_06_retry_spec_invariants.py` | 95 | ✅ VERIFIED |

### AC-2 EVENT-DRIVEN

> When the wrapped call raises an exception with status_code in {429, 529}, the system shall retry up to RATE_LIMIT_MAX_ATTEMPTS = 5 total attempts (4 retries: 2s, 4s, 8s, 16s) via wait_exponential(multiplier=2, min=2, max=16, exp_base=2); when status_code is in range(500, 600) (transient 5xx) or the exception is ConnectionError / TimeoutError / asyncio.TimeoutError, the system shall retry up to TRANSIENT_5XX_MAX_ATTEMPTS = 4 total attempts (3 retries); on exhaustion the system shall raise RetryExhaustedError(last_exc, attempts) chained via 'raise ... from e' and emit 'anthropic_retry_exhausted' audit event.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 2.1 | `test_ac2_retryable_status_codes_429_529` | `test_t_ai_06_retry_spec_invariants.py` | 113 | ✅ VERIFIED |
| 2.2 | `test_ac2_max_attempts_constants` | `test_t_ai_06_retry_spec_invariants.py` | 119 | ✅ VERIFIED |
| 2.3 | `test_ac2_wait_exponential_2_to_16` | `test_t_ai_06_retry_spec_invariants.py` | 127 | ✅ VERIFIED |
| 2.4 | `test_ac2_5xx_or_conn_timeout_retried` | `test_t_ai_06_retry_spec_invariants.py` | 135 | ✅ VERIFIED |
| 2.5 | `test_ac2_exhaustion_raises_retry_exhausted_with_chain` | `test_t_ai_06_retry_spec_invariants.py` | 158 | ✅ VERIFIED |

### AC-3 STATE-DRIVEN

> While retrying, the same idempotency_key + session_id + user_id are passed to every audit emit and preserved across attempts (callers route _session_id / _user_id / _idempotency_key kwargs into with_retry via the decorator); StopByExceptionType subclasses tenacity.stop.stop_base and selects RATE_LIMIT_MAX_ATTEMPTS vs TRANSIENT_5XX_MAX_ATTEMPTS based on _status_code_of(exc) so the policy is state-aware (not a single max-attempts constant).

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 3.1 | `test_ac3_stop_by_exception_type_inherits_stop_base` | `test_t_ai_06_retry_spec_invariants.py` | 173 | ✅ VERIFIED |
| 3.2 | `test_ac3_stop_picks_rate_limit_vs_5xx_max` | `test_t_ai_06_retry_spec_invariants.py` | 179 | ✅ VERIFIED |
| 3.3 | `test_ac3_decorator_routes_idempotency_session_user_id` | `test_t_ai_06_retry_spec_invariants.py` | 194 | ✅ VERIFIED |

### AC-4 OPTIONAL

> Where the exception lacks a status_code attribute but has .response.status_code (httpx.HTTPStatusError shape), _status_code_of(exc) shall extract it via getattr(exc, 'response', None).status_code so the retry policy still applies; where audit emit fails (memory_service unavailable), the module shall log a warning and continue (audit failure must not break the retry path).

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 4.1 | `test_ac4_status_code_fallback_to_response_attr` | `test_t_ai_06_retry_spec_invariants.py` | 216 | ✅ VERIFIED |
| 4.2 | `test_ac4_status_code_direct_attr_takes_precedence` | `test_t_ai_06_retry_spec_invariants.py` | 231 | ✅ VERIFIED |
| 4.3 | `test_ac4_audit_emit_failure_logged_not_raised` | `test_t_ai_06_retry_spec_invariants.py` | 240 | ✅ VERIFIED |

### AC-5 UNWANTED

> If a non-retryable 4xx (e.g. 400 / 401 / 403 / 404 / 422) is raised, is_retryable(exc) shall return False, the retry engine shall reraise immediately (no backoff), and the system shall emit an 'anthropic_non_retryable' audit event with the status_code + exception type; the module shall not import langgraph / langchain / litellm (ADR-010), shall not retry indefinitely (stop-after-attempt invariant), and shall not contain hardcoded Supabase / Anthropic credentials.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 5.1 | `test_ac5_non_retryable_4xx_returns_false` | `test_t_ai_06_retry_spec_invariants.py` | 258 | ✅ VERIFIED |
| 5.2 | `test_ac5_non_retryable_immediate_reraise_and_audit` | `test_t_ai_06_retry_spec_invariants.py` | 271 | ✅ VERIFIED |
| 5.3 | `test_ac5_no_hardcoded_supabase_or_anthropic_key` | `test_t_ai_06_retry_spec_invariants.py` | 288 | ✅ VERIFIED |

## AC 未紐付 test (cross-cutting / regression)

- `test_tickets_t_ai_06_canonical_ears` (`test_t_ai_06_retry_spec_invariants.py:299`)
- `test_tickets_t_ai_06_has_adr_link_and_files` (`test_t_ai_06_retry_spec_invariants.py:311`)
- `test_tickets_t_ai_06_ac_mentions_concrete_symbols` (`test_t_ai_06_retry_spec_invariants.py:320`)

## 完了判定 (ADR-011 単一ゲート)

- [x] existing_files 全件が repo に実在
- [x] test ファイル (1 件) 全 PASS (post-hoc 一括実行で確認)
- [x] AC 5 件すべてに test 関数または cross-cutting カバレッジが対応
- [x] `bash scripts/lint-mock.sh` 16/16 OK (repo 全体)
- [x] `python3 scripts/verify-slice.py T-AI-06` PASS

---

_自動生成 by `scripts/generate-audit-mds.py` (2026-05-14)_