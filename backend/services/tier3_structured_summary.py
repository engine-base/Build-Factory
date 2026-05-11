"""T-M28-04: Tier 3 9-section structured summary (background task).

M-28 Context Builder の Tier 3 = 95% context 到達時の自動 compaction.
chat_thread_store (M-30 schema) の messages を 9-section structured summary に
圧縮し, 元 thread に role='system' + compressed_summary={9 sections} で persist する.
emit_audit で memory_compacted event を記録 (AC-2 EVENT-DRIVEN).

9 sections (tier2_cache.KNOWN_SUMMARY_SECTIONS と一致):
  context / goals / decisions / open_questions / actions
  blockers / facts / preferences / next_steps

設計:
  - REUSE: chat_thread_store の append_message / list_messages
  - read 経路は完全 read-only (state mutate 無し)
  - 完全 in-process / sync (Phase 1, テスト容易性 + 2 秒以内応答)
  - 失敗時 audit emit せず persistent state を mutate しない (AC-4 UNWANTED)
  - audit log は in-memory (memory_service.emit_event は sqlite 依存で
    test env に不適合; M-30 stack に合わせる)

AC 対応:
  - UBIQUITOUS (AC-1): T-M28-04 を M-28 仕様通り実装
  - EVENT-DRIVEN (AC-2): trigger 時に action + timestamp を audit log に記録
  - STATE-DRIVEN (AC-3): RLS + audit_logs を CLAUDE.md §5.3 準拠で適用
    (Phase 1 は app-level audit; Postgres RLS migration は M-30 / 018 で別途)
  - UNWANTED (AC-4): invalid input → 4xx structured / persistent state mutate 無し
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Optional

from services import chat_thread_store as cts

logger = logging.getLogger(__name__)


class Tier3SummaryError(RuntimeError):
    pass


SECTION_KEYS = (
    "context",
    "goals",
    "decisions",
    "open_questions",
    "actions",
    "blockers",
    "facts",
    "preferences",
    "next_steps",
)

DEFAULT_MAX_TOKENS = 200_000
DEFAULT_THRESHOLD = 0.95
MIN_THRESHOLD = 0.10
MAX_THRESHOLD = 0.99
MIN_MAX_TOKENS = 1_000
MAX_MAX_TOKENS = 10_000_000
TOKEN_CHAR_DIVISOR = 3  # JP-heavy estimate (~3 chars/token)
MAX_SECTION_ITEMS = 5
MAX_ITEM_CHARS = 300
MAX_FETCH_MESSAGES = 10_000

AUDIT_ACTION_COMPACTED = "tier3.memory_compacted"
AUDIT_ACTION_SKIPPED = "tier3.compaction_skipped"


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_thread_id(thread_id: int) -> int:
    if not isinstance(thread_id, int) or isinstance(thread_id, bool) or thread_id <= 0:
        raise Tier3SummaryError("thread_id must be > 0")
    return thread_id


def _validate_max_tokens(max_tokens: int) -> int:
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool):
        raise Tier3SummaryError(
            f"max_tokens must be int in {MIN_MAX_TOKENS}..{MAX_MAX_TOKENS}"
        )
    if max_tokens < MIN_MAX_TOKENS or max_tokens > MAX_MAX_TOKENS:
        raise Tier3SummaryError(
            f"max_tokens must be in {MIN_MAX_TOKENS}..{MAX_MAX_TOKENS}"
        )
    return max_tokens


def _validate_threshold(threshold: float) -> float:
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise Tier3SummaryError(
            f"threshold must be float in [{MIN_THRESHOLD}, {MAX_THRESHOLD}]"
        )
    f = float(threshold)
    if f < MIN_THRESHOLD or f > MAX_THRESHOLD:
        raise Tier3SummaryError(
            f"threshold must be in [{MIN_THRESHOLD}, {MAX_THRESHOLD}]"
        )
    return f


# ──────────────────────────────────────────────────────────────────────
# Audit log (in-memory; AC-2 EVENT-DRIVEN + AC-3 STATE-DRIVEN)
# ──────────────────────────────────────────────────────────────────────


_AUDIT_LOG: list[dict] = []
_audit_lock = threading.Lock()


def _emit_audit(
    action: str,
    *,
    thread_id: int,
    summary_message_id: Optional[int],
    sections: list[str],
    detail: Optional[dict] = None,
) -> dict:
    entry = {
        "action": action,
        "timestamp": time.time(),
        "thread_id": thread_id,
        "summary_message_id": summary_message_id,
        "sections": list(sections),
        "detail": dict(detail or {}),
    }
    with _audit_lock:
        _AUDIT_LOG.append(entry)
    return entry


def list_audit_log(
    *,
    thread_id: Optional[int] = None,
    limit: int = 100,
) -> list[dict]:
    """audit log を新しい順で取得 (read-only)."""
    if thread_id is not None:
        _validate_thread_id(thread_id)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0 or limit > 10_000:
        raise Tier3SummaryError("limit must be int in 1..10000")
    with _audit_lock:
        items = list(_AUDIT_LOG)
    if thread_id is not None:
        items = [e for e in items if e.get("thread_id") == thread_id]
    items.reverse()
    return items[:limit]


def clear_audit_log() -> int:
    """テスト/管理用. 削除件数を返す."""
    with _audit_lock:
        n = len(_AUDIT_LOG)
        _AUDIT_LOG.clear()
        return n


# ──────────────────────────────────────────────────────────────────────
# Context usage estimation
# ──────────────────────────────────────────────────────────────────────


def estimate_context_usage(
    thread_id: int,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """thread の文字数 -> 推定トークン -> 占有率 を返す (read-only)."""
    thread_id = _validate_thread_id(thread_id)
    max_tokens = _validate_max_tokens(max_tokens)

    store = cts.get_store()
    if store.get_thread(thread_id) is None:
        raise Tier3SummaryError(f"thread not found: {thread_id}")

    total = store.count_messages(thread_id)
    if total == 0:
        return {
            "thread_id": thread_id,
            "message_count": 0,
            "char_count": 0,
            "estimated_tokens": 0,
            "max_tokens": max_tokens,
            "ratio": 0.0,
        }

    fetch_limit = min(total, MAX_FETCH_MESSAGES)
    offset = max(0, total - fetch_limit)
    msgs = store.list_messages(thread_id, limit=fetch_limit, offset=offset)
    char_count = sum(len(m.content) for m in msgs)
    est_tokens = char_count // TOKEN_CHAR_DIVISOR
    ratio = min(1.0, est_tokens / max_tokens) if max_tokens > 0 else 0.0
    return {
        "thread_id": thread_id,
        "message_count": total,
        "char_count": char_count,
        "estimated_tokens": est_tokens,
        "max_tokens": max_tokens,
        "ratio": ratio,
    }


def should_compact(usage: dict, *, threshold: float = DEFAULT_THRESHOLD) -> bool:
    if not isinstance(usage, dict):
        raise Tier3SummaryError("usage must be a dict")
    threshold = _validate_threshold(threshold)
    r = usage.get("ratio")
    if not isinstance(r, (int, float)):
        raise Tier3SummaryError("usage.ratio missing or non-numeric")
    return float(r) >= threshold


# ──────────────────────────────────────────────────────────────────────
# 9-section heuristic generator
# ──────────────────────────────────────────────────────────────────────


# 各 section の検出パターン (JP + EN 両対応)
_PATTERNS: dict[str, tuple[str, ...]] = {
    "goals": ("目標", "ゴール", "やりたい", "やりたいこと", "want to", "goal:", "objective"),
    "decisions": ("決定", "確定", "決まった", "採用", "approve", "decided", "confirm"),
    "open_questions": ("わからない", "教えて", "どう", "?", "？", "なぜ", "どうやって"),
    "actions": ("実行", "作成", "完了", "した", "行った", "executed", "created", "completed"),
    "blockers": ("ブロック", "詰まった", "進めない", "エラー", "ERROR", "error", "failed", "blocker"),
    "facts": ("事実", "実際", "fact", "確認した", "判明", "found"),
    "preferences": ("好き", "嫌い", "好み", "preference", "prefer", "好む", "苦手"),
    "next_steps": ("次は", "次に", "TODO", "todo", "next", "後で", "あとで", "予定"),
}

_REJECTED_PATTERNS = ("不採用", "却下", "やめる", "reject", "却下した")
_DECISION_REF_RE = re.compile(r"\bD-\d{3,5}\b")


def _short(text: str) -> str:
    s = (text or "").strip().replace("\n", " ")
    if len(s) > MAX_ITEM_CHARS:
        s = s[: MAX_ITEM_CHARS - 1] + "…"
    return s


def _classify(msg: cts.ChatMessage) -> list[str]:
    """1 メッセージが該当する section のリスト."""
    hits: list[str] = []
    content = msg.content or ""
    if _REJECTED_PATTERNS and any(p in content for p in _REJECTED_PATTERNS):
        # 不採用は decisions 側に明示マーク
        hits.append("decisions")
    if _DECISION_REF_RE.search(content):
        if "decisions" not in hits:
            hits.append("decisions")
    for section, patterns in _PATTERNS.items():
        if section in hits:
            continue
        if any(p in content for p in patterns):
            hits.append(section)
    return hits


def generate_summary(messages: list[cts.ChatMessage]) -> dict:
    """9-section heuristic summary.

    各 section は最大 MAX_SECTION_ITEMS 件の bullet を保持.
    新しい順で重複排除し最大件数で打ち切り.
    全 section は必ず key として存在 (空 list 可) — 9 sections 不変条件.
    """
    if not isinstance(messages, list):
        raise Tier3SummaryError("messages must be a list")
    for i, m in enumerate(messages):
        if not isinstance(m, cts.ChatMessage):
            raise Tier3SummaryError(f"messages[{i}] must be ChatMessage")

    summary: dict[str, list[str]] = {k: [] for k in SECTION_KEYS}
    seen: dict[str, set[str]] = {k: set() for k in SECTION_KEYS}

    # context: 最初の user message を要旨に
    for m in messages:
        if m.role == "user":
            s = _short(m.content)
            if s:
                summary["context"].append(s)
                seen["context"].add(s)
            break

    for m in messages:
        if m.role == "system":
            continue
        sections = _classify(m)
        for section in sections:
            bucket = summary[section]
            if len(bucket) >= MAX_SECTION_ITEMS:
                continue
            s = _short(m.content)
            if not s or s in seen[section]:
                continue
            bucket.append(s)
            seen[section].add(s)

    # invariant: 全 9 section key 存在
    return {k: list(summary[k]) for k in SECTION_KEYS}


# ──────────────────────────────────────────────────────────────────────
# Full pipeline (background task entry)
# ──────────────────────────────────────────────────────────────────────


def run_compaction(
    thread_id: int,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    threshold: float = DEFAULT_THRESHOLD,
    force: bool = False,
) -> dict:
    """95%-context 到達時の compaction を実行.

    Returns:
      compacted=True : {compacted, summary, message_id, audit_entry, usage}
      compacted=False: {compacted, reason, usage, audit_entry}

    AC-4: invalid 入力時は raise Tier3SummaryError (router 層で 4xx に変換).
          persistent state を mutate しない.
    """
    thread_id = _validate_thread_id(thread_id)
    max_tokens = _validate_max_tokens(max_tokens)
    threshold = _validate_threshold(threshold)
    if not isinstance(force, bool):
        raise Tier3SummaryError("force must be bool")

    usage = estimate_context_usage(thread_id, max_tokens=max_tokens)

    if not force and not should_compact(usage, threshold=threshold):
        audit = _emit_audit(
            AUDIT_ACTION_SKIPPED,
            thread_id=thread_id,
            summary_message_id=None,
            sections=[],
            detail={
                "reason": "below_threshold",
                "ratio": usage["ratio"],
                "threshold": threshold,
            },
        )
        return {
            "compacted": False,
            "reason": "below_threshold",
            "usage": usage,
            "audit_entry": audit,
        }

    store = cts.get_store()
    total = usage["message_count"]
    if total == 0:
        # AC-4: 空 thread の compaction 要求 → 4xx + state mutate しない
        raise Tier3SummaryError("thread has no messages to compact")

    fetch_limit = min(total, MAX_FETCH_MESSAGES)
    offset = max(0, total - fetch_limit)
    msgs = store.list_messages(thread_id, limit=fetch_limit, offset=offset)
    summary_dict = generate_summary(msgs)

    # persist: M-30 store に role='system' + compressed_summary で保存
    content = "[Tier3 compaction] 9-section structured summary"
    persisted = store.add_message(
        thread_id,
        "system",
        content,
        compressed_summary=summary_dict,
    )

    audit = _emit_audit(
        AUDIT_ACTION_COMPACTED,
        thread_id=thread_id,
        summary_message_id=persisted.id,
        sections=list(SECTION_KEYS),
        detail={
            "ratio": usage["ratio"],
            "threshold": threshold,
            "forced": force,
            "char_count": usage["char_count"],
        },
    )

    return {
        "compacted": True,
        "summary": summary_dict,
        "message_id": persisted.id,
        "audit_entry": audit,
        "usage": usage,
    }
