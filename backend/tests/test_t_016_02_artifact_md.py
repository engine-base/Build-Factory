"""T-016-02: artifact MD 化 (obsidian_sync 拡張) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-016 artifact → MD 変換 service + endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 obsidian_sync REUSE (backwards compat) + audit emit
  AC-4 UNWANTED      : invalid input / path traversal は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import artifact_md_renderer as amd
from services.artifact_md_renderer import (
    ArtifactMDError,
    build_obsidian_path,
    render_artifact_md,
    save_artifact_md,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _redirect_obsidian_root(monkeypatch, tmp_path):
    import services.artifact_md_renderer as a
    monkeypatch.setattr(a, "_OBSIDIAN_ROOT", tmp_path / "obsidian")
    yield {"root": tmp_path / "obsidian"}


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_render_basic():
    md = render_artifact_md({
        "id": "art-1",
        "type": "report",
        "title": "Test Report",
        "data": {"content": "本文です"},
    })
    assert "---" in md
    assert "title:" in md
    assert "Test Report" in md
    assert "本文です" in md


def test_service_render_with_frontmatter_fields():
    md = render_artifact_md({
        "id": "art-2",
        "type": "design",
        "title": "Spec",
        "workspace_id": 5,
        "task_id": 10,
        "status": "approved",
        "category_tags": ["spec", "design"],
        "data": {"summary": "summary text"},
    })
    assert "workspace_id: 5" in md
    assert "task_id: 10" in md
    assert "status: approved" in md
    assert "spec" in md
    assert "summary text" in md


def test_service_render_falls_back_to_data_sections():
    md = render_artifact_md({
        "id": "art-3",
        "data": {"section_a": "値A", "section_b": {"nested": 1}},
    })
    assert "## section_a" in md
    assert "値A" in md
    assert "## section_b" in md
    # nested は JSON block でレンダリング
    assert "```json" in md


def test_service_render_yaml_escapes_special():
    """YAML special chars (colon / newline) は quote/block scalar 化."""
    md = render_artifact_md({
        "id": "x",
        "type": "report",
        "title": "Title: with colon",
    })
    assert '"Title: with colon"' in md


def test_service_render_yaml_block_scalar_for_newline():
    md = render_artifact_md({
        "id": "x",
        "title": "Multi\nline",
    })
    assert "|" in md


def test_service_render_empty_title_uses_default():
    md = render_artifact_md({"id": "x", "title": "  "})
    assert "Untitled Artifact" in md


def test_service_render_invalid_artifact():
    with pytest.raises(ArtifactMDError):
        render_artifact_md("not-a-dict")


def test_service_render_long_title():
    with pytest.raises(ArtifactMDError):
        render_artifact_md({"id": "x", "title": "x" * (amd.MAX_TITLE_LEN + 1)})


def test_service_render_invalid_tags_type():
    with pytest.raises(ArtifactMDError):
        render_artifact_md({"id": "x", "tags": "not-list"})


def test_service_render_too_many_tags():
    with pytest.raises(ArtifactMDError):
        render_artifact_md({
            "id": "x",
            "tags": [f"t{i}" for i in range(amd.MAX_TAG_COUNT + 1)],
        })


def test_service_render_long_tag():
    with pytest.raises(ArtifactMDError):
        render_artifact_md({
            "id": "x",
            "tags": ["x" * (amd.MAX_TAG_LEN + 1)],
        })


def test_service_render_non_string_tag():
    with pytest.raises(ArtifactMDError):
        render_artifact_md({"id": "x", "tags": [123]})


def test_service_render_invalid_type_too_long():
    with pytest.raises(ArtifactMDError):
        render_artifact_md({
            "id": "x", "type": "x" * (amd.MAX_TYPE_LEN + 1),
        })


def test_service_render_non_string_title():
    with pytest.raises(ArtifactMDError):
        render_artifact_md({"id": "x", "title": 123})


def test_service_build_obsidian_path_basic(tmp_path):
    p = build_obsidian_path(
        {"id": "art-1", "type": "report"},
        root=tmp_path,
    )
    assert p == tmp_path / "artifacts" / "report" / "art-1.md"


def test_service_build_obsidian_path_default_type():
    p = build_obsidian_path({"id": "x"}, root=Path("/tmp"))
    assert p.parent.name == "artifact"  # default type


def test_service_build_obsidian_path_traversal_rejected():
    with pytest.raises(ArtifactMDError):
        build_obsidian_path({"id": "../etc/passwd", "type": "report"})


def test_service_build_obsidian_path_slash_rejected():
    with pytest.raises(ArtifactMDError):
        build_obsidian_path({"id": "abc/def", "type": "report"})


def test_service_build_obsidian_path_invalid_chars():
    with pytest.raises(ArtifactMDError):
        build_obsidian_path({"id": "abc$def", "type": "report"})


def test_service_build_obsidian_path_long_segment():
    with pytest.raises(ArtifactMDError):
        build_obsidian_path({"id": "x" * 201, "type": "report"})


def test_service_build_obsidian_path_no_id():
    with pytest.raises(ArtifactMDError):
        build_obsidian_path({"type": "report"})


def test_service_save_writes_file(_redirect_obsidian_root):
    result = save_artifact_md({
        "id": "art-save",
        "type": "report",
        "title": "Save Test",
        "data": {"content": "x"},
    })
    p = Path(result["path"])
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "Save Test" in text


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_render_endpoint(client):
    r = client.post(
        "/api/artifacts/md/render",
        json={
            "artifact": {
                "id": "art-r1",
                "type": "report",
                "title": "R1",
                "data": {"summary": "ok"},
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "markdown" in body
    assert "R1" in body["markdown"]


def test_ac1_save_endpoint(client, _redirect_obsidian_root):
    r = client.post(
        "/api/artifacts/md/save",
        json={
            "artifact": {
                "id": "art-s1",
                "type": "report",
                "title": "S1",
                "data": {"content": "x"},
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert Path(body["path"]).exists()


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_render_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/artifacts/md/render",
        json={"artifact": {"id": "x", "title": "x"}},
    )
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_save_within_2s(client, _redirect_obsidian_root):
    t0 = time.perf_counter()
    r = client.post(
        "/api/artifacts/md/save",
        json={"artifact": {"id": "perf", "title": "x"}},
    )
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/artifacts/md/render",
        json={"artifact": {"id": "x", "title": 123}},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "artifact_md.invalid"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 obsidian_sync REUSE + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_obsidian_sync_module_intact():
    """T-015-03 / 既存 services.obsidian_sync が無傷."""
    from services import obsidian_sync as os_mod
    assert hasattr(os_mod, "run_obsidian_sync")


def test_ac3_save_emits_audit(client, _redirect_obsidian_root, _capture_audit):
    client.post(
        "/api/artifacts/md/save",
        json={
            "artifact": {"id": "audit", "title": "x"},
            "actor_user_id": "alice",
        },
    )
    events = [e for e in _capture_audit if e["event_type"] == "artifact_md.saved"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"


def test_ac3_render_does_not_emit_audit(client, _capture_audit):
    """render は read-only — audit emit なし."""
    client.post(
        "/api/artifacts/md/render",
        json={"artifact": {"id": "x", "title": "x"},
               "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit
              if e["event_type"] in ("artifact_md.saved",)]
    assert len(events) == 0


def test_ac3_yaml_frontmatter_format():
    """artifact → MD のフロントマター形式が Obsidian 互換."""
    md = render_artifact_md({
        "id": "fm-1", "type": "spec", "title": "FM",
        "tags": ["a", "b"],
    })
    assert md.startswith("---\n")
    # frontmatter は --- で挟まれる
    assert md.count("---") >= 2


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_non_dict_artifact(client):
    r = client.post(
        "/api/artifacts/md/render",
        json={"artifact": "not-dict"},
    )
    assert r.status_code in (400, 422)


def test_ac4_long_title(client):
    r = client.post(
        "/api/artifacts/md/render",
        json={"artifact": {"id": "x",
                             "title": "x" * (amd.MAX_TITLE_LEN + 1)}},
    )
    assert r.status_code == 400


def test_ac4_too_many_tags(client):
    r = client.post(
        "/api/artifacts/md/render",
        json={"artifact": {"id": "x",
                             "tags": [f"t{i}" for i in range(amd.MAX_TAG_COUNT + 1)]}},
    )
    assert r.status_code == 400


def test_ac4_save_path_traversal_rejected(client):
    r = client.post(
        "/api/artifacts/md/save",
        json={"artifact": {"id": "../etc/passwd", "title": "x"}},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "artifact_md.unsafe_path"


def test_ac4_save_invalid_chars_rejected(client):
    r = client.post(
        "/api/artifacts/md/save",
        json={"artifact": {"id": "abc$def", "title": "x"}},
    )
    assert r.status_code == 403


def test_ac4_save_no_id_rejected(client):
    r = client.post(
        "/api/artifacts/md/save",
        json={"artifact": {"title": "x"}},
    )
    assert r.status_code == 400


def test_ac4_empty_actor(client):
    r = client.post(
        "/api/artifacts/md/render",
        json={"artifact": {"id": "x"}, "actor_user_id": " "},
    )
    assert r.status_code == 401


def test_ac4_save_path_does_not_escape_root(_redirect_obsidian_root):
    """traversal 試行で実 root 外にファイルが作られない."""
    root = _redirect_obsidian_root["root"]
    with pytest.raises(ArtifactMDError):
        save_artifact_md({"id": "../escape", "title": "x"}, root=root)
    # root 外にファイルが無い
    parent = root.parent
    escape_files = list(parent.glob("escape*"))
    assert escape_files == []


def test_ac4_rejected_save_does_not_emit_audit(client, _capture_audit):
    client.post(
        "/api/artifacts/md/save",
        json={"artifact": {"id": "../etc", "title": "x"}},
    )
    client.post(
        "/api/artifacts/md/save",
        json={"artifact": {"id": "x"}, "actor_user_id": " "},
    )
    events = [e for e in _capture_audit if e["event_type"] == "artifact_md.saved"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/artifacts/md/render",
         {"artifact": {"id": "x", "title": "x" * (amd.MAX_TITLE_LEN + 1)}}),
        ("POST", "/api/artifacts/md/render",
         {"artifact": {"id": "x"}, "actor_user_id": " "}),
        ("POST", "/api/artifacts/md/save",
         {"artifact": {"id": "../etc", "title": "x"}}),
        ("POST", "/api/artifacts/md/save",
         {"artifact": {"title": "x"}}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
