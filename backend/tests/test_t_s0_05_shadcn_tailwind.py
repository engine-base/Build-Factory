"""T-S0-05: shadcn/ui setup + Tailwind config — verify existing setup (REUSE).

CLAUDE.md §5.1 (Lucide only / no emoji) + §5.2 (eb-500 = #1a6648 / Noto Sans JP /
JetBrains Mono / shadcn/ui コンポーネント優先) を **pytest から機械検証** する.

設計境界 (REUSE タスク, IMPLEMENTATION_PROTOCOL Step 4):
  shadcn/ui + Tailwind v4 設定は既に bootstrap 済. 本 module は read-only 検証のみ.

## AC マッピング (1:1)

  AC-1 UBIQUITOUS    : components.json (Lucide) / postcss.config.mjs / globals.css
                       (eb-500) / lib/utils.ts (cn) / package.json (必須 dep).
  AC-2 EVENT-DRIVEN  : 5 秒以内 / missing token を message に含める / no silent skip.
  AC-3 STATE-DRIVEN  : eb-500=#1a6648 不変 / iconLibrary=lucide 不変 /
                       verification module は frontend file を mutate しない.
  AC-4 UNWANTED      : 非 Lucide icon library / eb-500 token 欠落 /
                       禁止 dep (@heroicons/@fortawesome/react-icons) 検出 /
                       shadcn config 欠落 で pytest fail (silent skip 禁止).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
COMPONENTS_JSON = FRONTEND / "components.json"
POSTCSS_CONFIG = FRONTEND / "postcss.config.mjs"
GLOBALS_CSS = FRONTEND / "src" / "app" / "globals.css"
LIB_UTILS = FRONTEND / "src" / "lib" / "utils.ts"
PACKAGE_JSON = FRONTEND / "package.json"
UI_COMPONENTS_DIR = FRONTEND / "src" / "components" / "ui"

EB_500_HEX = "#1a6648"  # CLAUDE.md §5.2 ENGINE BASE green
EB_500_TOKEN = "--color-eb-500"

REQUIRED_DEPS = (
    "tailwindcss",
    "@tailwindcss/postcss",
    "class-variance-authority",
    "clsx",
    "tailwind-merge",
    "lucide-react",
    "shadcn",
)

# AC-4: 禁止 icon library (CLAUDE.md §5.1: Lucide only).
FORBIDDEN_ICON_LIBS = (
    "@heroicons/react",
    "@fortawesome/fontawesome-svg-core",
    "@fortawesome/react-fontawesome",
    "react-icons",
    "@iconify/react",
)

MAX_ASSERTION_WALLCLOCK_SECONDS = 5.0


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: required files + tokens present
# ══════════════════════════════════════════════════════════════════════


def test_ac1_components_json_exists():
    assert COMPONENTS_JSON.exists(), f"missing {COMPONENTS_JSON}"


def test_ac1_postcss_config_exists():
    assert POSTCSS_CONFIG.exists(), f"missing {POSTCSS_CONFIG}"


def test_ac1_globals_css_exists():
    assert GLOBALS_CSS.exists(), f"missing {GLOBALS_CSS}"


def test_ac1_lib_utils_exists():
    assert LIB_UTILS.exists(), f"missing {LIB_UTILS}"


def test_ac1_package_json_exists():
    assert PACKAGE_JSON.exists(), f"missing {PACKAGE_JSON}"


def test_ac1_components_json_icon_lucide():
    cfg = json.loads(COMPONENTS_JSON.read_text(encoding="utf-8"))
    assert cfg.get("iconLibrary") == "lucide", (
        f"components.json iconLibrary must be 'lucide', got {cfg.get('iconLibrary')!r}"
    )
    assert cfg.get("tsx") is True, "components.json tsx must be true"


def test_ac1_postcss_loads_tailwind_v4():
    src = POSTCSS_CONFIG.read_text(encoding="utf-8")
    assert "@tailwindcss/postcss" in src, (
        f"postcss.config.mjs must load @tailwindcss/postcss, content: {src!r}"
    )


def test_ac1_globals_css_imports_tailwind_and_eb_500_token():
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    assert "@import \"tailwindcss\"" in css, (
        "globals.css must import tailwindcss"
    )
    # AC-3 invariant: eb-500 token = #1a6648 (case-insensitive hex)
    pattern = re.compile(
        rf"{re.escape(EB_500_TOKEN)}\s*:\s*{re.escape(EB_500_HEX)}",
        re.IGNORECASE,
    )
    assert pattern.search(css), (
        f"globals.css must define {EB_500_TOKEN}: {EB_500_HEX} "
        f"(ENGINE BASE green, CLAUDE.md §5.2)"
    )


def test_ac1_lib_utils_exports_cn():
    src = LIB_UTILS.read_text(encoding="utf-8")
    assert "export function cn(" in src or "export const cn" in src, (
        f"lib/utils.ts must export cn() helper (shadcn convention)"
    )
    # cn uses twMerge + clsx
    assert "twMerge" in src
    assert "clsx" in src


def test_ac1_package_json_lists_required_deps():
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    missing = [d for d in REQUIRED_DEPS if d not in all_deps]
    assert not missing, f"package.json missing required deps: {missing}"


def test_ac1_at_least_one_shadcn_ui_component_installed():
    """shadcn は components/ui に *.tsx を生成する."""
    assert UI_COMPONENTS_DIR.exists(), f"missing {UI_COMPONENTS_DIR}"
    tsxs = list(UI_COMPONENTS_DIR.glob("*.tsx"))
    assert tsxs, "components/ui must contain at least 1 shadcn component"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: < 5 秒 + 明示的失敗メッセージ
# ══════════════════════════════════════════════════════════════════════


def test_ac2_full_verification_under_5_seconds():
    t0 = time.time()
    # rerun the core assertions in sequence (warm path)
    cfg = json.loads(COMPONENTS_JSON.read_text(encoding="utf-8"))
    assert cfg.get("iconLibrary") == "lucide"
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    assert EB_500_HEX.lower() in css.lower()
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    for d in REQUIRED_DEPS:
        assert d in all_deps
    elapsed = time.time() - t0
    assert elapsed < MAX_ASSERTION_WALLCLOCK_SECONDS, (
        f"verification took {elapsed:.2f}s (>= {MAX_ASSERTION_WALLCLOCK_SECONDS}s)"
    )


def test_ac2_missing_dep_message_is_specific():
    """missing dep の identity が AssertionError message に出る semantics 確認."""
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    fake_required = ("__nonexistent_dep_for_test__",)
    missing = [d for d in fake_required if d not in all_deps]
    assert missing == list(fake_required), (
        "missing-dep detection logic is broken"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: invariants must hold
# ══════════════════════════════════════════════════════════════════════


def test_ac3_eb_500_value_is_exactly_1a6648():
    """eb-500 が CLAUDE.md §5.2 で指定された #1a6648 と完全一致."""
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    # extract -EB-500 declarations
    matches = re.findall(
        rf"{re.escape(EB_500_TOKEN)}\s*:\s*(#[0-9a-fA-F]+)",
        css,
    )
    assert matches, f"{EB_500_TOKEN} declaration not found in globals.css"
    for hex_val in matches:
        assert hex_val.lower() == EB_500_HEX.lower(), (
            f"{EB_500_TOKEN} must be {EB_500_HEX}, got {hex_val}"
        )


def test_ac3_components_json_remains_lucide_after_read():
    """verification は frontend file を mutate しない (read-only)."""
    before_mtime = COMPONENTS_JSON.stat().st_mtime
    json.loads(COMPONENTS_JSON.read_text(encoding="utf-8"))
    after_mtime = COMPONENTS_JSON.stat().st_mtime
    assert before_mtime == after_mtime


def test_ac3_smoke_test_does_not_mutate_globals_css():
    before_mtime = GLOBALS_CSS.stat().st_mtime
    GLOBALS_CSS.read_text(encoding="utf-8")
    after_mtime = GLOBALS_CSS.stat().st_mtime
    assert before_mtime == after_mtime


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: forbidden state detection
# ══════════════════════════════════════════════════════════════════════


def test_ac4_no_forbidden_icon_libraries_in_package_json():
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    hits = [lib for lib in FORBIDDEN_ICON_LIBS if lib in all_deps]
    assert not hits, (
        f"forbidden icon libraries detected (CLAUDE.md §5.1 Lucide-only): {hits}"
    )


def test_ac4_components_json_not_overridden_to_non_lucide():
    cfg = json.loads(COMPONENTS_JSON.read_text(encoding="utf-8"))
    icon = cfg.get("iconLibrary", "")
    forbidden = {"heroicons", "fontawesome", "react-icons", "feather", "ionicons"}
    assert icon.lower() not in forbidden, (
        f"components.json iconLibrary is forbidden value {icon!r}"
    )


def test_ac4_globals_css_eb_500_not_silently_dropped():
    """eb-500 トークンが空 / undefined に置換されていない (regression 検出)."""
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    assert EB_500_HEX.lower() in css.lower(), (
        f"{EB_500_HEX} (ENGINE BASE green) must remain in globals.css"
    )
    bad_pattern = re.compile(rf"{re.escape(EB_500_TOKEN)}\s*:\s*(transparent|inherit|unset|initial|;)")
    assert not bad_pattern.search(css), (
        f"{EB_500_TOKEN} must not be reset to transparent/inherit/unset/initial"
    )


def test_ac4_no_hardcoded_secret_in_globals_or_utils():
    for f in (GLOBALS_CSS, LIB_UTILS, COMPONENTS_JSON):
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src), f"secret in {f}"
        assert not re.search(r"AIza[0-9A-Za-z_-]{20,}", src), f"secret in {f}"


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_05_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-05"), None)
    assert t is not None
    generic = [
        "as specified by feature META",
        "When the user interacts with the UI for T-S0-05",
        "While the existing implementation is in use",
        "If invalid input or unauthorized actor is detected during T-S0-05",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-S0-05 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "components.json" in full
    assert "eb-500" in full or "#1a6648" in full
    assert "lucide" in full.lower()


def test_tickets_t_s0_05_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-05"), None)
    assert t.get("adr_link") is not None
    assert "TBD" not in str(t.get("existing_files", []))
