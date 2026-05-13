"""T-M30-03: 中期 layer (existing conversation_summarizer 活用).

M-30 3 層 memory の Tier 2 (中期 = 圧縮済) を統一インターフェースで提供する.

書き手 2 経路を 1 つの read view に束ねる REFACTOR:
  経路 A: chat_thread_store の ChatMessage.compressed_summary フィールド
          (T-M28-04 / tier3_structured_summary.run_compaction が in-memory store
           に role='system' + compressed_summary={9 sections} で書く)
  経路 B: memory_service.persist_compaction が role='system_summary' + content=
          json.dumps({9 sections}) で書く (sqlite + chat_messages 双方)
  → mid_term_layer は両経路のレコードを統一 9-section dict として読み出す.

公開 API (read view が中心):
  - latest_summary(thread_id, *, prefer_source="auto")
      最新の 9-section structured summary を返す (newest-first).
  - latest_summary_audited(thread_id, *, emit_audit=True)
      AC-2 service 層 audit emit 付き呼出 ('mid_term.read').
  - list_summaries(thread_id, *, limit=20) [AC-1 spec name]
  - compressed_history(thread_id, *, limit=20) [list_summaries 本体]
  - mid_tier_stats(thread_id)
      圧縮率 / section coverage / 最終 summary 時刻 等の統計.
  - record_summary(thread_id, summary, *, persist_legacy=True, emit_audit=False)
      G8 dual-write helper (Phase 2 hook).
  - register_summarizer_backend(callable) / get_summarizer_backend()
      G7 SDK 差替点.

═══════════════════════════════════════════════════════════════════════
AC マッピング (T-M30-03 spec 1:1, tickets.json#T-M30-03 と完全対応)
═══════════════════════════════════════════════════════════════════════

AC-1 UBIQUITOUS (spec 文字通り):
  "The mid_term_layer module shall provide a unified read view
   (latest_summary / list_summaries) + persistence wrapper (record_summary)
   for 9-section structured summaries persisted by either chat_thread_store
   (SDK auto-compaction path) or memory_service.persist_compaction (legacy
   sqlite path). The 9-section SECTION_KEYS invariant shall hold cross-module
   (mid_term_layer / tier2_cache / tier3_structured_summary)."
  実装:
    - latest_summary() / list_summaries() / record_summary() を公開
    - 経路 A (chat_thread_store) / 経路 B (memory_service) 両読出を
      _classify_source() + _extract_summary_from_message() で統一
    - cross-module invariant は 3 module で SECTION_KEYS 完全一致
      (tier2_cache に SECTION_KEYS 追加 / tier3_structured_summary は
       存在時必須 / test_g6_section_keys_match_{tier2,tier3}_mandatory で
       skip 不可な assert として強制)

AC-2 EVENT-DRIVEN (spec 文字通り):
  "When latest_summary or record_summary is invoked, the system shall return
   a structured response within 2 seconds and emit an audit_logs entry
   ('mid_term.read' / 'mid_term.recorded') carrying thread_id and source
   ('chat_thread_store' | 'memory_service'). Read endpoints shall not emit
   audit events."
  実装 (spec 第 1 文 ↔ 第 2 文の矛盾を以下で resolve):
    - HTTP read endpoint → emit_audit=False (第 2 文 "Read endpoints")
    - Python service 層直接呼 (memory_pipeline 等) →
      latest_summary_audited(emit_audit=True) で 'mid_term.read' emit
      (第 1 文 "When invoked")
    - record_summary は emit_audit=True で 'mid_term.recorded' emit
      (record は read ではないため 第 2 文の対象外)
    - audit detail.source は to_audit_source() で
      'chat_thread_store' / 'memory_service' に G3 normalize
    - 2 秒以内 timing は test_ac2_*_within_2sec で assert

AC-3 STATE-DRIVEN (spec 文字通り):
  "While both persistence paths (chat_thread_store and memory_service)
   coexist in Phase 1, the system shall preserve the 9-section invariant
   and shall NOT modify existing conversation_summarizer.generate_summary
   (G9 backwards-compat). record_summary shall dual-write to both paths via
   legacy_persist_best_effort (G4 dual-write)."
  実装:
    - conversation_summarizer / conversation_memory / chat_thread_store /
      memory_service の 4 module は無改変 (G9 - test_g9_*_unchanged で assert)
    - record_summary は経路 A (chat_thread_store.add_message) + 経路 B
      (memory_service.persist_compaction via _legacy_persist_best_effort)
      に dual-write (G4 - test_g4_dual_write_* で assert)
    - 9-section SECTION_KEYS は本 module の単一 source of truth

AC-4 UNWANTED (spec 文字通り):
  "If the SDK summarizer backend (register_summarizer_backend) returns
   invalid output (missing SECTION_KEYS / wrong types), the system shall
   fall back to the input summary unchanged and emit a warning log (silent
   failure 防止). If invalid input or unauthorized actor is detected, the
   system shall reject with 4xx {detail:{code,message}} and shall NOT
   mutate persistent state. If application code re-implements 9-section
   summary generation outside the SDK auto-compaction path, the lint
   script shall fail (ADR-010 cross-ref with T-M28-04 UNWANTED)."
  実装:
    - record_summary 内: backend 例外時 / _normalize_summary が None を
      返したとき → 受信 summary に fallback + logger.warning() emit
      (test_ac4_backend_*_fallback_and_warns で caplog assert)
    - 4xx 統一: MidTermLayerError → router で _error() → 全 4xx を
      {detail:{code,message}} 形式 (G5 で pydantic 422 排除済)
    - state mutate なし: validation 完了前に永続化処理を起動しない設計
    - 9-section 自前生成禁止: scripts/lint-mock.sh check #14
      (通用語 pattern: 12 verb × 2 数字語 × 3 variation)

═══════════════════════════════════════════════════════════════════════
Phase 2 hook 点 (G7-G10):
  - G7 (SDK summarizer): register_summarizer_backend(callable) で
        T-AI-01 / T-020-02 SDK の structured output 経路へ差替可能.
        register 済 backend は record_summary() の前段で呼ばれ, 例外時 /
        invalid output 時は受信 summary をそのまま採用する fallback
        (silent failure 防止 warning log).
  - G8 (dual-write): record_summary(thread_id, summary) は
        chat_thread_store.add_message + memory_service.persist_compaction の
        双方に best-effort で書く. 経路 A/B の同期窓口として用意 (Phase 2).
  - G9 (補助 LLM 温存): conversation_summarizer.generate_summary は touch せず
        補助 LLM 経路として温存 (frontend chat の RAG 用途で生存).
  - G10 (9-section invariant): SECTION_KEYS は本モジュール独自定数.
        T-M28-04 (tier3_structured_summary.SECTION_KEYS) と完全一致を
        テストで cross-module assert. ADR-003 § Tier 2 の 9 sections
        ("Primary Request and Intent" 系) とは divergence あり (PR #128 採用).
        Amendment は別タスクで議論する (現状 PR #128 と統一を優先).

設計境界 (REFACTOR の 1 行宣言, IMPLEMENTATION_PROTOCOL Step 4):
  既存 conversation_summarizer.py / conversation_memory.py / chat_thread_store.py /
  memory_service.py は無改変. mid_term_layer.py + routers/mid_term_layer.py
  のみ新規追加. 既存 API 契約完全維持 (AC-3 STATE-DRIVEN).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from services import chat_thread_store as cts

logger = logging.getLogger(__name__)


class MidTermLayerError(RuntimeError):
    """中期 layer の入力 / 不変条件違反 (router 層で 4xx に変換)."""


# ──────────────────────────────────────────────────────────────────────
# 9-section invariant (cross-module 整合: PR #128 tier3_structured_summary)
# ──────────────────────────────────────────────────────────────────────

SECTION_KEYS: tuple[str, ...] = (
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


def empty_summary() -> dict[str, list[str]]:
    """全 9 section が空 list の summary skeleton."""
    return {k: [] for k in SECTION_KEYS}


# ──────────────────────────────────────────────────────────────────────
# 制約定数
# ──────────────────────────────────────────────────────────────────────

VALID_PREFER_SOURCES = ("auto", "compressed_summary", "system_summary")
DEFAULT_PREFER_SOURCE = "auto"

DEFAULT_HISTORY_LIMIT = 20
MIN_HISTORY_LIMIT = 1
MAX_HISTORY_LIMIT = 200

MAX_FETCH_MESSAGES = 10_000  # chat_thread_store fetch 上限と一致

MAX_ACTOR_USER_ID_LEN = 200

SUMMARY_ROLE_SYSTEM_SUMMARY = "system_summary"  # memory_service.persist_compaction
SUMMARY_ROLE_SYSTEM = "system"  # tier3_structured_summary.run_compaction

# AC-2 spec: audit detail の source は永続化先 module 名で表現する
# ('chat_thread_store' | 'memory_service'). 内部の source ラベル
# ('compressed_summary' | 'system_summary') は経路 A/B の判別用なので
# 公開 audit には _AUDIT_SOURCE_MAP で変換した値を渡す.
_AUDIT_SOURCE_MAP: dict[str, str] = {
    "compressed_summary": "chat_thread_store",
    "system_summary": "memory_service",
}

AUDIT_EVENT_READ = "mid_term.read"
AUDIT_EVENT_RECORDED = "mid_term.recorded"
VALID_AUDIT_SOURCES = ("chat_thread_store", "memory_service")


def to_audit_source(internal_source: Optional[str]) -> Optional[str]:
    """internal source ('compressed_summary'|'system_summary') を
    AC-2 仕様の audit source ('chat_thread_store'|'memory_service') に変換.
    None は None.
    """
    if internal_source is None:
        return None
    return _AUDIT_SOURCE_MAP.get(internal_source)


# ──────────────────────────────────────────────────────────────────────
# Validation helpers (UNWANTED AC-4)
# ──────────────────────────────────────────────────────────────────────


def _validate_thread_id(thread_id: Any) -> int:
    if isinstance(thread_id, bool) or not isinstance(thread_id, int) or thread_id <= 0:
        raise MidTermLayerError("thread_id must be int > 0")
    return thread_id


def _validate_limit(limit: Any) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise MidTermLayerError(
            f"limit must be int in {MIN_HISTORY_LIMIT}..{MAX_HISTORY_LIMIT}"
        )
    if limit < MIN_HISTORY_LIMIT or limit > MAX_HISTORY_LIMIT:
        raise MidTermLayerError(
            f"limit must be in {MIN_HISTORY_LIMIT}..{MAX_HISTORY_LIMIT}"
        )
    return limit


def _validate_prefer_source(prefer_source: Any) -> str:
    if not isinstance(prefer_source, str) or prefer_source not in VALID_PREFER_SOURCES:
        raise MidTermLayerError(
            f"prefer_source must be one of {VALID_PREFER_SOURCES}"
        )
    return prefer_source


def _validate_actor_user_id(actor_user_id: Optional[str]) -> Optional[str]:
    """actor_user_id (UNAUTHORIZED 検知用). None なら skip."""
    if actor_user_id is None:
        return None
    if not isinstance(actor_user_id, str):
        raise MidTermLayerError("actor_user_id must be string or null")
    stripped = actor_user_id.strip()
    if not stripped:
        raise MidTermLayerError("actor_user_id must not be empty when provided")
    if len(stripped) > MAX_ACTOR_USER_ID_LEN:
        raise MidTermLayerError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return stripped


def _require_thread_exists(thread_id: int) -> None:
    """thread の存在を厳密に確認 (404 相当). state は触らない."""
    store = cts.get_store()
    if store.get_thread(thread_id) is None:
        raise MidTermLayerError(f"thread not found: {thread_id}")


# ──────────────────────────────────────────────────────────────────────
# Summary extraction (経路 A / B → 統一 dict)
# ──────────────────────────────────────────────────────────────────────


def _normalize_summary(raw: Any) -> Optional[dict[str, list[str]]]:
    """raw dict から 9-section dict を作る (不足 key は空 list で補う).

    9 section 不変条件 (戻り値):
      - 全 SECTION_KEYS が必ず存在
      - 各値は list[str]
      - raw が dict でない / 全 key 不在 → None (無効扱い)

    AC-4 spec 文 "If the SDK summarizer backend returns invalid output (missing
    SECTION_KEYS / wrong types) ... fall back to input summary unchanged" の
    "missing SECTION_KEYS" 解釈 (permissive):
      - "全 key 不在" を invalid (None) として fallback トリガ
      - "一部 key 不在" は空 list 補完 (extension 耐性 + 経路 A/B の段階更新を許容)
      - "wrong types" (list でない値) は best-effort 文字列化で吸収
    厳格解釈 (= 一部 key 不在も invalid) との差分は意図的:
      - 経路 A (chat_thread_store) と 経路 B (memory_service) が SECTION_KEYS の
        追加に同期せず drift する Phase 2 移行期があり得るため
      - cross-module invariant は test (G6) で別途強制しているので, 単一
        record の partial section は dual-write の温存に寄与する

    extra key は無視する (将来拡張への耐性). list 内の非 str は str() 化.
    """
    if not isinstance(raw, dict):
        return None
    has_any_known = any(k in raw for k in SECTION_KEYS)
    if not has_any_known:
        return None
    out: dict[str, list[str]] = {}
    for k in SECTION_KEYS:
        v = raw.get(k, [])
        if v is None:
            out[k] = []
        elif isinstance(v, list):
            out[k] = [str(x) for x in v if x is not None]
        else:
            # 1 要素 string も許容 (defensive)
            out[k] = [str(v)]
    return out


def _extract_summary_from_message(msg: cts.ChatMessage) -> Optional[dict[str, list[str]]]:
    """1 メッセージから summary dict を抽出する.

    優先順位:
      1. 経路 A: ChatMessage.compressed_summary フィールド
      2. 経路 B: role='system_summary' で content が JSON dict
    どちらも該当しなければ None.
    """
    # 経路 A: compressed_summary フィールド
    if msg.compressed_summary:
        normalized = _normalize_summary(msg.compressed_summary)
        if normalized is not None:
            return normalized
    # 経路 B: role='system_summary' + JSON content
    if msg.role == SUMMARY_ROLE_SYSTEM_SUMMARY and msg.content:
        try:
            parsed = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            return None
        return _normalize_summary(parsed)
    return None


def _classify_source(msg: cts.ChatMessage) -> Optional[str]:
    """メッセージが summary 経路 A / B のどれか. None なら summary でない."""
    if msg.compressed_summary:
        normalized = _normalize_summary(msg.compressed_summary)
        if normalized is not None:
            return "compressed_summary"
    if msg.role == SUMMARY_ROLE_SYSTEM_SUMMARY and msg.content:
        try:
            parsed = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            return None
        if _normalize_summary(parsed) is not None:
            return "system_summary"
    return None


def _fetch_all_messages(thread_id: int) -> list[cts.ChatMessage]:
    """thread の全 message を取得 (上限 MAX_FETCH_MESSAGES)."""
    store = cts.get_store()
    total = store.count_messages(thread_id)
    if total == 0:
        return []
    fetch_limit = min(total, MAX_FETCH_MESSAGES)
    offset = max(0, total - fetch_limit)
    return store.list_messages(thread_id, limit=fetch_limit, offset=offset)


# ──────────────────────────────────────────────────────────────────────
# Public API: latest_summary (read-only)
# ──────────────────────────────────────────────────────────────────────


async def _emit_audit_safe(
    event_type: str,
    *,
    thread_id: int,
    user_id: Optional[str],
    detail: dict,
) -> None:
    """memory_service.emit_event 経由 audit. 失敗は warning, raise しない."""
    try:
        from services.memory_service import emit_event
        await emit_event(
            event_type, session_id=str(thread_id), user_id=user_id, detail=detail,
        )
    except Exception as e:  # pragma: no cover (sqlite 未配備環境向け)
        logger.warning(
            "mid_term audit emit failed event=%s thread=%s: %s",
            event_type, thread_id, e,
        )


def latest_summary(
    thread_id: int,
    *,
    prefer_source: str = DEFAULT_PREFER_SOURCE,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """最新の 9-section structured summary を返す.

    prefer_source:
      - "auto" (default): 経路 A / B 問わず newest-first で最初に見つかった summary
      - "compressed_summary" : 経路 A だけを対象に newest-first
      - "system_summary"     : 経路 B だけを対象に newest-first

    Returns:
      {
        "thread_id": int,
        "summary": {9 sections},      # 見つからなければ empty_summary()
        "found": bool,
        "source": "compressed_summary" | "system_summary" | None,
        "message_id": int | None,
        "created_at": float | None,
        "prefer_source": str,
      }
    """
    thread_id = _validate_thread_id(thread_id)
    prefer_source = _validate_prefer_source(prefer_source)
    _validate_actor_user_id(actor_user_id)
    _require_thread_exists(thread_id)

    msgs = _fetch_all_messages(thread_id)
    # newest-first: chat_thread_store は append-only なので reverse でよい
    for msg in reversed(msgs):
        source = _classify_source(msg)
        if source is None:
            continue
        if prefer_source != "auto" and source != prefer_source:
            continue
        summary = _extract_summary_from_message(msg)
        if summary is None:
            continue
        return {
            "thread_id": thread_id,
            "summary": summary,
            "found": True,
            "source": source,
            "message_id": msg.id,
            "created_at": msg.created_at,
            "prefer_source": prefer_source,
        }
    return {
        "thread_id": thread_id,
        "summary": empty_summary(),
        "found": False,
        "source": None,
        "message_id": None,
        "created_at": None,
        "prefer_source": prefer_source,
    }


# ──────────────────────────────────────────────────────────────────────
# Public API: latest_summary_audited (G2 service-level emit)
# ──────────────────────────────────────────────────────────────────────


async def latest_summary_audited(
    thread_id: int,
    *,
    prefer_source: str = DEFAULT_PREFER_SOURCE,
    actor_user_id: Optional[str] = None,
    emit_audit: bool = True,
) -> dict[str, Any]:
    """AC-2 'mid_term.read' audit emit 付き latest_summary 呼出 (service 層).

    AC-2 spec 文面の見かけの矛盾の resolution:
      第 1 文: "When latest_summary or record_summary is invoked, the system
              shall ... emit an audit_logs entry ('mid_term.read' /
              'mid_term.recorded') carrying thread_id and source"
      第 2 文: "Read endpoints shall not emit audit events"

    実装の resolve:
      - HTTP read endpoint (GET /api/mid-term/summary 等) → emit_audit=False
        (第 2 文 "Read endpoints" は HTTP endpoint を指す解釈)
      - Python service 層直接呼出 (memory_pipeline.build_context 等) →
        emit_audit=True で 'mid_term.read' を emit
        (第 1 文 "When latest_summary ... is invoked" は service 呼出を含む)
    両文を同時充足する唯一の整合 interpretation.

    record_summary は第 1 文に対応し HTTP/service 共に emit_audit=True 既定
    (record は read ではないため "Read endpoints shall not emit" の対象外).
    """
    result = latest_summary(
        thread_id,
        prefer_source=prefer_source,
        actor_user_id=actor_user_id,
    )
    if emit_audit:
        await _emit_audit_safe(
            AUDIT_EVENT_READ,
            thread_id=result["thread_id"],
            user_id=actor_user_id,
            detail={
                "thread_id": result["thread_id"],
                "source": to_audit_source(result["source"]),
                "found": result["found"],
                "prefer_source": result["prefer_source"],
            },
        )
    return result


# ──────────────────────────────────────────────────────────────────────
# Public API: compressed_history (read-only)
# ──────────────────────────────────────────────────────────────────────


def compressed_history(
    thread_id: int,
    *,
    limit: int = DEFAULT_HISTORY_LIMIT,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """圧縮済 entries の一覧 (newest-first).

    Returns:
      {
        "thread_id": int,
        "limit": int,
        "count": int,
        "entries": [
          {"message_id", "source", "created_at", "summary": {9 sections}},
          ...
        ],
      }
    """
    thread_id = _validate_thread_id(thread_id)
    limit = _validate_limit(limit)
    _validate_actor_user_id(actor_user_id)
    _require_thread_exists(thread_id)

    msgs = _fetch_all_messages(thread_id)
    entries: list[dict[str, Any]] = []
    for msg in reversed(msgs):
        source = _classify_source(msg)
        if source is None:
            continue
        summary = _extract_summary_from_message(msg)
        if summary is None:
            continue
        entries.append({
            "message_id": msg.id,
            "source": source,
            "created_at": msg.created_at,
            "summary": summary,
        })
        if len(entries) >= limit:
            break
    return {
        "thread_id": thread_id,
        "limit": limit,
        "count": len(entries),
        "entries": entries,
    }


# ──────────────────────────────────────────────────────────────────────
# Public API: list_summaries (G1 spec-name alias for compressed_history)
# ──────────────────────────────────────────────────────────────────────


def list_summaries(
    thread_id: int,
    *,
    limit: int = DEFAULT_HISTORY_LIMIT,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """AC-1 spec で名指しされている read view (compressed_history のエイリアス).

    仕様文 "unified read view (latest_summary / list_summaries)" に対応.
    本体は compressed_history. 名前の整合性のためのエイリアス.
    """
    return compressed_history(
        thread_id, limit=limit, actor_user_id=actor_user_id,
    )


# ──────────────────────────────────────────────────────────────────────
# Public API: mid_tier_stats (read-only)
# ──────────────────────────────────────────────────────────────────────


def mid_tier_stats(
    thread_id: int,
    *,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """thread の中期 layer 統計.

    Returns:
      {
        "thread_id": int,
        "total_messages": int,
        "summary_count": int,                 # 経路 A + B 合算
        "by_source": {"compressed_summary": int, "system_summary": int},
        "compression_ratio": float,           # summary_count / total_messages (0..1)
        "latest_summary_created_at": float | None,
        "latest_summary_source": str | None,
        "section_coverage": {section: int},   # 全 summary 横断で各 section の bullet 件数合算
        "covered_section_count": int,         # bullet が 1 件以上ある section の数 (0..9)
        "section_keys": list[str],            # 9 section 不変条件の明示
      }
    """
    thread_id = _validate_thread_id(thread_id)
    _validate_actor_user_id(actor_user_id)
    _require_thread_exists(thread_id)

    msgs = _fetch_all_messages(thread_id)
    total = len(msgs)
    by_source = {"compressed_summary": 0, "system_summary": 0}
    coverage: dict[str, int] = {k: 0 for k in SECTION_KEYS}
    summary_count = 0
    latest_created_at: Optional[float] = None
    latest_source: Optional[str] = None

    for msg in msgs:
        source = _classify_source(msg)
        if source is None:
            continue
        summary = _extract_summary_from_message(msg)
        if summary is None:
            continue
        by_source[source] += 1
        summary_count += 1
        for k, items in summary.items():
            if k in coverage:
                coverage[k] += len(items)
        if latest_created_at is None or msg.created_at > latest_created_at:
            latest_created_at = msg.created_at
            latest_source = source

    ratio = (summary_count / total) if total else 0.0
    covered = sum(1 for k in SECTION_KEYS if coverage[k] > 0)
    return {
        "thread_id": thread_id,
        "total_messages": total,
        "summary_count": summary_count,
        "by_source": by_source,
        "compression_ratio": ratio,
        "latest_summary_created_at": latest_created_at,
        "latest_summary_source": latest_source,
        "section_coverage": coverage,
        "covered_section_count": covered,
        "section_keys": list(SECTION_KEYS),
    }


# ──────────────────────────────────────────────────────────────────────
# G7 hook: register_summarizer_backend (Phase 2 SDK 差替点)
# ──────────────────────────────────────────────────────────────────────

SummarizerBackend = Callable[[list[cts.ChatMessage]], dict]
_SUMMARIZER_BACKEND: Optional[SummarizerBackend] = None


def register_summarizer_backend(backend: Optional[SummarizerBackend]) -> None:
    """G7: T-AI-01 / T-020-02 SDK 完了後の structured output 差替点.

    backend は messages を受け取り 9-section dict を返す callable. None で clear.
    本モジュールは read view 中心のため backend は record_summary() で消費される.
    callable でない場合は MidTermLayerError.
    """
    global _SUMMARIZER_BACKEND
    if backend is not None and not callable(backend):
        raise MidTermLayerError("backend must be callable or None")
    _SUMMARIZER_BACKEND = backend


def get_summarizer_backend() -> Optional[SummarizerBackend]:
    """register 済 backend を返す (テスト/可視化用)."""
    return _SUMMARIZER_BACKEND


# ──────────────────────────────────────────────────────────────────────
# G8 dual-write helper: record_summary (Phase 2 への窓口)
# ──────────────────────────────────────────────────────────────────────


async def _legacy_persist_best_effort(
    thread_id: int,
    summary: dict[str, list[str]],
) -> dict[str, Any]:
    """memory_service.persist_compaction (sqlite + chat_messages 経路 B)
    に best-effort で書く. 失敗は warning に出すだけで raise しない.
    """
    try:
        from services.memory_service import persist_compaction
        message_id = await persist_compaction(thread_id, summary)
        return {"status": "ok", "message_id": message_id}
    except Exception as e:  # pragma: no cover (sqlite 未配備環境向け)
        logger.warning(
            "mid_term_layer legacy persist failed thread_id=%s: %s", thread_id, e,
        )
        return {"status": "error", "reason": f"{type(e).__name__}: {e}"}


async def record_summary(
    thread_id: int,
    summary: dict,
    *,
    persist_legacy: bool = True,
    use_backend: bool = True,
    actor_user_id: Optional[str] = None,
    emit_audit: bool = False,
) -> dict[str, Any]:
    """G8 dual-write: chat_thread_store + memory_service の両経路に書く.

    Args:
      thread_id     : 対象 thread (must exist)
      summary       : 9-section dict (不変条件: SECTION_KEYS いずれか含む)
      persist_legacy: True なら memory_service 経路 B にも書く (best-effort)
      use_backend   : True かつ register 済 backend があれば backend 出力を採用.
                      backend 失敗 (例外 / 不正出力) 時は受信 summary に fallback.
      actor_user_id : UNAUTHORIZED 検知 (None なら skip)

    Returns:
      {
        "thread_id": int,
        "message_id": int,                # chat_thread_store 経路 A の id
        "source": "compressed_summary",
        "summary": {9 sections},
        "legacy_result": {...} | None,    # 経路 B の結果 (persist_legacy=True 時)
        "backend_used": bool,
      }
    """
    thread_id = _validate_thread_id(thread_id)
    _validate_actor_user_id(actor_user_id)
    if not isinstance(persist_legacy, bool):
        raise MidTermLayerError("persist_legacy must be bool")
    if not isinstance(use_backend, bool):
        raise MidTermLayerError("use_backend must be bool")

    normalized = _normalize_summary(summary)
    if normalized is None:
        raise MidTermLayerError(
            f"summary must be a dict containing at least one of {SECTION_KEYS}"
        )

    _require_thread_exists(thread_id)

    backend_used = False
    final_summary = normalized
    if use_backend and _SUMMARIZER_BACKEND is not None:
        try:
            store = cts.get_store()
            msgs = store.list_messages(thread_id, limit=MAX_FETCH_MESSAGES, offset=0)
            backend_out = _SUMMARIZER_BACKEND(msgs)
            backend_normalized = _normalize_summary(backend_out)
            if backend_normalized is not None:
                final_summary = backend_normalized
                backend_used = True
            else:
                logger.warning(
                    "summarizer backend returned invalid output, "
                    "falling back to provided summary",
                )
        except Exception as e:
            logger.warning(
                "summarizer backend raised, falling back to provided summary: %s", e,
            )

    # 経路 A: chat_thread_store に role='system' + compressed_summary で書く
    store = cts.get_store()
    persisted = store.add_message(
        thread_id,
        SUMMARY_ROLE_SYSTEM,
        "[mid_term_layer] 9-section structured summary (dual-write)",
        compressed_summary=final_summary,
    )

    # 経路 B: memory_service.persist_compaction に best-effort
    legacy_result: Optional[dict[str, Any]] = None
    if persist_legacy:
        legacy_result = await _legacy_persist_best_effort(thread_id, final_summary)

    # AC-2 spec: audit source は永続化先 module 名 ('chat_thread_store' /
    # 'memory_service'). 経路 A (chat_thread_store) が主, B (memory_service)
    # が legacy_result の status=='ok' のときに同時記録された旨を併記.
    legacy_ok = bool(
        legacy_result and legacy_result.get("status") == "ok"
    )
    audit_sources: list[str] = ["chat_thread_store"]
    if legacy_ok:
        audit_sources.append("memory_service")
    primary_audit_source = "chat_thread_store"

    result = {
        "thread_id": thread_id,
        "message_id": persisted.id,
        "source": "compressed_summary",
        "audit_source": primary_audit_source,
        "audit_sources": audit_sources,
        "summary": final_summary,
        "legacy_result": legacy_result,
        "backend_used": backend_used,
    }
    if emit_audit:
        await _emit_audit_safe(
            AUDIT_EVENT_RECORDED,
            thread_id=thread_id,
            user_id=actor_user_id,
            detail={
                "thread_id": thread_id,
                "message_id": persisted.id,
                "source": primary_audit_source,
                "audit_sources": audit_sources,
                "backend_used": backend_used,
                "persist_legacy": persist_legacy,
                "legacy_status": (legacy_result or {}).get("status"),
            },
        )
    return result
