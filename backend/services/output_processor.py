"""
output_processor.py — AI 応答 → Artifact 自動生成

責務:
  AI 社員が返した markdown テキストや tool-ui ブロックを解析し、
  view 型に該当するパターンを検出して artifact を作成する。

スキル / AI 社員 はこの存在を知らない（外側から介入）。

検出する view 型（Phase 1 = 5 種）:
  - list      （箇条書き or タスクリスト）
  - table     （Markdown 表）
  - kanban    （明示的な ```kanban ブロック or AI が hint した時）
  - kpi-card  （明示的な ```kpi ブロック）
  - markdown  （上記に該当しない長文ドキュメント）

優先順位:
  1. 明示的フェンスブロック（```kanban / ```kpi 等）が最強
  2. 構造的に明確なもの（表・チェックリスト）
  3. それ以外の長文 → markdown 型に default fallback

設計原則:
  - 偽陽性を避ける（雑談を artifact 化しない）
  - 200 字以下・段落 1 つ以下は artifact 化しない
  - 同一スレッドに同じ type が既にある場合は更新候補として返す
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from services import artifact_service as art

# ──────────────────────────────────────────
# パターン検出器
# ──────────────────────────────────────────

# Markdown 表: |...|...|  ヘッダ行 + 区切り行 + 1 行以上のデータ
_TABLE_RE = re.compile(
    r"^\|.+\|\s*\n\|[\s\-:|]+\|\s*\n((?:\|.+\|\s*\n?)+)",
    re.MULTILINE,
)

# チェックリスト or 番号付き or "- " リスト（3 項目以上）
_LIST_ITEM_RE = re.compile(r"^\s*[-*]\s+(?:\[[ x]\]\s+)?(.+)$", re.MULTILINE)
_NUMBERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$", re.MULTILINE)
_CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[([ x])\]\s+(.+)$", re.MULTILINE)

# 明示的フェンスブロック: ```view-name JSON ```
_FENCE_RE = re.compile(
    r"```(list|table|kanban|kpi-card|kpi|markdown|chart|gantt|calendar|"
    r"compare|workflow|gallery|matrix|form|slide|mindmap)"
    r"\s*\n([\s\S]*?)\n```",
    re.IGNORECASE,
)


# ──────────────────────────────────────────
# 抽出関数（純粋関数・I/O 無し）
# ──────────────────────────────────────────

def _try_parse_table(text: str) -> Optional[dict]:
    m = _TABLE_RE.search(text)
    if not m:
        return None
    lines = text[m.start():m.end()].strip().split("\n")
    if len(lines) < 3:
        return None
    headers = [c.strip() for c in lines[0].strip("|").split("|")]
    rows = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(cells)
    if not rows:
        return None
    return {"columns": headers, "rows": rows}


def _try_parse_checklist(text: str) -> Optional[dict]:
    items = []
    for m in _CHECKBOX_RE.finditer(text):
        items.append({"text": m.group(2).strip(), "done": m.group(1) == "x"})
    if len(items) >= 2:
        return {"items": items}
    return None


def _try_parse_list(text: str) -> Optional[dict]:
    items = [m.group(1).strip() for m in _LIST_ITEM_RE.finditer(text)]
    items = [t for t in items if t and len(t) <= 200]
    if len(items) >= 3:
        return {"items": [{"text": t, "done": False} for t in items]}
    nums = [m.group(1).strip() for m in _NUMBERED_LIST_RE.finditer(text)]
    nums = [t for t in nums if t and len(t) <= 200]
    if len(nums) >= 3:
        return {"items": [{"text": t, "done": False} for t in nums]}
    return None


def _try_parse_fence(text: str) -> Optional[tuple[str, dict]]:
    """明示フェンス ```view-name\\n{...JSON...}\\n``` を検出する。

    対応する view 型（15 種すべて）:
      list / table / kanban / kpi-card / markdown
      chart / gantt / calendar / compare / workflow
      gallery / matrix / form / slide / mindmap
    """
    m = _FENCE_RE.search(text)
    if not m:
        return None
    raw = m.group(1).lower()
    lang = "kpi-card" if raw == "kpi" else raw
    body = m.group(2).strip()
    try:
        data = json.loads(body) if body.startswith("{") else {"text": body}
    except Exception:
        data = {"text": body}
    return lang, data


def _derive_title(text: str, fallback: str) -> str:
    """テキストから artifact タイトルを推定。最初の見出しを優先。"""
    h = re.search(r"^#+\s+(.+)$", text, re.MULTILINE)
    if h:
        return h.group(1).strip()[:80]
    line = text.strip().split("\n", 1)[0]
    return line[:60] if line else fallback


# ──────────────────────────────────────────
# 公開 API
# ──────────────────────────────────────────

async def process_ai_response(
    *,
    text: str,
    thread_id: Optional[int],
    employee_id: Optional[int],
    update_existing_id: Optional[str] = None,
) -> Optional[dict]:
    """AI 応答テキストから artifact を作成または更新する。

    Returns:
        作った artifact dict、もしくは検出無しなら None。
    """
    if not text or len(text) < 20:
        return None

    detected_type: Optional[str] = None
    data: Optional[dict] = None

    # 1. 明示フェンス（最優先）
    fence = _try_parse_fence(text)
    if fence:
        detected_type, data = fence

    # 2. 表
    if detected_type is None:
        tbl = _try_parse_table(text)
        if tbl:
            detected_type, data = "table", tbl

    # 3. チェックリスト
    if detected_type is None:
        cl = _try_parse_checklist(text)
        if cl:
            detected_type, data = "list", cl

    # 4. リスト（3 項目以上）
    if detected_type is None:
        ls = _try_parse_list(text)
        if ls and len(text) > 80:
            detected_type, data = "list", ls

    # 5. 長文 → markdown ドキュメント
    if detected_type is None:
        if len(text) > 400 and text.count("\n") > 4:
            detected_type, data = "markdown", {"text": text}

    if detected_type is None or data is None:
        return None

    title = _derive_title(text, fallback=detected_type)

    if update_existing_id:
        return await art.update_artifact(
            update_existing_id, title=title, data=data,
            actor=f"ai:employee_{employee_id}" if employee_id else "ai:secretary",
            note="AI 応答により更新",
        )
    return await art.create_artifact(
        type=detected_type, title=title, data=data,
        thread_id=thread_id, employee_id=employee_id,
        created_by=f"ai:employee_{employee_id}" if employee_id else "ai:secretary",
        actor=f"ai:employee_{employee_id}" if employee_id else "ai:secretary",
    )


async def find_active_artifact_for_thread(
    thread_id: int, type: Optional[str] = None,
) -> Optional[dict]:
    """同一スレッドの直近 artifact を返す（更新先候補）。"""
    items = await art.list_artifacts(thread_id=thread_id, type=type, limit=1)
    return items[0] if items else None
