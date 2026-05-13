"""T-M27-02: Intent 分類 (existing intent_preprocessor / mode_detector / skill_detector 統合).

M-27 Intent Router の Intent 分類段を統一インターフェース化する REFACTOR.

3 つの既存 detector を並列実行し、結果を 1 つの `IntentSignal` dict に束ねる:

  1. **explicit_intent** : `intent_preprocessor.detect_explicit_intent`
                          「覚えて」「メモして」等の明示指示 (= remember type)
  2. **mode**            : `mode_detector.detect_mode` (async)
                          chat / task の二値判定 (rule 90% + LLM 10% fallback)
  3. **skill**           : `skill_detector.detect_skill`
                          SKILL.md トリガーキーワード判定 (SKILL_TRIGGERS 辞書)

## 公開 API (read-only, side-effect は audit emit のみ)

- `classify(message, *, history, employee_primary_skill, actor_user_id,
            rules_only) -> dict`
    3 detector を並列実行し統一 dict を返す pipeline 入口
- `top_signal(explicit, skill, mode) -> dict`
    優先度ロジック (explicit > skill > mode) を純関数として export (テスト可)
- `register_classifier_backend(callable)`
    G18: SDK / 別 LLM 経路差替点

## ADR-010 整合性

Intent classification は **SDK auto 提供機能ではない** application-level routing
logic. 軽量 rule-based + 任意で LLM fallback (gpt-4o-mini via mode_detector).
LangGraph / LangChain は不使用 (lint-no-langgraph で監視).

## 設計境界 (REFACTOR 宣言 / IMPLEMENTATION_PROTOCOL Step 4)

既存 `intent_preprocessor.py` / `mode_detector.py` / `skill_detector.py` は
**完全に無改変**. 本 module は thin orchestrator で 3 detector の API を呼ぶだけ.
既存 import path / 関数シグネチャ / 戻り値構造は触らない.

## Spec gap closure (PR #128 G1-G6 / PR #129 G7-G10 / PR #130 G11-G14 /
本セッション PR #131 機械的ガード と同じ精神 / G18-G21)

- **G18** SDK / 別 LLM backend hook : `register_classifier_backend(callable)` で
        SDK / Anthropic 直 API への差替を可能化. 例外 / 不正出力時は本実装に
        fallback (silent failure 防止 warning ログ).
- **G19** rules-only mode           : `rules_only=True` で LLM fallback を無効化.
        CI / deterministic テスト / 高速応答が必要な場合の opt-out.
- **G20** 元 module 不変保証        : intent_preprocessor / mode_detector /
        skill_detector の symbol surface 不変. テストで cross-module 確認.
- **G21** top_signal 優先度抽象     : top_signal() を純関数として export し,
        優先順位ロジック (explicit > skill > mode) のテスト可能性を担保.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class IntentClassifierError(RuntimeError):
    """Intent classifier の入力 / 不変条件違反 (router 層で 4xx 変換)."""


# ──────────────────────────────────────────────────────────────────────
# 制約定数
# ──────────────────────────────────────────────────────────────────────

MAX_MESSAGE_CHARS = 4_000
MAX_HISTORY_ITEMS = 100
MAX_HISTORY_ITEM_CHARS = 4_000
MAX_PRIMARY_SKILL_LEN = 100
MAX_ACTOR_USER_ID_LEN = 200

VALID_MODES = ("chat", "task")

# top_signal 優先度: explicit > skill > mode
SIGNAL_PRIORITY = ("explicit", "skill", "mode")


# ──────────────────────────────────────────────────────────────────────
# Validation (AC-4 UNWANTED)
# ──────────────────────────────────────────────────────────────────────


def _validate_message(message: Any) -> str:
    if not isinstance(message, str) or not message.strip():
        raise IntentClassifierError("message must not be empty")
    s = message.strip()
    if len(s) > MAX_MESSAGE_CHARS:
        raise IntentClassifierError(
            f"message must be <= {MAX_MESSAGE_CHARS} chars"
        )
    return s


def _validate_history(history: Any) -> Optional[list[dict]]:
    if history is None:
        return None
    if not isinstance(history, list):
        raise IntentClassifierError("history must be a list or null")
    if len(history) > MAX_HISTORY_ITEMS:
        raise IntentClassifierError(
            f"history must be <= {MAX_HISTORY_ITEMS} items"
        )
    out: list[dict] = []
    for i, h in enumerate(history):
        if not isinstance(h, dict):
            raise IntentClassifierError(f"history[{i}] must be a dict")
        role = h.get("role")
        if role is not None and not isinstance(role, str):
            raise IntentClassifierError(f"history[{i}].role must be string")
        content = h.get("content") or h.get("message") or ""
        if not isinstance(content, str):
            raise IntentClassifierError(
                f"history[{i}].content must be string"
            )
        if len(content) > MAX_HISTORY_ITEM_CHARS:
            raise IntentClassifierError(
                f"history[{i}].content must be <= {MAX_HISTORY_ITEM_CHARS} chars"
            )
        out.append({"role": role, "content": content})
    return out


def _validate_primary_skill(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise IntentClassifierError("employee_primary_skill must be string or null")
    s = value.strip()
    if not s:
        raise IntentClassifierError(
            "employee_primary_skill must not be empty when provided"
        )
    if len(s) > MAX_PRIMARY_SKILL_LEN:
        raise IntentClassifierError(
            f"employee_primary_skill must be <= {MAX_PRIMARY_SKILL_LEN} chars"
        )
    return s


def _validate_actor_user_id(actor: Optional[str]) -> Optional[str]:
    if actor is None:
        return None
    if not isinstance(actor, str):
        raise IntentClassifierError("actor_user_id must be string or null")
    s = actor.strip()
    if not s:
        raise IntentClassifierError(
            "actor_user_id must not be empty when provided"
        )
    if len(s) > MAX_ACTOR_USER_ID_LEN:
        raise IntentClassifierError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return s


def _validate_rules_only(value: Any) -> bool:
    if not isinstance(value, bool):
        raise IntentClassifierError("rules_only must be bool")
    return value


# ──────────────────────────────────────────────────────────────────────
# G18: backend hook (SDK / 別 LLM 経路差替点)
# ──────────────────────────────────────────────────────────────────────

ClassifierBackend = Callable[[str, Optional[list[dict]], Optional[str]], dict]
"""backend(message, history, employee_primary_skill) -> dict.

dict は本 module の classify() と同じ形を返す:
  {"explicit_intent": ..., "mode": "chat|task", "skill": ..., "top_signal": ...}
"""

_CLASSIFIER_BACKEND: Optional[ClassifierBackend] = None


def register_classifier_backend(backend: Optional[ClassifierBackend]) -> None:
    """G18: claude-agent-sdk / Anthropic 直 API / 別 LLM 経路差替点.

    backend が callable でない場合 raise. None で clear.
    例外 / 不正出力時は本実装 (3 detector 並列) に fallback (warning ログ).
    """
    global _CLASSIFIER_BACKEND
    if backend is not None and not callable(backend):
        raise IntentClassifierError("classifier backend must be callable or None")
    _CLASSIFIER_BACKEND = backend


def get_classifier_backend() -> Optional[ClassifierBackend]:
    return _CLASSIFIER_BACKEND


def _validate_backend_output(out: object) -> dict:
    """backend 戻り dict の不変条件確認. 不正なら raise (caller が fallback)."""
    if not isinstance(out, dict):
        raise IntentClassifierError("backend must return a dict")
    for key in ("explicit_intent", "mode", "skill", "top_signal"):
        if key not in out:
            raise IntentClassifierError(f"backend output missing key: {key}")
    mode = out["mode"]
    if mode is not None and mode not in VALID_MODES:
        raise IntentClassifierError(
            f"backend output mode must be one of {VALID_MODES} or null, got {mode!r}"
        )
    if out["explicit_intent"] is not None and not isinstance(out["explicit_intent"], dict):
        raise IntentClassifierError(
            "backend output explicit_intent must be dict or null"
        )
    if out["skill"] is not None and not isinstance(out["skill"], str):
        raise IntentClassifierError(
            "backend output skill must be string or null"
        )
    if not isinstance(out["top_signal"], dict):
        raise IntentClassifierError("backend output top_signal must be dict")
    return out


# ──────────────────────────────────────────────────────────────────────
# G21: top_signal 優先度 (純関数 / テスト可)
# ──────────────────────────────────────────────────────────────────────


def top_signal(
    explicit_intent: Optional[dict],
    skill: Optional[str],
    mode: str,
) -> dict:
    """3 detector の結果から最優先シグナルを決定する純関数.

    優先順位 (G21): explicit > skill > mode

    Returns:
      {
        "kind": "explicit" | "skill" | "mode",
        "value": str,           # explicit -> intent type, skill -> skill name, mode -> "chat"/"task"
        "detail": dict | None,  # explicit -> intent dict, others -> None
        "priority_rank": int,   # 0=highest
      }
    """
    if explicit_intent and isinstance(explicit_intent, dict) and explicit_intent.get("type"):
        return {
            "kind": "explicit",
            "value": str(explicit_intent["type"]),
            "detail": dict(explicit_intent),
            "priority_rank": 0,
        }
    if skill and isinstance(skill, str):
        return {
            "kind": "skill",
            "value": skill,
            "detail": None,
            "priority_rank": 1,
        }
    if mode in VALID_MODES:
        return {
            "kind": "mode",
            "value": mode,
            "detail": None,
            "priority_rank": 2,
        }
    # fallback: 全部不明 → chat 扱い
    return {
        "kind": "mode",
        "value": "chat",
        "detail": None,
        "priority_rank": 2,
    }


# ──────────────────────────────────────────────────────────────────────
# 内部: 既存 3 detector を thin に呼ぶ wrapper
# ──────────────────────────────────────────────────────────────────────


def _call_explicit(message: str) -> Optional[dict]:
    """intent_preprocessor.detect_explicit_intent を thin 呼出 (G20)."""
    from services.intent_preprocessor import detect_explicit_intent
    try:
        return detect_explicit_intent(message)
    except Exception as e:  # pragma: no cover (defensive)
        logger.warning("explicit_intent detector failed: %s", e)
        return None


async def _call_mode(
    message: str,
    history: Optional[list[dict]],
    *,
    rules_only: bool,
) -> str:
    """mode_detector を thin 呼出 (G20).

    rules_only=True なら llm_detect をスキップして rule_detect のみ.
    """
    from services.mode_detector import rule_detect, detect_mode
    if rules_only:
        rule = rule_detect(message, history)
        return rule if rule is not None else "chat"
    try:
        return await detect_mode(message, history)
    except Exception as e:  # pragma: no cover
        logger.warning("mode_detector failed: %s", e)
        return "chat"


def _call_skill(
    message: str,
    history: Optional[list[dict]],
    employee_primary_skill: Optional[str],
) -> Optional[str]:
    """skill_detector.detect_skill を thin 呼出 (G20)."""
    from services.skill_detector import detect_skill
    try:
        return detect_skill(
            message,
            history=history,
            employee_primary_skill=employee_primary_skill,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("skill_detector failed: %s", e)
        return None


# ──────────────────────────────────────────────────────────────────────
# 公開 API: classify (entry point)
# ──────────────────────────────────────────────────────────────────────


async def classify(
    message: str,
    *,
    history: Optional[list[dict]] = None,
    employee_primary_skill: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    rules_only: bool = False,
    use_backend: bool = True,
) -> dict:
    """3 detector を並列実行し統一 Intent dict を返す.

    Returns:
      {
        "message_preview": str,        # 先頭 80 字
        "explicit_intent": dict|None,  # {"type": "remember", "content": "..."} or None
        "mode": "chat" | "task",
        "skill": str | None,           # SKILL.md 名 or None
        "top_signal": {                # 優先順位適用後のメインシグナル
          "kind": "explicit"|"skill"|"mode",
          "value": str,
          "detail": dict|None,
          "priority_rank": int,
        },
        "config": {
          "rules_only": bool,
          "backend_used": bool,
          "had_history": bool,
          "had_primary_skill": bool,
        },
        "meta": {
          "latency_ms": float,
          "input_chars": int,
        },
      }

    AC-4: invalid input → raise IntentClassifierError. persistent state mutate なし.
    G18: register 済 backend があれば優先 (use_backend=True 時). 例外/不正で fallback.
    G19: rules_only=True なら LLM fallback (mode_detector.llm_detect) をスキップ.
    G20: 既存 3 module は無改変.
    G21: top_signal は純関数として別途 export.
    """
    msg = _validate_message(message)
    hist = _validate_history(history)
    primary_skill = _validate_primary_skill(employee_primary_skill)
    _validate_actor_user_id(actor_user_id)
    rules_only = _validate_rules_only(rules_only)
    if not isinstance(use_backend, bool):
        raise IntentClassifierError("use_backend must be bool")

    t0 = time.time()
    backend_used = False
    result: Optional[dict] = None

    # G18: backend 優先 (失敗時 fallback)
    if use_backend and _CLASSIFIER_BACKEND is not None:
        try:
            raw = _CLASSIFIER_BACKEND(msg, hist, primary_skill)
            if asyncio.iscoroutine(raw):
                raw = await raw
            result = _validate_backend_output(raw)
            backend_used = True
        except Exception as e:
            logger.warning(
                "classifier backend failed, falling back to 3-detector: %s", e,
            )
            result = None

    if result is None:
        # 3 detector 並列実行
        explicit_task = asyncio.to_thread(_call_explicit, msg)
        mode_task = _call_mode(msg, hist, rules_only=rules_only)
        skill_task = asyncio.to_thread(_call_skill, msg, hist, primary_skill)
        explicit, mode, skill = await asyncio.gather(
            explicit_task, mode_task, skill_task,
            return_exceptions=False,
        )
        signal = top_signal(explicit, skill, mode)
        result = {
            "explicit_intent": explicit,
            "mode": mode,
            "skill": skill,
            "top_signal": signal,
        }

    elapsed_ms = (time.time() - t0) * 1000.0

    return {
        "message_preview": msg[:80],
        "explicit_intent": result["explicit_intent"],
        "mode": result["mode"],
        "skill": result["skill"],
        "top_signal": result["top_signal"],
        "config": {
            "rules_only": rules_only,
            "backend_used": backend_used,
            "had_history": hist is not None and len(hist) > 0,
            "had_primary_skill": primary_skill is not None,
        },
        "meta": {
            "latency_ms": round(elapsed_ms, 2),
            "input_chars": len(msg),
        },
    }
