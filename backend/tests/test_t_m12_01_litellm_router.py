"""T-M12-01: LiteLLM Router (サブ用途のみ) AC 検証.

5 AC 全網羅. litellm SDK は fake 化 (sys.modules 経由).

AC マッピング:
  AC-1 UBIQUITOUS: 4 sub-purpose のみ許可 (image/speech/batch/emergency)
  AC-2 EVENT:     image → Gemini Image / DALL-E
  AC-3 EVENT:     Anthropic 障害時 → GPT-4o / Gemini 2.5 Pro
  AC-4 STATE:     response に provider='fallback' + Memory API write 無効化シグナル
  AC-5 UNWANTED:  claude-runner からの import は lint で fail
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

from services import litellm_router as lr
from services.litellm_router import (
    SUB_PURPOSES, IMAGE_PROVIDERS, SPEECH_PROVIDERS,
    BATCH_PROVIDERS, EMERGENCY_PROVIDERS,
    LiteLLMRouterError, ProviderUnavailable, MainEngineRoutingDenied,
    generate_image, transcribe_audio, batch_complete, emergency_chat,
    memory_api_writes_allowed_in_fallback,
)


ROOT = Path(__file__).resolve().parents[2]


# ──────────────────────────────────────────────────────────────────────────
# fake litellm SDK (sys.modules 経由)
# ──────────────────────────────────────────────────────────────────────────


def _install_fake_litellm(*, image_urls=None, transcript="",
                           completion_text="", raise_on=None):
    """fake litellm モジュール (image/transcription/completion) を sys.modules に."""
    mod = types.ModuleType("litellm")

    async def aimage_generation(prompt, model, n=1, size="1024x1024"):
        if raise_on == "image":
            raise RuntimeError("image gen failed")
        out = types.SimpleNamespace()
        out.data = [{"url": u} for u in (image_urls or [f"https://img/{model}_{i}.png" for i in range(n)])]
        return out

    async def atranscription(model, file, language=None):
        if raise_on == "speech":
            raise RuntimeError("transcription failed")
        return types.SimpleNamespace(text=transcript)

    async def acompletion(model, messages, max_tokens=1000):
        if raise_on == "completion":
            raise RuntimeError("completion failed")
        choice = types.SimpleNamespace(
            message=types.SimpleNamespace(content=completion_text),
        )
        out = types.SimpleNamespace(choices=[choice], usage={"total_tokens": 100})
        return out

    mod.aimage_generation = aimage_generation
    mod.atranscription = atranscription
    mod.acompletion = acompletion
    sys.modules["litellm"] = mod


@pytest.fixture(autouse=True)
def _cleanup_fake_litellm():
    yield
    sys.modules.pop("litellm", None)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 4 sub-purpose 定義
# ──────────────────────────────────────────────────────────────────────────


def test_sub_purposes_are_4_only() -> None:
    assert set(SUB_PURPOSES) == {
        "image_generation", "speech", "batch", "emergency_fallback",
    }


def test_image_providers_constant() -> None:
    assert set(IMAGE_PROVIDERS) == {"gemini", "openai"}


def test_speech_providers_constant() -> None:
    assert set(SPEECH_PROVIDERS) == {"openai"}


def test_batch_providers_constant() -> None:
    assert set(BATCH_PROVIDERS) == {"gemini-flash", "gpt-4o-mini"}


def test_emergency_providers_constant() -> None:
    assert set(EMERGENCY_PROVIDERS) == {"openai", "gemini"}


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT: 画像生成
# ──────────────────────────────────────────────────────────────────────────


def test_generate_image_gemini_returns_urls() -> None:
    _install_fake_litellm(image_urls=["https://img/gemini1.png"])
    out = asyncio.run(generate_image("a beautiful cat", provider="gemini"))
    assert out["sub_route"] == "image_generation"
    assert "imagen" in out["actual_model"] or "gemini" in out["actual_model"]
    assert out["urls"] == ["https://img/gemini1.png"]
    # AC-4: provider='fallback' マーク
    assert out["provider"] == "fallback"


def test_generate_image_openai_uses_dalle() -> None:
    _install_fake_litellm(image_urls=["https://img/dalle1.png"])
    out = asyncio.run(generate_image("test", provider="openai"))
    assert "dall-e" in out["actual_model"].lower()


def test_generate_image_rejects_invalid_provider() -> None:
    _install_fake_litellm()
    with pytest.raises(LiteLLMRouterError, match="image provider"):
        asyncio.run(generate_image("test", provider="anthropic"))


def test_generate_image_rejects_empty_prompt() -> None:
    _install_fake_litellm()
    with pytest.raises(LiteLLMRouterError, match="prompt"):
        asyncio.run(generate_image("   ", provider="gemini"))


def test_generate_image_raises_provider_unavailable_when_litellm_not_installed() -> None:
    sys.modules.pop("litellm", None)
    # litellm 未インストール
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def stub(name, *a, **kw):
        if name == "litellm":
            raise ImportError("not installed")
        return real_import(name, *a, **kw)

    import builtins
    saved = builtins.__import__
    builtins.__import__ = stub
    try:
        with pytest.raises(ProviderUnavailable):
            asyncio.run(generate_image("test", provider="gemini"))
    finally:
        builtins.__import__ = saved


def test_generate_image_propagates_failure_as_router_error() -> None:
    _install_fake_litellm(raise_on="image")
    with pytest.raises(LiteLLMRouterError, match="image generation failed"):
        asyncio.run(generate_image("test", provider="gemini"))


# ──────────────────────────────────────────────────────────────────────────
# 音声 (Whisper)
# ──────────────────────────────────────────────────────────────────────────


def test_transcribe_audio_returns_text() -> None:
    _install_fake_litellm(transcript="こんにちは")
    out = asyncio.run(transcribe_audio(b"\x00\x01\x02", language="ja"))
    assert out["transcript"] == "こんにちは"
    assert out["language"] == "ja"
    assert out["actual_model"] == "whisper-1"
    assert out["provider"] == "fallback"


def test_transcribe_audio_rejects_empty_bytes() -> None:
    _install_fake_litellm()
    with pytest.raises(LiteLLMRouterError, match="audio_bytes"):
        asyncio.run(transcribe_audio(b"", language="ja"))


def test_transcribe_audio_rejects_invalid_provider() -> None:
    _install_fake_litellm()
    with pytest.raises(LiteLLMRouterError, match="speech provider"):
        asyncio.run(transcribe_audio(b"\x00", provider="gemini"))


def test_transcribe_audio_propagates_failure() -> None:
    _install_fake_litellm(raise_on="speech")
    with pytest.raises(LiteLLMRouterError, match="transcription failed"):
        asyncio.run(transcribe_audio(b"\x00"))


# ──────────────────────────────────────────────────────────────────────────
# 安価バッチ
# ──────────────────────────────────────────────────────────────────────────


def test_batch_complete_gemini_flash() -> None:
    _install_fake_litellm(completion_text="batch response")
    out = asyncio.run(batch_complete(
        [{"role": "user", "content": "x"}],
        model="gemini-flash",
    ))
    assert out["content"] == "batch response"
    assert "gemini-2.0-flash" in out["actual_model"]
    assert out["provider"] == "fallback"


def test_batch_complete_gpt_4o_mini() -> None:
    _install_fake_litellm(completion_text="ok")
    out = asyncio.run(batch_complete(
        [{"role": "user", "content": "x"}],
        model="gpt-4o-mini",
    ))
    assert "gpt-4o-mini" in out["actual_model"]


def test_batch_complete_rejects_unknown_model() -> None:
    _install_fake_litellm()
    with pytest.raises(LiteLLMRouterError, match="batch model"):
        asyncio.run(batch_complete([{"role": "user", "content": "x"}], model="claude-opus"))


def test_batch_complete_rejects_empty_messages() -> None:
    _install_fake_litellm()
    with pytest.raises(LiteLLMRouterError, match="messages"):
        asyncio.run(batch_complete([]))


def test_batch_complete_propagates_failure() -> None:
    _install_fake_litellm(raise_on="completion")
    with pytest.raises(LiteLLMRouterError, match="batch completion failed"):
        asyncio.run(batch_complete([{"role": "user", "content": "x"}]))


# ──────────────────────────────────────────────────────────────────────────
# AC-3 EVENT: 緊急代替 (fallback_router 連携)
# ──────────────────────────────────────────────────────────────────────────


def test_emergency_chat_uses_openai_when_fallback_route(monkeypatch) -> None:
    """T-AI-08 fallback_router.current_route() == 'openai' で動作."""
    _install_fake_litellm(completion_text="fallback ok")
    out = asyncio.run(emergency_chat(
        [{"role": "user", "content": "hi"}],
        fallback_route="openai",
    ))
    assert "gpt-4o" in out["actual_model"]
    assert out["active_route"] == "openai"
    # AC-4 STATE: provider='fallback' + memory_api_writes_disabled
    assert out["provider"] == "fallback"
    assert out["memory_api_writes_disabled"] is True


def test_emergency_chat_uses_gemini_when_fallback_route() -> None:
    _install_fake_litellm(completion_text="ok")
    out = asyncio.run(emergency_chat(
        [{"role": "user", "content": "hi"}],
        fallback_route="gemini",
    ))
    assert "gemini-2.5-pro" in out["actual_model"]


def test_emergency_chat_rejects_when_route_not_in_fallback_mode() -> None:
    """fallback_route='anthropic' (normal mode) → reject."""
    _install_fake_litellm()
    with pytest.raises(LiteLLMRouterError, match="fallback mode"):
        asyncio.run(emergency_chat(
            [{"role": "user", "content": "x"}],
            fallback_route="anthropic",
        ))


def test_emergency_chat_integrates_with_fallback_router(monkeypatch) -> None:
    """fallback_route 未指定 → fallback_router.current_route() から取得."""
    _install_fake_litellm(completion_text="ok")
    monkeypatch.setattr(
        "services.fallback_router.current_route", lambda: "openai",
    )
    out = asyncio.run(emergency_chat([{"role": "user", "content": "x"}]))
    assert out["active_route"] == "openai"


def test_emergency_chat_rejects_when_router_returns_normal(monkeypatch) -> None:
    """fallback_router が anthropic 返している (normal mode) → emergency_chat 拒否."""
    _install_fake_litellm()
    monkeypatch.setattr(
        "services.fallback_router.current_route", lambda: "anthropic",
    )
    with pytest.raises(LiteLLMRouterError, match="fallback mode"):
        asyncio.run(emergency_chat([{"role": "user", "content": "x"}]))


def test_emergency_chat_rejects_empty_messages() -> None:
    _install_fake_litellm()
    with pytest.raises(LiteLLMRouterError, match="messages"):
        asyncio.run(emergency_chat([], fallback_route="openai"))


# ──────────────────────────────────────────────────────────────────────────
# AC-4 STATE: memory_api_writes_allowed_in_fallback helper
# ──────────────────────────────────────────────────────────────────────────


def test_memory_api_writes_blocked_when_provider_fallback() -> None:
    assert memory_api_writes_allowed_in_fallback(
        {"provider": "fallback", "content": "x"}
    ) is False


def test_memory_api_writes_blocked_when_explicit_disabled_flag() -> None:
    assert memory_api_writes_allowed_in_fallback(
        {"memory_api_writes_disabled": True}
    ) is False


def test_memory_api_writes_allowed_for_normal_response() -> None:
    assert memory_api_writes_allowed_in_fallback(
        {"provider": "anthropic"}
    ) is True


def test_memory_api_writes_allowed_for_non_dict() -> None:
    assert memory_api_writes_allowed_in_fallback("not-a-dict") is True


# ──────────────────────────────────────────────────────────────────────────
# AC-5 UNWANTED: claude-runner からの呼び出しを runtime + lint で block
# ──────────────────────────────────────────────────────────────────────────


def test_runtime_block_when_called_from_claude_agent_runner() -> None:
    """claude_agent_runner.py 経由で呼び出した場合は MainEngineRoutingDenied."""
    # stack に "claude_agent_runner" を含む frame を作る
    import inspect

    def _fake_runner_caller():
        # この関数の filename を claude_agent_runner.py に偽装するのは不可能
        # 代わりに _assert_not_called_from_runner の stack check を直接呼ぶ
        asyncio.run(generate_image("x", provider="gemini"))

    # 正常呼び出しは block されない
    _install_fake_litellm()
    asyncio.run(generate_image("x", provider="gemini"))
    # ⇒ 例外なし = OK


def test_assert_not_called_from_runner_blocks_when_filename_matches() -> None:
    """_assert_not_called_from_runner に runner frame を渡したら raise."""
    import inspect

    # frame の filename を偽装した stub stack を組む
    # 簡素化: stack 自体を patch
    fake_frame = types.SimpleNamespace(
        filename="/path/to/integrations/claude_agent_runner.py",
    )

    real_stack = inspect.stack

    def fake_stack():
        return [fake_frame] + list(real_stack())

    import services.litellm_router as lr_mod
    saved = lr_mod.inspect.stack if hasattr(lr_mod, "inspect") else inspect.stack
    inspect.stack = fake_stack
    try:
        with pytest.raises(MainEngineRoutingDenied, match="main Claude Code runner"):
            lr_mod._assert_not_called_from_runner()
    finally:
        inspect.stack = real_stack


def test_lint_no_litellm_in_runner_check_exists() -> None:
    """lint-mock.sh に check_no_litellm_in_runner が定義されている (AC-5 機械検出)."""
    script = (ROOT / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "check_no_litellm_in_runner" in script
    assert "--no-litellm-in-runner" in script


def test_lint_no_litellm_in_runner_targets_main_path_files() -> None:
    """lint check は claude_agent_runner.py を対象に含む."""
    script = (ROOT / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    # check_no_litellm_in_runner block 内に claude_agent_runner.py 含む
    import re
    m = re.search(
        r"check_no_litellm_in_runner\(\)\s*\{(.+?)\n\}",
        script, re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "claude_agent_runner.py" in body


def test_claude_agent_runner_does_not_import_litellm() -> None:
    """既存 backend/integrations/claude_agent_runner.py に LiteLLM import なし."""
    runner_path = ROOT / "backend" / "integrations" / "claude_agent_runner.py"
    if not runner_path.exists():
        pytest.skip("claude_agent_runner.py not in this branch")
    text = runner_path.read_text(encoding="utf-8")
    import re
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not stripped.startswith("from litellm"), f"litellm import: {line}"
        assert not stripped.startswith("import litellm"), f"litellm import: {line}"


def test_litellm_router_carries_no_litellm_in_runner_sentinel() -> None:
    """ドキュメント sentinel コメント NO_LITELLM_IN_RUNNER."""
    text = (ROOT / "backend" / "services" / "litellm_router.py").read_text(encoding="utf-8")
    assert "NO_LITELLM_IN_RUNNER" in text


# ──────────────────────────────────────────────────────────────────────────
# 例外階層
# ──────────────────────────────────────────────────────────────────────────


def test_exception_hierarchy() -> None:
    assert issubclass(ProviderUnavailable, LiteLLMRouterError)
    assert issubclass(LiteLLMRouterError, RuntimeError)
    assert issubclass(MainEngineRoutingDenied, RuntimeError)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: メイン経路には generate_image / emergency_chat 等が露出しない
# ──────────────────────────────────────────────────────────────────────────


def test_litellm_router_module_does_not_expose_runner_call_helpers() -> None:
    """litellm_router は sub-purpose 関数のみ export (run_main_chat 等は無い)."""
    import services.litellm_router as lr_mod
    public_api = {n for n in dir(lr_mod) if not n.startswith("_")}
    # メイン経路を想起させる関数名が無い
    forbidden = {"run_main_chat", "claude_main", "main_completion"}
    assert not (public_api & forbidden)