"""T-025-02: EARS 形式分類 + 書き直し suggest service.

T-025-01 (EARS JSON Schema) の自然な続編. free-form text を 5 EARS 形式に
分類し、形式に沿った書き直しを suggest する.

## 動作モード (graceful degradation)

  1. **AI mode** (T-S0-08 マージ後):
     register_classifier_backend(callable) で claude-agent-sdk + Anthropic API
     を差替. `data/prompts/ears-classifier.md` を system prompt として使う.

  2. **Rule-based mode** (default / T-S0-08 マージ前):
     prefix keyword (When/While/Where/If/shall) で機械的に分類.
     書き直しも template ベース.

## 公開 API

  - classify(text, *, hint_type, use_backend) -> dict
  - suggest_rewrite(text, target_type) -> str
  - register_classifier_backend(callable) -> None  (G hook)
  - validate_against_schema(rewritten, target_type) -> bool

## ADR-010 整合性

本 module は **claude-agent-sdk の auto 機能を再実装しない**.
AI 経由分類は backend hook で差替 (G53 SDK-friendly).

## AC マッピング (T-025-02)

  AC-1 UBIQUITOUS    : classify / suggest_rewrite / register_classifier_backend
                       を公開. 5 EARS forms 全対応. T-025-01 schema と整合.
  AC-2 EVENT-DRIVEN  : classify() で {classified_type, confidence, rewritten_text,
                       rationale, warnings} dict 返却. 100ms 以内 (rule-based).
  AC-3 STATE-DRIVEN  : backend 未登録 → rule-based fallback. T-025-01 schema を
                       破壊しない (REUSE). audit_logs DB 書込なし.
  AC-4 UNWANTED      : invalid text / target_type で ValueError. backend output
                       が schema に従わない → fallback. hardcoded secret なし.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = REPO_ROOT / "data" / "prompts" / "ears-classifier.md"
SCHEMA_FILE = REPO_ROOT / "backend" / "schemas" / "ears_ac_schema.json"


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

VALID_TYPES = (
    "UBIQUITOUS",
    "EVENT-DRIVEN",
    "STATE-DRIVEN",
    "OPTIONAL",
    "UNWANTED",
)

# type → prefix keyword (T-025-01 schema の pattern と整合)
TYPE_PATTERNS: dict[str, re.Pattern] = {
    "EVENT-DRIVEN": re.compile(r"^When\b|when ", re.IGNORECASE),
    "STATE-DRIVEN": re.compile(r"^While\b|while ", re.IGNORECASE),
    "OPTIONAL": re.compile(r"^Where\b|where ", re.IGNORECASE),
    "UNWANTED": re.compile(r"^If\b|if ", re.IGNORECASE),
    "UBIQUITOUS": re.compile(r"shall|SHALL"),
}

# Suggest template per type (rewriter rules)
REWRITE_TEMPLATES = {
    "UBIQUITOUS": "The system shall {action}.",
    "EVENT-DRIVEN": "When {event}, the system shall {action}.",
    "STATE-DRIVEN": "While {state}, the system shall {action}.",
    "OPTIONAL": "Where {feature is enabled}, the system shall {action}.",
    "UNWANTED": "If {unwanted condition}, the system shall not {bad action}.",
}

MAX_TEXT_CHARS = 2000


# ──────────────────────────────────────────────────────────────────────
# G53: SDK backend hook (T-S0-08 マージ後の差替点)
# ──────────────────────────────────────────────────────────────────────

ClassifierBackend = Callable[[str, Optional[str]], dict]
"""backend(text, hint_type) -> classification dict.

Should return:
  {
    "classified_type": str,
    "confidence": float,
    "rewritten_text": str,
    "rationale": str,
    "warnings": list[str],
  }
"""

_BACKEND: Optional[ClassifierBackend] = None


def register_classifier_backend(backend: Optional[ClassifierBackend]) -> None:
    """SDK / AI backend を register. None で clear."""
    global _BACKEND
    if backend is not None and not callable(backend):
        raise ValueError("backend must be callable or None")
    _BACKEND = backend


def get_classifier_backend() -> Optional[ClassifierBackend]:
    return _BACKEND


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_text(value: object, *, allow_short: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("text must be string")
    s = value.strip()
    if not s:
        raise ValueError("text must not be empty")
    if not allow_short and len(s) < 10:
        raise ValueError("text must be >= 10 chars")
    if len(s) > MAX_TEXT_CHARS:
        raise ValueError(f"text must be <= {MAX_TEXT_CHARS} chars")
    return s


def _validate_target_type(value: object, *, allow_none: bool = False) -> Optional[str]:
    if value is None:
        if allow_none:
            return None
        raise ValueError("target_type must not be None")
    if not isinstance(value, str):
        raise ValueError("target_type must be string")
    upper = value.strip().upper()
    if upper not in VALID_TYPES:
        raise ValueError(
            f"target_type must be one of {VALID_TYPES}, got {value!r}"
        )
    return upper


# ──────────────────────────────────────────────────────────────────────
# Rule-based classification (default)
# ──────────────────────────────────────────────────────────────────────


def _classify_rule_based(text: str) -> tuple[str, float, str]:
    """Rule-based: prefix keyword + shall check.

    Returns:
        (classified_type, confidence, rationale)
    """
    # 優先順位: UNWANTED > EVENT > STATE > OPTIONAL > UBIQUITOUS
    # (UNWANTED が他 form の中にも"if"を含み得るため最優先)
    for type_name in ("UNWANTED", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL"):
        pat = TYPE_PATTERNS[type_name]
        if pat.search(text):
            return (type_name, 0.85, f"matched {type_name} prefix pattern")

    # fallback: "shall" を含めば UBIQUITOUS
    if TYPE_PATTERNS["UBIQUITOUS"].search(text):
        return ("UBIQUITOUS", 0.70, "contains 'shall', no specific form prefix")

    return ("UBIQUITOUS", 0.40, "no clear EARS form indicator; default UBIQUITOUS")


def _rewrite_template_based(text: str, target_type: str) -> str:
    """Rule-based rewrite: 既存 text を target_type の形式に整形.

    既に keyword を含む場合は基本そのまま. そうでなければ template prefix を追加.
    """
    s = text.strip()
    pat = TYPE_PATTERNS[target_type]

    # 既に pattern を満たす場合 (UBIQUITOUS は shall を含む等) → そのまま返す
    if pat.search(s):
        # ただし UBIQUITOUS の場合は他 form の prefix を持たないこと
        if target_type == "UBIQUITOUS":
            for other in ("UNWANTED", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL"):
                if TYPE_PATTERNS[other].search(s):
                    break
            else:
                return s
        else:
            return s

    # prefix を追加
    if target_type == "UBIQUITOUS":
        if "shall" not in s.lower():
            return f"The system shall {s.rstrip('.')}."
        return s
    elif target_type == "EVENT-DRIVEN":
        return f"When [event occurs], the system shall {s.rstrip('.')}."
    elif target_type == "STATE-DRIVEN":
        return f"While [state is active], the system shall {s.rstrip('.')}."
    elif target_type == "OPTIONAL":
        return f"Where [feature is enabled], the system shall {s.rstrip('.')}."
    elif target_type == "UNWANTED":
        if "not" in s.lower() or "reject" in s.lower() or "fail" in s.lower():
            return f"If [unwanted condition], the system shall {s.rstrip('.')}."
        return f"If [unwanted condition], the system shall not {s.rstrip('.')}."
    return s


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def classify(
    text: str,
    *,
    hint_type: Optional[str] = None,
    use_backend: bool = True,
) -> dict:
    """Classify free-form text into 5 EARS forms + suggest rewrite.

    Args:
        text: input text (10-2000 chars).
        hint_type: optional target type to bias the classifier.
        use_backend: try registered AI backend first (default True).

    Returns:
        {
          "classified_type": str,
          "confidence": float,
          "rewritten_text": str,
          "rationale": str,
          "warnings": list[str],
          "backend_used": bool,
        }
    """
    s = _validate_text(text)
    hint = _validate_target_type(hint_type, allow_none=True)
    if not isinstance(use_backend, bool):
        raise ValueError("use_backend must be bool")

    backend_used = False
    out: Optional[dict] = None

    if use_backend and _BACKEND is not None:
        try:
            raw = _BACKEND(s, hint)
            out = _validate_backend_output(raw)
            backend_used = True
        except Exception as e:
            logger.warning(
                "EARS classifier backend failed, falling back to rule-based: %s",
                e,
            )
            out = None

    if out is None:
        if hint:
            # hint があれば信用する
            classified = hint
            confidence = 0.95
            rationale = f"hint_type='{hint}' provided by caller"
        else:
            classified, confidence, rationale = _classify_rule_based(s)
        rewritten = _rewrite_template_based(s, classified)
        out = {
            "classified_type": classified,
            "confidence": confidence,
            "rewritten_text": rewritten,
            "rationale": rationale,
            "warnings": [],
        }

    # backend / rule どちらでも warnings を補強
    warnings = list(out.get("warnings", []))
    if classified := out.get("classified_type"):
        if classified == "UBIQUITOUS" and "UNWANTED" not in (hint or ""):
            # UNWANTED の重要性をリマインド (本セッション仕様徹底原則)
            warnings.append(
                "Consider adding an UNWANTED-form AC alongside (each ticket"
                " requires >= 1 UNWANTED per Build-Factory convention)."
            )

    return {
        "classified_type": out["classified_type"],
        "confidence": float(out["confidence"]),
        "rewritten_text": out["rewritten_text"],
        "rationale": out["rationale"],
        "warnings": warnings,
        "backend_used": backend_used,
    }


def suggest_rewrite(text: str, target_type: str) -> str:
    """Suggest a rewrite for the given target_type. Rule-based, no backend."""
    s = _validate_text(text)
    target = _validate_target_type(target_type)
    return _rewrite_template_based(s, target)


def validate_against_schema(rewritten_text: str, target_type: str) -> bool:
    """Check if rewritten_text conforms to T-025-01 schema for target_type."""
    s = _validate_text(rewritten_text, allow_short=True)
    target = _validate_target_type(target_type)
    pat = TYPE_PATTERNS[target]
    return bool(pat.search(s)) and 20 <= len(s) <= 2000


# ──────────────────────────────────────────────────────────────────────
# Backend output validation (graceful fallback)
# ──────────────────────────────────────────────────────────────────────


def _validate_backend_output(out: object) -> dict:
    if not isinstance(out, dict):
        raise ValueError("backend output must be dict")
    for key in ("classified_type", "confidence", "rewritten_text", "rationale"):
        if key not in out:
            raise ValueError(f"backend output missing key: {key}")
    ct = out["classified_type"]
    if ct not in VALID_TYPES:
        raise ValueError(f"backend classified_type invalid: {ct!r}")
    conf = out["confidence"]
    if not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
        raise ValueError(f"backend confidence must be in [0,1], got {conf!r}")
    if not isinstance(out["rewritten_text"], str):
        raise ValueError("backend rewritten_text must be string")
    if not isinstance(out["rationale"], str):
        raise ValueError("backend rationale must be string")
    return out


# ──────────────────────────────────────────────────────────────────────
# Prompt file loader (test-only / debug)
# ──────────────────────────────────────────────────────────────────────


def get_prompt_path() -> Path:
    return PROMPT_FILE


def load_system_prompt() -> Optional[str]:
    if not PROMPT_FILE.exists():
        return None
    try:
        return PROMPT_FILE.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("ears prompt load failed: %s", e)
        return None
