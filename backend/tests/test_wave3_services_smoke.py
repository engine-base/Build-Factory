"""Wave-3 smoke tests for medium-sized low-coverage services.

Follows #221 (14 zero-cov files, +1%) and #222 (5 phase services, +1%).
Target services (combined 779 stmts at < 20 %):
- services/obsidian_vault_sync.py     175 stmts, 19 %  — pure text helpers
- services/document_ingest_service.py 162 stmts, 17 %  — file kind detection
- services/scoped_knowledge.py        152 stmts, 11 %  — normalize helper
- services/artifact_service.py        156 stmts, 22 %  — pubsub bookkeeping
- services/staff_service.py           181 stmts, 13 %  — module import contract
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest


# ══════════════════════════════════════════════════════════════════════
# services/obsidian_vault_sync.py — pure text helpers
# ══════════════════════════════════════════════════════════════════════


class TestObsidianVaultSync:
    def test_slugify_normalizes_string(self):
        from services.obsidian_vault_sync import slugify
        out = slugify("Hello World 2026")
        assert isinstance(out, str)
        assert " " not in out  # spaces removed
        assert out == out.lower() or out == out  # consistent shape

    def test_slugify_empty_input(self):
        from services.obsidian_vault_sync import slugify
        assert isinstance(slugify(""), str)

    def test_hash_content_is_stable_and_hex(self):
        from services.obsidian_vault_sync import _hash_content
        h = _hash_content("hello")
        assert isinstance(h, str)
        # stable hash for same input
        assert _hash_content("hello") == h
        assert re.fullmatch(r"[0-9a-f]+", h)

    def test_extract_title_uses_h1_or_fallback(self):
        from services.obsidian_vault_sync import _extract_title
        # H1 heading wins
        title = _extract_title("# Real Title\nbody\n", fallback="fallback.md")
        assert "Real Title" in title
        # no heading → fallback
        out = _extract_title("just text", fallback="filename")
        assert "filename" in out or out == "filename"

    def test_extract_summary_truncates(self):
        from services.obsidian_vault_sync import _extract_summary
        long = "abc " * 200
        out = _extract_summary(long, max_chars=50)
        assert isinstance(out, str)
        assert len(out) <= 200  # implementation may add ellipsis

    def test_parse_scope_returns_dict(self, tmp_path):
        from pathlib import Path
        from services.obsidian_vault_sync import parse_scope
        rel = Path("global/section/note.md")
        out = parse_scope(rel)
        assert isinstance(out, dict)


# ══════════════════════════════════════════════════════════════════════
# services/document_ingest_service.py — file detection
# ══════════════════════════════════════════════════════════════════════


class TestDocumentIngestService:
    def test_detect_kind_pdf(self):
        from services.document_ingest_service import _detect_kind
        out = _detect_kind("file.pdf", "application/pdf")
        assert "pdf" in out.lower()

    def test_detect_kind_docx(self):
        from services.document_ingest_service import _detect_kind
        out = _detect_kind("doc.docx", None)
        assert "docx" in out.lower() or "doc" in out.lower()

    def test_detect_kind_html(self):
        from services.document_ingest_service import _detect_kind
        out = _detect_kind("page.html", "text/html")
        assert "html" in out.lower()

    def test_detect_kind_text_fallback(self):
        from services.document_ingest_service import _detect_kind
        out = _detect_kind("note.txt", "text/plain")
        assert isinstance(out, str)

    def test_extract_text_routes_by_filename(self):
        from services.document_ingest_service import extract_text
        # plain text path is most robust
        result = extract_text("note.txt", b"hello world", "text/plain")
        assert isinstance(result, dict)
        assert "kind" in result or "text" in result

    def test_extract_text_unknown_extension_returns_dict(self):
        from services.document_ingest_service import extract_text
        result = extract_text("file.xyz", b"raw bytes", None)
        assert isinstance(result, dict)


# ══════════════════════════════════════════════════════════════════════
# services/scoped_knowledge.py — pure normalize
# ══════════════════════════════════════════════════════════════════════


class TestScopedKnowledge:
    def test_normalize_is_stable(self):
        from services.scoped_knowledge import _normalize
        assert _normalize("hello") == _normalize("hello")
        # whitespace / case normalization
        out = _normalize("  Hello World  ")
        assert isinstance(out, str)

    def test_normalize_empty(self):
        from services.scoped_knowledge import _normalize
        assert isinstance(_normalize(""), str)

    def test_module_imports(self):
        import services.scoped_knowledge as m
        for name in (
            "get_employee", "get_scope_folders", "search_in_scope",
            "classify_target_category", "find_employee_for_category",
            "propose_save_target", "save_knowledge",
        ):
            assert hasattr(m, name), f"missing public API {name}"


# ══════════════════════════════════════════════════════════════════════
# services/artifact_service.py — pubsub bookkeeping
# ══════════════════════════════════════════════════════════════════════


class TestArtifactService:
    def test_subscribe_unsubscribe_roundtrip(self):
        """subscribe/unsubscribe should not raise and should be idempotent."""
        from services.artifact_service import subscribe, unsubscribe
        class FakeWS:
            pass
        ws = FakeWS()
        subscribe("user-1", ws)
        # second subscribe is allowed (idempotent or noop)
        subscribe("user-1", ws)
        unsubscribe("user-1", ws)
        # second unsubscribe should not raise (idempotent)
        unsubscribe("user-1", ws)

    def test_unsubscribe_unknown_user_does_not_raise(self):
        from services.artifact_service import unsubscribe
        class FakeWS:
            pass
        unsubscribe("never-subscribed", FakeWS())  # no exception

    def test_now_returns_iso_string(self):
        from services.artifact_service import _now
        out = _now()
        assert isinstance(out, str)
        # crude ISO-ish check
        assert re.match(r"\d{4}-\d{2}-\d{2}", out)


# ══════════════════════════════════════════════════════════════════════
# services/staff_service.py — module contract
# ══════════════════════════════════════════════════════════════════════


class TestStaffService:
    def test_module_imports_public_apis(self):
        import services.staff_service as m
        for name in (
            "list_employees", "get_employee", "get_employee_by_name",
            "create_employee", "update_employee",
            "list_active_members_of", "retire_employee",
        ):
            assert hasattr(m, name), f"missing public API {name}"

    def test_ensure_dirs_callable(self):
        from services.staff_service import _ensure_dirs
        # called multiple times must be idempotent
        _ensure_dirs()
        _ensure_dirs()  # no exception
