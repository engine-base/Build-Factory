"""T-011-01: Reviewer AI persona + Plan/Gen/Eval (REFACTOR / new wrapper).

既存 `backend/services/reviewer_loop.py` + `backend/routers/reviewer.py` は
**完全無改変** (REFACTOR invariant). 本 module は 3-phase Plan/Generate/Evaluate
を提供する thin wrapper.

## 3-Phase persona pattern (BMAD quinn)

  1. **Plan**     : 何をどの dimension で見るかを宣言.
  2. **Generate** : dimension ごとに findings を生成.
  3. **Evaluate** : 自己採点 (score / status / weakness).

各 phase は backend hook (claude-agent-sdk + Anthropic API) で差替可能.
未登録時は deterministic rule-based fallback (no DB / no LLM).

## ADR-010 整合

  - LangGraph / LangChain なし.
  - SDK auto 機能 (tool result trim / prompt cache / 9-section summary /
    Subagent / session resume) を再実装しない.
  - persona hook は (phase, payload) -> dict の callable.

## AC マッピング (T-011-01 REFACTOR)

  AC-1 UBIQUITOUS    : plan_review / generate_review / evaluate_review /
                       run_plan_gen_eval / register_persona_backend /
                       ReviewerPersonaError. 既存 reviewer.py /
                       reviewer_loop.py 無改変. REVIEW_DIMENSIONS REUSE.
  AC-2 EVENT-DRIVEN  : structured dict / 2 秒以内 (rule-based) / chain
                       Plan → Gen → Eval.
  AC-3 STATE-DRIVEN  : backend 未登録 → deterministic / no DB write /
                       REVIEW_DIMENSIONS 不変 / hook は 3 phase 外で呼ばない.
  AC-4 UNWANTED      : invalid review_kind / 空 target_artifact_ids /
                       score 範囲外 / backend 不正出力 → ReviewerPersonaError.
                       既存 API contract regress なし.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from services.reviewer_loop import REVIEW_DIMENSIONS

logger = logging.getLogger(__name__)


class ReviewerPersonaError(RuntimeError):
    """Reviewer persona の入力 / backend 不正出力 (router で 4xx に変換)."""


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

VALID_REVIEW_KINDS = ("task_review", "integration")
VALID_PHASES = ("plan", "generate", "evaluate")
DEFAULT_PASS_THRESHOLD = 0.70  # eval score >= → pass

MAX_ARTIFACT_IDS = 200
MAX_ACTOR_USER_ID_LEN = 200

PERSONA_NAME = "reviewer"  # BMAD quinn


# ──────────────────────────────────────────────────────────────────────
# Backend hook (G53 SDK 差替点)
# ──────────────────────────────────────────────────────────────────────

PersonaBackend = Callable[[str, dict], dict]
"""(phase, payload) -> dict.

phase: 'plan' | 'generate' | 'evaluate'
payload: phase 固有 input (plan = {review_kind, artifact_ids}, etc).
"""

_BACKEND: Optional[PersonaBackend] = None


def register_persona_backend(backend: Optional[PersonaBackend]) -> None:
    """SDK / AI backend register. None で clear.

    backend は (phase, payload) -> dict の callable. 例外 / 不正出力時は
    rule-based fallback (silent failure 防止 warning).
    """
    global _BACKEND
    if backend is not None and not callable(backend):
        raise ReviewerPersonaError("backend must be callable or None")
    _BACKEND = backend


def get_persona_backend() -> Optional[PersonaBackend]:
    return _BACKEND


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_review_kind(review_kind: Any) -> str:
    if not isinstance(review_kind, str) or review_kind not in VALID_REVIEW_KINDS:
        raise ReviewerPersonaError(
            f"review_kind must be one of {VALID_REVIEW_KINDS}, got {review_kind!r}"
        )
    return review_kind


def _validate_artifact_ids(artifact_ids: Any) -> list[str]:
    if not isinstance(artifact_ids, list):
        raise ReviewerPersonaError("target_artifact_ids must be a list")
    if not artifact_ids:
        raise ReviewerPersonaError("target_artifact_ids must not be empty")
    if len(artifact_ids) > MAX_ARTIFACT_IDS:
        raise ReviewerPersonaError(
            f"target_artifact_ids must be <= {MAX_ARTIFACT_IDS} entries"
        )
    cleaned: list[str] = []
    for i, a in enumerate(artifact_ids):
        if not isinstance(a, str) or not a.strip():
            raise ReviewerPersonaError(
                f"target_artifact_ids[{i}] must be non-empty string"
            )
        cleaned.append(a.strip())
    return cleaned


def _validate_score(score: Any) -> float:
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ReviewerPersonaError("score must be float in [0.0, 1.0]")
    f = float(score)
    if f < 0.0 or f > 1.0:
        raise ReviewerPersonaError(f"score must be in [0.0, 1.0], got {f}")
    return f


def _validate_actor_user_id(actor_user_id: Optional[str]) -> Optional[str]:
    if actor_user_id is None:
        return None
    if not isinstance(actor_user_id, str):
        raise ReviewerPersonaError("actor_user_id must be string or null")
    stripped = actor_user_id.strip()
    if not stripped:
        raise ReviewerPersonaError("actor_user_id must not be empty when provided")
    if len(stripped) > MAX_ACTOR_USER_ID_LEN:
        raise ReviewerPersonaError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return stripped


# ──────────────────────────────────────────────────────────────────────
# Backend invocation with graceful fallback
# ──────────────────────────────────────────────────────────────────────


def _call_backend(phase: str, payload: dict) -> Optional[dict]:
    """backend hook を試す. 失敗 / 不正出力時 None で fallback indicate."""
    if phase not in VALID_PHASES:
        raise ReviewerPersonaError(
            f"phase must be one of {VALID_PHASES}, got {phase!r}"
        )
    if _BACKEND is None:
        return None
    try:
        out = _BACKEND(phase, payload)
    except Exception as e:
        logger.warning(
            "reviewer persona backend failed phase=%s: %s", phase, e,
        )
        return None
    if not isinstance(out, dict):
        logger.warning(
            "reviewer persona backend returned non-dict phase=%s (got %s)",
            phase, type(out).__name__,
        )
        return None
    return out


# ──────────────────────────────────────────────────────────────────────
# Phase 1: Plan
# ──────────────────────────────────────────────────────────────────────


def plan_review(
    review_kind: str,
    target_artifact_ids: list[str],
    *,
    use_backend: bool = True,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Phase 1: 何をどの dimension で見るかの plan."""
    kind = _validate_review_kind(review_kind)
    ids = _validate_artifact_ids(target_artifact_ids)
    _validate_actor_user_id(actor_user_id)

    t0 = time.time()
    backend_used = False
    plan_body: Optional[dict] = None
    if use_backend:
        raw = _call_backend("plan", {"review_kind": kind, "artifact_ids": ids})
        if raw and isinstance(raw.get("dimensions"), list):
            plan_body = {
                "dimensions": [str(d) for d in raw["dimensions"]],
                "rationale": str(raw.get("rationale", "")),
            }
            backend_used = True

    if plan_body is None:
        # rule-based: use REVIEW_DIMENSIONS verbatim
        plan_body = {
            "dimensions": list(REVIEW_DIMENSIONS[kind]),
            "rationale": (
                f"rule-based plan: cover all {len(REVIEW_DIMENSIONS[kind])} "
                f"dimensions for {kind} review of {len(ids)} artifact(s)."
            ),
        }

    return {
        "persona": PERSONA_NAME,
        "phase": "plan",
        "review_kind": kind,
        "target_artifact_ids": ids,
        "dimensions": plan_body["dimensions"],
        "rationale": plan_body["rationale"],
        "backend_used": backend_used,
        "latency_ms": int((time.time() - t0) * 1000),
    }


# ──────────────────────────────────────────────────────────────────────
# Phase 2: Generate
# ──────────────────────────────────────────────────────────────────────


def generate_review(
    plan: dict,
    *,
    use_backend: bool = True,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Phase 2: plan に基づいて dimension ごとに findings を生成."""
    if not isinstance(plan, dict):
        raise ReviewerPersonaError("plan must be dict")
    dims = plan.get("dimensions")
    if not isinstance(dims, list) or not dims:
        raise ReviewerPersonaError("plan.dimensions must be non-empty list")
    kind = plan.get("review_kind")
    _validate_review_kind(kind)
    ids = plan.get("target_artifact_ids", [])
    _validate_artifact_ids(ids)
    _validate_actor_user_id(actor_user_id)

    t0 = time.time()
    backend_used = False
    findings: Optional[list[dict]] = None

    if use_backend:
        raw = _call_backend("generate", {"plan": plan})
        if raw and isinstance(raw.get("findings"), list):
            cand: list[dict] = []
            for f in raw["findings"]:
                if not isinstance(f, dict):
                    cand = []
                    break
                dim = f.get("dimension")
                note = f.get("note")
                severity = f.get("severity", "info")
                if not isinstance(dim, str) or not isinstance(note, str):
                    cand = []
                    break
                if severity not in ("info", "warn", "error"):
                    severity = "info"
                cand.append({"dimension": dim, "note": note, "severity": severity})
            if cand:
                findings = cand
                backend_used = True

    if findings is None:
        # rule-based: dimension ごとに placeholder finding
        findings = [
            {
                "dimension": d,
                "note": (
                    f"rule-based review note for '{d}': check that all "
                    f"{len(ids)} target artifact(s) satisfy this dimension."
                ),
                "severity": "info",
            }
            for d in dims
        ]

    return {
        "persona": PERSONA_NAME,
        "phase": "generate",
        "review_kind": kind,
        "findings": findings,
        "backend_used": backend_used,
        "latency_ms": int((time.time() - t0) * 1000),
    }


# ──────────────────────────────────────────────────────────────────────
# Phase 3: Evaluate
# ──────────────────────────────────────────────────────────────────────


def evaluate_review(
    review: dict,
    *,
    use_backend: bool = True,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Phase 3: review の自己採点 + 弱点抽出."""
    if not isinstance(review, dict):
        raise ReviewerPersonaError("review must be dict")
    findings = review.get("findings")
    if not isinstance(findings, list):
        raise ReviewerPersonaError("review.findings must be a list")
    _validate_score(pass_threshold)
    _validate_actor_user_id(actor_user_id)

    t0 = time.time()
    backend_used = False
    score: Optional[float] = None
    weakness: Optional[list[str]] = None

    if use_backend:
        raw = _call_backend("evaluate", {"review": review})
        if raw and "score" in raw:
            try:
                score = _validate_score(raw["score"])
                w = raw.get("weakness", [])
                if isinstance(w, list):
                    weakness = [str(x) for x in w]
                    backend_used = True
            except ReviewerPersonaError:
                # backend gave malformed score → fallback
                score = None
                weakness = None
                backend_used = False

    if score is None:
        # rule-based: severity 比率からスコアを計算
        n = len(findings)
        if n == 0:
            score = 0.0
        else:
            ok_count = sum(
                1 for f in findings
                if isinstance(f, dict) and f.get("severity") in ("info", None)
            )
            score = ok_count / n
        weakness = []
        for f in findings:
            if isinstance(f, dict) and f.get("severity") == "error":
                weakness.append(f"error severity: {f.get('dimension', '?')}")

    status = "pass" if score >= pass_threshold else "needs_revision"
    return {
        "persona": PERSONA_NAME,
        "phase": "evaluate",
        "score": score,
        "status": status,
        "pass_threshold": pass_threshold,
        "weakness": weakness or [],
        "backend_used": backend_used,
        "latency_ms": int((time.time() - t0) * 1000),
    }


# ──────────────────────────────────────────────────────────────────────
# Full chain
# ──────────────────────────────────────────────────────────────────────


def run_plan_gen_eval(
    review_kind: str,
    target_artifact_ids: list[str],
    *,
    use_backend: bool = True,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Plan → Generate → Evaluate を chain して全結果を返す."""
    plan = plan_review(
        review_kind,
        target_artifact_ids,
        use_backend=use_backend,
        actor_user_id=actor_user_id,
    )
    review = generate_review(
        plan,
        use_backend=use_backend,
        actor_user_id=actor_user_id,
    )
    evaluation = evaluate_review(
        review,
        use_backend=use_backend,
        pass_threshold=pass_threshold,
        actor_user_id=actor_user_id,
    )
    return {
        "persona": PERSONA_NAME,
        "plan": plan,
        "review": review,
        "evaluation": evaluation,
        "status": evaluation["status"],
        "backend_used": (
            plan["backend_used"]
            or review["backend_used"]
            or evaluation["backend_used"]
        ),
    }


def list_review_kinds() -> list[str]:
    return list(VALID_REVIEW_KINDS)
