"""T-015-02: SVG 図解自動生成 (existing output_processor REFACTOR).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 5 公開 API / eb-* palette / 既存 output_processor 無改変.
  AC-2 EVENT-DRIVEN  : 100ms 以内 (pure function) / XML escape / aria-label.
  AC-3 STATE-DRIVEN  : 副作用なし / MAX_ROWS=100, MAX_COLS=20, MAX_TEXT=200 制限.
  AC-4 UNWANTED      : invalid kind / payload で SvgDiagramError / XSS escape.
"""
from __future__ import annotations

import json as _json
import re
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "svg_diagram.py"
EXISTING_OP = REPO_ROOT / "backend" / "services" / "output_processor.py"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_public_api():
    from services import svg_diagram as sd
    for sym in (
        "table_to_svg", "checklist_to_svg", "list_to_svg",
        "auto_diagram", "list_diagram_kinds",
        "SvgDiagramError", "DIAGRAM_KINDS",
        "EB_500", "EB_400", "EB_200", "EB_50",
        "MAX_ROWS", "MAX_COLS", "MAX_TEXT_CHARS",
    ):
        assert hasattr(sd, sym), f"missing service.{sym}"


def test_ac1_eb_palette_values():
    from services import svg_diagram as sd
    assert sd.EB_500 == "#1a6648"


def test_ac1_existing_output_processor_unchanged():
    """output_processor.py に svg_diagram 依存なし (REUSE)."""
    assert EXISTING_OP.exists()
    src = EXISTING_OP.read_text(encoding="utf-8")
    assert "from services.svg_diagram" not in src
    assert "import services.svg_diagram" not in src


def test_ac1_existing_output_processor_symbols_intact():
    """既存 output_processor の主要 symbol が残っている."""
    from services import output_processor as op
    for sym in ("process_ai_response",):
        assert hasattr(op, sym)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 100ms / XML escape / aria-label
# ══════════════════════════════════════════════════════════════════════


def test_ac2_table_to_svg_basic():
    from services import svg_diagram as sd
    svg = sd.table_to_svg({
        "headers": ["Col A", "Col B"],
        "rows": [["1", "2"], ["3", "4"]],
    })
    assert svg.startswith("<svg ")
    assert svg.endswith("</svg>")
    assert "Col A" in svg
    assert "Col B" in svg
    assert "1" in svg
    assert sd.EB_500 in svg


def test_ac2_checklist_to_svg_basic():
    from services import svg_diagram as sd
    svg = sd.checklist_to_svg({
        "items": [
            {"text": "Done item", "checked": True},
            {"text": "Pending", "checked": False},
        ],
    })
    assert "Done item" in svg
    assert "Pending" in svg
    assert sd.EB_500 in svg


def test_ac2_list_to_svg_basic():
    from services import svg_diagram as sd
    svg = sd.list_to_svg({"items": ["alpha", "beta", "gamma"]})
    for item in ("alpha", "beta", "gamma"):
        assert item in svg


def test_ac2_within_100ms():
    from services import svg_diagram as sd
    t0 = time.time()
    sd.table_to_svg({
        "headers": ["A", "B", "C"],
        "rows": [[str(i), str(i*2), str(i*3)] for i in range(20)],
    })
    elapsed = (time.time() - t0) * 1000
    assert elapsed < 100


def test_ac2_xml_escape_special_chars():
    from services import svg_diagram as sd
    svg = sd.list_to_svg({
        "items": ["<script>alert(1)</script>", "a & b", "she said \"hi\""],
    })
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    assert "&amp;" in svg
    assert "&quot;" in svg


def test_ac2_aria_label_present():
    from services import svg_diagram as sd
    for builder, payload in [
        (sd.table_to_svg, {"headers": ["a"], "rows": [["b"]]}),
        (sd.checklist_to_svg, {"items": [{"text": "x", "checked": False}]}),
        (sd.list_to_svg, {"items": ["x"]}),
    ]:
        svg = builder(payload)
        assert 'role="img"' in svg
        assert "aria-label" in svg


def test_ac2_auto_diagram_dispatch():
    from services import svg_diagram as sd
    for kind, payload in [
        ("table", {"headers": ["a"], "rows": [["b"]]}),
        ("checklist", {"items": ["x"]}),
        ("list", {"items": ["y"]}),
    ]:
        svg = sd.auto_diagram(kind, payload)
        assert svg.startswith("<svg ")


def test_ac2_list_diagram_kinds():
    from services import svg_diagram as sd
    kinds = sd.list_diagram_kinds()
    assert set(kinds) == {"table", "checklist", "list"}


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: no side effects + limits
# ══════════════════════════════════════════════════════════════════════


def test_ac3_max_rows_cap():
    """MAX_ROWS を超える input は truncate."""
    from services import svg_diagram as sd
    payload = {"items": [f"item-{i}" for i in range(200)]}
    svg = sd.list_to_svg(payload)
    # MAX_ROWS=100 までしか含まれない
    assert "item-99" in svg
    # 100 以上は除外
    assert "item-150" not in svg


def test_ac3_max_text_chars_truncate():
    """長文字列は MAX_TEXT_CHARS で truncate (+ '...')."""
    from services import svg_diagram as sd
    long_text = "x" * 500
    svg = sd.list_to_svg({"items": [long_text]})
    # 200 + "..." までしか含まれない
    assert "..." in svg
    assert "x" * 500 not in svg


def test_ac3_module_does_not_write_audit_logs():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "emit_event" not in code
    assert "from services.memory_service" not in code


def test_ac3_no_http_or_file_io():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "httpx" not in code
    assert "requests.get" not in code
    assert "open(" not in code
    assert "Path(" not in code or "Path(__file__)" not in code  # logger only


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
# AC-4 UNWANTED: invalid input + XSS escape
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_payload_type_raises():
    from services import svg_diagram as sd
    for bad in (None, "not dict", [], 123):
        with pytest.raises(sd.SvgDiagramError):
            sd.table_to_svg(bad)


def test_ac4_empty_payload_raises():
    from services import svg_diagram as sd
    with pytest.raises(sd.SvgDiagramError):
        sd.table_to_svg({})


def test_ac4_invalid_table_rows_raises():
    from services import svg_diagram as sd
    with pytest.raises(sd.SvgDiagramError):
        sd.table_to_svg({"headers": ["a"], "rows": "not list"})


def test_ac4_invalid_table_row_item_raises():
    from services import svg_diagram as sd
    with pytest.raises(sd.SvgDiagramError):
        sd.table_to_svg({"headers": ["a"], "rows": ["not_list_row"]})


def test_ac4_empty_checklist_items_raises():
    from services import svg_diagram as sd
    with pytest.raises(sd.SvgDiagramError):
        sd.checklist_to_svg({"items": []})


def test_ac4_invalid_kind_raises():
    from services import svg_diagram as sd
    for bad in ("BOGUS", "", None, 123, "graph"):
        with pytest.raises(sd.SvgDiagramError):
            sd.auto_diagram(bad, {"headers": ["a"], "rows": []})


def test_ac4_xss_escape_in_text():
    """text 内の特殊文字を XML escape (XSS 防止)."""
    from services import svg_diagram as sd
    svg = sd.table_to_svg({
        "headers": ["<img onerror='alert(1)'>", "x"],
        "rows": [["<script>", "y"]],
    })
    assert "<img" not in svg.replace("<svg", "X")  # SVG root 以外に <img> なし
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_ac4_no_hardcoded_secret():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_015_02_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-015-02"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the relevant API endpoint or service function is invoked for T-015-02",
        "While refactoring for T-015-02 is in progress",
        "If invalid input or unauthorized actor is detected during T-015-02",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-015-02 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "svg_diagram.py" in full
    assert "table_to_svg" in full
    assert "SvgDiagramError" in full


def test_tickets_t_015_02_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-015-02"), None)
    assert t.get("adr_link") is not None
