"""T-005b-03: コンポーネントカタログ + 画面遷移マップ (新規 / mock HTML scanner).

docs/mocks/2026-05-09_v1/ 配下の 43 画面 HTML から bf-* meta を抽出し、
component catalog (screen → feature/task/component) + 遷移 DAG (画面 → 画面)
を read-only に提供する.

## 設計

  - 純関数 (filesystem read のみ). DB write / network なし.
  - 外部 HTML parser に依存しない (re module で <meta>/<a href> を抽出).
  - in-memory cache (mocks_dir path keyed). reset_cache() で明示クリア.
  - path traversal 防止: mocks_dir の Path.resolve() を baseline に
    全 file Path が is_relative_to(mocks_dir) を満たすことを検証.

## 公開 API

  - build_catalog(mocks_dir, *, use_cache=True) -> dict
      全 mock を scan して {total, screens: [...]} を返す.
  - build_transition_map(mocks_dir, *, use_cache=True) -> dict
      画面 → 画面 の遷移 DAG を返す.
  - list_screens(mocks_dir) -> list[dict]
      catalog の screen 一覧 (薄い helper).
  - get_screen(mocks_dir, screen_id) -> dict
      1 screen の情報を返す.
  - reset_cache() -> None

## ADR-010 整合

  - main runner path で LangGraph / LangChain 依存なし.
  - 純粋関数ベース (claude-agent-sdk auto 機能は使わない).

## AC マッピング (T-005b-03 NEW)

  AC-1 UBIQUITOUS    : 公開 API + REST endpoint mount. mock HTML から
                       bf-screen-id / bf-feature-id / bf-task-ids / bf-spec-link
                       を抽出.
  AC-2 EVENT-DRIVEN  : 43 mock corpus を 2 秒以内 / transition map の
                       nodes/edges/stats 構造を返す / lexicographic stable order.
  AC-3 STATE-DRIVEN  : read-only / in-memory cache / bf-* 命名規約維持.
  AC-4 UNWANTED      : mocks_dir 不在 / 0 file / bf-screen-id 欠落 / 不正 format /
                       path traversal で ComponentCatalogError (400/404).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ComponentCatalogError(RuntimeError):
    """カタログ抽出エラー (router で 4xx に変換)."""


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MOCKS_DIR = REPO_ROOT / "docs" / "mocks" / "2026-05-09_v1"

SCREEN_ID_PATTERN = re.compile(r"^S-\d{3}$")
SCREEN_HTML_PATTERN = re.compile(r"^S-\d{3}.*\.html$")

# bf-* meta 抽出 (順序不問の正規表現)
_META_RE_TEMPLATE = (
    r'<meta[^>]*name=["\']{name}["\'][^>]*content=["\']([^"\']*)["\']'
)
_META_RE_TEMPLATE_REV = (
    r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*name=["\']{name}["\']'
)


def _extract_meta(html: str, name: str) -> Optional[str]:
    """<meta name="bf-X" content="Y"> または <meta name="X" content="Y"> から
    Y を抽出 (order tolerant / bf- prefix optional for legacy mocks).

    bootstrap 後の 43 mock の一部 (S-007 系) は legacy `name="screen-id"` 形式、
    他 (S-006 系) は `name="bf-screen-id"` 形式. 両方を許容する.
    """
    candidates = [name]
    if name.startswith("bf-"):
        candidates.append(name[3:])  # bf-screen-id → screen-id
    else:
        candidates.append(f"bf-{name}")
    for n in candidates:
        m = re.search(_META_RE_TEMPLATE.format(name=re.escape(n)), html)
        if m is None:
            m = re.search(_META_RE_TEMPLATE_REV.format(name=re.escape(n)), html)
        if m:
            return m.group(1)
    return None


# href="../...S-NNN-*.html" の抽出
_HREF_SCREEN_RE = re.compile(
    r'href=["\']([^"\']*?S-\d{3}[^"\']*?\.html)["\']'
)

# Component pattern: well-known shadcn / mock classes (heuristic)
_COMPONENT_PATTERNS: dict[str, re.Pattern] = {
    "kpi-card": re.compile(r"class=[\"'][^\"']*\bkpi-card\b"),
    "sidebar-link": re.compile(r"class=[\"'][^\"']*\bsidebar-link\b"),
    "alert-row": re.compile(r"class=[\"'][^\"']*\balert-row\b"),
    "gauge": re.compile(r"class=[\"'][^\"']*\bgauge\b"),
    "lucide-icon": re.compile(
        r'data-lucide=["\'][^"\']+["\']|lucide\.createIcons'
    ),
    "tailwind": re.compile(r"https://cdn\.tailwindcss\.com|@tailwindcss"),
}


# ──────────────────────────────────────────────────────────────────────
# In-memory cache
# ──────────────────────────────────────────────────────────────────────

_CATALOG_CACHE: dict[str, dict[str, Any]] = {}
_TRANSITION_CACHE: dict[str, dict[str, Any]] = {}


def reset_cache() -> None:
    """テスト/明示クリア用."""
    _CATALOG_CACHE.clear()
    _TRANSITION_CACHE.clear()


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_mocks_dir(mocks_dir: Any) -> Path:
    if isinstance(mocks_dir, str):
        p = Path(mocks_dir)
    elif isinstance(mocks_dir, Path):
        p = mocks_dir
    else:
        raise ComponentCatalogError("mocks_dir must be str or Path")
    if not p.exists():
        raise ComponentCatalogError(f"mocks_dir does not exist: {p}")
    if not p.is_dir():
        raise ComponentCatalogError(f"mocks_dir is not a directory: {p}")
    return p.resolve()


def _validate_screen_id(screen_id: Any) -> str:
    if not isinstance(screen_id, str):
        raise ComponentCatalogError("screen_id must be str")
    if not SCREEN_ID_PATTERN.match(screen_id):
        raise ComponentCatalogError(
            f"screen_id must match /^S-\\d{{3}}$/, got {screen_id!r}"
        )
    return screen_id


def _check_path_inside(path: Path, base: Path) -> None:
    """path が base 配下にあること (path traversal 防止)."""
    try:
        path.resolve().relative_to(base)
    except ValueError as e:
        raise ComponentCatalogError(
            f"path traversal detected: {path} not inside {base}"
        ) from e


# ──────────────────────────────────────────────────────────────────────
# Scanning helpers
# ──────────────────────────────────────────────────────────────────────


def _iter_screen_files(mocks_dir: Path) -> list[Path]:
    """mocks_dir 配下の S-NNN-*.html を lexicographic order で返す."""
    if not mocks_dir.exists():
        return []
    files: list[Path] = []
    for p in sorted(mocks_dir.rglob("S-*.html")):
        if SCREEN_HTML_PATTERN.match(p.name):
            _check_path_inside(p, mocks_dir)
            files.append(p)
    return files


def _split_csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


_SCREEN_ID_FROM_FILENAME = re.compile(r"^(S-\d{3})\b")


def _parse_screen_html(html: str, mocks_dir: Path, file_path: Path) -> dict[str, Any]:
    """1 mock HTML から catalog entry を作る.

    screen_id 抽出順:
      1. <meta name="bf-screen-id" content="..."> または <meta name="screen-id" ...>
      2. ファイル名 prefix `S-NNN-...` から derive (legacy mock 救済)

    どちらでも取れなければ ComponentCatalogError (AC-4 規約).
    抽出後 screen_id が `^S-\\d{3}$` を満たさなければ同じく fail.
    """
    screen_id = _extract_meta(html, "bf-screen-id")
    if not screen_id or not SCREEN_ID_PATTERN.match(screen_id):
        # meta が無い / S-NNN format 違反 → filename からの推定 (legacy mock 救済)
        fm = _SCREEN_ID_FROM_FILENAME.match(file_path.name)
        if fm:
            screen_id = fm.group(1)
    if not screen_id or not SCREEN_ID_PATTERN.match(screen_id):
        raise ComponentCatalogError(
            f"missing or malformed screen_id in {file_path.name}: {screen_id!r}"
        )
    features = _split_csv(_extract_meta(html, "bf-feature-id"))
    tasks = _split_csv(_extract_meta(html, "bf-task-ids"))
    spec_link = _extract_meta(html, "bf-spec-link") or ""

    components: list[str] = []
    for name, pat in _COMPONENT_PATTERNS.items():
        if pat.search(html):
            components.append(name)
    components.sort()

    # 遷移先 (links_to) を抽出
    links_to: set[str] = set()
    for m in _HREF_SCREEN_RE.finditer(html):
        href = m.group(1)
        # extract S-NNN from filename
        name_match = re.search(r"S-(\d{3})", href)
        if name_match:
            target = f"S-{name_match.group(1)}"
            if target != screen_id:  # self-link 除外
                links_to.add(target)

    try:
        rel = file_path.relative_to(mocks_dir).as_posix()
    except ValueError:
        rel = file_path.as_posix()

    return {
        "screen_id": screen_id,
        "file_path": rel,
        "features": sorted(features),
        "tasks": sorted(tasks),
        "spec_link": spec_link,
        "components": components,
        "links_to": sorted(links_to),
    }


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def build_catalog(
    mocks_dir: Any = None,
    *,
    use_cache: bool = True,
) -> dict[str, Any]:
    """全 mock HTML を scan して catalog を返す.

    Returns:
      {
        "total": int,
        "mocks_dir": str,
        "screens": [
          {screen_id, file_path, features, tasks, spec_link, components, links_to},
          ...  # lexicographic by screen_id
        ],
      }
    """
    if mocks_dir is None:
        mocks_dir = DEFAULT_MOCKS_DIR
    md = _validate_mocks_dir(mocks_dir)
    cache_key = str(md)
    if use_cache and cache_key in _CATALOG_CACHE:
        return _CATALOG_CACHE[cache_key]

    files = _iter_screen_files(md)
    if not files:
        raise ComponentCatalogError(f"no S-NNN-*.html files in {md}")

    screens: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for f in files:
        html = f.read_text(encoding="utf-8", errors="replace")
        entry = _parse_screen_html(html, md, f)
        if entry["screen_id"] in seen_ids:
            # duplicate screen_id is suspicious but not fatal; warn + skip first occurrence
            logger.warning(
                "duplicate screen_id %s in %s (keeping first)",
                entry["screen_id"], f,
            )
            continue
        seen_ids.add(entry["screen_id"])
        screens.append(entry)

    screens.sort(key=lambda s: s["screen_id"])
    result = {
        "total": len(screens),
        "mocks_dir": str(md),
        "screens": screens,
    }
    if use_cache:
        _CATALOG_CACHE[cache_key] = result
    return result


def build_transition_map(
    mocks_dir: Any = None,
    *,
    use_cache: bool = True,
) -> dict[str, Any]:
    """画面 → 画面 の遷移 DAG.

    Returns:
      {
        "mocks_dir": str,
        "nodes": [{screen_id, screen_count_in}, ...],
        "edges": [{from, to}, ...],     # lexicographic
        "stats": {
          "total_screens": int,
          "total_edges": int,
          "orphan_screens": list[str],  # 入出力が 0 の screen
        },
      }
    """
    if mocks_dir is None:
        mocks_dir = DEFAULT_MOCKS_DIR
    md = _validate_mocks_dir(mocks_dir)
    cache_key = str(md)
    if use_cache and cache_key in _TRANSITION_CACHE:
        return _TRANSITION_CACHE[cache_key]

    catalog = build_catalog(md, use_cache=use_cache)
    screens = catalog["screens"]
    screen_ids = {s["screen_id"] for s in screens}

    edges: list[tuple[str, str]] = []
    incoming: dict[str, int] = {sid: 0 for sid in screen_ids}
    outgoing: dict[str, int] = {sid: 0 for sid in screen_ids}

    for s in screens:
        src = s["screen_id"]
        for tgt in s["links_to"]:
            # 未知の screen_id は edge に含めない (透過的に skip)
            if tgt not in screen_ids:
                continue
            edges.append((src, tgt))
            incoming[tgt] += 1
            outgoing[src] += 1

    edges.sort()  # tuple sort = lexicographic by (from, to)

    nodes = [
        {
            "screen_id": sid,
            "screen_count_in": incoming[sid],
            "screen_count_out": outgoing[sid],
        }
        for sid in sorted(screen_ids)
    ]
    orphans = sorted(
        sid for sid in screen_ids
        if incoming[sid] == 0 and outgoing[sid] == 0
    )

    result = {
        "mocks_dir": str(md),
        "nodes": nodes,
        "edges": [{"from": f, "to": t} for (f, t) in edges],
        "stats": {
            "total_screens": len(screen_ids),
            "total_edges": len(edges),
            "orphan_screens": orphans,
        },
    }
    if use_cache:
        _TRANSITION_CACHE[cache_key] = result
    return result


def list_screens(mocks_dir: Any = None) -> list[dict[str, Any]]:
    """catalog の screen 一覧を返す薄い helper."""
    return build_catalog(mocks_dir)["screens"]


def get_screen(mocks_dir: Any, screen_id: str) -> dict[str, Any]:
    """単一 screen の catalog entry を返す."""
    if mocks_dir is None:
        mocks_dir = DEFAULT_MOCKS_DIR
    sid = _validate_screen_id(screen_id)
    cat = build_catalog(mocks_dir)
    for s in cat["screens"]:
        if s["screen_id"] == sid:
            return s
    raise ComponentCatalogError(f"screen not found: {sid}")
