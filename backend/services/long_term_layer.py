"""T-M30-04: 長期 layer (existing long_term_memory + obsidian_sync 統合).

M-30 3 層 memory の Tier 3 (永続記憶) を統一インターフェースで提供する.

3 つの persist sink:
  - Mem0 (ベクトル) ← long_term_memory.py REUSE
  - Obsidian Markdown (人間可読) ← obsidian_sync.py / obsidian_vault_sync.py REUSE
  - Constitution (松本判断基準) ← read-only system prompt 注入元

公開 API:
  - persist(user_id, content, *, source, tags) -> dict
      mem0 + obsidian の両方に書く (best-effort)
  - retrieve(user_id, query, *, top_k, min_score, scopes) -> dict
      mem0 + obsidian-derived knowledge_base から横断検索
  - list_sources(user_id) -> dict
      tracked source の status (mem0 件数 / obsidian path / 最終 sync)

設計:
  - persist は best-effort: 片方が落ちても他方は成功させ result に status を載せる
  - 既存 module は無改変 (REFACTOR で thin orchestrator のみ追加)
  - persistent state mutation は失敗時に rollback / 各 sink に独立記録
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import time
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


class LongTermLayerError(RuntimeError):
    pass


VALID_SOURCES = ("conversation", "fact", "decision", "knowledge", "constitution")
VALID_SCOPES = ("mem0", "obsidian")
DEFAULT_SCOPES = ("mem0", "obsidian")
MAX_CONTENT_CHARS = 50_000
MAX_USER_ID_LEN = 200
MAX_TAGS = 20
MAX_TAG_LEN = 50
MAX_QUERY_CHARS = 2_000
MAX_TOP_K = 100
DEFAULT_TOP_K = 10
DEFAULT_MIN_SCORE = 0.0


def _validate_user_id(user_id: str) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise LongTermLayerError("user_id must not be empty")
    user_id = user_id.strip()
    if len(user_id) > MAX_USER_ID_LEN:
        raise LongTermLayerError(f"user_id must be <= {MAX_USER_ID_LEN} chars")
    # path traversal 防止
    if not re.fullmatch(r"[A-Za-z0-9_\-.]+", user_id):
        raise LongTermLayerError(
            "user_id must contain only alphanumeric, '-', '_', '.'"
        )
    return user_id


def _validate_content(content: str) -> str:
    if not isinstance(content, str) or not content.strip():
        raise LongTermLayerError("content must not be empty")
    if len(content) > MAX_CONTENT_CHARS:
        raise LongTermLayerError(f"content must be <= {MAX_CONTENT_CHARS} chars")
    return content


def _validate_source(source: str) -> str:
    if not isinstance(source, str) or source not in VALID_SOURCES:
        raise LongTermLayerError(
            f"source must be one of {VALID_SOURCES}"
        )
    return source


def _validate_tags(tags: Optional[Iterable[str]]) -> list[str]:
    if tags is None:
        return []
    if not isinstance(tags, (list, tuple)):
        raise LongTermLayerError("tags must be a list or null")
    out: list[str] = []
    for t in tags:
        if not isinstance(t, str) or not t.strip():
            raise LongTermLayerError("tags[*] must be non-empty string")
        t = t.strip()
        if len(t) > MAX_TAG_LEN:
            raise LongTermLayerError(f"tag must be <= {MAX_TAG_LEN} chars")
        out.append(t)
    if len(out) > MAX_TAGS:
        raise LongTermLayerError(f"tags must be <= {MAX_TAGS}")
    return out


def _validate_scopes(scopes: Optional[Iterable[str]]) -> list[str]:
    if scopes is None:
        return list(DEFAULT_SCOPES)
    if not isinstance(scopes, (list, tuple)):
        raise LongTermLayerError("scopes must be a list")
    out: list[str] = []
    for s in scopes:
        if s not in VALID_SCOPES:
            raise LongTermLayerError(
                f"scope {s!r} not in {VALID_SCOPES}"
            )
        if s in out:
            raise LongTermLayerError("scopes must be unique")
        out.append(s)
    if not out:
        raise LongTermLayerError("scopes must be a non-empty list")
    return out


def _get_obsidian_root() -> Path:
    """Test では BF_OBSIDIAN_ROOT で差し替え可能."""
    p = os.environ.get("BF_OBSIDIAN_ROOT")
    if p:
        return Path(p)
    default = Path.home() / ".build-factory" / "obsidian"
    return default


# ──────────────────────────────────────────────────────────────────────
# persist
# ──────────────────────────────────────────────────────────────────────


async def _persist_to_mem0(
    user_id: str, content: str, *, source: str, tags: list[str],
) -> dict:
    try:
        from services.long_term_memory import add_conversation
    except Exception as e:  # pragma: no cover
        return {"status": "skipped", "reason": f"import failed: {e}"}
    try:
        await add_conversation(
            user_id,
            [{"role": "user", "content": content}],
            metadata={"source": source, "tags": tags},
        )
        return {"status": "ok"}
    except Exception as e:  # pragma: no cover
        return {"status": "error", "reason": str(e)[:200]}


async def _persist_to_obsidian(
    user_id: str, content: str, *, source: str, tags: list[str],
) -> dict:
    root = _get_obsidian_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        # path traversal を validate 済みの user_id で防止
        user_dir = root / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        # check ファイルパスが root の subtree であることを確認
        resolved = user_dir.resolve()
        if not str(resolved).startswith(str(root.resolve())):
            return {"status": "error",
                    "reason": "user_dir escapes obsidian root"}
        ts = int(time.time() * 1000)
        # 同 ms 内の連続 persist でも collision しないよう random suffix
        suffix = secrets.token_hex(3)
        fname = f"{source}-{ts}-{suffix}.md"
        fpath = user_dir / fname
        front = "---\n"
        front += f"source: {source}\n"
        front += f"tags: [{', '.join(tags)}]\n"
        front += f"created_at: {ts}\n"
        front += "---\n\n"
        fpath.write_text(front + content, encoding="utf-8")
        return {
            "status": "ok",
            "path": str(fpath.relative_to(root)),
        }
    except Exception as e:  # pragma: no cover
        return {"status": "error", "reason": str(e)[:200]}


async def persist(
    user_id: str,
    content: str,
    *,
    source: str = "conversation",
    tags: Optional[Iterable[str]] = None,
    scopes: Optional[Iterable[str]] = None,
) -> dict:
    user_id = _validate_user_id(user_id)
    content = _validate_content(content)
    source = _validate_source(source)
    tags_l = _validate_tags(tags)
    scope_list = _validate_scopes(scopes)

    results: dict[str, dict] = {}
    if "mem0" in scope_list:
        results["mem0"] = await _persist_to_mem0(
            user_id, content, source=source, tags=tags_l,
        )
    if "obsidian" in scope_list:
        results["obsidian"] = await _persist_to_obsidian(
            user_id, content, source=source, tags=tags_l,
        )
    overall = "ok" if all(
        r.get("status") == "ok" for r in results.values()
    ) else "partial"
    if all(r.get("status") in ("error", "skipped") for r in results.values()) \
            and results:
        overall = "failed"
    return {
        "user_id": user_id,
        "source": source,
        "tags": tags_l,
        "scopes": scope_list,
        "status": overall,
        "results": results,
    }


# ──────────────────────────────────────────────────────────────────────
# retrieve
# ──────────────────────────────────────────────────────────────────────


async def _retrieve_from_mem0(
    user_id: str, query: str, *, top_k: int,
) -> list[dict]:
    try:
        from services.long_term_memory import search_relevant_memories
    except Exception as e:  # pragma: no cover
        logger.warning("mem0 import failed: %s", e)
        return []
    try:
        items = await search_relevant_memories(user_id, query, limit=top_k)
    except Exception as e:  # pragma: no cover
        logger.warning("mem0 search failed: %s", e)
        return []
    out: list[dict] = []
    for s in items or []:
        if not isinstance(s, str):
            continue
        out.append({
            "scope": "mem0",
            "user_id": user_id,
            "snippet": s[:500],
            "score": 1.0,  # mem0 は score を返さないので 1.0 固定
        })
    return out


async def _retrieve_from_obsidian(
    user_id: str, query: str, *, top_k: int, min_score: float,
) -> list[dict]:
    root = _get_obsidian_root()
    if not root.exists():
        return []
    user_dir = root / user_id
    if not user_dir.exists():
        return []
    # 簡易 token-overlap マッチ (実 production は obsidian_sync で
    # knowledge_base に取り込み → embedding_service.search_knowledge)
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    scored: list[dict] = []
    for fpath in sorted(user_dir.glob("*.md")):
        try:
            text = fpath.read_text(encoding="utf-8")
        except Exception:  # pragma: no cover
            continue
        score = _token_overlap_score(q_tokens, text)
        if score >= min_score:
            scored.append({
                "scope": "obsidian",
                "user_id": user_id,
                "path": str(fpath.relative_to(root)),
                "snippet": text[:500],
                "score": round(score, 4),
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def _tokenize(text: str) -> set[str]:
    if not isinstance(text, str):
        return set()
    cleaned = "".join(c.lower() if c.isalnum() else " " for c in text)
    return {tok for tok in cleaned.split() if len(tok) >= 2}


def _token_overlap_score(q_tokens: set[str], text: str) -> float:
    t_tokens = _tokenize(text)
    if not t_tokens or not q_tokens:
        return 0.0
    return len(q_tokens & t_tokens) / float(len(q_tokens))


async def retrieve(
    user_id: str,
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
    scopes: Optional[Iterable[str]] = None,
) -> dict:
    user_id = _validate_user_id(user_id)
    if not isinstance(query, str) or not query.strip():
        raise LongTermLayerError("query must not be empty")
    query = query.strip()
    if len(query) > MAX_QUERY_CHARS:
        raise LongTermLayerError(f"query must be <= {MAX_QUERY_CHARS} chars")
    if not isinstance(top_k, int) or top_k <= 0 or top_k > MAX_TOP_K:
        raise LongTermLayerError(f"top_k must be 1..{MAX_TOP_K}")
    if not isinstance(min_score, (int, float)) or not (0.0 <= min_score <= 1.0):
        raise LongTermLayerError("min_score must be 0.0..1.0")
    scope_list = _validate_scopes(scopes)

    coros: list = []
    used_scopes: list[str] = []
    if "mem0" in scope_list:
        coros.append(_retrieve_from_mem0(user_id, query, top_k=top_k))
        used_scopes.append("mem0")
    if "obsidian" in scope_list:
        coros.append(_retrieve_from_obsidian(
            user_id, query, top_k=top_k, min_score=min_score,
        ))
        used_scopes.append("obsidian")
    results = await asyncio.gather(*coros, return_exceptions=True)

    merged: list[dict] = []
    per_scope: dict[str, int] = {}
    for scope, res in zip(used_scopes, results):
        if isinstance(res, Exception):
            per_scope[scope] = 0
            continue
        per_scope[scope] = len(res)
        merged.extend(res)
    merged.sort(key=lambda x: x["score"], reverse=True)
    merged = merged[:top_k]
    return {
        "user_id": user_id,
        "query": query,
        "scopes": scope_list,
        "count": len(merged),
        "per_scope_count": per_scope,
        "results": merged,
    }


# ──────────────────────────────────────────────────────────────────────
# list_sources
# ──────────────────────────────────────────────────────────────────────


async def list_sources(user_id: str) -> dict:
    user_id = _validate_user_id(user_id)
    root = _get_obsidian_root()
    user_dir = root / user_id
    obsidian_files: list[dict] = []
    obsidian_root_exists = root.exists()
    if obsidian_root_exists and user_dir.exists():
        for fpath in sorted(user_dir.glob("*.md")):
            try:
                stat = fpath.stat()
                obsidian_files.append({
                    "path": str(fpath.relative_to(root)),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
            except Exception:  # pragma: no cover
                continue

    mem0_count: Optional[int]
    try:
        from services.long_term_memory import all_memories
        items = await all_memories(user_id)
        mem0_count = len(items) if isinstance(items, list) else 0
    except Exception as e:  # pragma: no cover
        logger.warning("mem0 list_sources failed: %s", e)
        mem0_count = None

    return {
        "user_id": user_id,
        "obsidian": {
            "root_exists": obsidian_root_exists,
            "user_dir_exists": user_dir.exists(),
            "file_count": len(obsidian_files),
            "files": obsidian_files,
        },
        "mem0": {
            "count": mem0_count,
            "available": mem0_count is not None,
        },
    }
