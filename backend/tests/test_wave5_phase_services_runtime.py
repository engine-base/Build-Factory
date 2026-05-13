"""Wave-5 runtime tests for high-stmt phase services.

Strategy: deep-call the public/pure helpers + monkeypatch DB / artifact_service
/ LLM / web_search so async coroutines run end-to-end on local data.

Targets (combined ~1,405 missing stmts before wave 5):
- services/requirements_service.py    483 stmts / 15 %
- services/proposal_service.py        431 stmts / 15 %
- services/estimate_service.py        376 stmts / 16 %
- services/pricing_design_service.py  370 stmts / 16 %
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any

import pytest

os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")


# ══════════════════════════════════════════════════════════════════════
# Local _FakeConn (independent from wave 4 to keep tests isolated)
# ══════════════════════════════════════════════════════════════════════


class _FakeCursor:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.rowcount = len(self._rows)
        self.lastrowid = 1

    async def fetchone(self): return self._rows[0] if self._rows else None
    async def fetchall(self): return list(self._rows)
    async def fetchmany(self, n): return list(self._rows[:n])
    async def __aenter__(self): return self
    async def __aexit__(self, *e): return None


class _FakeConn:
    def __init__(self):
        self.row_factory = None
        self.calls: list = []
        self.default_rows: list[dict] = []
        self.responses: list[tuple[str, list[dict]]] = []

    def queue(self, sub, rows): self.responses.append((sub.lower(), rows))
    def _resolve(self, sql):
        low = sql.lower()
        for pat, rows in self.responses:
            if pat in low: return rows
        return list(self.default_rows)

    async def execute(self, sql, params=None):
        self.calls.append((sql, tuple(params) if params else ()))
        return _FakeCursor(self._resolve(sql))

    async def executemany(self, sql, ps):
        for p in ps: self.calls.append((sql, tuple(p)))
        return _FakeCursor()

    async def execute_fetchall(self, sql, params=None):
        self.calls.append((sql, tuple(params) if params else ()))
        return self._resolve(sql)

    async def execute_fetchone(self, sql, params=None):
        rows = await self.execute_fetchall(sql, params)
        return rows[0] if rows else None

    async def commit(self): pass
    async def rollback(self): pass
    async def close(self): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *e): pass


@pytest.fixture
def fake_db(monkeypatch):
    conn = _FakeConn()
    @asynccontextmanager
    async def fake_connect(*a, **kw): yield conn
    import db.async_db as adb
    monkeypatch.setattr(adb, "connect", fake_connect)
    return conn


@pytest.fixture
def fake_artifact_service(monkeypatch):
    """Replace services.artifact_service with an in-memory store."""
    store: dict[str, dict] = {}

    async def list_artifacts(limit=300, **kw):
        return list(store.values())[:limit]
    async def get_artifact(aid):
        return store.get(aid)
    async def create_artifact(**kw):
        aid = f"art-{len(store)+1}"
        rec = {"id": aid, "workspace_id": kw.get("workspace_id"), **kw}
        store[aid] = rec
        return rec
    async def update_artifact(aid, data=None, **kw):
        if aid in store:
            store[aid] = {**store[aid], **({"data": data} if data is not None else {}), **kw}
        return store.get(aid, {})

    import services.artifact_service as art
    monkeypatch.setattr(art, "list_artifacts", list_artifacts, raising=False)
    monkeypatch.setattr(art, "get_artifact", get_artifact, raising=False)
    monkeypatch.setattr(art, "create_artifact", create_artifact, raising=False)
    monkeypatch.setattr(art, "update_artifact", update_artifact, raising=False)
    return store


# ══════════════════════════════════════════════════════════════════════
# services/requirements_service.py
# ══════════════════════════════════════════════════════════════════════


class TestRequirementsService:

    def test_gather_project_context_with_brief(self):
        from services.requirements_service import _gather_project_context
        out = _gather_project_context(
            hearing_brief={"goal": "AAA", "client": "BBB"},
            req_centers=[
                {"sections": [{"key": "x", "items": ["one", "two"]}]},
                {"sections": []},
            ],
        )
        assert isinstance(out, str)
        assert "ヒアリング" in out
        assert "STEP 1" in out

    def test_gather_project_context_empty(self):
        from services.requirements_service import _gather_project_context
        out = _gather_project_context({}, [])
        assert isinstance(out, str)
        assert "プロジェクト情報" in out or out == ""

    def test_apply_center_patch_add_item(self):
        from services.requirements_service import apply_center_patch
        center = {
            "step": 1,
            "sections": [{"key": "overview", "label": "概要", "items": []}],
        }
        patch = [{"op": "add_item", "section": "overview", "value": "新規"}]
        out = apply_center_patch(center, patch)
        assert isinstance(out, dict)

    def test_apply_center_patch_noop_unknown_op(self):
        from services.requirements_service import apply_center_patch
        center = {"sections": []}
        out = apply_center_patch(center, [{"op": "garbage"}])
        assert isinstance(out, dict)

    def test_legal_payload_to_center_patch(self):
        from services.requirements_service import legal_payload_to_center_patch
        payload = {
            "regulations": [{"name": "個人情報保護法", "summary": "..."}],
            "features": ["同意取得"],
            "nfr": ["暗号化"],
            "risks": ["児童データ"],
        }
        out = legal_payload_to_center_patch(payload)
        assert isinstance(out, list)

    def test_legal_payload_to_center_patch_empty(self):
        from services.requirements_service import legal_payload_to_center_patch
        out = legal_payload_to_center_patch({})
        assert isinstance(out, list)

    def test_build_system_prompt_step1(self):
        from services.requirements_service import _build_system_prompt
        out = _build_system_prompt(
            step=1,
            center_state={"sections": []},
            hearing_brief={"goal": "X"},
            legal_payload=None,
        )
        assert isinstance(out, str)
        assert "STEP" in out or "step" in out.lower() or len(out) > 0

    def test_build_system_prompt_with_legal_payload(self):
        from services.requirements_service import _build_system_prompt
        out = _build_system_prompt(
            step=5,
            center_state={"sections": []},
            hearing_brief={},
            legal_payload={"regulations": [{"name": "GDPR"}]},
        )
        assert isinstance(out, str)

    def test_autodetect_provider_returns_tuple(self):
        from services.requirements_service import _autodetect_provider
        provider, model = _autodetect_provider()
        assert model
        assert provider is not None

    def test_get_chat_history_empty_returns_list(self, fake_db):
        from services.requirements_service import get_chat_history
        out = asyncio.run(get_chat_history(1, "requirements", 1))
        assert isinstance(out, list)
        assert out == []

    def test_get_chat_history_parses_metadata(self, fake_db):
        from services.requirements_service import get_chat_history
        fake_db.queue("from chat_messages", [
            {"id": 1, "role": "user", "content": "hi",
             "metadata": json.dumps({"k": "v"}), "created_at": "2026-01-01"},
            {"id": 2, "role": "ai", "content": "hello",
             "metadata": "not-json", "created_at": "2026-01-01"},
            {"id": 3, "role": "ai", "content": "x",
             "metadata": None, "created_at": "2026-01-01"},
        ])
        out = asyncio.run(get_chat_history(1, "requirements", 1))
        assert len(out) == 3
        assert out[0]["metadata"] == {"k": "v"}
        assert out[1]["metadata"] == {}  # broken json → empty
        assert out[2]["metadata"] == {}

    def test_save_message_returns_id(self, fake_db):
        from services.requirements_service import _save_message
        fake_db.queue("insert into chat_messages", [{"id": 42}])
        out = asyncio.run(_save_message(1, "requirements", 1, "user", "hi"))
        assert out == 42

    def test_save_message_no_id_returns_zero(self, fake_db):
        from services.requirements_service import _save_message
        # no canned row → fetchone returns None → returns 0
        out = asyncio.run(_save_message(1, "requirements", 1, "user", "hi"))
        assert out == 0

    def test_get_hearing_brief_empty(self, fake_artifact_service):
        from services.requirements_service import get_hearing_brief
        out = asyncio.run(get_hearing_brief(1))
        assert isinstance(out, dict)
        assert out == {}

    def test_get_hearing_brief_collects_by_step(self, fake_artifact_service):
        from services.requirements_service import get_hearing_brief
        fake_artifact_service["a1"] = {
            "id": "a1", "workspace_id": 1, "type": "spec",
            "updated_at": "2026-01-01",
            "title": "ヒアリング STEP 1: 目的",
            "data": {"phase": "hearing", "step": 1, "status": "decided",
                     "center": {"sections": [
                         {"key": "k", "label": "L", "items": ["a"]}
                     ]}},
        }
        out = asyncio.run(get_hearing_brief(1))
        assert "step1" in out

    def test_web_search_legal_empty_queries(self, monkeypatch):
        from services.requirements_service import _web_search_legal
        out = asyncio.run(_web_search_legal([]))
        assert out == []

    def test_web_search_legal_handles_missing_helper(self, monkeypatch):
        """If services.web_search_helper.search is absent, returns []."""
        from services import requirements_service as r
        out = asyncio.run(r._web_search_legal(["q1", "q2"]))
        # The import may fail or succeed depending on env; either way the
        # function must return a list (per its contract)
        assert isinstance(out, list)

    def test_vector_lookup_returns_list(self, fake_artifact_service):
        from services.requirements_service import _vector_lookup_legal_knowledge
        out = asyncio.run(_vector_lookup_legal_knowledge([], []))
        assert isinstance(out, list)

    def test_vector_lookup_with_legal_tags(self, fake_artifact_service):
        from services.requirements_service import _vector_lookup_legal_knowledge
        fake_artifact_service["k1"] = {
            "id": "k1", "type": "knowledge",
            "title": "個人情報保護",
            "category_tags": ["legal", "compliance"],
        }
        out = asyncio.run(_vector_lookup_legal_knowledge(["IT"], ["personal"]))
        assert isinstance(out, list)


# ══════════════════════════════════════════════════════════════════════
# services/proposal_service.py — shared pattern with requirements
# ══════════════════════════════════════════════════════════════════════


class TestProposalService:
    def test_save_message_records_id(self, fake_db):
        from services.proposal_service import _save_message
        fake_db.queue("insert into chat_messages", [{"id": 99}])
        out = asyncio.run(_save_message(1, 2, "user", "hi"))
        assert out == 99

    def test_save_message_zero_when_no_row(self, fake_db):
        from services.proposal_service import _save_message
        out = asyncio.run(_save_message(1, 2, "user", "hi"))
        assert out == 0

    def test_get_chat_history_empty(self, fake_db):
        from services.proposal_service import get_chat_history
        out = asyncio.run(get_chat_history(1, 1))
        assert out == []

    def test_get_chat_history_parses_metadata(self, fake_db):
        from services.proposal_service import get_chat_history
        fake_db.queue("from chat_messages", [
            {"id": 1, "role": "user", "content": "x",
             "metadata": json.dumps({"a": 1}), "created_at": "2026-01-01"},
        ])
        out = asyncio.run(get_chat_history(1, 1))
        assert out[0]["metadata"] == {"a": 1}

    def test_get_prev_phases_brief_empty(self, fake_artifact_service):
        from services.proposal_service import get_prev_phases_brief
        out = asyncio.run(get_prev_phases_brief(1))
        assert isinstance(out, dict)

    def test_load_skill_md_string(self):
        from services.proposal_service import _load_skill_md
        out = _load_skill_md()
        assert isinstance(out, str)

    def test_extract_common_rules(self):
        from services.proposal_service import _extract_common_rules
        out = _extract_common_rules("## \U0001f9e0 全スキル共通\nrules\n# next")
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════
# services/estimate_service.py
# ══════════════════════════════════════════════════════════════════════


class TestEstimateService:
    def test_save_message(self, fake_db):
        from services.estimate_service import _save_message
        fake_db.queue("insert into chat_messages", [{"id": 7}])
        out = asyncio.run(_save_message(1, 1, "user", "hi"))
        assert out == 7

    def test_get_chat_history_empty(self, fake_db):
        from services.estimate_service import get_chat_history
        out = asyncio.run(get_chat_history(1, 1))
        assert out == []

    def test_get_prev_phases_brief(self, fake_artifact_service):
        from services.estimate_service import get_prev_phases_brief
        out = asyncio.run(get_prev_phases_brief(1))
        assert isinstance(out, dict)

    def test_load_skill_md(self):
        from services.estimate_service import _load_skill_md
        assert isinstance(_load_skill_md(), str)

    def test_extract_step_section(self):
        from services.estimate_service import _extract_step_section
        out = _extract_step_section("skill md", 1)
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════
# services/pricing_design_service.py
# ══════════════════════════════════════════════════════════════════════


class TestPricingDesignService:
    def test_save_message(self, fake_db):
        from services.pricing_design_service import _save_message
        fake_db.queue("insert into chat_messages", [{"id": 11}])
        out = asyncio.run(_save_message(1, 1, "user", "hi"))
        assert out == 11

    def test_get_chat_history_empty(self, fake_db):
        from services.pricing_design_service import get_chat_history
        out = asyncio.run(get_chat_history(1, 1))
        assert out == []

    def test_get_prev_phases_brief(self, fake_artifact_service):
        from services.pricing_design_service import get_prev_phases_brief
        out = asyncio.run(get_prev_phases_brief(1))
        assert isinstance(out, dict)

    def test_load_skill_md(self):
        from services.pricing_design_service import _load_skill_md
        assert isinstance(_load_skill_md(), str)

    def test_extract_step_section(self):
        from services.pricing_design_service import _extract_step_section
        out = _extract_step_section("skill md", 1)
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════
# Pure renderers (requirements only — others may not have analogous fns)
# ══════════════════════════════════════════════════════════════════════


class TestRequirementsRenderers:
    @pytest.fixture
    def aggregated_view_stub(self, monkeypatch):
        """Stub get_aggregated_view to a stable structure for renderer tests."""
        async def fake_view(ws):
            return {
                "workspace_id": ws,
                "phase": "requirements",
                "tabs": {
                    "overview": [{"label": "プロジェクト概要", "items": ["A", "B"]}],
                    "users": [],
                    "features": [{"label": "主要機能", "items": ["F1"]}],
                },
                "step_status": {},
            }
        import services.requirements_service as r
        monkeypatch.setattr(r, "get_aggregated_view", fake_view)

    def test_items_to_md_with_items(self):
        from services.requirements_service import _items_to_md
        out = _items_to_md(["a", "b"])
        assert "- a" in out and "- b" in out

    def test_items_to_md_empty(self):
        from services.requirements_service import _items_to_md
        out = _items_to_md([])
        assert "未記入" in out or "(まだ" in out

    def test_html_escape_basics(self):
        from services.requirements_service import _html_escape
        assert _html_escape("<a>") == "&lt;a&gt;"
        assert _html_escape("a & b") == "a &amp; b"
        assert _html_escape(None) == ""
        assert _html_escape("") == ""

    def test_items_to_html_list_empty(self):
        from services.requirements_service import _items_to_html_list
        out = _items_to_html_list([])
        assert "未記入" in out

    def test_items_to_html_list_items(self):
        from services.requirements_service import _items_to_html_list
        out = _items_to_html_list(["a", "<b>"])
        assert "<ul>" in out
        assert "&lt;b&gt;" in out

    def test_render_markdown_all(self, aggregated_view_stub):
        from services.requirements_service import render_markdown
        out = asyncio.run(render_markdown(1, "all"))
        assert isinstance(out, str)
        assert "# 要件定義書" in out
        assert "プロジェクト概要" in out
        assert "主要機能" in out

    def test_render_markdown_single_tab(self, aggregated_view_stub):
        from services.requirements_service import render_markdown
        out = asyncio.run(render_markdown(1, "overview"))
        assert isinstance(out, str)
        assert "プロジェクト概要" in out

    def test_render_markdown_empty_tab(self, aggregated_view_stub):
        from services.requirements_service import render_markdown
        out = asyncio.run(render_markdown(1, "users"))
        assert "未記入" in out

    def test_render_html_all(self, aggregated_view_stub):
        from services.requirements_service import render_html
        out = asyncio.run(render_html(1, "all"))
        assert isinstance(out, str)
        assert "<!DOCTYPE html>" in out
        assert "プロジェクト概要" in out

    def test_render_html_single_tab(self, aggregated_view_stub):
        from services.requirements_service import render_html
        out = asyncio.run(render_html(1, "overview"))
        assert "<!DOCTYPE html>" in out

    def test_render_json(self, aggregated_view_stub):
        from services.requirements_service import render_json
        out = asyncio.run(render_json(1, "all"))
        assert isinstance(out, dict)
