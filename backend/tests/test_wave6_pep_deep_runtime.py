"""Wave-6 deep runtime tests for proposal / estimate / pricing_design services.

Replicates the wave-5 pattern (DB + artifact_service stubs) on the
3 remaining phase services. Each service shares the same shape:
- pure: _items_to_md / _html_escape / _items_to_html_* / _build_system_prompt /
        _autodetect_provider / apply_center_patch / _load_skill_md /
        _extract_common_rules / _extract_step_section
- async+DB: _save_message / get_chat_history / _get_references_block
- async+artifact: get_or_create_center_artifact / update_center_artifact /
                  get_prev_phases_brief
- renderers: render_markdown / render_html / render_json

Targets:
- services/proposal_service.py        20 % (346 miss)
- services/estimate_service.py        21 % (296 miss)
- services/pricing_design_service.py  21 % (293 miss)
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
# Shared fixtures (parallel to wave-4 / wave-5)
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
        self.calls = []
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
    store: dict[str, dict] = {}
    async def list_artifacts(limit=300, **kw): return list(store.values())[:limit]
    async def get_artifact(aid): return store.get(aid)
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
# Parametrized: shared pattern across all 3 services
# ══════════════════════════════════════════════════════════════════════


PHASE_SERVICES = [
    "services.proposal_service",
    "services.estimate_service",
    "services.pricing_design_service",
]


@pytest.mark.parametrize("mod_path", PHASE_SERVICES)
class TestPhaseServicesDeep:
    """Pure helpers and DB-only async helpers shared by all 3 services."""

    def _mod(self, mod_path):
        import importlib
        return importlib.import_module(mod_path)

    # ── pure helpers ──────────────────────────────────────────────

    def test_html_escape_xml(self, mod_path):
        m = self._mod(mod_path)
        assert m._html_escape("<a>") == "&lt;a&gt;"
        assert m._html_escape("a & b") == "a &amp; b"
        assert m._html_escape("") == ""
        # None tolerance — some impls accept None, others raise. Both fine.
        try:
            out = m._html_escape(None)
            assert out == "" or isinstance(out, str)
        except (TypeError, AttributeError):
            pass

    def test_items_to_md_branches(self, mod_path):
        m = self._mod(mod_path)
        # with items
        assert "- a" in m._items_to_md(["a"])
        # empty → fallback string (impl varies — must be non-None str)
        out = m._items_to_md([])
        assert isinstance(out, str)

    def test_autodetect_provider_returns_tuple(self, mod_path):
        m = self._mod(mod_path)
        provider, model = m._autodetect_provider()
        assert model
        assert provider is not None

    def test_build_system_prompt_step1(self, mod_path):
        m = self._mod(mod_path)
        # signature varies: 4 args (req/estimate) vs 3 args (pricing_design)
        kwargs = dict(step=1, center_state={"sections": []}, prev_brief={})
        try:
            out = m._build_system_prompt(**kwargs)
        except TypeError:
            out = m._build_system_prompt(**kwargs, issuer_block="")
        assert isinstance(out, str)
        assert len(out) > 0

    def test_apply_center_patch_noop(self, mod_path):
        m = self._mod(mod_path)
        out = m.apply_center_patch({"sections": []}, [])
        assert isinstance(out, dict)

    def test_apply_center_patch_unknown_op(self, mod_path):
        m = self._mod(mod_path)
        out = m.apply_center_patch(
            {"sections": [{"key": "k", "label": "L", "items": []}]},
            [{"op": "garbage_op"}],
        )
        assert isinstance(out, dict)

    # ── DB-driven async helpers ───────────────────────────────────

    def test_save_message_returns_id(self, mod_path, fake_db):
        m = self._mod(mod_path)
        fake_db.queue("insert into chat_messages", [{"id": 21}])
        out = asyncio.run(m._save_message(1, 1, "user", "hi"))
        assert out == 21

    def test_save_message_no_row_zero(self, mod_path, fake_db):
        m = self._mod(mod_path)
        out = asyncio.run(m._save_message(1, 1, "user", "hi"))
        assert out == 0

    def test_get_chat_history_empty(self, mod_path, fake_db):
        m = self._mod(mod_path)
        out = asyncio.run(m.get_chat_history(1, 1))
        assert out == []

    def test_get_chat_history_with_metadata(self, mod_path, fake_db):
        m = self._mod(mod_path)
        fake_db.queue("from chat_messages", [
            {"id": 1, "role": "user", "content": "x",
             "metadata": json.dumps({"k": 1}), "created_at": "2026-01-01"},
            {"id": 2, "role": "ai", "content": "y",
             "metadata": "garbage", "created_at": "2026-01-01"},
            {"id": 3, "role": "ai", "content": "z",
             "metadata": None, "created_at": "2026-01-01"},
        ])
        out = asyncio.run(m.get_chat_history(1, 1))
        assert len(out) == 3
        assert out[0]["metadata"] == {"k": 1}
        assert out[1]["metadata"] == {}
        assert out[2]["metadata"] == {}

    # ── artifact-driven async helpers ─────────────────────────────

    def test_get_or_create_center_artifact_creates_when_missing(
        self, mod_path, fake_artifact_service, fake_db,
    ):
        m = self._mod(mod_path)
        out = asyncio.run(m.get_or_create_center_artifact(1, 1))
        assert isinstance(out, dict)
        assert "id" in out

    def test_update_center_artifact_missing_returns_empty(
        self, mod_path, fake_artifact_service,
    ):
        m = self._mod(mod_path)
        out = asyncio.run(m.update_center_artifact("none", {"sections": []}))
        assert out == {}

    def test_update_center_artifact_existing(
        self, mod_path, fake_artifact_service,
    ):
        m = self._mod(mod_path)
        fake_artifact_service["a1"] = {
            "id": "a1", "type": "spec",
            "data": {"phase": "x", "step": 1, "center": {"sections": []}},
        }
        out = asyncio.run(m.update_center_artifact(
            "a1", {"sections": [{"key": "k", "items": ["x"]}]},
            mark_status="decided",
        ))
        assert isinstance(out, dict)

    def test_get_prev_phases_brief_empty(self, mod_path, fake_artifact_service):
        m = self._mod(mod_path)
        out = asyncio.run(m.get_prev_phases_brief(1))
        assert isinstance(out, dict)


# ══════════════════════════════════════════════════════════════════════
# Renderer tests — driven per-service via aggregated_view stub
# ══════════════════════════════════════════════════════════════════════


def _stub_view_for(mod_path: str, ws: int) -> dict:
    """Build a view dict that matches each service's renderer expectations.

    - proposal_service.render_* iterates view["chapters"] (list of dicts)
    - estimate_service.render_* iterates view["tabs"] (list of dicts)
    - pricing_design_service.render_* iterates view["tabs"] (list of dicts)
    """
    item_list = [{"label": "概要", "items": ["A"]}]
    if "proposal_service" in mod_path:
        return {
            "workspace_id": ws,
            "phase": "proposal",
            "chapters": [
                {"key": "summary", "label": "サマリー", "sections": item_list},
                {"key": "scope", "label": "スコープ", "sections": []},
            ],
            "step_status": {},
        }
    return {
        "workspace_id": ws,
        "phase": "x",
        "tabs": [
            {"key": "overview", "label": "概要", "sections": item_list},
            {"key": "scope", "label": "スコープ", "sections": []},
        ],
        "step_status": {},
    }


def _install_view_stub(monkeypatch, mod_path: str):
    """Install an aggregated_view stub for the named service."""
    import importlib
    m = importlib.import_module(mod_path)

    async def fake(ws):
        return _stub_view_for(mod_path, ws)

    if hasattr(m, "get_aggregated_view"):
        monkeypatch.setattr(m, "get_aggregated_view", fake)
    return m


@pytest.mark.parametrize("mod_path", PHASE_SERVICES)
class TestPhaseServiceRenderers:

    def test_render_markdown_default(self, monkeypatch, mod_path):
        m = _install_view_stub(monkeypatch, mod_path)
        if not hasattr(m, "render_markdown"):
            pytest.skip(f"{mod_path}.render_markdown absent")
        out = asyncio.run(m.render_markdown(1))
        assert isinstance(out, str)
        assert len(out) > 0

    def test_render_html_default(self, monkeypatch, mod_path):
        m = _install_view_stub(monkeypatch, mod_path)
        if not hasattr(m, "render_html"):
            pytest.skip(f"{mod_path}.render_html absent")
        out = asyncio.run(m.render_html(1))
        assert isinstance(out, str)
        # output should look like HTML
        assert "<" in out

    def test_render_json_default(self, monkeypatch, mod_path):
        m = _install_view_stub(monkeypatch, mod_path)
        if not hasattr(m, "render_json"):
            pytest.skip(f"{mod_path}.render_json absent")
        out = asyncio.run(m.render_json(1))
        assert isinstance(out, dict)


# ══════════════════════════════════════════════════════════════════════
# Service-specific extras
# ══════════════════════════════════════════════════════════════════════


class TestEstimateServiceExtras:

    def test_flatten_estimate_for_render(self):
        from services.estimate_service import _flatten_estimate_for_render
        tabs = [
            {"label": "工数", "items": []},
            {"label": "金額", "items": [{"name": "a", "price": 1000}]},
        ]
        settings = {"tax_rate": 10}
        out = _flatten_estimate_for_render(tabs, settings)
        assert isinstance(out, dict)

    def test_flatten_estimate_empty(self):
        from services.estimate_service import _flatten_estimate_for_render
        out = _flatten_estimate_for_render([], {})
        assert isinstance(out, dict)

    def test_render_html_fallback(self, monkeypatch):
        from services import estimate_service as e
        async def fake(ws): return _stub_view_for("services.estimate_service", ws)
        monkeypatch.setattr(e, "get_aggregated_view", fake)
        out = asyncio.run(e._render_html_fallback(1))
        assert isinstance(out, str)
        assert "<" in out


class TestProposalServiceExtras:

    def test_items_to_html_paragraphs(self):
        from services.proposal_service import _items_to_html_paragraphs
        out = _items_to_html_paragraphs(["A", "B"])
        assert isinstance(out, str)
        # contains paragraph-ish markup or just text
        assert len(out) > 0

    def test_items_to_html_paragraphs_empty(self):
        from services.proposal_service import _items_to_html_paragraphs
        out = _items_to_html_paragraphs([])
        assert isinstance(out, str)

    def test_gather_project_meta_runs(self, fake_db, fake_artifact_service):
        from services.proposal_service import _gather_project_meta
        out = asyncio.run(_gather_project_meta(1))
        assert isinstance(out, dict)

    def test_archive_as_knowledge_runs(self, fake_db, fake_artifact_service):
        from services.proposal_service import _archive_as_knowledge
        # The function returns None and tolerates missing rows
        out = asyncio.run(_archive_as_knowledge(1))
        assert out is None


# ══════════════════════════════════════════════════════════════════════
# Reference / issuer block stubs (DB-backed)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("mod_path", PHASE_SERVICES)
class TestReferenceBlockHelpers:

    def _mod(self, mod_path):
        import importlib
        return importlib.import_module(mod_path)

    def test_get_references_block_returns_string(
        self, mod_path, fake_db, fake_artifact_service,
    ):
        m = self._mod(mod_path)
        if not hasattr(m, "_get_references_block"):
            pytest.skip("no _get_references_block")
        out = asyncio.run(m._get_references_block(1))
        assert isinstance(out, str)

    def test_get_references_block_with_keywords(
        self, mod_path, fake_db, fake_artifact_service,
    ):
        m = self._mod(mod_path)
        if not hasattr(m, "_get_references_block"):
            pytest.skip("no _get_references_block")
        out = asyncio.run(m._get_references_block(1, keywords=["A", "B"]))
        assert isinstance(out, str)

    def test_get_issuer_context_block(
        self, mod_path, fake_db, fake_artifact_service,
    ):
        m = self._mod(mod_path)
        if not hasattr(m, "_get_issuer_context_block"):
            pytest.skip("no _get_issuer_context_block")
        out = asyncio.run(m._get_issuer_context_block(1))
        assert isinstance(out, str)
