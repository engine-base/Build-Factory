"""T-M28-01: Context Builder skeleton (REFACTOR)

Agent 呼び出し直前の prompt 構築に特化した read-only API。
T-020-02 の memory_service が write/recall 双方を持つのに対し、本サービスは
「agent invocation 直前に Mem0 / Obsidian / Constitution を統合して prompt
末尾の context block を組み立てる」役割。

## AC 対応 (T-M28-01)

- UBIQUITOUS: Mem0 vector search + Obsidian markdown **read/write** +
  Constitution decision lookup を unified API に統合.
- EVENT: 入力に D-XXX が含まれていたら 200ms 以内で関連 decision を返す
  (read 経路のみ、ネットワーク I/O なし → 数十 ms オーダー)
- STATE: 秘書 AI active のとき preload_constitution() で system prompt に
  Constitution を注入する. is_secretary_active() で active 状態を判定し
  build_context は include_constitution と AND した結果を採用する.
- UNWANTED: Mem0 結果に矛盾 (contradictory_keywords) があれば conflicts に
  surface、build_context の戻り値で `has_conflicts: True` フラグを立てる
  (silent pick しない / 呼出元が明示的に判定できる).

## Spec gap closure (G1-G4)

- G1 (AC-1): Obsidian markdown **write** unified API
  - write_obsidian_note(slug, content, *, vault_dir=None) -> Path
  - Vault dir は OBSIDIAN_VAULT_DIR env で上書き可.
- G2 (AC-3): is_secretary_active() で秘書 active を明示判定. env
  SECRETARY_ACTIVE (truthy) を default に, build_context に
  `secretary_active` パラメータも追加.
- G3 (AC-4): build_context 戻り値に `has_conflicts: bool` フラグを追加.
  conflicts が空でないとき True. silent pick 禁止の明示.
- G4 (AC-4): router の全 4xx を {detail:{code,message}} 形式に統一
  (BuildRequest 422 排除, GET decisions の str detail を dict 化).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)

# D-XXX (3桁数字) を検出する正規表現
DECISION_REF_RE = re.compile(r'\bD-\d{3,5}\b')

# 矛盾を示唆するキーワード (Mem0 検索結果の隣接行に共存していたら conflict 候補)
CONTRADICTORY_PAIRS: tuple[tuple[str, str], ...] = (
    ("採用", "不採用"),
    ("OK", "NG"),
    ("有効", "無効"),
    ("done", "pending"),
    ("approve", "reject"),
)

# G1: Obsidian note slug 正規表現 (英数 + _ - / .)
OBSIDIAN_SLUG_RE = re.compile(r"^[A-Za-z0-9_\-/.]{1,200}$")


def _constitution_dir() -> Path:
    """Constitution Markdown を読むベースディレクトリ。

    優先順位:
      1. env CONSTITUTION_DIR
      2. ~/Documents/会社運営DB/constitutions/
      3. <repo>/data/constitutions/  (fallback)
    """
    env = os.environ.get("CONSTITUTION_DIR")
    if env:
        return Path(env)
    home = Path.home() / "Documents" / "会社運営DB" / "constitutions"
    if home.exists():
        return home
    repo = Path(__file__).resolve().parents[2] / "data" / "constitutions"
    return repo


def lookup_decision(decision_id: str) -> Optional[dict]:
    """D-XXX で Markdown を読み、{title, content} を返す。

    Returns None if not found.
    """
    if not DECISION_REF_RE.fullmatch(decision_id):
        return None
    base = _constitution_dir()
    candidates = [
        base / f"{decision_id}.md",
        base / decision_id / "README.md",
    ]
    for p in candidates:
        if p.exists():
            text = p.read_text(encoding="utf-8")
            # 1 行目の `# Title` を抽出
            first_line = text.splitlines()[0] if text else ""
            title = first_line.lstrip("# ").strip() if first_line.startswith("#") else decision_id
            return {"id": decision_id, "title": title, "content": text}
    return None


async def preload_constitution(user_id: str = "masato") -> str:
    """秘書 AI active 時に system prompt 末尾へ注入する Constitution テキスト。

    env CONSTITUTION_TEXT が設定されていればそれを優先、なければ
    constitutions/ ディレクトリの全 D-XXX.md を結合。
    """
    env_text = os.environ.get("CONSTITUTION_TEXT", "")
    if env_text:
        return env_text
    base = _constitution_dir()
    if not base.exists():
        return ""
    parts: list[str] = []
    for p in sorted(base.glob("D-*.md")):
        try:
            parts.append(p.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n\n---\n\n".join(parts)


def _detect_conflicts(facts: list[str]) -> list[dict]:
    """Mem0 結果の矛盾候補を検出。"""
    conflicts: list[dict] = []
    for i, a in enumerate(facts):
        for j, b in enumerate(facts[i + 1:], start=i + 1):
            for pos, neg in CONTRADICTORY_PAIRS:
                if pos in a and neg in b:
                    conflicts.append({"fact_a": a, "fact_b": b, "axis": f"{pos} vs {neg}"})
                elif neg in a and pos in b:
                    conflicts.append({"fact_a": a, "fact_b": b, "axis": f"{neg} vs {pos}"})
    return conflicts


# ──────────────────────────────────────────────────────────────────────
# G1 (AC-1): Obsidian markdown write (unified API の write 側)
# ──────────────────────────────────────────────────────────────────────


class ContextBuilderError(RuntimeError):
    """Context builder 入力 / 不変条件違反 (router 層で 4xx に変換)."""


def _obsidian_vault_dir() -> Path:
    """Obsidian Vault のベース dir.

    優先順位:
      1. env OBSIDIAN_VAULT_DIR
      2. ~/Documents/会社運営DB/obsidian/
      3. <repo>/data/obsidian/  (fallback)
    """
    env = os.environ.get("OBSIDIAN_VAULT_DIR")
    if env:
        return Path(env)
    home = Path.home() / "Documents" / "会社運営DB" / "obsidian"
    if home.exists():
        return home
    return Path(__file__).resolve().parents[2] / "data" / "obsidian"


def read_obsidian_note(slug: str, *, vault_dir: Optional[Path] = None) -> Optional[str]:
    """Obsidian Vault から markdown を読む. 不在は None.

    AC-1 unified API の read 側.
    """
    if not isinstance(slug, str) or not OBSIDIAN_SLUG_RE.match(slug):
        raise ContextBuilderError(
            "obsidian slug must be 1-200 chars of [A-Za-z0-9_-/.]",
        )
    if ".." in slug or slug.startswith("/"):
        raise ContextBuilderError("obsidian slug must not contain '..' or leading '/'")
    base = (vault_dir or _obsidian_vault_dir()).resolve()
    p = (base / f"{slug}.md").resolve()
    # path traversal 防止
    try:
        p.relative_to(base)
    except ValueError:
        raise ContextBuilderError("slug escapes vault dir")
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def write_obsidian_note(
    slug: str,
    content: str,
    *,
    vault_dir: Optional[Path] = None,
) -> Path:
    """Obsidian Vault に markdown を書く. dir 不在なら自動作成.

    AC-1 unified API の write 側 (G1 closure).

    Returns:
      書込先 Path. validation 失敗時 ContextBuilderError (4xx).
    """
    if not isinstance(slug, str) or not OBSIDIAN_SLUG_RE.match(slug):
        raise ContextBuilderError(
            "obsidian slug must be 1-200 chars of [A-Za-z0-9_-/.]",
        )
    if ".." in slug or slug.startswith("/"):
        raise ContextBuilderError("obsidian slug must not contain '..' or leading '/'")
    if not isinstance(content, str):
        raise ContextBuilderError("content must be string")
    if len(content) > 1_000_000:  # 1 MiB cap
        raise ContextBuilderError("content must be <= 1,000,000 chars")
    base = (vault_dir or _obsidian_vault_dir()).resolve()
    base.mkdir(parents=True, exist_ok=True)
    p = (base / f"{slug}.md").resolve()
    try:
        p.relative_to(base)
    except ValueError:
        raise ContextBuilderError("slug escapes vault dir")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ──────────────────────────────────────────────────────────────────────
# G2 (AC-3): secretary AI active 状態判定
# ──────────────────────────────────────────────────────────────────────


_TRUTHY = {"1", "true", "yes", "on"}


def is_secretary_active(override: Optional[bool] = None) -> bool:
    """秘書 AI が active かを判定 (AC-3 STATE).

    優先順位:
      1. override (明示的に渡された場合)
      2. env SECRETARY_ACTIVE (truthy なら active)
      3. default = True (Phase 1 では常に active)
    """
    if override is not None:
        return bool(override)
    raw = os.environ.get("SECRETARY_ACTIVE")
    if raw is None:
        return True
    return raw.strip().lower() in _TRUTHY


async def build_context(
    user_message: str,
    session_id: int,
    *,
    prior_session_id: Optional[int] = None,
    user_id: Optional[str] = None,
    top_k: int = 5,
    include_constitution: bool = True,
    secretary_active: Optional[bool] = None,
) -> dict:
    """Agent invocation 直前の context block を組み立てる。

    Args:
      secretary_active: G2 (AC-3) STATE 判定. None なら is_secretary_active()
        の判定 (env SECRETARY_ACTIVE) を採用. False なら constitution を空に
        する (include_constitution=True でも秘書 inactive なら注入しない).

    Returns:
      {
        "memory_block": str,           # system prompt 末尾へ追加するテキスト
        "decisions": list[dict],       # 検出された D-XXX とその content
        "constitution": str,           # preload_constitution の結果 (opt)
        "mem0_facts": list[str],       # 取得した Mem0 fact (UNWANTED 用)
        "conflicts": list[dict],       # 矛盾候補
        "has_conflicts": bool,         # G3: silent pick 禁止の明示 flag
        "secretary_active": bool,      # G2: STATE 判定結果
      }
    """
    if not isinstance(user_message, str) or not user_message.strip():
        raise ContextBuilderError("user_message must not be empty")
    if isinstance(session_id, bool) or not isinstance(session_id, int) or session_id <= 0:
        raise ContextBuilderError("session_id must be int > 0")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not (1 <= top_k <= 20):
        raise ContextBuilderError("top_k must be int in 1..20")

    # 1. memory_service の merge を REUSE (Tier 1-3 統合経路)
    try:
        from services.memory_service import merge_for_session
        memory_block = await merge_for_session(
            session_id=session_id,
            prior_session_id=prior_session_id,
            user_message=user_message,
            user_id=user_id,
            top_k=top_k,
        )
    except Exception:
        memory_block = ""

    # 2. D-XXX decision lookup
    decisions: list[dict] = []
    for ref in DECISION_REF_RE.findall(user_message):
        d = lookup_decision(ref)
        if d:
            decisions.append(d)

    # 3. Constitution preload (G2 AC-3: 秘書 AI active かつ include_constitution)
    active = is_secretary_active(secretary_active)
    constitution = ""
    if include_constitution and active:
        constitution = await preload_constitution(user_id or "masato")

    # 4. Mem0 facts (conflict detection 用に取得)
    mem0_facts: list[str] = []
    try:
        from services.long_term_memory import search_relevant_memories
        mem0_facts = await search_relevant_memories(
            user_id=user_id or "masato", query=user_message, limit=top_k,
        )
    except Exception:
        pass

    # 5. UNWANTED AC: 矛盾 surface (G3: has_conflicts フラグも明示)
    conflicts = _detect_conflicts(mem0_facts) if mem0_facts else []
    has_conflicts = bool(conflicts)

    return {
        "memory_block": memory_block,
        "decisions": decisions,
        "constitution": constitution,
        "mem0_facts": mem0_facts,
        "conflicts": conflicts,
        "has_conflicts": has_conflicts,
        "secretary_active": active,
    }
