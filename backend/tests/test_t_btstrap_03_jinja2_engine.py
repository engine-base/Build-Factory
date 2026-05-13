"""T-BTSTRAP-03: Jinja2 プレースホルダ置換エンジン — 4 AC 1:1.

AC マッピング:
  AC-1 UBIQUITOUS (#1) : 全 .j2 を Jinja2 render
  AC-1 UBIQUITOUS (#2) : 10 placeholders サポート
  AC-2 EVENT-DRIVEN    : 必須欠落で BootstrapError + atomic (書出ゼロ)
  AC-3 STATE-DRIVEN    : autoescape=False (Markdown / HTML 保持)
  AC-4 UNWANTED        : 残存 {{ }} で fail + commit しない
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from services import project_bootstrap_engine as pbe
from services.project_bootstrap_engine import (
    BootstrapError,
    DEFAULT_VALUES,
    REQUIRED_PLACEHOLDERS,
    render_project_bootstrap,
    render_template_string,
    validate_metadata,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPO_ROOT / "templates" / "project-bootstrap"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def good_metadata():
    return {
        "project_name": "TestProject",
        "project_slug": "test-project",
        "client_name": "ACME Corp",
        "deadline": "2026-12-31",
        "phase": "1",
        "owner_email": "test@example.com",
        "tech_stack": "FastAPI",
        "ai_employees": "mary, devon",
        "template_version": "1.2.0",
    }


@pytest.fixture
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS (#2): 10 placeholders サポート
# ══════════════════════════════════════════════════════════════════════


def test_ac1_required_placeholders_count_exactly_10():
    assert len(REQUIRED_PLACEHOLDERS) == 10


def test_ac1_required_placeholders_set():
    expected = {
        "project_name", "project_slug", "client_name", "deadline",
        "phase", "owner_email", "tech_stack", "ai_employees",
        "template_version", "generated_at",
    }
    assert set(REQUIRED_PLACEHOLDERS) == expected


def test_ac1_default_values_cover_optional_placeholders():
    """deadline / phase / tech_stack / ai_employees / template_version /
    owner_email は default で補完される (caller 不要)."""
    for key in (
        "deadline", "phase", "tech_stack", "ai_employees",
        "template_version", "owner_email",
    ):
        assert key in DEFAULT_VALUES


def test_ac1_validate_metadata_returns_all_required_keys(good_metadata):
    merged = validate_metadata(good_metadata)
    for key in REQUIRED_PLACEHOLDERS:
        assert key in merged
    # generated_at は runtime で確定 (int 文字列)
    assert merged["generated_at"].isdigit()


def test_ac1_minimum_metadata_with_defaults_works():
    """default が埋まる 4 placeholders だけでも minimum で動く."""
    minimal = {
        "project_name": "X", "project_slug": "x",
        "client_name": "C", "owner_email": "x@y.z",
    }
    merged = validate_metadata(minimal)
    assert merged["project_name"] == "X"
    assert merged["deadline"] == DEFAULT_VALUES["deadline"]


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS (#1): 全 .j2 を render
# ══════════════════════════════════════════════════════════════════════


def test_ac1_render_all_j2_files_in_template_root(tmp_path, good_metadata):
    result = render_project_bootstrap(good_metadata, output_dir=tmp_path)
    # templates/project-bootstrap 配下の全 .j2 件数
    j2_count = len(list(TEMPLATE_ROOT.rglob("*.j2")))
    assert j2_count >= 2  # CLAUDE.md.j2 + HANDOVER.md.j2 は確実に存在
    assert result["files_rendered"] == j2_count
    assert len(result["files_written"]) == j2_count


def test_ac1_render_strips_j2_suffix(tmp_path, good_metadata):
    result = render_project_bootstrap(good_metadata, output_dir=tmp_path)
    for rel in result["files_written"]:
        assert not rel.endswith(".j2")
    # CLAUDE.md.j2 → CLAUDE.md
    assert "CLAUDE.md" in result["files_written"]


def test_ac1_render_substitutes_placeholders(tmp_path, good_metadata):
    render_project_bootstrap(good_metadata, output_dir=tmp_path)
    claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "TestProject" in claude
    assert "ACME Corp" in claude


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 必須欠落で BootstrapError + atomic
# ══════════════════════════════════════════════════════════════════════


def test_ac2_validate_rejects_non_dict():
    for bad in (None, "str", [], 123):
        with pytest.raises(BootstrapError):
            validate_metadata(bad)


def test_ac2_validate_rejects_missing_required():
    with pytest.raises(BootstrapError, match="missing required placeholders"):
        validate_metadata({"project_name": "X"})


def test_ac2_validate_rejects_blank_required():
    bad = {
        "project_name": "", "project_slug": "x",
        "client_name": "C", "owner_email": "x@y.z",
    }
    with pytest.raises(BootstrapError, match="missing required placeholders"):
        validate_metadata(bad)


def test_ac2_atomic_no_file_written_on_missing_placeholder(tmp_path):
    """AC-2 atomic: 必須欠落で BootstrapError → output_dir に file 1 件も出ない."""
    bad = {"project_name": "X"}  # 他 9 件不足
    files_before = list(tmp_path.iterdir())
    with pytest.raises(BootstrapError):
        render_project_bootstrap(bad, output_dir=tmp_path)
    files_after = list(tmp_path.iterdir())
    assert files_before == files_after  # 何も書かれていない


def test_ac2_atomic_no_file_written_on_render_failure(tmp_path, good_metadata, monkeypatch):
    """Jinja2 render の中で例外が起きても output_dir に 1 件も書かない."""
    # template_root に 「未定義変数を使う bogus .j2」を 1 件足す
    bogus_root = tmp_path / "bogus_templates"
    bogus_root.mkdir()
    # 正常 .j2 1 件
    (bogus_root / "good.j2").write_text("hello {{project_name}}", encoding="utf-8")
    # 未定義変数 .j2 1 件 → StrictUndefined で例外
    (bogus_root / "bad.j2").write_text("oops {{unknown_var}}", encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with pytest.raises(BootstrapError):
        render_project_bootstrap(
            good_metadata, output_dir=out_dir, template_root=bogus_root,
        )
    # atomic: good.j2 も書かれていない
    assert list(out_dir.iterdir()) == []


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: autoescape=False (Markdown / HTML 保持)
# ══════════════════════════════════════════════════════════════════════


def test_ac3_autoescape_false_preserves_html(good_metadata):
    """HTML タグや & 等が escape されない."""
    text = "<b>{{project_name}}</b> & friends"
    out = render_template_string(text, validate_metadata(good_metadata))
    # autoescape=True なら &amp; / &lt; に変換される. False なので原文保持.
    assert "<b>TestProject</b>" in out
    assert " & " in out


def test_ac3_autoescape_false_preserves_markdown(good_metadata):
    """Markdown 表記 (>, |, *, _, #) が escape されない."""
    text = "# Hello {{project_name}}\n\n> note _italic_ *bold*"
    out = render_template_string(text, validate_metadata(good_metadata))
    assert "# Hello TestProject" in out
    assert "_italic_" in out and "*bold*" in out


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: 残存 {{ }} で fail
# ══════════════════════════════════════════════════════════════════════


def test_ac4_unrendered_placeholder_detected_in_string(good_metadata):
    """render 後に literal `{{ unknown }}` が残ったら fail."""
    # Jinja2 escape 構文 で literal を残す (raw block 経由)
    text = r"{% raw %}{{leftover_var}}{% endraw %}"
    with pytest.raises(BootstrapError, match="unrendered placeholders remain"):
        render_template_string(text, validate_metadata(good_metadata))


def test_ac4_unrendered_in_template_file_aborts_atomic(tmp_path, good_metadata):
    """render 結果に {{ }} が残る j2 があれば atomic abort."""
    root = tmp_path / "templates"
    root.mkdir()
    (root / "ok.j2").write_text("hi {{project_name}}", encoding="utf-8")
    # `raw` block で literal を残す → render 後に残存
    (root / "bad.j2").write_text("{% raw %}{{still_here}}{% endraw %}", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(BootstrapError, match="unrendered placeholders remain"):
        render_project_bootstrap(good_metadata, output_dir=out, template_root=root)
    assert list(out.iterdir()) == []


def test_ac4_validate_unrendered_can_be_disabled(good_metadata):
    """validate_unrendered=False で AC-4 check を skip できる (debug 用)."""
    text = r"{% raw %}{{x}}{% endraw %}"
    out = render_template_string(
        text, validate_metadata(good_metadata), validate_unrendered=False,
    )
    assert out == "{{x}}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 path traversal / safety
# ══════════════════════════════════════════════════════════════════════


def test_ac4_no_j2_in_template_root_raises(tmp_path, good_metadata):
    empty = tmp_path / "empty_templates"
    empty.mkdir()
    with pytest.raises(BootstrapError, match="no .j2 files"):
        render_project_bootstrap(good_metadata, output_dir=tmp_path, template_root=empty)


def test_ac4_missing_template_root_raises(tmp_path, good_metadata):
    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(BootstrapError, match="template_root not found"):
        render_project_bootstrap(
            good_metadata, output_dir=tmp_path, template_root=nonexistent,
        )


# ══════════════════════════════════════════════════════════════════════
# REST endpoint (AC 全網羅)
# ══════════════════════════════════════════════════════════════════════


def test_endpoint_placeholders(client):
    r = client.get("/api/bootstrap/placeholders")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 10
    assert set(body["required"]) == set(REQUIRED_PLACEHOLDERS)
    assert "deadline" in body["defaults"]


def test_endpoint_render_string_success(client, good_metadata):
    r = client.post("/api/bootstrap/render-string", json={
        "text": "hello {{project_name}}", "metadata": good_metadata,
    })
    assert r.status_code == 200
    assert "TestProject" in r.json()["rendered"]


def test_endpoint_render_string_missing_text_400(client, good_metadata):
    r = client.post("/api/bootstrap/render-string", json={
        "metadata": good_metadata,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bootstrap.invalid"


def test_endpoint_render_string_missing_required_400(client):
    r = client.post("/api/bootstrap/render-string", json={
        "text": "hi {{project_name}}", "metadata": {},
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bootstrap.missing_placeholders"


def test_endpoint_render_string_unrendered_400(client, good_metadata):
    r = client.post("/api/bootstrap/render-string", json={
        "text": r"{% raw %}{{unknown}}{% endraw %}", "metadata": good_metadata,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bootstrap.unrendered"


def test_endpoint_render_project_success(client, good_metadata, tmp_path):
    r = client.post("/api/bootstrap/render", json={
        "metadata": good_metadata,
        "output_dir": str(tmp_path),
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["files_rendered"] >= 2
    assert "CLAUDE.md" in body["files_written"]


def test_endpoint_render_invalid_output_dir_400(client, good_metadata):
    r = client.post("/api/bootstrap/render", json={
        "metadata": good_metadata, "output_dir": "",
    })
    assert r.status_code == 400


def test_endpoint_render_rejects_output_inside_templates(client, good_metadata):
    """templates/project-bootstrap/ 内への output は reject (上書き防止)."""
    r = client.post("/api/bootstrap/render", json={
        "metadata": good_metadata,
        "output_dir": str(TEMPLATE_ROOT / "out"),
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bootstrap.invalid"


def test_endpoint_render_missing_metadata_400(client, tmp_path):
    r = client.post("/api/bootstrap/render", json={
        "output_dir": str(tmp_path), "metadata": "not dict",
    })
    assert r.status_code == 400


def test_endpoint_all_4xx_detail_shape(client, good_metadata):
    """全 4xx response が {detail:{code,message}} 形式."""
    cases = [
        ("/api/bootstrap/render-string", {"metadata": {}}, 400),
        ("/api/bootstrap/render-string",
         {"text": "x", "metadata": {}}, 400),
        ("/api/bootstrap/render",
         {"metadata": good_metadata, "output_dir": ""}, 400),
    ]
    for path, body, expected in cases:
        r = client.post(path, json=body)
        assert r.status_code == expected, f"{path}: {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert detail.get("code", "").startswith("bootstrap.")
        assert isinstance(detail.get("message", ""), str) and detail["message"]


# ══════════════════════════════════════════════════════════════════════
# Cross-reference: tickets + ADR
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_btstrap_03_has_5_ac():
    import json
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-BTSTRAP-03"), None)
    assert t is not None
    # spec は 5 AC (UBIQUITOUS×2 + EVENT + STATE + UNWANTED)
    assert len(t["acceptance_criteria"]) == 5
    assert "T-BTSTRAP-01" in t.get("deps", [])


def test_module_docstring_documents_ac():
    doc = pbe.__doc__ or ""
    for ac in ("AC-1", "AC-2", "AC-3", "AC-4"):
        assert ac in doc
    assert "Jinja2" in doc
    assert "autoescape=False" in doc


def test_changelog_documents_template_version_1_2_0():
    """DEFAULT_VALUES.template_version が CHANGELOG 最新と一致."""
    changelog = (REPO_ROOT / "templates" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert DEFAULT_VALUES["template_version"] in changelog
