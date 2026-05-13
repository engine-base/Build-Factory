"""T-015-01: 共通テンプレ registry (existing artifact_export REFACTOR).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 6 公開 API / TEMPLATE_REGISTRY 3 種 / VALID_FORMATS 5 種 /
                       既存 artifact_export 無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : list 100ms / get info / render delegate.
  AC-3 STATE-DRIVEN  : read-only / 既存 artifact_export API 不変 /
                       minimal のみ available (corporate/branded placeholder).
  AC-4 UNWANTED      : invalid format / template / format×template 不整合 /
                       未 available template で ValueError.
"""
from __future__ import annotations

import json as _json
import re
import time
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "shared_templates.py"
EXISTING_EXPORT = REPO_ROOT / "backend" / "services" / "artifact_export.py"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_public_api():
    from services import shared_templates as st
    for sym in (
        "list_templates", "get_template_info", "validate_format_template",
        "render_with_template", "get_default_template",
        "is_format_supported_by_any",
        "TEMPLATE_REGISTRY", "VALID_FORMATS",
    ):
        assert hasattr(st, sym), f"missing st.{sym}"


def test_ac1_registry_has_3_templates():
    from services import shared_templates as st
    assert "minimal" in st.TEMPLATE_REGISTRY
    assert "corporate" in st.TEMPLATE_REGISTRY
    assert "branded" in st.TEMPLATE_REGISTRY


def test_ac1_registry_metadata_complete():
    from services import shared_templates as st
    required_keys = ("name", "display_name", "description",
                     "supported_formats", "tier", "available")
    for name, info in st.TEMPLATE_REGISTRY.items():
        for key in required_keys:
            assert key in info, f"{name} missing {key}"


def test_ac1_valid_formats_5():
    from services import shared_templates as st
    assert len(st.VALID_FORMATS) == 5
    for fmt in ("excel", "pptx", "pdf", "md", "html"):
        assert fmt in st.VALID_FORMATS


def test_ac1_existing_artifact_export_unchanged():
    """artifact_export.py に shared_templates 依存なし (REUSE)."""
    assert EXISTING_EXPORT.exists()
    src = EXISTING_EXPORT.read_text(encoding="utf-8")
    assert "from services.shared_templates" not in src
    assert "import services.shared_templates" not in src


def test_ac1_existing_artifact_export_has_required_symbols():
    from services import artifact_export as ae
    for sym in ("export_to_excel", "export_to_pptx", "export_to_pdf",
                "export_artifact"):
        assert hasattr(ae, sym)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: list / get / render
# ══════════════════════════════════════════════════════════════════════


def test_ac2_list_templates_returns_list_of_dicts():
    from services import shared_templates as st
    items = st.list_templates()
    assert isinstance(items, list)
    assert len(items) == 3
    for item in items:
        for key in ("name", "display_name", "supported_formats", "tier", "available"):
            assert key in item


def test_ac2_list_templates_only_available():
    from services import shared_templates as st
    items = st.list_templates(only_available=True)
    # minimal のみ available=True (corporate/branded は将来)
    assert len(items) == 1
    assert items[0]["name"] == "minimal"


def test_ac2_list_within_100ms():
    from services import shared_templates as st
    t0 = time.time()
    st.list_templates()
    elapsed = (time.time() - t0) * 1000
    assert elapsed < 100


def test_ac2_get_template_info_returns_dict():
    from services import shared_templates as st
    info = st.get_template_info("minimal")
    assert info["name"] == "minimal"
    assert info["available"] is True
    assert "excel" in info["supported_formats"]


def test_ac2_validate_format_template_valid_combo():
    from services import shared_templates as st
    result = st.validate_format_template("excel", "minimal")
    assert result["valid"] is True
    assert result["format"] == "excel"
    assert result["template"] == "minimal"


def test_ac2_render_with_template_delegates(monkeypatch, tmp_path):
    """render_with_template が export_artifact に delegate."""
    from services import shared_templates as st
    captured = {}

    def fake_export_artifact(artifact, format, template="minimal"):
        captured["args"] = (artifact, format, template)
        return tmp_path / f"out.{format}"

    monkeypatch.setattr(
        "services.artifact_export.export_artifact",
        fake_export_artifact,
    )

    result = st.render_with_template(
        {"id": 1, "name": "test"}, "excel", template_name="minimal",
    )
    assert captured["args"] == ({"id": 1, "name": "test"}, "excel", "minimal")
    assert result == tmp_path / "out.excel"


def test_ac2_get_default_template():
    from services import shared_templates as st
    assert st.get_default_template() == "minimal"


def test_ac2_is_format_supported_by_any():
    from services import shared_templates as st
    # minimal supports all 5 formats
    for fmt in ("excel", "pptx", "pdf", "md", "html"):
        assert st.is_format_supported_by_any(fmt) is True


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: read-only + immutable registry
# ══════════════════════════════════════════════════════════════════════


def test_ac3_registry_immutable_contract():
    """TEMPLATE_REGISTRY が module-level constant として動作."""
    from services import shared_templates as st
    # 元 dict を変更せずに list_templates の返値が dict copy であることを verify
    items = st.list_templates()
    items[0]["name"] = "HACKED"
    # 再取得して original 不変
    items2 = st.list_templates()
    assert items2[0]["name"] != "HACKED"


def test_ac3_module_does_not_write_to_audit_logs():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "emit_event" not in code
    assert "from services.memory_service" not in code


def test_ac3_only_minimal_available_currently():
    from services import shared_templates as st
    assert st.TEMPLATE_REGISTRY["minimal"]["available"] is True
    assert st.TEMPLATE_REGISTRY["corporate"]["available"] is False
    assert st.TEMPLATE_REGISTRY["branded"]["available"] is False


def _strip_comments(src: str) -> str:
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_format_raises():
    from services import shared_templates as st
    for bad in ("docx", "BOGUS", "", None, 123, []):
        with pytest.raises(ValueError):
            st.validate_format_template(bad, "minimal")


def test_ac4_invalid_template_raises():
    from services import shared_templates as st
    for bad in ("ultra", "BOGUS", "", None, 123):
        with pytest.raises(ValueError):
            st.get_template_info(bad)


def test_ac4_unsupported_format_template_combo_raises():
    """unsupported format×template combo → ValueError.
    実装では format check が available check より先に走るため、
    branded + md は 'does not support format' で reject される.
    corporate + excel (supported format だが available=False) は
    'not yet available' で reject される."""
    from services import shared_templates as st
    # branded + md → format 非対応で ValueError (branded は pdf/html のみ)
    with pytest.raises(ValueError, match="does not support format"):
        st.validate_format_template("md", "branded")
    # corporate + excel (supported format) → available=False で ValueError
    with pytest.raises(ValueError, match="not yet available"):
        st.validate_format_template("excel", "corporate")


def test_ac4_render_unavailable_template_raises(monkeypatch):
    from services import shared_templates as st

    def should_not_be_called(*a, **k):
        raise AssertionError("export_artifact should not be called for unavailable template")

    monkeypatch.setattr(
        "services.artifact_export.export_artifact",
        should_not_be_called,
    )
    with pytest.raises(ValueError):
        st.render_with_template({"id": 1}, "pdf", template_name="branded")


def test_ac4_render_invalid_artifact_raises():
    from services import shared_templates as st
    for bad in (None, "not dict", [], 123):
        with pytest.raises(ValueError):
            st.render_with_template(bad, "excel")


def test_ac4_only_available_validation_in_validate_format_template():
    from services import shared_templates as st
    # minimal + supported format → OK
    st.validate_format_template("md", "minimal")
    # minimal + unsupported format → ValueError ではない (minimal は all 5 format 対応)


def test_ac4_only_available_must_be_bool():
    from services import shared_templates as st
    for bad in ("yes", 1, 0, None):
        with pytest.raises(ValueError):
            st.list_templates(only_available=bad)


def test_ac4_no_hardcoded_secrets():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "Bearer " not in code


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_015_01_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-015-01"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the user interacts with the UI for T-015-01",
        "While refactoring for T-015-01 is in progress",
        "If invalid input or unauthorized actor is detected during T-015-01",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-015-01 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "shared_templates.py" in full
    assert "TEMPLATE_REGISTRY" in full
    assert "minimal" in full


def test_tickets_t_015_01_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-015-01"), None)
    assert t.get("adr_link") is not None
