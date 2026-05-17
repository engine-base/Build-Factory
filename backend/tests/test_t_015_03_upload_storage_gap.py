"""T-015-03: Storage upload + 共有リンク + Markdown 併記 — gap closure (G1-G3).

主要実装 (services/upload_service.py + routers/uploads.py + 22 既存 tests) は
完備. 本 PR で **audit emit + TTL range + timing 実測** の 3 件 gap を埋める.

## Gaps

  G1 (AC-STATE audit_log v2.1 #7): upload 成功 / 拒否時に audit emit が
     無かった → uploads.upload_succeeded / uploads.upload_rejected を
     memory_service 経由で発火.
  G2 (AC-2 timing 実測): 2 秒以内の実測 test 追補.
  G3 (AC-1 share TTL range): MIN_SHARE_TTL_SECONDS / MAX_SHARE_TTL_SECONDS の
     定数 + range validation 検証.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from services import upload_service as us
from services.upload_service import (
    EVENT_UPLOAD_REJECTED,
    EVENT_UPLOAD_SUCCEEDED,
    MAX_BYTES,
    MAX_SHARE_TTL_SECONDS,
    MIN_SHARE_TTL_SECONDS,
    upload_image,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def isolated_local_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "LOCAL_FALLBACK_DIR", tmp_path)
    # supabase 未設定で local fallback 経路
    # NOTE: upload_service.py captures SUPABASE_URL / SUPABASE_SERVICE_KEY at
    # module import time, so monkeypatch.setenv alone is insufficient when
    # conftest.py has already populated test defaults. We patch both the env
    # (for any lazy readers) and the captured module-level constants.
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "")
    monkeypatch.setattr(us, "SUPABASE_URL", "")
    monkeypatch.setattr(us, "SUPABASE_SERVICE_KEY", "")
    return tmp_path


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({"event_type": event_type, "detail": detail or {}})
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ══════════════════════════════════════════════════════════════════════
# G1 (AC-STATE audit_log): upload 成功 / 拒否で audit emit
# ══════════════════════════════════════════════════════════════════════


def test_g1_event_constants_exported():
    assert EVENT_UPLOAD_SUCCEEDED == "uploads.upload_succeeded"
    assert EVENT_UPLOAD_REJECTED == "uploads.upload_rejected"


def test_g1_upload_success_emits_audit(isolated_local_dir, _capture_audit):
    """正常 upload で uploads.upload_succeeded audit emit."""
    asyncio.run(upload_image(
        account_id=1, kind="logo", filename="t.png",
        content=b"\x89PNG\r\n\x1a\n" + b"x" * 100,
        content_type="image/png",
    ))
    events = [e for e in _capture_audit if e["event_type"] == EVENT_UPLOAD_SUCCEEDED]
    assert len(events) == 1
    d = events[0]["detail"]
    assert d["account_id"] == 1
    assert d["kind"] == "logo"
    assert "path" in d
    assert "size" in d
    assert "share_ttl_seconds" in d


def test_g1_upload_oversize_emits_rejected_audit(isolated_local_dir, _capture_audit):
    big = b"x" * (MAX_BYTES + 1)
    with pytest.raises(ValueError, match="too large"):
        asyncio.run(upload_image(
            account_id=1, kind="logo", filename="big.png",
            content=big, content_type="image/png",
        ))
    events = [e for e in _capture_audit if e["event_type"] == EVENT_UPLOAD_REJECTED]
    assert len(events) >= 1
    assert events[-1]["detail"]["reason"] == "file_too_large"


def test_g1_upload_invalid_mime_emits_rejected_audit(isolated_local_dir, _capture_audit):
    with pytest.raises(ValueError, match="unsupported content type"):
        asyncio.run(upload_image(
            account_id=1, kind="logo", filename="x.exe",
            content=b"MZ" * 100, content_type="application/x-msdownload",
        ))
    events = [e for e in _capture_audit if e["event_type"] == EVENT_UPLOAD_REJECTED]
    assert len(events) >= 1
    assert events[-1]["detail"]["reason"] == "unsupported_content_type"


# ══════════════════════════════════════════════════════════════════════
# G3 (AC-1 share TTL range)
# ══════════════════════════════════════════════════════════════════════


def test_g3_ttl_range_constants():
    """spec の TTL 制約定数 (60 sec - 30 day)."""
    assert MIN_SHARE_TTL_SECONDS == 60
    assert MAX_SHARE_TTL_SECONDS == 60 * 60 * 24 * 30


def test_g3_ttl_below_min_rejected(isolated_local_dir, _capture_audit):
    with pytest.raises(ValueError, match="share_ttl_seconds"):
        asyncio.run(upload_image(
            account_id=1, kind="logo", filename="t.png",
            content=b"\x89PNG\r\n\x1a\nx", content_type="image/png",
            share_ttl_seconds=10,  # < 60
        ))
    events = [e for e in _capture_audit if e["event_type"] == EVENT_UPLOAD_REJECTED]
    assert any(e["detail"].get("reason") == "ttl_out_of_range" for e in events)


def test_g3_ttl_above_max_rejected(isolated_local_dir, _capture_audit):
    with pytest.raises(ValueError, match="share_ttl_seconds"):
        asyncio.run(upload_image(
            account_id=1, kind="logo", filename="t.png",
            content=b"\x89PNG\r\n\x1a\nx", content_type="image/png",
            share_ttl_seconds=MAX_SHARE_TTL_SECONDS + 1,
        ))
    events = [e for e in _capture_audit if e["event_type"] == EVENT_UPLOAD_REJECTED]
    assert any(e["detail"].get("reason") == "ttl_out_of_range" for e in events)


def test_g3_ttl_non_int_rejected(isolated_local_dir, _capture_audit):
    for bad in ("3600", None, 3.5, True):
        with pytest.raises(ValueError):
            asyncio.run(upload_image(
                account_id=1, kind="logo", filename="t.png",
                content=b"\x89PNG\r\n\x1a\nx", content_type="image/png",
                share_ttl_seconds=bad,  # type: ignore[arg-type]
            ))


def test_g3_ttl_at_min_accepted(isolated_local_dir, _capture_audit):
    """境界値: MIN_SHARE_TTL_SECONDS は accept される."""
    out = asyncio.run(upload_image(
        account_id=1, kind="logo", filename="t.png",
        content=b"\x89PNG\r\n\x1a\nx", content_type="image/png",
        share_ttl_seconds=MIN_SHARE_TTL_SECONDS,
    ))
    assert out["share_ttl_seconds"] == MIN_SHARE_TTL_SECONDS


def test_g3_ttl_at_max_accepted(isolated_local_dir, _capture_audit):
    out = asyncio.run(upload_image(
        account_id=1, kind="logo", filename="t.png",
        content=b"\x89PNG\r\n\x1a\nx", content_type="image/png",
        share_ttl_seconds=MAX_SHARE_TTL_SECONDS,
    ))
    assert out["share_ttl_seconds"] == MAX_SHARE_TTL_SECONDS


# ══════════════════════════════════════════════════════════════════════
# G2 (AC-2 timing 実測)
# ══════════════════════════════════════════════════════════════════════


def test_g2_local_upload_within_2sec(isolated_local_dir, _capture_audit):
    """local fallback での 1MB upload は 2 秒以内."""
    content = b"\x89PNG\r\n\x1a\n" + b"x" * (1024 * 1024)
    t0 = time.time()
    asyncio.run(upload_image(
        account_id=1, kind="logo", filename="big.png",
        content=content, content_type="image/png",
    ))
    elapsed_ms = (time.time() - t0) * 1000
    assert elapsed_ms < 2000, f"upload {elapsed_ms:.0f}ms exceeded 2s"


# ══════════════════════════════════════════════════════════════════════
# Endpoint smoke (G1 + G3 router 経路)
# ══════════════════════════════════════════════════════════════════════


def test_endpoint_invalid_ttl_400_with_code(client, isolated_local_dir, _capture_audit):
    """router 経由で TTL out-of-range が 400 + invalid_ttl code."""
    r = client.post(
        "/api/uploads",
        data={"account_id": "1", "kind": "logo", "share_ttl_seconds": "10"},
        files={"file": ("t.png", b"\x89PNG\r\n\x1a\nx", "image/png")},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "invalid_ttl"


def test_endpoint_unknown_kind_400(client, isolated_local_dir, _capture_audit):
    r = client.post(
        "/api/uploads",
        data={"account_id": "1", "kind": "bogus_kind"},
        files={"file": ("t.png", b"\x89PNG", "image/png")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "unknown_kind"


def test_endpoint_4xx_form_uniformity(client, isolated_local_dir, _capture_audit):
    """全 4xx の {detail:{code,message}} 統一."""
    cases = [
        ({"account_id": "1", "kind": "bogus"},
         {"file": ("t.png", b"x", "image/png")},
         400, "unknown_kind"),
        ({"account_id": "1", "kind": "logo", "share_ttl_seconds": "10"},
         {"file": ("t.png", b"\x89PNG", "image/png")},
         400, "invalid_ttl"),
        ({"account_id": "1", "kind": "logo"},
         {"file": ("t.exe", b"x", "application/x-msdownload")},
         400, "unsupported_content_type"),
    ]
    for data, files, expected_status, expected_code in cases:
        r = client.post("/api/uploads", data=data, files=files)
        assert r.status_code == expected_status, f"{data}: {r.status_code}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert detail.get("code") == expected_code


# ══════════════════════════════════════════════════════════════════════
# Cross-reference: tickets + module docstring
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_015_03_has_4_ac():
    import json
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-015-03"), None)
    assert t is not None
    assert len(t["acceptance_criteria"]) == 4


def test_module_docstring_documents_event_constants():
    doc = us.__doc__ or ""
    assert "uploads.upload_succeeded" in doc
    assert "uploads.upload_rejected" in doc
    assert "T-015-03" in doc
