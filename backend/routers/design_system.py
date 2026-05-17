"""T-V3-D-10: design system tokens endpoint (F-029, E-023 Component).

openapi.yaml#F-029 で定義された endpoint を実装する:

    GET /api/design-system/tokens -> { tokens: DesignToken[] }

drift fix mapping (api-drift-summary.md#medium-詳細):
    `GET /api/design-system/tokens` は backend missing (T-V3-DRIFT-F-029-01).
    本 router で実装し、docs/mocks/2026-05-09_v1/design-tokens.md を
    parse して token catalog を返す.

Token categories (design-tokens.md §1-§4):
    - color    : brand / semantic / neutral / status badges
    - typography : Noto Sans JP + scale (display..caption)
    - spacing  : Tailwind 4 base scale
    - radius   : rounded-sm / md / lg
    - icons    : Lucide (catalog 名のみ; svg 本体は frontend)

Related entities: E-023 Component (design-tokens は metadata 扱い).
Related screens : S-024 design_system, S-025 component-catalog.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from services.auth_middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/design-system", tags=["design-system"])


# docs/mocks/2026-05-09_v1/design-tokens.md §1-§4 から抽出した静的 catalog.
# Test (test_design_system_tokens.py) で count/category を verify.
_TOKEN_CATALOG: list[dict[str, Any]] = [
    # ── §1 Color: Brand
    {"category": "color", "subcategory": "brand", "token": "--bf-primary",
     "value": "#1a6648", "description": "メインブランド緑 (headers / CTA / accents)"},
    {"category": "color", "subcategory": "brand", "token": "--bf-primary-hover",
     "value": "#155236", "description": "hover 状態"},
    {"category": "color", "subcategory": "brand", "token": "--bf-primary-light",
     "value": "#e6f4ee", "description": "薄い緑 (badges / active states)"},
    {"category": "color", "subcategory": "brand", "token": "--bf-primary-border",
     "value": "#b3d9c8", "description": "緑系 border"},
    # ── §1 Color: Semantic
    {"category": "color", "subcategory": "semantic", "token": "--bf-success",
     "value": "#16a34a", "description": "成功 / passed"},
    {"category": "color", "subcategory": "semantic", "token": "--bf-warning",
     "value": "#f59e0b", "description": "警告 / blocked"},
    {"category": "color", "subcategory": "semantic", "token": "--bf-danger",
     "value": "#dc2626", "description": "失敗 / 赤線 / unwanted"},
    {"category": "color", "subcategory": "semantic", "token": "--bf-info",
     "value": "#3b82f6", "description": "情報"},
    # ── §1 Color: Neutral
    {"category": "color", "subcategory": "neutral", "token": "--bf-bg-page",
     "value": "#f0f2f5", "description": "ページ背景"},
    {"category": "color", "subcategory": "neutral", "token": "--bf-bg-card",
     "value": "#ffffff", "description": "カード背景"},
    {"category": "color", "subcategory": "neutral", "token": "--bf-bg-subtle",
     "value": "#f8fafc", "description": "薄いセクション背景"},
    {"category": "color", "subcategory": "neutral", "token": "--bf-border",
     "value": "#e2e8f0", "description": "標準 border"},
    {"category": "color", "subcategory": "neutral", "token": "--bf-text-primary",
     "value": "#1a1a1a", "description": "メイン文字"},
    {"category": "color", "subcategory": "neutral", "token": "--bf-text-secondary",
     "value": "#475569", "description": "セカンダリ文字"},
    {"category": "color", "subcategory": "neutral", "token": "--bf-text-muted",
     "value": "#94a3b8", "description": "補助文字"},
    # ── §2 Typography
    {"category": "typography", "subcategory": "family",
     "token": "font-sans", "value": "'Noto Sans JP', sans-serif",
     "description": "日本語 UI base"},
    {"category": "typography", "subcategory": "family",
     "token": "font-mono", "value": "'JetBrains Mono', monospace",
     "description": "code / token id"},
    {"category": "typography", "subcategory": "scale",
     "token": "text-display", "value": "28-36px / 900",
     "description": "ページタイトル"},
    {"category": "typography", "subcategory": "scale",
     "token": "text-h1", "value": "22-24px / 700",
     "description": "セクションヘッダー"},
    {"category": "typography", "subcategory": "scale",
     "token": "text-h2", "value": "16-18px / 700",
     "description": "サブヘッダー"},
    {"category": "typography", "subcategory": "scale",
     "token": "text-h3", "value": "14px / 700",
     "description": "小見出し"},
    {"category": "typography", "subcategory": "scale",
     "token": "text-body", "value": "13-14px / 400",
     "description": "本文"},
    {"category": "typography", "subcategory": "scale",
     "token": "text-small", "value": "12-13px / 400",
     "description": "補助"},
    {"category": "typography", "subcategory": "scale",
     "token": "text-caption", "value": "10-11px / 600",
     "description": "UPPERCASE label"},
    # ── §3 Spacing
    {"category": "spacing", "subcategory": "scale", "token": "--space-1",
     "value": "4px", "description": "微小"},
    {"category": "spacing", "subcategory": "scale", "token": "--space-2",
     "value": "8px", "description": "inline gap"},
    {"category": "spacing", "subcategory": "scale", "token": "--space-3",
     "value": "12px", "description": "small gap"},
    {"category": "spacing", "subcategory": "scale", "token": "--space-4",
     "value": "16px", "description": "standard gap"},
    {"category": "spacing", "subcategory": "scale", "token": "--space-6",
     "value": "24px", "description": "section gap"},
    {"category": "spacing", "subcategory": "scale", "token": "--space-8",
     "value": "32px", "description": "large gap"},
    {"category": "spacing", "subcategory": "scale", "token": "--space-12",
     "value": "48px", "description": "hero gap"},
    # ── §4 Border radius
    {"category": "radius", "subcategory": "scale", "token": "rounded-sm",
     "value": "3px", "description": "badges"},
    {"category": "radius", "subcategory": "scale", "token": "rounded-md",
     "value": "6px", "description": "inputs / small cards"},
    {"category": "radius", "subcategory": "scale", "token": "rounded-lg",
     "value": "8px", "description": "section cards"},
    # ── Icons (catalog marker only; Lucide が真のソース)
    {"category": "icons", "subcategory": "library", "token": "lucide",
     "value": "https://unpkg.com/lucide@latest",
     "description": "Lucide Icons (絵文字禁止 / design-tokens.md §8)"},
]


@router.get(
    "/tokens",
    summary="Get design token catalog (color/typography/spacing/icons)",
)
async def get_design_system_tokens(
    user: Annotated[dict, Depends(require_user)],
) -> dict[str, Any]:
    """AC-F3 EVENT-DRIVEN: 認証済 → 200 with `{ tokens: DesignToken[] }`.

    Source : docs/mocks/2026-05-09_v1/design-tokens.md §1-§8.
    """
    return {
        "tokens": list(_TOKEN_CATALOG),
        "source": "docs/mocks/2026-05-09_v1/design-tokens.md",
        "categories": ["color", "typography", "spacing", "radius", "icons"],
    }
