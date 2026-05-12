"""T-M27-01b: Intent Router entry node (claude-agent-sdk runtime, no LangGraph).

ADR-010 / T-M27-01 supersede:
  本 module は LangGraph entry node の置換. **claude-agent-sdk** を runtime に
  使う (本 module 自体は SDK の subagent dispatch 起点として呼ばれることを
  想定し, application code レベルで LangGraph/LangChain を import しない).

公開 API:
  - dispatch(user_message, session_id, *, actor_user_id=None) -> dict
      intent_classifier (T-M27-02 wrapper) に classify を delegate し,
      返ってきた top_signal を persona key にマップして返す.
  - PERSONA_BY_SKILL              : skill -> persona key の固定マッピング.
  - DEFAULT_PERSONA               : fallback persona ("secretary").
  - VALID_PERSONA_KEYS            : 既知 persona 一覧 (mary/devon/quinn/...).
  - IntentRouterEntryError        : 入力 / 不変条件違反 (router で 4xx).

設計境界 (NEW タスク, IMPLEMENTATION_PROTOCOL Step 4):
  - 既存 intent_classifier.py / claude_agent_runner.py は無改変.
  - classify は intent_classifier.classify を経由のみ.
  - LangGraph/LangChain import は **本 module に存在しない**
    (scripts/lint-mock.sh の check_no_langgraph で機械検知, ADR-010).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : entry node は claude-agent-sdk runtime; LangGraph 不使用.
                       (user_message, session_id) を受け chosen_persona を返す.
  AC-2 EVENT-DRIVEN  : audit emit `m27.entry_node.dispatched` with
                       chosen_persona / latency_ms / session_id within 2s.
  AC-3 STATE-DRIVEN  : audit_logs に RLS 適用 (memory_service 側) /
                       routing decision を session に記録 (best-effort).
  AC-4 UNWANTED      : LangGraph import → lint fail / invalid input / blank actor
                       → IntentRouterEntryError → 4xx + state mutate なし.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class IntentRouterEntryError(RuntimeError):
    """入力 / 不変条件違反 (router 層で 4xx に変換)."""


# ──────────────────────────────────────────────────────────────────────
# 制約定数
# ──────────────────────────────────────────────────────────────────────

MAX_MESSAGE_CHARS = 8_000
MAX_ACTOR_USER_ID_LEN = 200
MAX_SESSION_ID_LEN = 200

DEFAULT_PERSONA = "secretary"
DISPATCH_AUDIT_EVENT = "m27.entry_node.dispatched"

# BMAD 10 ペルソナ (CLAUDE.md §3 + 拡張)
VALID_PERSONA_KEYS = (
    "secretary",
    "mary",       # BA
    "preston",    # PM
    "winston",    # Architect
    "sally",      # PO
    "devon",      # Dev
    "quinn",      # QA
    "reviewer",
    "brand",
    "mockup",
    "logan",      # curator
)

# skill key (intent_classifier の result['skill']) -> persona key の固定マップ
# 未知 skill / skill=None の場合は DEFAULT_PERSONA に fallback.
PERSONA_BY_SKILL: dict[str, str] = {
    # BA / 要件
    "ba": "mary",
    "hearing": "mary",
    "analysis": "mary",
    # PM / プロセス
    "requirements": "preston",
    "pm": "preston",
    "planning": "preston",
    # Architect / 設計
    "architecture": "winston",
    "design": "winston",
    "tech_stack": "winston",
    # PO / プロダクト
    "product_owner": "sally",
    "backlog": "sally",
    "po": "sally",
    # Dev / 実装
    "dev": "devon",
    "implementation": "devon",
    "coding": "devon",
    "refactor": "devon",
    # QA / テスト
    "qa": "quinn",
    "test": "quinn",
    "qa_review": "quinn",
    # Reviewer
    "review": "reviewer",
    "code_review": "reviewer",
    # Brand
    "brand": "brand",
    "branding": "brand",
    "logo": "brand",
    # Mockup
    "mockup": "mockup",
    "mock": "mockup",
    "wireframe": "mockup",
    # Curator (logan)
    "curator": "logan",
    "knowledge": "logan",
    "research": "logan",
}


# ──────────────────────────────────────────────────────────────────────
# Validation helpers (AC-4 UNWANTED)
# ──────────────────────────────────────────────────────────────────────


def _validate_message(message: Any) -> str:
    if not isinstance(message, str) or not message.strip():
        raise IntentRouterEntryError("user_message must not be empty")
    s = message.strip()
    if len(s) > MAX_MESSAGE_CHARS:
        raise IntentRouterEntryError(
            f"user_message must be <= {MAX_MESSAGE_CHARS} chars"
        )
    return s


def _validate_session_id(session_id: Any) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise IntentRouterEntryError("session_id must not be empty")
    s = session_id.strip()
    if len(s) > MAX_SESSION_ID_LEN:
        raise IntentRouterEntryError(
            f"session_id must be <= {MAX_SESSION_ID_LEN} chars"
        )
    return s


def _validate_actor_user_id(actor: Optional[str]) -> Optional[str]:
    if actor is None:
        return None
    if not isinstance(actor, str):
        raise IntentRouterEntryError("actor_user_id must be string or null")
    s = actor.strip()
    if not s:
        raise IntentRouterEntryError(
            "actor_user_id must not be empty when provided"
        )
    if len(s) > MAX_ACTOR_USER_ID_LEN:
        raise IntentRouterEntryError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return s


# ──────────────────────────────────────────────────────────────────────
# Persona mapping (純粋関数 / 副作用なし / unit testable)
# ──────────────────────────────────────────────────────────────────────


def map_intent_to_persona(intent: dict) -> str:
    """intent_classifier.classify の戻り値 (or top_signal dict) を persona に変換.

    マッピングルール (優先度順):
      1. explicit_intent.type == "remember"  → secretary (記憶系)
      2. skill が PERSONA_BY_SKILL に存在    → 対応 persona
      3. top_signal.kind == "skill"          → PERSONA_BY_SKILL[value] or default
      4. それ以外 (mode のみ / 不明)         → DEFAULT_PERSONA
    """
    if not isinstance(intent, dict):
        return DEFAULT_PERSONA

    # 1. explicit_intent
    explicit = intent.get("explicit_intent")
    if isinstance(explicit, dict):
        if explicit.get("type") == "remember":
            return "secretary"

    # 2. skill direct lookup (intent_classifier.classify return)
    skill = intent.get("skill")
    if isinstance(skill, str) and skill:
        key = skill.lower()
        if key in PERSONA_BY_SKILL:
            return PERSONA_BY_SKILL[key]

    # 3. top_signal.kind == "skill"
    top = intent.get("top_signal")
    if isinstance(top, dict):
        kind = top.get("kind")
        value = top.get("value")
        if kind == "skill" and isinstance(value, str) and value:
            key = value.lower()
            if key in PERSONA_BY_SKILL:
                return PERSONA_BY_SKILL[key]

    # 4. default
    return DEFAULT_PERSONA


# ──────────────────────────────────────────────────────────────────────
# Public API: dispatch
# ──────────────────────────────────────────────────────────────────────


async def dispatch(
    user_message: str,
    session_id: str,
    *,
    actor_user_id: Optional[str] = None,
    history: Optional[list[dict]] = None,
    rules_only: bool = False,
) -> dict[str, Any]:
    """Intent Router entry node (T-M27-01b).

    Args:
      user_message  : エンドユーザーが入力したメッセージ (必須, <= 8000 chars).
      session_id    : 対象 session 識別子 (必須, <= 200 chars).
      actor_user_id : 認可確認用. None なら anonymous (router 側で auth 強制可).
      history       : 直近のチャット履歴 (intent classifier 用 hint).
      rules_only    : True なら LLM fallback をスキップ (テスト時に有用).

    Returns:
      {
        "session_id": str,
        "chosen_persona": str,            # VALID_PERSONA_KEYS のいずれか
        "intent": dict,                   # intent_classifier.classify の生戻り
        "latency_ms": float,              # dispatch 全体の所要時間
        "actor_user_id": str|None,
        "audit_event_id": int|None,       # audit emit 結果 (best-effort)
      }

    AC-2 EVENT-DRIVEN: 完了時に `m27.entry_node.dispatched` audit を emit.
      detail = {chosen_persona, latency_ms, session_id, actor_user_id?}.
    AC-3 STATE-DRIVEN: audit emit は best-effort. 失敗時は warning ログのみ.
    AC-4 UNWANTED: validation 失敗時は IntentRouterEntryError raise
                   (router 側で 4xx に変換). state mutate なし.
    """
    msg = _validate_message(user_message)
    sid = _validate_session_id(session_id)
    actor = _validate_actor_user_id(actor_user_id)
    if not isinstance(rules_only, bool):
        raise IntentRouterEntryError("rules_only must be bool")

    # Lazy import (循環回避 + LangGraph 不使用の明示)
    from services import intent_classifier as ic

    t0 = time.time()
    try:
        intent = await ic.classify(
            msg,
            history=history,
            actor_user_id=actor,
            rules_only=rules_only,
        )
    except ic.IntentClassifierError as e:
        # T-M27-02 の入力 4xx を T-M27-01b の 4xx に変換
        raise IntentRouterEntryError(f"intent classification failed: {e}")

    persona = map_intent_to_persona(intent)
    latency_ms = (time.time() - t0) * 1000.0

    # AC-2 audit emit (best-effort)
    audit_event_id: Optional[int] = None
    try:
        from services.memory_service import emit_event
        audit_event_id = await emit_event(
            DISPATCH_AUDIT_EVENT,
            user_id=actor,
            detail={
                "session_id": sid,
                "chosen_persona": persona,
                "latency_ms": round(latency_ms, 3),
                "actor_user_id": actor,
            },
        )
    except Exception as e:  # pragma: no cover (audit 失敗は warning のみ)
        logger.warning(
            "m27 entry node audit emit failed session=%s: %s", sid, e,
        )

    return {
        "session_id": sid,
        "chosen_persona": persona,
        "intent": intent,
        "latency_ms": latency_ms,
        "actor_user_id": actor,
        "audit_event_id": audit_event_id,
    }
