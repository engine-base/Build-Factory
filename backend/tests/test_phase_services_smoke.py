"""Smoke tests for high-stmt low-coverage phase services (CLAUDE.md §5.3).

Wave-2 follow-up to #221 (which covered the 0 % files).
This PR targets the 5 services that hold the most stmts at < 20 %:
- services/requirements_service.py  483 stmts, 10 %
- services/proposal_service.py      431 stmts, 10 %
- services/estimate_service.py      376 stmts, 11 %
- services/pricing_design_service.py 370 stmts, 11 %
- services/artifact_export.py       307 stmts, 5 %

Tests cover the shared pure helpers (get_step_meta / empty_center_state
/ _load_skill_md / _extract_common_rules / _extract_step_section)
plus artifact_export pure helpers (_ts / _output_path / format dispatch).
"""
from __future__ import annotations

import re

import pytest


# ══════════════════════════════════════════════════════════════════════
# Shared "phase service" smoke (4 services × ~5 helpers = 20 tests)
# ══════════════════════════════════════════════════════════════════════


PHASE_SERVICES = [
    "services.requirements_service",
    "services.proposal_service",
    "services.estimate_service",
    "services.pricing_design_service",
]


@pytest.mark.parametrize("mod_path", PHASE_SERVICES)
class TestPhaseServiceSharedHelpers:

    def test_steps_constant_exists_and_non_empty(self, mod_path):
        import importlib
        m = importlib.import_module(mod_path)
        assert hasattr(m, "STEPS")
        assert isinstance(m.STEPS, list)
        assert len(m.STEPS) > 0
        for s in m.STEPS:
            assert "step" in s

    def test_get_step_meta_returns_dict_for_valid_step(self, mod_path):
        import importlib
        m = importlib.import_module(mod_path)
        first = m.STEPS[0]["step"]
        meta = m.get_step_meta(first)
        assert isinstance(meta, dict)
        assert meta.get("step") == first

    def test_get_step_meta_returns_none_for_invalid_step(self, mod_path):
        import importlib
        m = importlib.import_module(mod_path)
        assert m.get_step_meta(99999) is None

    def test_empty_center_state_unknown_step_returns_skeleton(self, mod_path):
        import importlib
        m = importlib.import_module(mod_path)
        out = m.empty_center_state(99999)
        assert isinstance(out, dict)
        assert out["step"] == 99999
        assert "sections" in out
        assert out["sections"] == []

    def test_empty_center_state_valid_step_returns_dict(self, mod_path):
        import importlib
        m = importlib.import_module(mod_path)
        first = m.STEPS[0]["step"]
        out = m.empty_center_state(first)
        assert isinstance(out, dict)
        assert out["step"] == first

    def test_load_skill_md_returns_string(self, mod_path):
        import importlib
        m = importlib.import_module(mod_path)
        if not hasattr(m, "_load_skill_md"):
            pytest.skip(f"{mod_path}._load_skill_md absent")
        out = m._load_skill_md()
        assert isinstance(out, str)  # may be "" if file absent

    def test_extract_common_rules_returns_string(self, mod_path):
        import importlib
        m = importlib.import_module(mod_path)
        if not hasattr(m, "_extract_common_rules"):
            pytest.skip(f"{mod_path}._extract_common_rules absent")
        out = m._extract_common_rules("## \U0001f9e0 全スキル共通\nrule a\nrule b\n")
        assert isinstance(out, str)
        # 空入力でも例外を出さない
        assert isinstance(m._extract_common_rules(""), str)

    def test_extract_step_section_returns_string(self, mod_path):
        import importlib
        m = importlib.import_module(mod_path)
        if not hasattr(m, "_extract_step_section"):
            pytest.skip(f"{mod_path}._extract_step_section absent")
        out = m._extract_step_section("dummy skill md", 1)
        assert isinstance(out, str)


# ══════════════════════════════════════════════════════════════════════
# services/artifact_export.py — pure path / dispatch helpers
# ══════════════════════════════════════════════════════════════════════


class TestArtifactExport:
    def test_ts_returns_timestamp_string(self):
        from services.artifact_export import _ts
        out = _ts()
        assert isinstance(out, str)
        # YYYYMMDD_HHMMSS shape
        assert re.fullmatch(r"\d{8}_\d{6}", out)

    def test_output_path_creates_dir_and_returns_path(self, tmp_path, monkeypatch):
        from pathlib import Path
        import services.artifact_export as ae
        monkeypatch.setattr(ae, "EXPORT_DIR", tmp_path)
        out = ae._output_path("test-artifact-id", "xlsx")
        assert isinstance(out, Path)
        assert out.parent.exists()  # mkdir(parents=True, exist_ok=True)
        assert out.suffix == ".xlsx"

    def test_export_artifact_dispatches_by_format(self, tmp_path, monkeypatch):
        """export_artifact should route via EXPORTERS dict by format key."""
        import services.artifact_export as ae
        monkeypatch.setattr(ae, "EXPORT_DIR", tmp_path)

        called = {}
        def fake_excel(artifact, template="minimal"):
            called["excel"] = True
            return tmp_path / "out.xlsx"
        def fake_pptx(artifact, template="minimal"):
            called["pptx"] = True
            return tmp_path / "out.pptx"
        def fake_pdf(artifact, template="minimal"):
            called["pdf"] = True
            return tmp_path / "out.pdf"

        # EXPORTERS dict is bound at import time → patch the dict itself
        monkeypatch.setitem(ae.EXPORTERS, "excel", fake_excel)
        monkeypatch.setitem(ae.EXPORTERS, "pptx", fake_pptx)
        monkeypatch.setitem(ae.EXPORTERS, "pdf", fake_pdf)

        ae.export_artifact({"id": "x"}, "excel")
        ae.export_artifact({"id": "x"}, "pptx")
        ae.export_artifact({"id": "x"}, "pdf")
        assert called == {"excel": True, "pptx": True, "pdf": True}

    def test_export_artifact_unknown_format_raises(self, tmp_path, monkeypatch):
        import services.artifact_export as ae
        monkeypatch.setattr(ae, "EXPORT_DIR", tmp_path)
        # contract: unsupported format → ValueError("unsupported format: ...")
        with pytest.raises(ValueError, match="unsupported format"):
            ae.export_artifact({"id": "x"}, "unknown_xyz_format")


# ══════════════════════════════════════════════════════════════════════
# services/requirements_service.py — additional pure helpers
# ══════════════════════════════════════════════════════════════════════


class TestRequirementsServiceHelpers:
    def test_gather_project_context_returns_string(self):
        import services.requirements_service as m
        if not hasattr(m, "_gather_project_context"):
            pytest.skip("_gather_project_context absent")
        out = m._gather_project_context(
            hearing_brief={"goal": "X", "client": "Y"},
            req_centers=[],
        )
        assert isinstance(out, str)
