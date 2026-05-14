"""T-AI-04: Constitution 自動注入エンジン.

CLAUDE.md §3 必須 8 項目 #4。 全 AI 社員のセッション開始時に
masato の judgment criteria (Constitution) を system prompt の cached prefix
として inject する。

## AC マッピング

- UBIQUITOUS: 全 session で最新 version を inject (prompt cache 用 prefix)
- EVENT:    Constitution 更新時に全 active session の cache を invalidate
- STATE:    secretary → 全文 / 他 role → Section 2 (values) + Section 4 (red lines)
- OPTIONAL: workspace 別 override マージ (workspace 優先)
- UNWANTED: corrupted/missing → AI session 全 block + alert (constitution なしで動かない)

## データ source

  1. DB: bf_constitutions テーブル (workspace=null = グローバル / workspace_id 指定で override)
     - principles JSONB: { "section_1_mission": "...", "section_2_values": [...],
                          "section_3_methods": [...], "section_4_red_lines": [...],
                          "section_5_examples": [...] }
     - is_current=TRUE が最新
  2. ファイル fallback: env CONSTITUTION_TEXT (envset) > docs/constitution.md

## Sections

  Section 1: ミッション / 事業
  Section 2: 価値観 (values) ← 全 role に inject
  Section 3: 行動原則 (methods)
  Section 4: レッドライン (red lines) ← 全 role に inject
  Section 5: 具体例 (examples)

## ADR-012 cascade (Memory Tool delegation)

ADR-012 で「T-AI-04 は Anthropic Memory Tool に delegate」と明記.
本 module は constitution の DB / env 読出 + AC-STATE role 別 inject の本体を
保持し, Memory Tool (services.anthropic_memory_tool) は constitution snapshot
を `/memories/constitution/<version>.json` に出力するファイル経路として
活用する (将来 PR で連携追加予定). 本 PR では cross-ref を docstring 化 +
audit emit + lint で機械検知強化.

## Gap closure (本 PR)

- G1 (AC-EVENT): invalidate_cache() で audit emit ('constitution.cache_invalidated').
- G2 (AC-UNWANTED): MissingConstitution / CorruptConstitution raise 時に
  audit emit ('constitution.session_blocked').
- G3 (AC-1/4): scripts/lint-mock.sh に check_no_self_constitution_inject を追加し,
  constitution を自前で system prompt に組み立てる経路を禁止 (本 module の
  inject_for_session() 以外).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# section の予約キー (DB principles JSONB)
SECTION_KEYS = (
    "section_1_mission",
    "section_2_values",
    "section_3_methods",
    "section_4_red_lines",
    "section_5_examples",
)

# 非 secretary に inject される sections (AC-STATE)
NON_SECRETARY_SECTIONS = ("section_2_values", "section_4_red_lines")


class ConstitutionError(RuntimeError):
    """Constitution の不在 / 破損 / 起動失敗の総称 (AC-UNWANTED で AI block する)."""


class CorruptConstitution(ConstitutionError):
    """principles が破損 / 必須 section 欠落."""


class MissingConstitution(ConstitutionError):
    """Constitution が DB にもファイルにも見つからない."""


@dataclass(frozen=True)
class Constitution:
    """1 つの Constitution snapshot."""

    version: int
    workspace_id: Optional[int]
    principles: dict[str, Any]
    authored_by: Optional[str] = None
    sections: tuple[str, ...] = field(default_factory=lambda: SECTION_KEYS)

    def section_text(self, key: str) -> str:
        v = self.principles.get(key)
        if v is None:
            return ""
        if isinstance(v, list):
            return "\n".join(f"- {item}" for item in v)
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False, indent=2)
        return str(v)

    def to_prompt(self, *, sections: tuple[str, ...]) -> str:
        """指定 section のみを system prompt 用テキストに."""
        parts: list[str] = [f"# 【Constitution v{self.version}】"]
        for sec in sections:
            body = self.section_text(sec)
            if body:
                parts.append(f"## {sec}\n{body}")
        return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────
# DB I/O (psycopg/sqlite lazy import)
# ──────────────────────────────────────────────────────────────────────────


def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


async def _load_from_db(workspace_id: Optional[int] = None) -> Optional[Constitution]:
    """bf_constitutions から is_current=TRUE な行を取得.

    project_id が workspace に紐づくため、 簡易的に workspace_id を project_id 相当として扱う
    (workspace 1 project 1 の前提)。 workspace_id=None なら project_id=NULL (グローバル) を許容。
    """
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            if workspace_id is None:
                cur = await db.execute(
                    "SELECT id, version, principles, authored_by FROM bf_constitutions "
                    "WHERE is_current = TRUE AND project_id IS NULL "
                    "ORDER BY version DESC LIMIT 1"
                )
            else:
                cur = await db.execute(
                    "SELECT id, version, principles, authored_by FROM bf_constitutions "
                    "WHERE is_current = TRUE AND project_id = ? "
                    "ORDER BY version DESC LIMIT 1",
                    (workspace_id,),
                )
            rows = await cur.fetchall()
    except Exception as e:
        logger.warning("constitution load failed: %s", e)
        return None

    if not rows:
        return None
    row = dict(rows[0])
    principles = row.get("principles")
    if isinstance(principles, str):
        try:
            principles = json.loads(principles)
        except Exception as e:
            raise CorruptConstitution(f"principles JSON parse failed: {e}")
    if not isinstance(principles, dict) or not principles:
        raise CorruptConstitution("principles must be non-empty object")
    return Constitution(
        version=int(row.get("version") or 1),
        workspace_id=workspace_id,
        principles=principles,
        authored_by=row.get("authored_by"),
    )


def _load_from_env() -> Optional[Constitution]:
    """env CONSTITUTION_TEXT を Section 2 (values) として読み込む fallback."""
    text = os.environ.get("CONSTITUTION_TEXT", "")
    if not text.strip():
        return None
    return Constitution(
        version=0,
        workspace_id=None,
        principles={"section_2_values": text.strip()},
    )


# ──────────────────────────────────────────────────────────────────────────
# Cache (AC-UBIQUITOUS prompt cache用 prefix / AC-EVENT invalidate)
# ──────────────────────────────────────────────────────────────────────────


_cache: dict[tuple[Optional[int], int], Constitution] = {}
_cache_lock = asyncio.Lock()


async def get_active_constitution(
    *, workspace_id: Optional[int] = None,
) -> Constitution:
    """最新 active Constitution を返す (cache hit 優先).

    Raises:
      MissingConstitution: DB にも env にも見つからない (AC-UNWANTED)
      CorruptConstitution: principles 破損 (AC-UNWANTED)
    """
    async with _cache_lock:
        # workspace_id が指定されたなら、 まず workspace 個別 → 無ければ global
        candidates = (workspace_id, None) if workspace_id is not None else (None,)
        for wid in candidates:
            cached = _cache.get((wid, 0))
            if cached is not None:
                return cached
            c = await _load_from_db(workspace_id=wid)
            if c is not None:
                _cache[(wid, 0)] = c
                return c

    # DB に無ければ env fallback
    env_c = _load_from_env()
    if env_c is None:
        # G2 (AC-UNWANTED): AI session 全 block + alert (audit emit)
        await _emit_audit(
            EVENT_SESSION_BLOCKED,
            detail={
                "reason": "missing",
                "workspace_id": workspace_id,
                "message": "Constitution not found in DB or CONSTITUTION_TEXT env",
            },
        )
        raise MissingConstitution(
            "Constitution not found (DB and CONSTITUTION_TEXT env both empty). "
            "AI sessions must be blocked until masato provides Constitution."
        )
    return env_c


async def _emit_audit(event_type: str, *, detail: dict) -> None:
    """audit_logs に event を emit. 失敗は warning のみ (best-effort)."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id="system", detail=detail)
    except Exception as e:  # pragma: no cover (sqlite 未配備環境向け)
        logger.warning("constitution audit emit failed %s: %s", event_type, e)


# audit event types (T-AI-04 gap closure G1/G2)
EVENT_CACHE_INVALIDATED = "constitution.cache_invalidated"
EVENT_SESSION_BLOCKED = "constitution.session_blocked"


async def invalidate_cache(*, reason: str = "manual") -> int:
    """AC-EVENT: Constitution 更新時に呼ぶ。 全 cache をクリア.

    G1 (gap closure): cleared entries count を audit emit する.

    Args:
      reason: invalidation 理由 (manual / version_bump / corruption_detected 等)

    Returns:
      クリアしたエントリ数.
    """
    async with _cache_lock:
        cleared = len(_cache)
        _cache.clear()
    await _emit_audit(
        EVENT_CACHE_INVALIDATED,
        detail={"cleared_entries": cleared, "reason": reason},
    )
    return cleared


# ──────────────────────────────────────────────────────────────────────────
# Merge (AC-OPTIONAL: workspace override)
# ──────────────────────────────────────────────────────────────────────────


def merge_constitutions(
    base: Constitution, override: Optional[Constitution],
) -> Constitution:
    """AC-OPTIONAL: workspace override が指定された section だけ上書き.

    workspace 優先 (conflict on section → workspace value)。
    """
    if override is None:
        return base
    merged: dict[str, Any] = dict(base.principles)
    for k, v in (override.principles or {}).items():
        if v is None or v == "" or v == []:
            continue
        merged[k] = v
    return Constitution(
        version=max(base.version, override.version),
        workspace_id=override.workspace_id,
        principles=merged,
        authored_by=override.authored_by or base.authored_by,
    )


# ──────────────────────────────────────────────────────────────────────────
# Inject (AC-UBIQUITOUS / STATE)
# ──────────────────────────────────────────────────────────────────────────


async def inject_for_session(
    *,
    role: str = "default",
    workspace_id: Optional[int] = None,
) -> str:
    """セッション開始時に system prompt 末尾へ追加する Constitution テキスト.

    AC-STATE: role='secretary' → 全 section、 他 → Section 2 + 4 のみ
    AC-UNWANTED: Constitution 不在 → MissingConstitution raise (caller が AI session block する)
    """
    # workspace override (AC-OPTIONAL)
    base = await get_active_constitution(workspace_id=None)
    override = None
    if workspace_id is not None:
        try:
            override = await _load_from_db(workspace_id=workspace_id)
        except Exception:
            override = None
    merged = merge_constitutions(base, override)

    # 必須 section の存在チェック (AC-UNWANTED corrupt)
    if role == "secretary":
        sections = SECTION_KEYS
    else:
        sections = NON_SECRETARY_SECTIONS
        # 非 secretary でも section_4_red_lines は必須 (AI block fallback 判定)
        for required in NON_SECRETARY_SECTIONS:
            if not merged.section_text(required):
                # Section 2 と 4 はどちらも無いとレッドラインが伝わらない → corrupted
                if required == "section_4_red_lines":
                    raise CorruptConstitution(
                        f"required section '{required}' is missing from Constitution"
                    )
    return merged.to_prompt(sections=sections)


# ──────────────────────────────────────────────────────────────────────────
# Health check (AC-UNWANTED guard at startup)
# ──────────────────────────────────────────────────────────────────────────


async def assert_constitution_available() -> Constitution:
    """起動時 health check: Constitution が存在し parse 可能であることを保証.

    AC-UNWANTED: corrupted/missing なら raise → caller が AI session を block する.
    G2: corrupted 検知時に audit emit ('constitution.session_blocked' reason='corrupt').
    """
    c = await get_active_constitution()
    if not c.principles:
        await _emit_audit(
            EVENT_SESSION_BLOCKED,
            detail={"reason": "corrupt", "message": "principles is empty"},
        )
        raise CorruptConstitution("Constitution principles is empty")
    if not c.section_text("section_4_red_lines"):
        await _emit_audit(
            EVENT_SESSION_BLOCKED,
            detail={
                "reason": "corrupt",
                "message": "section_4_red_lines missing",
                "version": c.version,
            },
        )
        raise CorruptConstitution(
            "Section 4 (red lines) is missing — AI session cannot start without red lines"
        )
    return c
