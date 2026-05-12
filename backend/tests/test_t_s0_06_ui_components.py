"""T-S0-06: 共通 UI components (Button/Input/Modal/Toast/Badge) — 4 AC.

REUSE: PR #61 で shadcn 基盤 5 primitive (button / input / dialog /
sonner / badge) が既に存在する. 本 module は **spec contract layer** として
4 AC が各 .tsx の symbol / 依存パッケージ / Lucide-only invariant と 1:1
整合していることを Python 静的解析で機械検証する.

(Node 環境を前提とせず、 backend pytest が TSX を文字列として読んで検査.)

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 5 primitive ファイルが存在 / button + badge が cva /
                       dialog が 10 named export / sonner が toast 再 export.
  AC-2 EVENT-DRIVEN  : 各 file が canonical 依存 (radix / cva / sonner) を
                       import / sonner が toast 再 export.
  AC-3 STATE-DRIVEN  : emoji なし / dangerouslySetInnerHTML なし / fetch /
                       axios / useQuery / useSWR なし / #1a6648 ハードコード
                       なし.
  AC-4 UNWANTED      : button が VariantProps typed / dialog が radix /
                       reactflow / langgraph / langchain / litellm import なし.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = REPO_ROOT / "frontend" / "src" / "components" / "ui"

BUTTON = UI_DIR / "button.tsx"
INPUT = UI_DIR / "input.tsx"
DIALOG = UI_DIR / "dialog.tsx"
SONNER = UI_DIR / "sonner.tsx"
BADGE = UI_DIR / "badge.tsx"

PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"


PRIMITIVE_FILES = (BUTTON, INPUT, DIALOG, SONNER, BADGE)

EMOJI_PATTERN = re.compile(
    r"[\U0001F300-\U0001FAFF"
    r"\U00002600-\U000027BF"
    r"\U0001F000-\U0001F2FF]"
)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 5 canonical primitives exist + cva + dialog 10 exports
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("path", PRIMITIVE_FILES, ids=lambda p: p.name)
def test_ac1_primitive_file_exists(path):
    assert path.exists(), f"missing primitive: {path}"


def test_ac1_button_exports_button_and_variants():
    src = BUTTON.read_text(encoding="utf-8")
    assert re.search(r"\bButton\b", src)
    assert re.search(r"\bbuttonVariants\b", src)
    assert "export { Button, buttonVariants }" in src or (
        "export" in src and "Button" in src and "buttonVariants" in src
    )


def test_ac1_button_uses_cva():
    src = BUTTON.read_text(encoding="utf-8")
    assert "class-variance-authority" in src
    assert "cva" in src
    assert "VariantProps" in src


def test_ac1_badge_uses_cva():
    src = BADGE.read_text(encoding="utf-8")
    assert "class-variance-authority" in src
    assert "cva" in src
    assert "badgeVariants" in src


def test_ac1_input_exports_input():
    src = INPUT.read_text(encoding="utf-8")
    assert "export { Input }" in src or re.search(r"export\s+\{\s*Input\s*\}", src)


def test_ac1_dialog_10_named_exports():
    """Dialog primitive (Modal) が 10 個の named export を出す."""
    src = DIALOG.read_text(encoding="utf-8")
    required = [
        "Dialog", "DialogTrigger", "DialogContent", "DialogHeader",
        "DialogFooter", "DialogTitle", "DialogDescription",
        "DialogClose", "DialogPortal", "DialogOverlay",
    ]
    # 1 つの export 文に 10 個全部入っている想定
    export_block = re.search(
        r"export\s*\{([^}]+)\}",
        src,
        re.DOTALL,
    )
    assert export_block, "Dialog file must have an export { ... } block"
    body = export_block.group(1)
    for sym in required:
        assert sym in body, f"Dialog missing export: {sym}"


def test_ac1_sonner_exports_toaster_and_toast():
    """Toast primitive: sonner.tsx が Toaster + toast 再 export."""
    src = SONNER.read_text(encoding="utf-8")
    assert "export function Toaster" in src or re.search(
        r"export\s+\{[^}]*Toaster[^}]*\}", src,
    )
    # toast を sonner から re-export
    assert re.search(r'export\s*\{\s*toast\s*\}\s*from\s*["\']sonner["\']', src)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — canonical deps (radix / cva / sonner / lucide)
# ══════════════════════════════════════════════════════════════════════


def test_ac2_dialog_imports_radix_dialog():
    src = DIALOG.read_text(encoding="utf-8")
    assert "@radix-ui/react-dialog" in src


def test_ac2_dialog_uses_lucide_x_icon():
    src = DIALOG.read_text(encoding="utf-8")
    # Close button: <X /> from lucide-react
    assert "lucide-react" in src
    assert re.search(r"\bX\b", src)


def test_ac2_sonner_imports_sonner_toaster():
    src = SONNER.read_text(encoding="utf-8")
    assert 'from "sonner"' in src or "from 'sonner'" in src
    assert "Toaster" in src


def test_ac2_package_json_has_required_deps():
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    for required in (
        "class-variance-authority",
        "@radix-ui/react-dialog",
        "sonner",
        "lucide-react",
        "tailwindcss",
    ):
        assert required in deps, f"missing package.json dep: {required}"


def test_ac2_no_legacy_reactflow_in_package_json():
    """T-009-02 invariant: legacy 'reactflow' 名前空間禁止."""
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert "reactflow" not in deps
    # @xyflow/react v12+ のみが正規
    assert "@xyflow/react" in deps


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — Lucide-only / no XSS / no fetch / no hex
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("path", PRIMITIVE_FILES, ids=lambda p: p.name)
def test_ac3_no_emoji(path):
    src = path.read_text(encoding="utf-8")
    hits = EMOJI_PATTERN.findall(src)
    assert not hits, f"emoji in {path.name}: {hits}"


@pytest.mark.parametrize("path", PRIMITIVE_FILES, ids=lambda p: p.name)
def test_ac3_no_dangerously_set_inner_html(path):
    src = path.read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in src


@pytest.mark.parametrize("path", PRIMITIVE_FILES, ids=lambda p: p.name)
def test_ac3_no_backend_fetch_in_primitive(path):
    """presentation primitive は backend を直接呼ばない (layer separation)."""
    src = path.read_text(encoding="utf-8")
    assert not re.search(r"\bfetch\s*\(", src), (
        f"forbidden fetch() in primitive {path.name}"
    )
    assert "axios" not in src
    assert "useQuery" not in src
    assert "useSWR" not in src
    assert "@/lib/api/" not in src


@pytest.mark.parametrize("path", PRIMITIVE_FILES, ids=lambda p: p.name)
def test_ac3_no_hardcoded_eb_hex(path):
    """ENGINE BASE green の hex (#1a6648) を直接書かない (Tailwind class 経由)."""
    src = path.read_text(encoding="utf-8")
    assert "#1a6648" not in src
    # 他の hard-coded brand hex も typically ない
    # ※ Tailwind の bg-eb-500 / text-eb-500 などのクラス参照は OK


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — type safety + radix + no forbidden imports
# ══════════════════════════════════════════════════════════════════════


def test_ac4_button_variant_typed_with_variant_props():
    """VariantProps<typeof buttonVariants> によりコンパイル時に variant 制約."""
    src = BUTTON.read_text(encoding="utf-8")
    assert "VariantProps" in src
    assert "buttonVariants" in src


def test_ac4_badge_variant_typed_with_variant_props():
    src = BADGE.read_text(encoding="utf-8")
    assert "VariantProps" in src
    assert "badgeVariants" in src


def test_ac4_dialog_built_on_radix():
    """Dialog の a11y は radix 委譲."""
    src = DIALOG.read_text(encoding="utf-8")
    assert "DialogPrimitive.Root" in src or "DialogPrimitive" in src
    # Content + Overlay + Portal は radix が必須前提
    for sym in ("Content", "Overlay", "Portal"):
        assert sym in src


@pytest.mark.parametrize("path", PRIMITIVE_FILES, ids=lambda p: p.name)
def test_ac4_no_reactflow_legacy(path):
    src = path.read_text(encoding="utf-8")
    assert 'from "reactflow"' not in src
    assert "from 'reactflow'" not in src


@pytest.mark.parametrize("path", PRIMITIVE_FILES, ids=lambda p: p.name)
def test_ac4_no_langgraph_langchain_litellm(path):
    """ADR-010 main path 禁止."""
    src = path.read_text(encoding="utf-8").lower()
    for forbidden in ("langgraph", "langchain", "litellm"):
        assert forbidden not in src, (
            f"forbidden lib {forbidden} in {path.name}"
        )


@pytest.mark.parametrize("path", PRIMITIVE_FILES, ids=lambda p: p.name)
def test_ac4_no_hardcoded_secret(path):
    src = path.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_06_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-06"), None)
    assert t is not None
    generic = [
        "as specified by feature META",
        "When the user interacts with the UI for T-S0-06",
        "While the existing implementation is in use",
        "If invalid input or unauthorized actor is detected during T-S0-06",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-S0-06 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "button.tsx", "input.tsx", "dialog.tsx", "sonner.tsx", "badge.tsx",
        "class-variance-authority", "VariantProps",
        "@radix-ui/react-dialog", "sonner",
        "DialogTrigger", "DialogContent", "DialogPortal", "DialogOverlay",
        "buttonVariants", "badgeVariants",
    ):
        assert sym in full, f"T-S0-06 AC missing concrete symbol: {sym}"


def test_tickets_t_s0_06_has_adr_link_and_no_tbd():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-06"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert len(files) >= 13, f"expected >= 13 existing_files, got {len(files)}"
    assert "TBD" not in str(files)
    for required in (
        "frontend/src/components/ui/button.tsx",
        "frontend/src/components/ui/input.tsx",
        "frontend/src/components/ui/dialog.tsx",
        "frontend/src/components/ui/sonner.tsx",
        "frontend/src/components/ui/badge.tsx",
        "frontend/package.json",
    ):
        assert required in files, f"missing existing_file: {required}"


def test_tickets_t_s0_06_canonical_ears_types():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-06"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-S0-06 still uses legacy alias: {ty}"
        )
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"]
