"""T-015-02: SVG 図解自動生成 (existing output_processor REFACTOR / pure svg builders).

既存 `backend/services/output_processor.py` (parse_table / checklist / list /
fence) は **完全無改変** (REUSE). 本 module は output_processor が抽出した
構造化 dict (table / checklist / list) を SVG markup に変換する純関数群を提供.

## 設計

  - 入力: dict (output_processor の戻り値と互換)
  - 出力: SVG string (HTML embeddable)
  - eb-* palette token 内蔵 (eb-500 #1a6648 を主色)
  - 外部 SVG library に依存しない (pure string builder + escape)

## ADR-010 整合性

LLM-generated 図解の表示は frontend / artifact_md_renderer 経由が現状.
本 module は backend で確定的 (deterministic) SVG を生成し、export_artifact
(T-015-01) との連携を可能にする.

## AC マッピング (T-015-02 REFACTOR)

  AC-1 UBIQUITOUS    : table_to_svg / checklist_to_svg / list_to_svg /
                       auto_diagram (dispatcher) を公開. 既存 output_processor 無改変.
  AC-2 EVENT-DRIVEN  : 100ms 以内 / 純関数 (deterministic).
  AC-3 STATE-DRIVEN  : 副作用なし / state mutate なし / XML escape 徹底.
  AC-4 UNWANTED      : invalid input (空 / 非 dict / 不正 schema) で
                       SvgDiagramError raise / XSS 防止のため特殊文字 escape.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SvgDiagramError(ValueError):
    """SVG diagram 生成エラー."""


# ──────────────────────────────────────────────────────────────────────
# Palette (CLAUDE.md §5.2)
# ──────────────────────────────────────────────────────────────────────

EB_500 = "#1a6648"  # ENGINE BASE primary
EB_400 = "#287058"
EB_200 = "#8fb5a3"
EB_50 = "#e8f2ec"
TEXT_DARK = "#1f2937"
TEXT_MUTED = "#6b7280"

DEFAULT_PADDING = 12
DEFAULT_ROW_HEIGHT = 28
DEFAULT_FONT_SIZE = 14
MAX_ROWS = 100
MAX_COLS = 20
MAX_TEXT_CHARS = 200


# ──────────────────────────────────────────────────────────────────────
# XML escape (XSS / malformed SVG 防止)
# ──────────────────────────────────────────────────────────────────────


def _xml_escape(text: object) -> str:
    """SVG text node 用 XML escape (& < > " ')."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    s = text
    if len(s) > MAX_TEXT_CHARS:
        s = s[:MAX_TEXT_CHARS] + "..."
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&#39;")
    )


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_dict(payload: object, *, kind: str) -> dict:
    if not isinstance(payload, dict):
        raise SvgDiagramError(f"{kind} payload must be dict")
    if not payload:
        raise SvgDiagramError(f"{kind} payload must not be empty")
    return payload


def _validate_str_list(items: object, *, field: str) -> list[str]:
    if not isinstance(items, list):
        raise SvgDiagramError(f"{field} must be a list")
    out = []
    for it in items[:MAX_ROWS]:
        out.append("" if it is None else str(it))
    return out


# ──────────────────────────────────────────────────────────────────────
# Table → SVG
# ──────────────────────────────────────────────────────────────────────


def table_to_svg(payload: dict) -> str:
    """Convert {headers, rows} dict to SVG table markup.

    Expected payload:
      {"headers": ["A", "B"], "rows": [["a1", "b1"], ["a2", "b2"]]}
    """
    d = _validate_dict(payload, kind="table")
    headers = _validate_str_list(d.get("headers", []), field="headers")
    rows_raw = d.get("rows", [])
    if not isinstance(rows_raw, list):
        raise SvgDiagramError("table.rows must be a list")
    rows = []
    for r in rows_raw[:MAX_ROWS]:
        if not isinstance(r, list):
            raise SvgDiagramError("each row must be a list")
        rows.append([_xml_escape(c) for c in r[:MAX_COLS]])
    if not headers and not rows:
        raise SvgDiagramError("table must have at least headers or rows")

    n_cols = max(len(headers), max((len(r) for r in rows), default=0))
    n_cols = min(n_cols, MAX_COLS)
    col_width = 160
    width = n_cols * col_width + DEFAULT_PADDING * 2
    height = (len(rows) + 1) * DEFAULT_ROW_HEIGHT + DEFAULT_PADDING * 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="table diagram">',
        f'<rect width="100%" height="100%" fill="white"/>',
    ]

    # header row
    for i in range(n_cols):
        x = DEFAULT_PADDING + i * col_width
        y = DEFAULT_PADDING
        parts.append(
            f'<rect x="{x}" y="{y}" width="{col_width}" '
            f'height="{DEFAULT_ROW_HEIGHT}" fill="{EB_500}" stroke="{EB_400}"/>'
        )
        label = _xml_escape(headers[i] if i < len(headers) else "")
        parts.append(
            f'<text x="{x + 8}" y="{y + 20}" font-size="{DEFAULT_FONT_SIZE}" '
            f'fill="white" font-weight="bold">{label}</text>'
        )

    # data rows
    for r_idx, row in enumerate(rows):
        for c_idx in range(n_cols):
            x = DEFAULT_PADDING + c_idx * col_width
            y = DEFAULT_PADDING + (r_idx + 1) * DEFAULT_ROW_HEIGHT
            bg = "white" if r_idx % 2 == 0 else EB_50
            parts.append(
                f'<rect x="{x}" y="{y}" width="{col_width}" '
                f'height="{DEFAULT_ROW_HEIGHT}" fill="{bg}" stroke="{EB_200}"/>'
            )
            cell = row[c_idx] if c_idx < len(row) else ""
            parts.append(
                f'<text x="{x + 8}" y="{y + 20}" font-size="{DEFAULT_FONT_SIZE}" '
                f'fill="{TEXT_DARK}">{cell}</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


# ──────────────────────────────────────────────────────────────────────
# Checklist → SVG
# ──────────────────────────────────────────────────────────────────────


def checklist_to_svg(payload: dict) -> str:
    """Convert {items: [{text, checked}]} dict to SVG checklist.

    Expected payload:
      {"items": [{"text": "...", "checked": true}, ...]}
    """
    d = _validate_dict(payload, kind="checklist")
    items_raw = d.get("items", [])
    if not isinstance(items_raw, list):
        raise SvgDiagramError("checklist.items must be a list")
    items = []
    for it in items_raw[:MAX_ROWS]:
        if not isinstance(it, dict):
            # tolerate plain strings
            items.append({"text": str(it), "checked": False})
            continue
        items.append({
            "text": _xml_escape(it.get("text", "")),
            "checked": bool(it.get("checked", False)),
        })
    if not items:
        raise SvgDiagramError("checklist must have at least 1 item")

    width = 640
    height = len(items) * DEFAULT_ROW_HEIGHT + DEFAULT_PADDING * 2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="checklist diagram">',
        f'<rect width="100%" height="100%" fill="white"/>',
    ]

    for i, it in enumerate(items):
        y = DEFAULT_PADDING + i * DEFAULT_ROW_HEIGHT + 4
        box_color = EB_500 if it["checked"] else "white"
        box_stroke = EB_500
        parts.append(
            f'<rect x="{DEFAULT_PADDING}" y="{y}" width="18" height="18" '
            f'fill="{box_color}" stroke="{box_stroke}" stroke-width="2" rx="2"/>'
        )
        if it["checked"]:
            parts.append(
                f'<path d="M{DEFAULT_PADDING + 3} {y + 10} l4 4 l8 -8" '
                f'stroke="white" stroke-width="2" fill="none"/>'
            )
        parts.append(
            f'<text x="{DEFAULT_PADDING + 26}" y="{y + 14}" '
            f'font-size="{DEFAULT_FONT_SIZE}" fill="{TEXT_DARK}">{it["text"]}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


# ──────────────────────────────────────────────────────────────────────
# List → SVG (bullet list)
# ──────────────────────────────────────────────────────────────────────


def list_to_svg(payload: dict) -> str:
    """Convert {items: [str]} or {items: [{text}]} to SVG bullet list."""
    d = _validate_dict(payload, kind="list")
    items_raw = d.get("items", [])
    if not isinstance(items_raw, list):
        raise SvgDiagramError("list.items must be a list")
    items = []
    for it in items_raw[:MAX_ROWS]:
        if isinstance(it, dict):
            items.append(_xml_escape(it.get("text", "")))
        else:
            items.append(_xml_escape(it))
    if not items:
        raise SvgDiagramError("list must have at least 1 item")

    width = 640
    height = len(items) * DEFAULT_ROW_HEIGHT + DEFAULT_PADDING * 2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="list diagram">',
        f'<rect width="100%" height="100%" fill="white"/>',
    ]

    for i, text in enumerate(items):
        y = DEFAULT_PADDING + i * DEFAULT_ROW_HEIGHT + 4
        cy = y + 9
        parts.append(
            f'<circle cx="{DEFAULT_PADDING + 6}" cy="{cy}" r="4" fill="{EB_500}"/>'
        )
        parts.append(
            f'<text x="{DEFAULT_PADDING + 18}" y="{y + 14}" '
            f'font-size="{DEFAULT_FONT_SIZE}" fill="{TEXT_DARK}">{text}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


# ──────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────

DIAGRAM_KINDS = ("table", "checklist", "list")


def auto_diagram(kind: str, payload: dict) -> str:
    """Dispatch to the appropriate diagram builder based on kind."""
    if not isinstance(kind, str):
        raise SvgDiagramError("kind must be string")
    k = kind.strip().lower()
    if k not in DIAGRAM_KINDS:
        raise SvgDiagramError(
            f"kind must be one of {DIAGRAM_KINDS}, got {kind!r}"
        )
    if k == "table":
        return table_to_svg(payload)
    if k == "checklist":
        return checklist_to_svg(payload)
    if k == "list":
        return list_to_svg(payload)
    raise SvgDiagramError(f"unknown kind: {k}")  # pragma: no cover


def list_diagram_kinds() -> list[str]:
    return list(DIAGRAM_KINDS)
