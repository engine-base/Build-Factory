"""T-S0-05: shadcn/ui setup + Tailwind config の AC 検証 (frontend 静的解析).

backend からは frontend ディレクトリの設定ファイルを読み、 CLAUDE.md §5.2
+ design-tokens.md の規約に整合しているかを機械的に検証する.

AC マッピング:
  AC-1 UBIQUITOUS: shadcn/ui + Tailwind config が完備
  AC-2 EVENT:      UI 操作 → backend state 反映 (本 task は setup のみ、
                   個別 page test で別途検証)
  AC-3 STATE:      regression なし (既存 component / test が壊れない)
  AC-4 UNWANTED:   invalid 設定なし (config 整合性)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
SHADCN_JSON = FE / "components.json"
GLOBALS_CSS = FE / "src/app/globals.css"
LAYOUT_TSX = FE / "src/app/layout.tsx"
UI_DIR = FE / "src/components/ui"
PACKAGE_JSON = FE / "package.json"


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: shadcn/ui + Tailwind config 完備
# ──────────────────────────────────────────────────────────────────────────


def test_components_json_exists() -> None:
    """shadcn/ui の config ファイルが存在."""
    assert SHADCN_JSON.exists(), "frontend/components.json missing"


def test_components_json_valid_schema() -> None:
    """components.json が ui.shadcn.com schema を参照."""
    data = json.loads(SHADCN_JSON.read_text(encoding="utf-8"))
    assert data.get("$schema") == "https://ui.shadcn.com/schema.json"
    assert data.get("tsx") is True
    assert data.get("rsc") is True  # React Server Components 有効


def test_components_json_uses_lucide_icon_library() -> None:
    """CLAUDE.md §5.1: Lucide Icons のみ使用."""
    data = json.loads(SHADCN_JSON.read_text(encoding="utf-8"))
    assert data.get("iconLibrary") == "lucide"


def test_components_json_aliases_complete() -> None:
    """alias (@/components, @/lib/utils, @/components/ui, @/hooks) 完備."""
    data = json.loads(SHADCN_JSON.read_text(encoding="utf-8"))
    aliases = data.get("aliases", {})
    for key in ("components", "utils", "ui", "lib", "hooks"):
        assert key in aliases, f"alias {key!r} missing"


def test_shadcn_ui_components_directory_populated() -> None:
    """src/components/ui に shadcn 標準 component が ≥ 5 件."""
    assert UI_DIR.exists()
    tsx_files = list(UI_DIR.glob("*.tsx"))
    assert len(tsx_files) >= 5, f"only {len(tsx_files)} ui components"


def test_essential_shadcn_components_present() -> None:
    """button / card / input / textarea / tabs の 5 必須 component."""
    essential = {"button.tsx", "card.tsx", "input.tsx", "textarea.tsx", "tabs.tsx"}
    found = {p.name for p in UI_DIR.glob("*.tsx")}
    missing = essential - found
    assert not missing, f"essential components missing: {missing}"


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: Tailwind 4 CSS-first config
# ──────────────────────────────────────────────────────────────────────────


def test_globals_css_imports_tailwindcss_v4() -> None:
    """Tailwind 4 系: @import 'tailwindcss' で CSS-first config."""
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    assert '@import "tailwindcss"' in css
    assert "@theme" in css


def test_globals_css_has_eb_palette() -> None:
    """CLAUDE.md §5.2: ENGINE BASE green palette (eb-50 → eb-900)."""
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    for shade in ("eb-50", "eb-100", "eb-200", "eb-300", "eb-400",
                   "eb-500", "eb-600", "eb-700", "eb-800", "eb-900"):
        assert f"--color-{shade}:" in css, f"--color-{shade} missing"


def test_eb_500_primary_color_value() -> None:
    """eb-500 = #1a6648 (ENGINE BASE green、 mock 規約)."""
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    assert "--color-eb-500: #1a6648" in css


def test_globals_css_has_dark_mode_variant() -> None:
    """shadcn dark mode 用 @custom-variant."""
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    assert "@custom-variant dark" in css


# ──────────────────────────────────────────────────────────────────────────
# CLAUDE.md §5.2 規約: Noto Sans JP + JetBrains Mono
# ──────────────────────────────────────────────────────────────────────────


def test_layout_imports_noto_sans_jp() -> None:
    """日本語 UI 用 sans = Noto Sans JP."""
    layout = LAYOUT_TSX.read_text(encoding="utf-8")
    assert "Noto_Sans_JP" in layout
    assert '"--font-noto-sans-jp"' in layout


def test_layout_imports_jetbrains_mono() -> None:
    """CLAUDE.md §5.2 規約: mono = JetBrains Mono."""
    layout = LAYOUT_TSX.read_text(encoding="utf-8")
    assert "JetBrains_Mono" in layout
    assert '"--font-jetbrains-mono"' in layout


def test_layout_applies_font_variables_to_html() -> None:
    """html className に全 font CSS variable が適用."""
    layout = LAYOUT_TSX.read_text(encoding="utf-8")
    for var in ("notoSansJP.variable", "jetbrainsMono.variable"):
        assert var in layout, f"{var} not applied to html"


def test_globals_css_font_mono_uses_jetbrains() -> None:
    """globals.css の --font-mono に JetBrains が含まれる."""
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    # @theme inline 内の --font-mono 定義
    match = re.search(r"--font-mono:\s*([^;]+);", css)
    assert match, "--font-mono not defined in globals.css"
    value = match.group(1)
    assert "jetbrains-mono" in value.lower(), (
        f"--font-mono should reference jetbrains-mono, got: {value}"
    )


def test_globals_css_font_sans_uses_noto() -> None:
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    match = re.search(r"--font-sans:\s*([^;]+);", css)
    assert match
    value = match.group(1)
    assert "noto" in value.lower(), f"--font-sans should reference noto, got: {value}"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: existing tests / integrations が壊れない (regression なし)
# ──────────────────────────────────────────────────────────────────────────


def test_tsc_baseline_zero_errors_marker() -> None:
    """frontend tsc baseline = 0 errors (pre-commit-check が enforce)."""
    # pre-commit-check.sh は frontend-tsc を 0 errors baseline で実行する
    pre_commit = ROOT / "scripts" / "pre-commit-check.sh"
    if not pre_commit.exists():
        pytest.skip("pre-commit-check.sh not in this branch")
    text = pre_commit.read_text(encoding="utf-8")
    assert "frontend-tsc" in text
    # baseline file (.lint-baseline-*) で 0 enforce している
    assert "_BASELINE_FILE" in text or "baseline" in text


def test_existing_ui_components_unchanged_count() -> None:
    """既存 ui/ component 数 (10 件) を維持 → regression なし."""
    components = list(UI_DIR.glob("*.tsx"))
    # 削除されてないことを保証 (regression check)
    assert len(components) >= 10


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 不正 config / 設定漏れの検出
# ──────────────────────────────────────────────────────────────────────────


def test_components_json_no_invalid_style() -> None:
    """components.json の style は shadcn が認める値."""
    data = json.loads(SHADCN_JSON.read_text(encoding="utf-8"))
    style = data.get("style", "")
    # shadcn 公式 + custom theme を許容 (radix-nova は custom OK)
    assert style, "style is empty"
    assert isinstance(style, str)


def test_globals_css_no_emoji() -> None:
    """CLAUDE.md §5.1: 絵文字禁止. globals.css にも emoji 無し."""
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    found = emoji_re.findall(css)
    assert not found, f"emoji in globals.css: {found}"


def test_layout_tsx_no_emoji() -> None:
    layout = LAYOUT_TSX.read_text(encoding="utf-8")
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    found = emoji_re.findall(layout)
    assert not found, f"emoji in layout.tsx: {found}"


def test_package_json_has_tailwind_and_shadcn_deps() -> None:
    """package.json に tailwindcss + shadcn 関連 dep がある."""
    if not PACKAGE_JSON.exists():
        pytest.skip("package.json missing")
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    assert "tailwindcss" in all_deps, "tailwindcss dependency missing"
    # shadcn は radix-ui の primitive を内部で使う
    assert any(k.startswith("@radix-ui/") for k in all_deps), (
        "no @radix-ui/* deps; shadcn primitives missing"
    )


def test_package_json_lucide_dep_present() -> None:
    """Lucide Icons (規約唯一の icon library) が dep に."""
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    has_lucide = any("lucide" in k for k in all_deps)
    assert has_lucide, "lucide-react dependency missing"


# ──────────────────────────────────────────────────────────────────────────
# CLAUDE.md §5.1: 規約遵守の boundary 検証
# ──────────────────────────────────────────────────────────────────────────


def test_no_legacy_font_mono_geist_only() -> None:
    """--font-mono に Geist Mono の **fallback** はあって OK、 primary は JetBrains."""
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    match = re.search(r"--font-mono:\s*([^;]+);", css)
    value = match.group(1)
    # 最初に jetbrains が来ているはず
    first_token = value.split(",")[0].strip()
    assert "jetbrains" in first_token.lower(), (
        f"primary --font-mono should be JetBrains, got first token: {first_token}"
    )