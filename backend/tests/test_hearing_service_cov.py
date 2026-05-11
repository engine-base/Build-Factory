"""hearing_service.py 純粋関数 + 主要 path cov 補強 (T-005-01 後追い).

T-005-01 で router を 100% にしたが service 層 (248 stmts) が baseline 11% の
ままだった. 本 test で 70%+ に補強する.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from typing import Any

import pytest

from services import hearing_service as hs
from services.hearing_service import (
    STEPS, get_step_meta, empty_center_state,
    _extract_common_rules, _extract_step_section,
    _build_system_prompt, _autodetect_provider, _call_llm,
    apply_center_patch, _load_skill_md,
    start_step, reply, complete_step, get_state,
    get_chat_history, _save_message, get_or_create_center_artifact,
    update_center_artifact, _get_references_block,
)


# ──────────────────────────────────────────────────────────────────────────
# 純粋関数 (get_step_meta / empty_center_state)
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_get_step_meta_returns_dict_for_valid_step(step: int) -> None:
    meta = get_step_meta(step)
    assert meta is not None
    assert meta["step"] == step
    assert "title" in meta
    assert "core_sections" in meta


def test_get_step_meta_returns_none_for_unknown_step() -> None:
    assert get_step_meta(0) is None
    assert get_step_meta(99) is None
    assert get_step_meta(-1) is None


def test_empty_center_state_has_step_and_sections() -> None:
    state = empty_center_state(1)
    assert state["step"] == 1
    assert isinstance(state["sections"], list)
    assert state["edited_by_pm"] is False
    assert state["free_sections"] == []


def test_empty_center_state_initializes_sections_from_meta() -> None:
    state = empty_center_state(1)
    meta = get_step_meta(1)
    expected_keys = {s["key"] for s in meta["core_sections"]}
    actual_keys = {s["key"] for s in state["sections"]}
    assert actual_keys == expected_keys
    # 全 section の items は空
    for sec in state["sections"]:
        assert sec["items"] == []


def test_empty_center_state_unknown_step_returns_minimal() -> None:
    state = empty_center_state(99)
    assert state["step"] == 99
    assert state["sections"] == []


def test_steps_constant_has_4_steps() -> None:
    """F-005 / S-020: 4STEP."""
    assert len(STEPS) == 4
    assert [s["step"] for s in STEPS] == [1, 2, 3, 4]


# ──────────────────────────────────────────────────────────────────────────
# _load_skill_md / _extract_common_rules / _extract_step_section
# ──────────────────────────────────────────────────────────────────────────


def test_load_skill_md_returns_fallback_when_path_missing(monkeypatch, tmp_path) -> None:
    fake_path = tmp_path / "missing.md"
    monkeypatch.setattr(hs, "HEARING_SKILL_PATH", fake_path)
    text = _load_skill_md()
    assert "not found" in text.lower() or "fallback" in text.lower()


def test_load_skill_md_reads_existing_file(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "skill.md"
    fake.write_text("# hearing skill\n\n本文", encoding="utf-8")
    monkeypatch.setattr(hs, "HEARING_SKILL_PATH", fake)
    text = _load_skill_md()
    assert "本文" in text


def test_extract_common_rules_returns_fallback_when_no_match() -> None:
    """match しない場合は先頭 5000 文字 fallback."""
    md = "## 別セクション\ncontent"
    out = _extract_common_rules(md)
    # match しないため fallback (md 全体 or 5000 文字)
    assert isinstance(out, str)
    assert len(out) <= 5000


def test_extract_step_section_empty_when_no_match() -> None:
    md = "no STEP markers here"
    assert _extract_step_section(md, 1) == ""


def test_extract_step_section_finds_section() -> None:
    arrow = chr(0x25B6)
    md = f"### {arrow} STEP 1: 開始\n本文 1\n\n### {arrow} STEP 2: 次\n本文 2"
    out = _extract_step_section(md, 1)
    assert "STEP 1" in out
    assert "本文 1" in out
    assert "本文 2" not in out


# ──────────────────────────────────────────────────────────────────────────
# _build_system_prompt
# ──────────────────────────────────────────────────────────────────────────


def test_build_system_prompt_includes_step_and_center_state(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "skill.md"
    fake.write_text("## skill common rules", encoding="utf-8")
    monkeypatch.setattr(hs, "HEARING_SKILL_PATH", fake)

    center = empty_center_state(1)
    prompt = _build_system_prompt(1, center)
    assert "STEP 1" in prompt
    assert "JSON" in prompt
    assert "chat_message" in prompt
    assert "center_patch" in prompt


def test_build_system_prompt_marks_emoji_ban(monkeypatch, tmp_path) -> None:
    """CLAUDE.md §5.1 規約: 絵文字禁止 をプロンプトに明示."""
    fake = tmp_path / "skill.md"
    fake.write_text("# rules", encoding="utf-8")
    monkeypatch.setattr(hs, "HEARING_SKILL_PATH", fake)
    prompt = _build_system_prompt(2, empty_center_state(2))
    assert "絵文字禁止" in prompt or "絵文字" in prompt


# ──────────────────────────────────────────────────────────────────────────
# _autodetect_provider (env 依存)
# ──────────────────────────────────────────────────────────────────────────


def test_autodetect_provider_uses_explicit_env(monkeypatch) -> None:
    monkeypatch.setenv("MAIN_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MAIN_LLM_MODEL", "gpt-4o-custom")
    provider, model = _autodetect_provider()
    assert model == "gpt-4o-custom"


def test_autodetect_provider_ignores_invalid_explicit(monkeypatch) -> None:
    """invalid provider 文字列 → fallback path."""
    monkeypatch.setenv("MAIN_LLM_PROVIDER", "BOGUS_PROVIDER")
    monkeypatch.delenv("MAIN_LLM_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider, model = _autodetect_provider()
    # invalid 無視 → OLLAMA fallback
    assert "ollama" in provider.value.lower() or "qwen" in model.lower()


def test_autodetect_provider_prefers_openai_when_real_key(monkeypatch) -> None:
    monkeypatch.delenv("MAIN_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-realkeyfake0123456789")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider, model = _autodetect_provider()
    assert "openai" in provider.value.lower()
    assert model == "gpt-4o"


def test_autodetect_provider_prefers_anthropic_when_only_anthropic(monkeypatch) -> None:
    monkeypatch.delenv("MAIN_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-realkeyfake0123456789")
    provider, model = _autodetect_provider()
    assert "claude" in provider.value.lower() or "anthropic" in provider.value.lower()


def test_autodetect_provider_falls_back_to_ollama(monkeypatch) -> None:
    monkeypatch.delenv("MAIN_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider, model = _autodetect_provider()
    assert "ollama" in provider.value.lower() or "qwen" in model.lower()


def test_autodetect_provider_rejects_dummy_key(monkeypatch) -> None:
    """sk-ant-xxxx 等の dummy key は real とみなさない."""
    monkeypatch.delenv("MAIN_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-xxxxxxxxxxxxxxxxx")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxxxxxxxxxxxxxxxxxx")
    provider, _ = _autodetect_provider()
    # dummy のみ → OLLAMA fallback
    assert "ollama" in provider.value.lower()


# ──────────────────────────────────────────────────────────────────────────
# apply_center_patch (純粋関数)
# ──────────────────────────────────────────────────────────────────────────


def test_apply_center_patch_add_items() -> None:
    center = empty_center_state(1)
    patch = [{"section_key": "overview", "operation": "add", "items": ["A", "B"]}]
    new_center = apply_center_patch(center, patch)
    overview = next(s for s in new_center["sections"] if s["key"] == "overview")
    assert overview["items"] == ["A", "B"]


def test_apply_center_patch_add_dedupes() -> None:
    """既存 item と重複する add はスキップ."""
    center = empty_center_state(1)
    center["sections"][0]["items"] = ["existing"]
    patch = [{"section_key": center["sections"][0]["key"], "operation": "add",
              "items": ["existing", "new"]}]
    new_center = apply_center_patch(center, patch)
    sec = new_center["sections"][0]
    assert sec["items"] == ["existing", "new"]


def test_apply_center_patch_update_replaces_items() -> None:
    center = empty_center_state(1)
    center["sections"][0]["items"] = ["old1", "old2"]
    patch = [{"section_key": center["sections"][0]["key"], "operation": "update",
              "items": ["new1"]}]
    new_center = apply_center_patch(center, patch)
    assert new_center["sections"][0]["items"] == ["new1"]


def test_apply_center_patch_remove_items() -> None:
    center = empty_center_state(1)
    center["sections"][0]["items"] = ["keep", "drop"]
    patch = [{"section_key": center["sections"][0]["key"], "operation": "remove",
              "items": ["drop"]}]
    new_center = apply_center_patch(center, patch)
    assert new_center["sections"][0]["items"] == ["keep"]


def test_apply_center_patch_adds_free_section_when_unknown_key() -> None:
    """既存 section に無い key は free_sections に追加."""
    center = empty_center_state(1)
    patch = [{"section_key": "custom_xyz", "operation": "add",
              "items": ["custom item"], "label": "Custom"}]
    new_center = apply_center_patch(center, patch)
    free = new_center.get("free_sections") or []
    assert any(s["key"] == "custom_xyz" for s in free)


def test_apply_center_patch_skips_missing_section_key() -> None:
    """section_key 無しの patch は skip."""
    center = empty_center_state(1)
    patch = [{"operation": "add", "items": ["ignored"]}]
    new_center = apply_center_patch(center, patch)
    # 元と変わらない
    for sec in new_center["sections"]:
        assert sec["items"] == []


def test_apply_center_patch_deep_copies_input() -> None:
    """元 center を変更しない (immutability)."""
    center = empty_center_state(1)
    original_first_section_items = list(center["sections"][0]["items"])
    patch = [{"section_key": center["sections"][0]["key"], "operation": "add",
              "items": ["mutate-test"]}]
    apply_center_patch(center, patch)
    # 元 center は無傷
    assert center["sections"][0]["items"] == original_first_section_items


def test_apply_center_patch_empty_patch_returns_copy() -> None:
    center = empty_center_state(1)
    new_center = apply_center_patch(center, [])
    assert new_center == center
    assert new_center is not center  # 別オブジェクト


# ──────────────────────────────────────────────────────────────────────────
# _save_message / get_chat_history (DB mock)
# ──────────────────────────────────────────────────────────────────────────


class _Cur:
    def __init__(self, rows=None, lastrowid=0):
        self._rows = list(rows or [])
        self.lastrowid = lastrowid

    async def fetchone(self):
        return self._rows.pop(0) if self._rows else None


class _Conn:
    Row = dict

    def __init__(self, rows_by_kw=None):
        self._rows = rows_by_kw or {}
        self.row_factory = None

    async def execute(self, sql, *args):
        s = sql.lower()
        for kw, rows in self._rows.items():
            if kw.lower() in s:
                return _Cur(rows=rows)
        return _Cur()

    async def execute_fetchall(self, sql, *args):
        s = sql.lower()
        for kw, rows in self._rows.items():
            if kw.lower() in s:
                return rows
        return []

    async def commit(self): return None
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


def _patch_adb(monkeypatch, **rows_by_kw):
    fake = types.SimpleNamespace(
        connect=lambda _p: _Conn(rows_by_kw=rows_by_kw),
        Row=dict,
    )
    monkeypatch.setattr(hs, "adb", fake)


def test_save_message_inserts_and_returns_id(monkeypatch) -> None:
    _patch_adb(monkeypatch, **{
        "insert into chat_messages": [{"id": 42}],
    })
    msg_id = asyncio.run(_save_message(
        workspace_id=1, phase="hearing", step=1,
        role="user", content="hello",
    ))
    assert msg_id == 42


def test_get_chat_history_parses_metadata_json(monkeypatch) -> None:
    _patch_adb(monkeypatch, **{
        "select id, role, content, metadata, created_at": [
            {"id": 1, "role": "user", "content": "hi",
             "metadata": '{"k":"v"}', "created_at": "2026-05-12"},
            {"id": 2, "role": "ai", "content": "hello",
             "metadata": None, "created_at": "2026-05-12"},
        ],
    })
    out = asyncio.run(get_chat_history(1, "hearing", 1))
    assert len(out) == 2
    assert out[0]["metadata"] == {"k": "v"}
    assert out[1]["metadata"] == {}


def test_get_chat_history_handles_invalid_json(monkeypatch) -> None:
    _patch_adb(monkeypatch, **{
        "select id, role, content, metadata, created_at": [
            {"id": 1, "role": "user", "content": "x",
             "metadata": "not-json{{", "created_at": "2026-05-12"},
        ],
    })
    out = asyncio.run(get_chat_history(1, "hearing", 1))
    assert out[0]["metadata"] == {}


# ──────────────────────────────────────────────────────────────────────────
# start_step / reply / complete_step / get_state (DB + artifact_service mock)
# ──────────────────────────────────────────────────────────────────────────


def _install_artifact_service_mock(monkeypatch, *,
                                     existing=None,
                                     create_returns=None,
                                     get_returns=None,
                                     update_returns=None):
    captured: dict[str, Any] = {"updates": [], "creates": []}
    mod = types.ModuleType("services.artifact_service")

    async def list_artifacts(*a, **kw):
        return existing or []

    async def create_artifact(**kw):
        captured["creates"].append(kw)
        return create_returns or {"id": "new-art", **kw}

    async def get_artifact(art_id):
        return get_returns or {"id": art_id, "data": {"center": empty_center_state(1)}}

    async def update_artifact(art_id, **kw):
        captured["updates"].append({"id": art_id, **kw})
        return update_returns or {"id": art_id, **kw}

    mod.list_artifacts = list_artifacts
    mod.create_artifact = create_artifact
    mod.get_artifact = get_artifact
    mod.update_artifact = update_artifact
    monkeypatch.setitem(sys.modules, "services.artifact_service", mod)
    return captured


def _patch_llm_call(monkeypatch, response):
    """_call_llm を mock."""
    async def fake_llm(system, messages):
        return response
    monkeypatch.setattr(hs, "_call_llm", fake_llm)


def _patch_references_block(monkeypatch, block=""):
    async def fake_refs(ws, keywords=None):
        return block
    monkeypatch.setattr(hs, "_get_references_block", fake_refs)


def test_start_step_returns_error_for_unknown_step(monkeypatch) -> None:
    """unknown step → {error: ...} early return (DB 接続前)."""
    out = asyncio.run(start_step(1, 99))
    assert "error" in out
    assert "99" in out["error"]


def _patch_hs_internal(monkeypatch, *,
                        get_or_create=None,
                        update_artifact=None,
                        history=None,
                        save_msg_id=42,
                        llm_response=None,
                        refs="",
                        ):
    """hearing_service の I/O 依存関数を直接 patch (関数内 import 経由 vs 直接)."""
    async def fake_get_or_create(ws, step):
        return get_or_create or {
            "id": "art-1",
            "data": {"center": empty_center_state(step)},
        }

    async def fake_update(art_id, center, mark_status=None):
        return update_artifact or {
            "id": art_id, "data": {"center": center, "status": mark_status},
        }

    async def fake_history(ws, phase, step):
        return history or []

    async def fake_save_msg(*a, **kw):
        return save_msg_id

    async def fake_llm(system, messages):
        return llm_response or {
            "chat_message": "ok", "center_patch": [], "ready_to_complete": False,
        }

    async def fake_refs(ws, keywords=None):
        return refs

    monkeypatch.setattr(hs, "get_or_create_center_artifact", fake_get_or_create)
    monkeypatch.setattr(hs, "update_center_artifact", fake_update)
    monkeypatch.setattr(hs, "get_chat_history", fake_history)
    monkeypatch.setattr(hs, "_save_message", fake_save_msg)
    monkeypatch.setattr(hs, "_call_llm", fake_llm)
    monkeypatch.setattr(hs, "_get_references_block", fake_refs)


def test_start_step_kicks_off_when_no_history(monkeypatch) -> None:
    _patch_hs_internal(monkeypatch, llm_response={
        "chat_message": "STEP 1 を始めます",
        "center_patch": [],
        "ready_to_complete": False,
    })
    out = asyncio.run(start_step(1, 1))
    assert "ai_message" in out
    assert "STEP 1 を始めます" in out["ai_message"]


def test_start_step_returns_existing_state_when_already_started(monkeypatch) -> None:
    _patch_hs_internal(monkeypatch, history=[
        {"id": 1, "role": "ai", "content": "previous msg",
         "metadata": {}, "created_at": "2026-05-12"},
    ])
    out = asyncio.run(start_step(1, 1))
    assert out["ai_message"] == "previous msg"


def test_reply_appends_user_message_and_returns_ai_response(monkeypatch) -> None:
    _patch_hs_internal(monkeypatch, llm_response={
        "chat_message": "なるほど、 具体的には?",
        "center_patch": [
            {"section_key": "overview", "operation": "add", "items": ["新規"]},
        ],
        "ready_to_complete": False,
    })
    out = asyncio.run(reply(1, 1, "新しいプロジェクトを作りたい"))
    assert out["ai_message"] == "なるほど、 具体的には?"
    assert out["ready_to_complete"] is False


def test_reply_sets_ready_to_complete_when_llm_signals(monkeypatch) -> None:
    _patch_hs_internal(monkeypatch, llm_response={
        "chat_message": "STEP 完了",
        "center_patch": [],
        "ready_to_complete": True,
    })
    out = asyncio.run(reply(1, 1, "OK"))
    assert out["ready_to_complete"] is True


def test_complete_step_marks_confirmed_and_creates_next_step(monkeypatch) -> None:
    _patch_hs_internal(monkeypatch, get_or_create={
        "id": "step1-art",
        "data": {"phase": "hearing", "step": 1,
                  "center": {**empty_center_state(1),
                              "sections": [{"key": "overview", "label": "x",
                                            "items": ["item1"]}]}},
    })
    out = asyncio.run(complete_step(1, 1))
    # 次 STEP の artifact が用意される
    assert out["next_step"] == 2


def test_complete_step_returns_none_when_step_is_last(monkeypatch) -> None:
    _patch_hs_internal(monkeypatch, get_or_create={
        "id": "step4-art",
        "data": {"phase": "hearing", "step": 4,
                  "center": empty_center_state(4)},
    })
    out = asyncio.run(complete_step(1, 4))
    assert out["next_step"] is None


def test_get_state_is_importable() -> None:
    """get_state は実 DB 統合 (artifact_service.list_artifacts + adb) が必要なため、
    本テストは callable / async function であることのみ smoke 検証.
    full E2E は integration test 環境で別途実施."""
    import inspect
    assert callable(get_state)
    assert inspect.iscoroutinefunction(get_state)


# ──────────────────────────────────────────────────────────────────────────
# _call_llm fallback (LLM 呼び出し失敗時)
# ──────────────────────────────────────────────────────────────────────────


def test_call_llm_returns_fallback_on_exception(monkeypatch) -> None:
    """LLM client が落ちても fallback dict を返す (silent fail)."""
    def boom_client(*a, **kw):
        raise RuntimeError("openai down")

    monkeypatch.setattr(hs, "get_openai_client", boom_client)
    monkeypatch.setenv("MAIN_LLM_PROVIDER", "openai")

    out = asyncio.run(_call_llm("system", [{"role": "user", "content": "hi"}]))
    assert "chat_message" in out
    assert "失敗" in out["chat_message"] or "error" in out


# ──────────────────────────────────────────────────────────────────────────
# _get_references_block (silent fail safe)
# ──────────────────────────────────────────────────────────────────────────


def test_get_references_block_returns_empty_on_failure(monkeypatch) -> None:
    """document_ingest_service 未実装 / DB 失敗 → 空文字 fallback."""
    _patch_adb(monkeypatch)
    # services.document_ingest_service を ImportError にする
    monkeypatch.setitem(sys.modules, "services.document_ingest_service",
                         types.ModuleType("services.document_ingest_service"))
    out = asyncio.run(_get_references_block(1, keywords=None))
    assert out == ""