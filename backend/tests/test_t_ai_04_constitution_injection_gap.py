"""T-AI-04: Constitution 自動注入エンジン — gap closure (G1-G3).

主要実装 (services/constitution_engine.py + tests/test_constitution_engine.py
25 件) は完備. 本 PR は **tickets.json T-AI-04 AC との 3 件の追補 gap** を埋める.

## Gaps

  G1 (AC-EVENT): invalidate_cache() で audit emit ('constitution.cache_invalidated').
  G2 (AC-UNWANTED): MissingConstitution / CorruptConstitution raise 時に audit
     emit ('constitution.session_blocked' reason=missing/corrupt).
  G3 (AC-1/4): lint で Constitution 自前 inject を機械検知
     (check_no_self_constitution_inject).
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from services import constitution_engine as ce
from services.constitution_engine import (
    Constitution,
    ConstitutionError,
    CorruptConstitution,
    EVENT_CACHE_INVALIDATED,
    EVENT_SESSION_BLOCKED,
    MissingConstitution,
    assert_constitution_available,
    get_active_constitution,
    invalidate_cache,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture
def stub_db_global_constitution(monkeypatch):
    """DB から base constitution を返す stub."""
    async def fake_load(workspace_id=None):
        if workspace_id is None:
            return Constitution(
                version=1, workspace_id=None,
                principles={
                    "section_1_mission": "build the OS",
                    "section_2_values": ["honesty", "speed"],
                    "section_3_methods": ["EARS", "lint"],
                    "section_4_red_lines": ["no AGPL", "no force push"],
                    "section_5_examples": [],
                },
            )
        return None
    monkeypatch.setattr(ce, "_load_from_db", fake_load)
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    # cache をクリアして fresh state
    asyncio.run(invalidate_cache(reason="test_setup"))
    return fake_load


@pytest.fixture
def stub_db_empty(monkeypatch):
    """DB / env 両方 empty な状態."""
    async def fake_load(workspace_id=None):
        return None
    monkeypatch.setattr(ce, "_load_from_db", fake_load)
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    asyncio.run(invalidate_cache(reason="test_setup"))


# ══════════════════════════════════════════════════════════════════════
# G1 (AC-EVENT): invalidate_cache emits audit
# ══════════════════════════════════════════════════════════════════════


def test_g1_event_audit_constants():
    assert EVENT_CACHE_INVALIDATED == "constitution.cache_invalidated"
    assert EVENT_SESSION_BLOCKED == "constitution.session_blocked"


def test_g1_invalidate_cache_returns_cleared_count(_capture_audit, stub_db_global_constitution):
    # warm cache
    asyncio.run(get_active_constitution())
    # invalidate
    cleared = asyncio.run(invalidate_cache(reason="version_bump"))
    assert cleared >= 1


def test_g1_invalidate_cache_emits_audit(_capture_audit, stub_db_global_constitution):
    _capture_audit.clear()  # setup の emit を除外
    asyncio.run(get_active_constitution())
    asyncio.run(invalidate_cache(reason="version_bump"))
    events = [e for e in _capture_audit if e["event_type"] == EVENT_CACHE_INVALIDATED]
    assert len(events) >= 1
    ev = events[-1]
    assert ev["detail"]["reason"] == "version_bump"
    assert "cleared_entries" in ev["detail"]
    assert ev["user_id"] == "system"


def test_g1_invalidate_cache_default_reason_manual(_capture_audit):
    _capture_audit.clear()
    asyncio.run(invalidate_cache())
    events = [e for e in _capture_audit if e["event_type"] == EVENT_CACHE_INVALIDATED]
    assert events[-1]["detail"]["reason"] == "manual"


# ══════════════════════════════════════════════════════════════════════
# G2 (AC-UNWANTED): block + alert audit emit
# ══════════════════════════════════════════════════════════════════════


def test_g2_missing_constitution_emits_session_blocked(_capture_audit, stub_db_empty):
    _capture_audit.clear()
    with pytest.raises(MissingConstitution):
        asyncio.run(get_active_constitution())
    events = [e for e in _capture_audit if e["event_type"] == EVENT_SESSION_BLOCKED]
    assert len(events) >= 1
    assert events[-1]["detail"]["reason"] == "missing"


def test_g2_corrupt_empty_principles_emits_session_blocked(
    _capture_audit, monkeypatch,
):
    """principles 空の Constitution で health check が CorruptConstitution + audit."""
    _capture_audit.clear()

    async def fake_get_active(*, workspace_id=None):
        return Constitution(version=1, workspace_id=None, principles={})

    monkeypatch.setattr(ce, "get_active_constitution", fake_get_active)
    with pytest.raises(CorruptConstitution):
        asyncio.run(assert_constitution_available())
    events = [e for e in _capture_audit if e["event_type"] == EVENT_SESSION_BLOCKED]
    assert len(events) >= 1
    assert events[-1]["detail"]["reason"] == "corrupt"


def test_g2_corrupt_missing_red_lines_emits_session_blocked(
    _capture_audit, monkeypatch,
):
    """section_4_red_lines 欠落で CorruptConstitution + audit."""
    _capture_audit.clear()

    async def fake_get_active(*, workspace_id=None):
        return Constitution(
            version=2, workspace_id=None,
            principles={"section_2_values": ["only values"]},
        )

    monkeypatch.setattr(ce, "get_active_constitution", fake_get_active)
    with pytest.raises(CorruptConstitution, match="red lines"):
        asyncio.run(assert_constitution_available())
    events = [e for e in _capture_audit if e["event_type"] == EVENT_SESSION_BLOCKED]
    assert len(events) >= 1
    detail = events[-1]["detail"]
    assert detail["reason"] == "corrupt"
    assert "red_lines" in detail["message"]


# ══════════════════════════════════════════════════════════════════════
# G3 (AC-1/4): lint で Constitution 自前 inject 検知
# ══════════════════════════════════════════════════════════════════════


def test_g3_lint_check_no_self_constitution_inject_exists():
    script = (REPO_ROOT / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "check_no_self_constitution_inject" in script
    assert "--no-self-constitution" in script


def test_g3_lint_check_passes_on_clean_code():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-self-constitution"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, f"lint failed: {r.stdout} {r.stderr}"
    assert "OK" in r.stdout


def test_g3_no_self_inject_function_outside_engine():
    """禁止語が backend/services / routers / ai_agents / integrations に
    現れていないことを Python レベルでも assert."""
    forbidden = (
        "_build_constitution_prompt",
        "_inject_constitution_manually",
        "_compose_red_lines_inline",
        "_manual_constitution_inject",
    )
    base = REPO_ROOT / "backend"
    targets = []
    for sub in ("services", "routers", "ai_agents", "integrations"):
        d = base / sub
        if d.exists():
            targets.extend(d.rglob("*.py"))
    for py in targets:
        if py.name == "constitution_engine.py":
            continue
        text = py.read_text(encoding="utf-8")
        for word in forbidden:
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert f"def {word}" not in line, (
                    f"forbidden self-inject function {word!r} in {py}"
                )


# ══════════════════════════════════════════════════════════════════════
# Cross-reference: tickets / docstring
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_ai_04_has_5_ac():
    import json
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-04"), None)
    assert t is not None
    assert len(t["acceptance_criteria"]) == 5
    assert "T-AI-01" in t["deps"]


def test_module_docstring_documents_gap_closures():
    doc = ce.__doc__ or ""
    for g in ("G1", "G2", "G3"):
        assert g in doc, f"docstring must mention {g}"
    assert "ADR-012" in doc


def test_event_constants_exported():
    """audit event 定数が export されている (caller 用 cross-ref)."""
    assert hasattr(ce, "EVENT_CACHE_INVALIDATED")
    assert hasattr(ce, "EVENT_SESSION_BLOCKED")
