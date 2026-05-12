#!/usr/bin/env python3
"""T-019-02: modify 対象 GitHub Issue 化 (scanner).

## 目的

T-019-01 (bootstrap archive: onlook/penpot 削除) の続編. 将来 archive / refactor /
deprecate される候補を機械的に検出し、構造化 JSON として出力する.
JSON から GitHub Issue を作る手順は docs/modify-targets/README.md に文書化.

## 検出カテゴリ

1. **deprecated_deps** : requirements.txt / package.json で TODO/DEPRECATED コメント付き
2. **stale_routers**   : backend/routers/ で main.py から include されていない router
3. **stale_services**  : backend/services/ で他コードから import されていない service
4. **archived_keyword**: ソース内に '# ARCHIVE' / '# DEPRECATED' / 'TODO: remove' タグ

## 設計

- side effect なし: scan して JSON を stdout / file に出すだけ
- gh CLI で Issue 化は **別工程** (auto しない. 文書化のみ)
- 既存 lint-mock.sh / pre-commit-check.sh は無改変 (REUSE)

## Usage

  python3 scripts/scan-modify-targets.py                  # stdout に JSON
  python3 scripts/scan-modify-targets.py --out PATH       # file 出力
  python3 scripts/scan-modify-targets.py --category=stale_routers  # filter

## AC マッピング (T-019-02)

  AC-1 UBIQUITOUS    : scanner script を提供 / structured JSON 出力 / categories 明示.
  AC-2 EVENT-DRIVEN  : スキャン時に target_count + categories を report.
  AC-3 STATE-DRIVEN  : repo state を mutate しない (read-only) /
                       GitHub Issue を直接作らない (gh CLI への変換は docs).
  AC-4 UNWANTED      : invalid --out path / invalid --category で exit 2.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


VALID_CATEGORIES = (
    "deprecated_deps",
    "stale_routers",
    "stale_services",
    "archived_keyword",
)

# 検出キーワード (archived_keyword category)
ARCHIVE_TAGS = (
    "# ARCHIVE",
    "# DEPRECATED",
    "TODO: remove",
    "TODO: deprecate",
    "FIXME: archive",
)


# ──────────────────────────────────────────────────────────────────────
# Scanners
# ──────────────────────────────────────────────────────────────────────


def _scan_deprecated_deps() -> list[dict]:
    """requirements.txt / package.json で deprecated コメント付きの依存を検出."""
    targets: list[dict] = []
    req = REPO_ROOT / "backend" / "requirements.txt"
    if req.exists():
        for i, line in enumerate(req.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if any(tag in line for tag in (
                "DEPRECATED", "deprecated", "REMOVE", "TODO: remove",
            )):
                targets.append({
                    "category": "deprecated_deps",
                    "file": "backend/requirements.txt",
                    "line": i,
                    "snippet": line.strip()[:200],
                    "reason": "deprecated marker in dependency file",
                })
    pkg = REPO_ROOT / "frontend" / "package.json"
    if pkg.exists():
        # package.json では comment 不可だが JSON5 風や別途 deprecated check
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            # peerDependenciesMeta 等で deprecated flag を見るのが本筋だが
            # 簡略化: 何もしない (将来 npm audit 結果連携)
            _ = data
        except Exception:
            pass
    return targets


def _list_python_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts or ".pytest_cache" in p.parts:
            continue
        out.append(p)
    return out


def _scan_stale_routers() -> list[dict]:
    """backend/routers/ の中で backend/main.py から include_router されていない module."""
    routers_dir = REPO_ROOT / "backend" / "routers"
    main_py = REPO_ROOT / "backend" / "main.py"
    if not routers_dir.exists() or not main_py.exists():
        return []
    main_src = main_py.read_text(encoding="utf-8")

    targets: list[dict] = []
    for py in routers_dir.glob("*.py"):
        if py.name == "__init__.py":
            continue
        mod_name = py.stem
        # main.py に import 文 OR include_router 文があるか
        import_re = re.compile(
            rf"from\s+routers\.{re.escape(mod_name)}\s+import|"
            rf"from\s+routers\s+import\s+[^#\n]*\b{re.escape(mod_name)}\b"
        )
        if not import_re.search(main_src):
            targets.append({
                "category": "stale_routers",
                "file": f"backend/routers/{py.name}",
                "line": 0,
                "snippet": f"router module not referenced in main.py",
                "reason": "no import statement in main.py",
            })
    return targets


def _scan_stale_services() -> list[dict]:
    """backend/services/ で他コードから import されていない module (rough)."""
    services_dir = REPO_ROOT / "backend" / "services"
    backend_dir = REPO_ROOT / "backend"
    if not services_dir.exists():
        return []
    # 各 service module 名を抽出
    service_names = [p.stem for p in services_dir.glob("*.py") if p.name != "__init__.py"]

    # 全 .py 中の import 文を集計
    references: dict[str, int] = {name: 0 for name in service_names}
    for py in _list_python_files(backend_dir):
        if py.parent.name == "services" and py.name in [f"{n}.py" for n in service_names]:
            # 自分自身は除外
            continue
        try:
            src = py.read_text(encoding="utf-8")
        except Exception:
            continue
        for name in service_names:
            patt = re.compile(
                rf"from\s+services\.{re.escape(name)}\s+import|"
                rf"from\s+services\s+import\s+[^#\n]*\b{re.escape(name)}\b|"
                rf"services\.{re.escape(name)}\."
            )
            if patt.search(src):
                references[name] += 1

    targets: list[dict] = []
    for name, count in references.items():
        if count == 0:
            targets.append({
                "category": "stale_services",
                "file": f"backend/services/{name}.py",
                "line": 0,
                "snippet": f"service module not referenced from backend/",
                "reason": "no import statement detected in backend/",
            })
    return targets


def _scan_archived_keyword() -> list[dict]:
    """ソース内に '# ARCHIVE' / '# DEPRECATED' / 'TODO: remove' タグがある箇所."""
    targets: list[dict] = []
    for py in _list_python_files(REPO_ROOT / "backend"):
        try:
            for i, line in enumerate(
                py.read_text(encoding="utf-8").splitlines(), 1,
            ):
                for tag in ARCHIVE_TAGS:
                    if tag in line:
                        rel = py.relative_to(REPO_ROOT)
                        targets.append({
                            "category": "archived_keyword",
                            "file": str(rel),
                            "line": i,
                            "snippet": line.strip()[:200],
                            "reason": f"matched tag: {tag!r}",
                        })
                        break
        except Exception:
            continue
    return targets


# ──────────────────────────────────────────────────────────────────────
# Public scan
# ──────────────────────────────────────────────────────────────────────


def scan(category: str | None = None) -> dict[str, Any]:
    """Run scan and return structured result."""
    if category is not None and category not in VALID_CATEGORIES:
        raise ValueError(
            f"category must be one of {VALID_CATEGORIES}, got {category!r}"
        )
    all_targets: list[dict] = []
    if category is None or category == "deprecated_deps":
        all_targets += _scan_deprecated_deps()
    if category is None or category == "stale_routers":
        all_targets += _scan_stale_routers()
    if category is None or category == "stale_services":
        all_targets += _scan_stale_services()
    if category is None or category == "archived_keyword":
        all_targets += _scan_archived_keyword()

    by_category: dict[str, int] = {}
    for t in all_targets:
        by_category[t["category"]] = by_category.get(t["category"], 0) + 1

    return {
        "total": len(all_targets),
        "by_category": by_category,
        "targets": all_targets,
    }


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan modify targets (T-019-02). Outputs structured JSON.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="output file path (default: stdout)",
    )
    parser.add_argument(
        "--category",
        type=str,
        choices=VALID_CATEGORIES,
        default=None,
        help="filter to single category",
    )
    args = parser.parse_args(argv)

    try:
        result = scan(category=args.category)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(payload + "\n", encoding="utf-8")
            print(
                f"wrote {result['total']} targets to {out_path}",
                file=sys.stderr,
            )
        except OSError as e:
            print(f"ERROR: cannot write to {out_path}: {e}", file=sys.stderr)
            return 2
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
