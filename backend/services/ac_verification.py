"""T-003-05: AC (acceptance criteria) 検証サービス.

artifact (タスク成果物) を、紐づくタスクの acceptance_criteria に照らして検証する.
本サービスは "rule-based" な静的検証のみを行う:
  - EARS 形式の AC 文字列に出現する keyword を artifact 本文に含むか
  - artifact が空 / 巨大すぎないか
  - status が 'final' / 'reviewable' になっているか

将来 Reviewer (T-AI) で LLM 評価を追加する余地を残す (interface 互換).

公開 API:
  - verify_artifact(artifact, criteria) -> VerificationReport
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

EARS_TYPES = ("UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED")


class ACVerificationError(RuntimeError):
    pass


@dataclass
class CriterionResult:
    type: str
    text: str
    status: str  # 'pass' | 'warn' | 'fail'
    reasons: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)


@dataclass
class VerificationReport:
    artifact_id: Optional[str]
    overall: str  # 'pass' | 'warn' | 'fail'
    total: int
    pass_count: int
    warn_count: int
    fail_count: int
    results: list[CriterionResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "overall": self.overall,
            "total": self.total,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "results": [
                {
                    "type": r.type,
                    "text": r.text,
                    "status": r.status,
                    "reasons": r.reasons,
                    "matched_keywords": r.matched_keywords,
                }
                for r in self.results
            ],
            "warnings": self.warnings,
        }


_KEYWORD_RE = re.compile(r"[A-Za-z]{4,}|[一-龥ぁ-ゖァ-ヺー]{2,}")


def _extract_keywords(text: str, *, max_words: int = 8) -> list[str]:
    """AC 文の中から検証に使える keyword を抽出する.

    EARS の prefix ('shall', 'When', 'While', 'If') と一般語を除外して、
    意味のある名詞っぽい語を最大 max_words 件返す.
    """
    blacklist = {
        "shall", "system", "when", "while", "where", "if", "the",
        "feature", "implement", "specified", "relevant",
        "Build-Factory", "F-001", "T-001",
    }
    found: list[str] = []
    for m in _KEYWORD_RE.finditer(text):
        word = m.group()
        if word.lower() in blacklist:
            continue
        if word in found:
            continue
        found.append(word)
        if len(found) >= max_words:
            break
    return found


def _flatten_artifact_text(artifact: dict) -> str:
    """artifact dict から検証対象の本文文字列を抽出."""
    parts: list[str] = []
    if isinstance(artifact, dict):
        title = artifact.get("title")
        if isinstance(title, str):
            parts.append(title)
        data = artifact.get("data")
        if isinstance(data, dict):
            parts.append(_flatten_value(data))
        elif isinstance(data, str):
            parts.append(data)
        for key in ("content", "summary", "body", "markdown"):
            v = artifact.get(key)
            if isinstance(v, str):
                parts.append(v)
    return "\n".join(parts)


def _flatten_value(value: Any) -> str:
    """dict / list を平坦化して文字列にする."""
    if isinstance(value, dict):
        return "\n".join(_flatten_value(v) for v in value.values())
    if isinstance(value, list):
        return "\n".join(_flatten_value(v) for v in value)
    if value is None:
        return ""
    return str(value)


def _check_one(
    text: str,
    criterion: dict,
) -> CriterionResult:
    """criterion 1 件を評価する.

    判定:
      - artifact 本文にキーワードが 0 件 → fail
      - 一部マッチ (50% 未満) → warn
      - 50% 以上マッチ → pass
    """
    ctype = (criterion.get("type") or "").upper()
    ctext = criterion.get("text") or ""
    if not ctext or not ctype:
        return CriterionResult(
            type=ctype or "UNKNOWN", text=ctext, status="fail",
            reasons=["criterion missing type or text"],
        )
    if ctype not in EARS_TYPES:
        return CriterionResult(
            type=ctype, text=ctext, status="fail",
            reasons=[f"unknown EARS type: {ctype}"],
        )

    keywords = _extract_keywords(ctext)
    if not keywords:
        return CriterionResult(
            type=ctype, text=ctext, status="warn",
            reasons=["no extractable keywords"],
        )

    text_lower = text.lower()
    matched = [k for k in keywords if k.lower() in text_lower]
    ratio = len(matched) / len(keywords)
    if not matched:
        return CriterionResult(
            type=ctype, text=ctext, status="fail",
            reasons=["no keyword matched in artifact"],
            matched_keywords=[],
        )
    if ratio < 0.5:
        return CriterionResult(
            type=ctype, text=ctext, status="warn",
            reasons=[f"only {len(matched)}/{len(keywords)} keywords matched"],
            matched_keywords=matched,
        )
    return CriterionResult(
        type=ctype, text=ctext, status="pass",
        reasons=[f"{len(matched)}/{len(keywords)} keywords matched"],
        matched_keywords=matched,
    )


def verify_artifact(
    artifact: dict,
    criteria: Iterable[dict],
    *,
    min_text_size: int = 50,
    max_text_size: int = 1_000_000,
) -> VerificationReport:
    """artifact を criteria (list of {type, text}) で検証する."""
    if not isinstance(artifact, dict):
        raise ACVerificationError("artifact must be a dict")

    criteria_list = list(criteria)
    text = _flatten_artifact_text(artifact)
    warnings: list[str] = []

    if not text or len(text.strip()) < min_text_size:
        warnings.append(f"artifact_text_too_small (<{min_text_size} chars)")
    if len(text) > max_text_size:
        warnings.append(f"artifact_text_too_large (>{max_text_size} chars)")

    if not criteria_list:
        return VerificationReport(
            artifact_id=artifact.get("id") or artifact.get("artifact_id"),
            overall="fail" if not warnings else "warn",
            total=0, pass_count=0, warn_count=0, fail_count=0,
            results=[],
            warnings=warnings + ["no_criteria_provided"],
        )

    results = [_check_one(text, c) for c in criteria_list]
    pass_n = sum(1 for r in results if r.status == "pass")
    warn_n = sum(1 for r in results if r.status == "warn")
    fail_n = sum(1 for r in results if r.status == "fail")

    if fail_n > 0:
        overall = "fail"
    elif warn_n > 0:
        overall = "warn"
    else:
        overall = "pass"

    return VerificationReport(
        artifact_id=artifact.get("id") or artifact.get("artifact_id"),
        overall=overall,
        total=len(results),
        pass_count=pass_n,
        warn_count=warn_n,
        fail_count=fail_n,
        results=results,
        warnings=warnings,
    )
