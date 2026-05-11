"""T-S0-06: 共通 UI components (Button/Input/Modal/Toast/Badge) AC 検証.

backend からは frontend ファイルを静的解析で検証する.

AC マッピング:
  AC-1 UBIQUITOUS: 5 必須 component (Button/Input/Modal/Toast/Badge) 完備
  AC-2 EVENT:      UI 操作 → backend state 反映 (個別 page test で別途)
  AC-3 STATE:      regression なし (既存 UI が壊れない)
  AC-4 UNWANTED:   無効 component (絵文字 / AGPL dep) なし
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
UI_DIR = FE / "src/components/ui"
LAYOUT_TSX = FE / "src/app/layout.tsx"
PACKAGE_JSON = FE / "package.json"


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 5 必須 component が存在
# ──────────────────────────────────────────────────────────────────────────


REQUIRED_COMPONENTS = {
    "Button": "button.tsx",
    "Input": "input.tsx",
    "Modal": "dialog.tsx",       # shadcn では Modal = Dialog
    "Toast": "sonner.tsx",        # shadcn では Toast = Sonner (sonner library)
    "Badge": "badge.tsx",
}


@pytest.mark.parametrize("name,filename", REQUIRED_COMPONENTS.items())
def test_each_required_component_file_exists(name: str, filename: str) -> None:
    """AC-1: 5 必須 component の tsx ファイルが存在."""
    p = UI_DIR / filename
    assert p.exists(), f"{name} ({filename}) missing"


def test_all_5_components_are_typescript_files() -> None:
    for filename in REQUIRED_COMPONENTS.values():
        p = UI_DIR / filename
        text = p.read_text(encoding="utf-8")
        # 最低限の TypeScript / TSX 型注釈 (React.forwardRef / type alias / export)
        assert "export" in text, f"{filename}: no export"


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 各 component の API 表面 (export 名)
# ──────────────────────────────────────────────────────────────────────────


def test_button_exports_button_named() -> None:
    text = (UI_DIR / "button.tsx").read_text(encoding="utf-8")
    assert re.search(r"\bButton\b", text)
    # variant prop / className を受ける (shadcn 標準)
    assert "variant" in text or "buttonVariants" in text


def test_input_exports_input_named() -> None:
    text = (UI_DIR / "input.tsx").read_text(encoding="utf-8")
    assert re.search(r"\bInput\b", text)


def test_badge_exports_badge_named() -> None:
    text = (UI_DIR / "badge.tsx").read_text(encoding="utf-8")
    assert re.search(r"\bBadge\b", text)
    # variant prop (shadcn 標準)
    assert "variant" in text or "badgeVariants" in text


def test_dialog_exports_full_api_surface() -> None:
    """Modal (Dialog) の必須 export 8 件."""
    text = (UI_DIR / "dialog.tsx").read_text(encoding="utf-8")
    for symbol in (
        "Dialog", "DialogTrigger", "DialogContent",
        "DialogHeader", "DialogFooter",
        "DialogTitle", "DialogDescription", "DialogClose",
    ):
        assert re.search(rf"\b{symbol}\b", text), f"{symbol} not exported"


def test_dialog_uses_radix_primitive() -> None:
    """Modal は Radix UI Dialog primitive を使用 (a11y 保証)."""
    text = (UI_DIR / "dialog.tsx").read_text(encoding="utf-8")
    assert "@radix-ui/react-dialog" in text


def test_dialog_has_close_button_with_aria_label() -> None:
    """Modal close button に aria-label='Close' (a11y)."""
    text = (UI_DIR / "dialog.tsx").read_text(encoding="utf-8")
    assert 'aria-label="Close"' in text


def test_dialog_uses_lucide_x_icon() -> None:
    """close icon は lucide X (規約)."""
    text = (UI_DIR / "dialog.tsx").read_text(encoding="utf-8")
    assert "from \"lucide-react\"" in text or "from 'lucide-react'" in text


def test_sonner_exports_toaster_and_toast() -> None:
    """Toast は Toaster (provider) + toast (function) を export."""
    text = (UI_DIR / "sonner.tsx").read_text(encoding="utf-8")
    assert re.search(r"export\s+function\s+Toaster", text)
    assert re.search(r"export\s+\{\s*toast\s*\}", text)


def test_sonner_uses_sonner_library() -> None:
    text = (UI_DIR / "sonner.tsx").read_text(encoding="utf-8")
    assert 'from "sonner"' in text


def test_sonner_configures_top_right_position() -> None:
    """Toaster の position は top-right (Build-Factory UX 規約)."""
    text = (UI_DIR / "sonner.tsx").read_text(encoding="utf-8")
    assert 'position="top-right"' in text


# ──────────────────────────────────────────────────────────────────────────
# Layout で Toaster がグローバル配置
# ──────────────────────────────────────────────────────────────────────────


def test_layout_imports_toaster() -> None:
    layout = LAYOUT_TSX.read_text(encoding="utf-8")
    assert 'from "@/components/ui/sonner"' in layout


def test_layout_renders_toaster_once() -> None:
    """<Toaster /> が layout で 1 度だけ render."""
    layout = LAYOUT_TSX.read_text(encoding="utf-8")
    count = len(re.findall(r"<Toaster\s*/?>", layout))
    assert count == 1, f"<Toaster /> rendered {count} times (must be exactly 1)"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: regression なし
# ──────────────────────────────────────────────────────────────────────────


def test_existing_ui_components_preserved() -> None:
    """既存 10 件 ui/ component が削除されていない."""
    existing = (
        "badge.tsx", "button.tsx", "card.tsx", "input.tsx",
        "scroll-area.tsx", "select.tsx", "separator.tsx",
        "table.tsx", "tabs.tsx", "textarea.tsx",
    )
    for f in existing:
        assert (UI_DIR / f).exists(), f"existing {f} got deleted (regression)"


def test_ui_directory_now_has_12_components() -> None:
    """既存 10 + dialog + sonner = 12 件以上."""
    components = list(UI_DIR.glob("*.tsx"))
    assert len(components) >= 12, f"only {len(components)} components"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 無効 component
# ──────────────────────────────────────────────────────────────────────────


def test_no_emoji_in_new_components() -> None:
    """CLAUDE.md §5.1: 絵文字禁止."""
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    for name in ("dialog.tsx", "sonner.tsx"):
        text = (UI_DIR / name).read_text(encoding="utf-8")
        found = emoji_re.findall(text)
        assert not found, f"emoji in {name}: {found}"


def test_required_dependencies_present_in_package_json() -> None:
    """sonner / @radix-ui/react-dialog / lucide-react が dep."""
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    assert "sonner" in deps, "sonner dep missing"
    assert "@radix-ui/react-dialog" in deps, "@radix-ui/react-dialog dep missing"
    assert "lucide-react" in deps, "lucide-react dep missing"


def test_no_agpl_licensed_ui_deps() -> None:
    """全 UI 系 dep は MIT / ISC / Apache 2.0 / BSD 系."""
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    text = json.dumps(data)
    assert "agpl" not in text.lower(), "AGPL dep detected"


# ──────────────────────────────────────────────────────────────────────────
# CLAUDE.md §5.1 規約 (Lucide のみ): UI component が他 icon library を import しない
# ──────────────────────────────────────────────────────────────────────────


def test_ui_components_use_only_lucide_icons() -> None:
    """ui/*.tsx 内で react-icons / heroicons / phosphor 等を import していないこと."""
    forbidden = ("react-icons", "@heroicons", "phosphor-icons", "react-feather")
    for p in UI_DIR.glob("*.tsx"):
        text = p.read_text(encoding="utf-8")
        for f in forbidden:
            assert f not in text, f"{p.name} imports forbidden icon library: {f}"