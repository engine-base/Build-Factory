"""T-M28-01: Context Builder skeleton (REFACTOR)

Agent 呼び出し直前の prompt 構築に特化した read-only API。
T-020-02 の memory_service が write/recall 双方を持つのに対し、本サービスは
「agent invocation 直前に Mem0 / Obsidian / Constitution を統合して prompt
末尾の context block を組み立てる」役割。

## AC 対応 (T-M28-01)

- UBIQUITOUS: Mem0 vector search + Obsidian markdown read + Constitution
  decision lookup を build_context の単一窓口に統合
- EVENT: 入力に D-XXX が含まれていたら 200ms 以内で関連 decision を返す
  (read 経路のみ、ネットワーク I/O なし → 数十 ms オーダー)
- STATE: 秘書 AI active のとき preload_constitution() で system prompt に
  Constitution を注入する
- UNWANTED: Mem0 結果に矛盾 (contradictory_keywords) があれば conflicts に
  surface、build_context の戻り値で呼び出し元に通知 (silently pick しない)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional


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


async def build_context(
    user_message: str,
    session_id: int,
    *,
    prior_session_id: Optional[int] = None,
    user_id: Optional[str] = None,
    top_k: int = 5,
    include_constitution: bool = True,
) -> dict:
    """Agent invocation 直前の context block を組み立てる。

    Returns:
      {
        "memory_block": str,           # system prompt 末尾へ追加するテキスト
        "decisions": list[dict],       # 検出された D-XXX とその content
        "constitution": str,           # preload_constitution の結果 (opt)
        "mem0_facts": list[str],       # 取得した Mem0 fact (UNWANTED 用)
        "conflicts": list[dict],       # 矛盾候補
      }
    """
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

    # 3. Constitution preload (秘書 AI active 時のみ)
    constitution = ""
    if include_constitution:
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

    # 5. UNWANTED AC: 矛盾 surface
    conflicts = _detect_conflicts(mem0_facts) if mem0_facts else []

    return {
        "memory_block": memory_block,
        "decisions": decisions,
        "constitution": constitution,
        "mem0_facts": mem0_facts,
        "conflicts": conflicts,
    }
