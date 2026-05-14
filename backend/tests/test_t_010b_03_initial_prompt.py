"""T-010b-03: 初期プロンプト構築 (M-28 経由) 1:1 spec test.

REFACTOR: 既存 context_builder.build_context を REUSE して
build_initial_prompt wrapper を追加. persona ごとに Constitution section 選択 +
memory block + facts を統合した system_prompt を返す.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : persona ごとに section 選択 + memory + decisions 統合
  AC-2 EVENT-DRIVEN  : structured response (success or {detail:{code,message}}) <2sec
  AC-3 STATE-DRIVEN  : backwards-compat 維持 (build_context API 不変)
  AC-4 UNWANTED      : invalid persona → ContextBuilderError → router で 4xx 化
"""
import asyncio
import time
import pytest


# ════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: build_initial_prompt が動く + system_prompt 含む
# ════════════════════════════════════════════════════════════════════


def test_ac1_function_exposed():
    """build_initial_prompt が context_builder から export される."""
    from services import context_builder
    assert hasattr(context_builder, "build_initial_prompt")
    assert callable(context_builder.build_initial_prompt)


@pytest.mark.asyncio
async def test_ac1_secretary_persona_full_constitution(monkeypatch):
    """secretary persona は Constitution 全文 inject."""
    monkeypatch.setenv("SECRETARY_ACTIVE", "true")
    from services.context_builder import build_initial_prompt
    result = await build_initial_prompt(
        user_message="hello",
        session_id=1,
        persona="secretary",
        user_id="masato",
    )
    assert result["persona"] == "secretary"
    assert "system_prompt" in result
    assert isinstance(result["system_prompt"], str)


@pytest.mark.asyncio
async def test_ac1_includes_existing_build_context_keys():
    """build_context の既存返却キーをすべて保持 (backwards-compat)."""
    from services.context_builder import build_initial_prompt
    result = await build_initial_prompt(
        user_message="test",
        session_id=99,
        persona="mary",
    )
    for k in ("memory_block", "decisions", "constitution", "mem0_facts",
              "conflicts", "has_conflicts", "secretary_active"):
        assert k in result, f"key '{k}' missing from result"


# ════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: structured response < 2 sec
# ════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ac2_returns_dict_within_2_seconds():
    """build_initial_prompt が dict を 2 秒以内に返す."""
    from services.context_builder import build_initial_prompt
    t0 = time.time()
    result = await build_initial_prompt(
        user_message="time check",
        session_id=2,
        persona="winston",
    )
    elapsed = time.time() - t0
    assert isinstance(result, dict)
    assert elapsed < 2.0, f"build_initial_prompt took {elapsed}s (need <2)"


@pytest.mark.asyncio
async def test_ac2_response_structure_has_persona_and_system_prompt():
    """response shape: {persona, system_prompt, ...build_context_keys}."""
    from services.context_builder import build_initial_prompt
    result = await build_initial_prompt(
        user_message="shape test",
        session_id=3,
        persona="quinn",
    )
    assert "persona" in result and result["persona"] == "quinn"
    assert "system_prompt" in result
    assert "workspace_id" in result


# ════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: backwards-compat (build_context 不変)
# ════════════════════════════════════════════════════════════════════


def test_ac3_build_context_signature_unchanged():
    """build_context の signature が変わってない (REFACTOR backwards-compat)."""
    import inspect
    from services.context_builder import build_context
    sig = inspect.signature(build_context)
    params = list(sig.parameters.keys())
    expected = ["user_message", "session_id", "prior_session_id", "user_id",
                "top_k", "include_constitution", "secretary_active"]
    for p in expected:
        assert p in params, f"build_context lost parameter: {p}"


@pytest.mark.asyncio
async def test_ac3_build_initial_prompt_uses_build_context_internally():
    """build_initial_prompt は build_context を内部で呼ぶ (REUSE invariant)."""
    import inspect
    from services.context_builder import build_initial_prompt
    src = inspect.getsource(build_initial_prompt)
    assert "build_context" in src, "build_initial_prompt must REUSE build_context"


# ════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid input → ContextBuilderError
# ════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ac4_empty_persona_raises():
    """persona='' → ContextBuilderError."""
    from services.context_builder import build_initial_prompt, ContextBuilderError
    with pytest.raises(ContextBuilderError):
        await build_initial_prompt(
            user_message="hi", session_id=1, persona="",
        )


@pytest.mark.asyncio
async def test_ac4_non_string_persona_raises():
    """persona=int → ContextBuilderError."""
    from services.context_builder import build_initial_prompt, ContextBuilderError
    with pytest.raises(ContextBuilderError):
        await build_initial_prompt(
            user_message="hi", session_id=1, persona=123,
        )


@pytest.mark.asyncio
async def test_ac4_invalid_session_id_raises():
    """session_id=0 → ContextBuilderError (existing build_context invariant)."""
    from services.context_builder import build_initial_prompt, ContextBuilderError
    with pytest.raises(ContextBuilderError):
        await build_initial_prompt(
            user_message="hi", session_id=0, persona="secretary",
        )
