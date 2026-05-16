#!/usr/bin/env python3
"""lint-mock-impl-diff — mock HTML と React 実装の machine-readable meta 一致を検証する.

T-FOUNDATION-02 (Gate #8 / lint #17 mock-impl-diff) の実体.
v3 機能分解で各 mock HTML に埋め込まれた `<meta name="screen-id|feature-id|task-ids|entities|phase">`
と、対応する `frontend/src/screens/<screen-id>.tsx` の JSDoc / data-* 属性 / `?meta` import
のいずれかから抽出した meta を field-wise に diff して drift を報告する.

サポートする impl meta 抽出方法 (優先度順):
  1. JSDoc: `* @screen-id S-XXX` 等
  2. data attr: `<div data-screen-id="S-XXX" data-feature-id="F-XXX" ...>`
  3. mock_path import (将来用 vite plugin) — 現状は detect-only で警告のみ

DriftEntry schema:
  {
    "screen_id": str,
    "field": str,                # "screen-id" | "feature-id" | "task-ids" | "entities" | "phase"
    "mock_value": Any,           # mock 側の値 (str or None)
    "impl_value": Any | None,    # impl 側の値 (str or None)
    "severity": "error" | "warning",
    "kind": str                  # "value_mismatch" | "missing_in_impl" | "missing_in_mock"
                                 #   | "missing_field_in_impl" | "missing_field_in_mock"
  }

Usage:
  python3 scripts/lint-mock-impl-diff.py [--mock-dir DIR] [--impl-dir DIR] [--output PATH]
                                          [--strict] [--self-test]

CI / Gate #8 / lint #17 の単一エントリポイント.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import TypedDict

# ----------------------------------------------------------------
# 設定 / 定数
# ----------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MOCK_DIR = REPO_ROOT / "docs/mocks/2026-05-09_v1"
DEFAULT_IMPL_DIR = REPO_ROOT / "frontend/src"

# meta フィールド (mock HTML の <meta name="..."> と impl の @key / data-key)
META_FIELDS: tuple[str, ...] = (
    "screen-id",
    "feature-id",
    "task-ids",
    "entities",
    "phase",
)


class DriftEntry(TypedDict):
    """1 件の drift エントリ."""

    screen_id: str
    field: str
    mock_value: str | None
    impl_value: str | None
    severity: str  # "error" | "warning"
    kind: str


class MockMeta(TypedDict, total=False):
    """1 つの mock HTML から抽出した meta dict."""

    screen_id: str  # "screen-id" は dict key 用に正規化済み
    feature_id: str
    task_ids: str
    entities: str
    phase: str


# ----------------------------------------------------------------
# mock HTML パーサ (stdlib html.parser のみ)
# ----------------------------------------------------------------


class _MetaTagCollector(HTMLParser):
    """<meta name="..." content="..."> を集める軽量パーサ."""

    def __init__(self) -> None:
        super().__init__()
        self.metas: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attr_dict: dict[str, str] = {k.lower(): (v or "") for k, v in attrs}
        name = attr_dict.get("name")
        content = attr_dict.get("content")
        if name is None or content is None:
            return
        if name in META_FIELDS:
            self.metas[name] = content


def extract_mock_meta(html_path: Path) -> dict[str, str]:
    """mock HTML から meta 5 field を抽出.

    返り値: { "screen-id": "S-XXX", ... } (見つかった field のみ).
    """
    text = html_path.read_text(encoding="utf-8", errors="replace")
    parser = _MetaTagCollector()
    parser.feed(text)
    return parser.metas


# ----------------------------------------------------------------
# impl tsx パーサ (regex のみ)
# ----------------------------------------------------------------

# JSDoc: `* @screen-id S-001` の行頭 / 末尾 trim. content は alnum + 記号 (空白を含まない値想定).
_JSDOC_RE = re.compile(
    r"\*\s+@(screen-id|feature-id|task-ids|entities|phase)\s+(\S.*?)\s*$",
    re.MULTILINE,
)

# data-* attr: `data-screen-id="S-001"` (引用符は " or ')
_DATA_ATTR_RE = re.compile(
    r"""data-(screen-id|feature-id|task-ids|entities|phase)\s*=\s*["']([^"']*)["']""",
)

# mock_path import (将来用 vite plugin)
_META_IMPORT_RE = re.compile(
    r"""import\s+\w+\s+from\s+["']([^"']+\?meta)["']""",
)


def extract_impl_meta(tsx_path: Path) -> tuple[dict[str, str], bool]:
    """impl tsx から meta を抽出.

    返り値: (meta_dict, has_meta_import)
      - meta_dict: { "screen-id": "S-001", ... } (JSDoc + data-attr の union, JSDoc 優先)
      - has_meta_import: `?meta` import が見つかれば True (将来用; 現状は警告のみ)
    """
    text = tsx_path.read_text(encoding="utf-8", errors="replace")

    meta: dict[str, str] = {}

    # 1) data attr (低優先度): JSDoc に上書きされ得る
    for m in _DATA_ATTR_RE.finditer(text):
        key, value = m.group(1), m.group(2)
        meta[key] = value

    # 2) JSDoc (高優先度): data attr を上書き
    for m in _JSDOC_RE.finditer(text):
        key, value = m.group(1), m.group(2).strip()
        meta[key] = value

    # 3) ?meta import (detect only)
    has_meta_import = bool(_META_IMPORT_RE.search(text))

    return meta, has_meta_import


# ----------------------------------------------------------------
# diff ロジック
# ----------------------------------------------------------------


def _normalize(value: str | None) -> str | None:
    """比較前の正規化: trim + カンマ区切り順序の正規化 (set 比較相当)."""
    if value is None:
        return None
    v = value.strip()
    if "," in v:
        # CSV 値は順序非依存で比較する (task-ids / entities)
        parts = sorted(p.strip() for p in v.split(",") if p.strip())
        return ",".join(parts)
    return v


def diff_one_screen(
    screen_id: str,
    mock_meta: dict[str, str],
    impl_meta: dict[str, str] | None,
) -> list[DriftEntry]:
    """1 screen 分の mock vs impl meta diff を計算する.

    Args:
        screen_id: 画面 ID (mock の screen-id).
        mock_meta: mock HTML から抽出した meta.
        impl_meta: impl tsx から抽出した meta. None なら impl ファイル不在.

    Returns:
        DriftEntry のリスト (drift が無ければ空リスト).
    """
    drifts: list[DriftEntry] = []

    # impl ファイル不在 -> 各フィールド 1 件として error
    if impl_meta is None:
        drifts.append(
            DriftEntry(
                screen_id=screen_id,
                field="*",
                mock_value=mock_meta.get("screen-id"),
                impl_value=None,
                severity="error",
                kind="missing_in_impl",
            )
        )
        return drifts

    for field in META_FIELDS:
        mock_v = mock_meta.get(field)
        impl_v = impl_meta.get(field)

        if mock_v is None and impl_v is None:
            # 両側欠落 = mock の meta 不備 (UNWANTED AC で error にする)
            drifts.append(
                DriftEntry(
                    screen_id=screen_id,
                    field=field,
                    mock_value=None,
                    impl_value=None,
                    severity="error",
                    kind="missing_field_in_mock",
                )
            )
            continue

        if mock_v is None:
            # mock 側に meta 無し (UNWANTED AC で error)
            drifts.append(
                DriftEntry(
                    screen_id=screen_id,
                    field=field,
                    mock_value=None,
                    impl_value=impl_v,
                    severity="error",
                    kind="missing_field_in_mock",
                )
            )
            continue

        if impl_v is None:
            drifts.append(
                DriftEntry(
                    screen_id=screen_id,
                    field=field,
                    mock_value=mock_v,
                    impl_value=None,
                    severity="warning",
                    kind="missing_field_in_impl",
                )
            )
            continue

        if _normalize(mock_v) != _normalize(impl_v):
            drifts.append(
                DriftEntry(
                    screen_id=screen_id,
                    field=field,
                    mock_value=mock_v,
                    impl_value=impl_v,
                    severity="warning",
                    kind="value_mismatch",
                )
            )

    return drifts


# ----------------------------------------------------------------
# scan: ディレクトリ全体を回す
# ----------------------------------------------------------------


def resolve_impl_path(impl_dir: Path, screen_id: str) -> Path:
    """`<impl_dir>/screens/<screen-id>.tsx` を返す (存在チェックは呼び出し側)."""
    return impl_dir / "screens" / f"{screen_id}.tsx"


def scan(mock_dir: Path, impl_dir: Path) -> list[DriftEntry]:
    """mock_dir 配下の全 .html を scan し、impl_dir と diff した drift を返す."""
    all_drifts: list[DriftEntry] = []
    html_paths = sorted(mock_dir.rglob("*.html"))

    for html_path in html_paths:
        mock_meta = extract_mock_meta(html_path)
        # screen-id 自体が無いファイル (index.html 等) は skip
        screen_id = mock_meta.get("screen-id")
        if not screen_id:
            continue

        impl_path = resolve_impl_path(impl_dir, screen_id)
        if not impl_path.exists():
            all_drifts.extend(diff_one_screen(screen_id, mock_meta, None))
            continue

        impl_meta, _has_import = extract_impl_meta(impl_path)
        all_drifts.extend(diff_one_screen(screen_id, mock_meta, impl_meta))

    return all_drifts


# ----------------------------------------------------------------
# self-test
# ----------------------------------------------------------------


def _run_self_test() -> int:
    """4 fixture (aligned / drifted / missing_impl / missing_meta) を検証する.

    Returns:
        0: all 4 cases PASS
        1: いずれかが想定外
    """
    fixtures_dir = Path(__file__).resolve().parent / "tests" / "fixtures" / "mock-impl-diff"
    mock_aligned = fixtures_dir / "mock-aligned.html"
    mock_drifted = fixtures_dir / "mock-drifted.html"
    impl_aligned = fixtures_dir / "impl-aligned.tsx"
    impl_drifted = fixtures_dir / "impl-drifted.tsx"

    failures: list[str] = []

    # case 1: aligned (mock + impl 完全一致 -> drift 0)
    aligned_mock_meta = extract_mock_meta(mock_aligned)
    aligned_impl_meta, _ = extract_impl_meta(impl_aligned)
    drifts_aligned = diff_one_screen("S-901", aligned_mock_meta, aligned_impl_meta)
    if drifts_aligned:
        failures.append(
            f"[aligned] expected 0 drift, got {len(drifts_aligned)}: {drifts_aligned!r}"
        )
    else:
        print("[self-test] aligned: PASS (0 drift)")

    # case 2: drifted (feature-id / task-ids / entities / phase 全て drift -> 4 件 value_mismatch)
    drifted_mock_meta = extract_mock_meta(mock_drifted)
    drifted_impl_meta, _ = extract_impl_meta(impl_drifted)
    drifts_drifted = diff_one_screen("S-902", drifted_mock_meta, drifted_impl_meta)
    mismatch_count = sum(1 for d in drifts_drifted if d["kind"] == "value_mismatch")
    if mismatch_count != 4:
        failures.append(
            f"[drifted] expected 4 value_mismatch drifts, got {mismatch_count}: {drifts_drifted!r}"
        )
    else:
        print(f"[self-test] drifted: PASS ({mismatch_count} value_mismatch drifts)")

    # case 3: missing_impl (aligned mock + impl ファイル無し -> 1 件 missing_in_impl error)
    drifts_missing_impl = diff_one_screen("S-901", aligned_mock_meta, None)
    if not (
        len(drifts_missing_impl) == 1
        and drifts_missing_impl[0]["kind"] == "missing_in_impl"
        and drifts_missing_impl[0]["severity"] == "error"
    ):
        failures.append(
            f"[missing_impl] expected 1 missing_in_impl error drift, got: {drifts_missing_impl!r}"
        )
    else:
        print("[self-test] missing_impl: PASS (1 missing_in_impl error)")

    # case 4: missing_meta (mock に meta 無し + impl は aligned -> 5 件 missing_field_in_mock error)
    drifts_missing_meta = diff_one_screen("S-901", {}, aligned_impl_meta)
    missing_mock_count = sum(
        1
        for d in drifts_missing_meta
        if d["kind"] == "missing_field_in_mock" and d["severity"] == "error"
    )
    if missing_mock_count != 5:
        failures.append(
            f"[missing_meta] expected 5 missing_field_in_mock error drifts, "
            f"got {missing_mock_count}: {drifts_missing_meta!r}"
        )
    else:
        print(f"[self-test] missing_meta: PASS ({missing_mock_count} missing_field_in_mock error)")

    if failures:
        print("\n[self-test] FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[self-test] ALL 4 CASES PASS")
    return 0


# ----------------------------------------------------------------
# main / CLI
# ----------------------------------------------------------------


def _format_report(drifts: list[DriftEntry]) -> str:
    """drift list を JSON 文字列 (pretty) で返す."""
    return json.dumps(
        {"drift_count": len(drifts), "drifts": drifts},
        ensure_ascii=False,
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="lint-mock-impl-diff — mock HTML と React 実装の meta 一致を検証する",
    )
    parser.add_argument(
        "--mock-dir",
        type=Path,
        default=DEFAULT_MOCK_DIR,
        help=f"mock HTML root (default: {DEFAULT_MOCK_DIR.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--impl-dir",
        type=Path,
        default=DEFAULT_IMPL_DIR,
        help=f"frontend src root (default: {DEFAULT_IMPL_DIR.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output JSON path (default: stdout)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 if any drift is found",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run 4 fixture cases and exit (skips --mock-dir / --impl-dir scan)",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    mock_dir: Path = args.mock_dir
    impl_dir: Path = args.impl_dir

    if not mock_dir.exists():
        print(f"error: --mock-dir does not exist: {mock_dir}", file=sys.stderr)
        return 2
    if not impl_dir.exists():
        print(f"error: --impl-dir does not exist: {impl_dir}", file=sys.stderr)
        return 2

    drifts = scan(mock_dir, impl_dir)
    report = _format_report(drifts)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
    else:
        print(report)

    if args.strict and drifts:
        # Tier 2 AC (OPTIONAL --strict + UNWANTED missing_in_mock) を満たすため
        # drift > 0 (error / warning 問わず) で exit 1.
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
