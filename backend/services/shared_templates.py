"""T-015-01: 共通テンプレ (existing artifact_export REFACTOR / template registry + metadata).

既存 `backend/services/artifact_export.py` (export_to_excel / pptx / pdf /
export_artifact) は **完全無改変** (REUSE). 本 module は:
  1. 利用可能 template の registry を提供 (list_templates / get_template_info)
  2. format × template 組合せの validation
  3. 既存 export_artifact への thin delegation

## 既存 artifact_export.py (T-015-01 deps T-S0-05 で merged)

  - export_to_excel(artifact, template="minimal")
  - export_to_pptx(artifact, template="minimal")
  - export_to_pdf(artifact, template="minimal")
  - export_artifact(artifact, format, template="minimal") ← orchestrator

template 種類は docstring に「minimal / corporate / branded」とあるが、
現状 minimal のみ実装. 本 module で **registry を明示化** し、将来追加時の
validation 基盤を構築.

## AC マッピング (T-015-01 REFACTOR)

  AC-1 UBIQUITOUS    : list_templates / get_template_info / validate_format_template /
                       render_with_template を公開. 既存 artifact_export 無改変.
  AC-2 EVENT-DRIVEN  : list / get は 100ms 以内. render は delegate.
  AC-3 STATE-DRIVEN  : read-only registry / 既存 artifact_export API 不変.
  AC-4 UNWANTED      : invalid format / invalid template で ValueError.
                       hardcoded secret / 外部 URL なし.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Template registry (T-015-01 で明示化)
# ──────────────────────────────────────────────────────────────────────

VALID_FORMATS = ("excel", "pptx", "pdf", "md", "html")

# 各 template の metadata
TEMPLATE_REGISTRY: dict[str, dict[str, Any]] = {
    "minimal": {
        "name": "minimal",
        "display_name": "Minimal",
        "description": "シンプルなレイアウト. ロゴ・色なし.",
        "supported_formats": ("excel", "pptx", "pdf", "md", "html"),
        "tier": "basic",
        "available": True,
    },
    "corporate": {
        "name": "corporate",
        "display_name": "Corporate",
        "description": "企業向け. ロゴ + ヘッダー/フッター付き.",
        "supported_formats": ("excel", "pptx", "pdf"),
        "tier": "standard",
        "available": False,  # 将来実装
    },
    "branded": {
        "name": "branded",
        "display_name": "Branded (ENGINE BASE)",
        "description": "ENGINE BASE ブランド (eb-500 #1a6648). 提案書 / 見積書向け.",
        "supported_formats": ("pdf", "html"),
        "tier": "premium",
        "available": False,  # 将来実装
    },
}


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_format(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("format must be string")
    s = value.strip().lower()
    if s not in VALID_FORMATS:
        raise ValueError(
            f"format must be one of {VALID_FORMATS}, got {value!r}"
        )
    return s


def _validate_template_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("template name must be string")
    s = value.strip().lower()
    if not s:
        raise ValueError("template name must not be empty")
    if s not in TEMPLATE_REGISTRY:
        raise ValueError(
            f"template must be one of {tuple(TEMPLATE_REGISTRY.keys())}, "
            f"got {value!r}"
        )
    return s


def _validate_artifact(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("artifact must be a dict")
    if not value:
        raise ValueError("artifact must not be empty")
    return value


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def list_templates(*, only_available: bool = False) -> list[dict]:
    """利用可能 template の registry を返す.

    Args:
        only_available: True で available=True のみ.
    """
    if not isinstance(only_available, bool):
        raise ValueError("only_available must be bool")
    items = []
    for name, info in TEMPLATE_REGISTRY.items():
        if only_available and not info.get("available"):
            continue
        items.append({
            "name": name,
            "display_name": info["display_name"],
            "description": info["description"],
            "supported_formats": list(info["supported_formats"]),
            "tier": info["tier"],
            "available": info["available"],
        })
    return items


def get_template_info(template_name: str) -> dict:
    """単一 template の metadata. 不正 name で ValueError."""
    name = _validate_template_name(template_name)
    info = TEMPLATE_REGISTRY[name]
    return {
        "name": name,
        "display_name": info["display_name"],
        "description": info["description"],
        "supported_formats": list(info["supported_formats"]),
        "tier": info["tier"],
        "available": info["available"],
    }


def validate_format_template(format: str, template_name: str) -> dict:
    """format × template の組合せ validation.

    Returns:
      {"valid": True} or raises ValueError with reason.
    """
    fmt = _validate_format(format)
    name = _validate_template_name(template_name)
    info = TEMPLATE_REGISTRY[name]
    if fmt not in info["supported_formats"]:
        raise ValueError(
            f"template '{name}' does not support format '{fmt}'. "
            f"Supported: {info['supported_formats']}"
        )
    if not info["available"]:
        raise ValueError(
            f"template '{name}' is not yet available (tier={info['tier']})"
        )
    return {"valid": True, "format": fmt, "template": name}


def render_with_template(
    artifact: dict,
    format: str,
    *,
    template_name: str = "minimal",
) -> Path:
    """artifact を template で render. 既存 export_artifact に delegate."""
    art = _validate_artifact(artifact)
    fmt = _validate_format(format)
    name = _validate_template_name(template_name)

    # validation (available + format support)
    validate_format_template(fmt, name)

    # delegate to existing artifact_export
    from services import artifact_export as ae
    return ae.export_artifact(art, fmt, template=name)


def get_default_template() -> str:
    """default template (minimal)."""
    return "minimal"


def is_format_supported_by_any(format: str) -> bool:
    """指定 format をサポートする template が 1 つでもあるか."""
    fmt = _validate_format(format)
    return any(
        fmt in info["supported_formats"] and info["available"]
        for info in TEMPLATE_REGISTRY.values()
    )
