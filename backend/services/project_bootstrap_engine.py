"""T-BTSTRAP-03: Jinja2 プレースホルダ置換エンジン (NEW / Sprint S2 / F-003).

新規案件を `templates/project-bootstrap/` から bootstrap する際に, ワークスペース
メタデータを context として全 `.j2` ファイルを Jinja2 render する純 service.

## AC マッピング (1:1)

  AC-1 UBIQUITOUS (#1) : templates/project-bootstrap/ 配下の **全 .j2 ファイル**
                         を Jinja2 で render する.
  AC-1 UBIQUITOUS (#2) : **10 placeholders 必須サポート** =
                         project_name, project_slug, client_name, deadline,
                         phase, owner_email, tech_stack, ai_employees,
                         template_version, generated_at
  AC-2 EVENT-DRIVEN    : 必須 placeholder が metadata に欠落していたら,
                         **どのファイルも書き出す前に** BootstrapError を raise (atomic).
  AC-3 STATE-DRIVEN    : autoescape=False で render (Markdown / HTML 出力を保持).
  AC-4 UNWANTED        : render 後に `{{ }}` (未置換 placeholder) が残っていたら
                         validation で fail し commit しない.

## 公開 API

  - REQUIRED_PLACEHOLDERS: tuple[str, ...]  必須 10 件
  - DEFAULT_VALUES: dict[str, Any]          optional な置換補完 (deadline 等)
  - class BootstrapError(RuntimeError)
  - validate_metadata(metadata) -> dict     不足は BootstrapError
  - render_template_string(text, metadata) -> str  単一文字列 render (AC-4 残存検査込)
  - render_project_bootstrap(metadata, *, output_dir, template_root=None)
      -> dict {"files_written": [...], "files_rendered": int}
      atomic: 全 .j2 を一旦 in-memory で render し, 全成功時のみ output_dir へ書込.

## ADR / 関連

  - T-BTSTRAP-01 (deps; templates 構造)
  - T-BTSTRAP-02 (blocks; WorkspaceService.bootstrap で本 engine を呼ぶ)
  - ADR-009 (各案件への強制レイヤー自動展開)
  - M-31 (要件)
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

try:
    from jinja2 import (  # type: ignore[import-not-found]
        Environment,
        FileSystemLoader,
        StrictUndefined,
        TemplateError,
        Undefined,
    )
    _JINJA_AVAILABLE = True
except ImportError:  # pragma: no cover (jinja2 は requirements.txt に固定済)
    _JINJA_AVAILABLE = False

logger = logging.getLogger(__name__)


# AC-1 UBIQUITOUS (#2): 必須 10 placeholders
REQUIRED_PLACEHOLDERS: tuple[str, ...] = (
    "project_name",
    "project_slug",
    "client_name",
    "deadline",
    "phase",
    "owner_email",
    "tech_stack",
    "ai_employees",
    "template_version",
    "generated_at",
)

# 自動補完される optional default (caller が値を渡したら上書き)
DEFAULT_VALUES: dict[str, Any] = {
    "deadline": "未定",
    "phase": "1",
    "tech_stack": "Next.js 15 / FastAPI / Supabase",
    "ai_employees": "mary, winston, devon, quinn, sally",
    "template_version": "1.2.0",  # templates/CHANGELOG.md latest
    "owner_email": "masato@engine-base.com",
}

# 未置換 {{ }} 検出用 (AC-4 UNWANTED).
# Jinja2 control statements ({% %}) や comments ({# #}) は対象外.
# `\{\{` (escaped literal) は除外.
UNRENDERED_PATTERN = re.compile(r"\{\{[^{}]+\}\}")

# 制約定数
MAX_OUTPUT_PATH_LEN = 300
MAX_RENDERED_FILES = 1000  # 1 bootstrap で書ける最大ファイル数 (DOS 防止)


class BootstrapError(RuntimeError):
    """Bootstrap engine の入力 / 不変条件違反 (router 層で 4xx 変換)."""


# ──────────────────────────────────────────────────────────────────────
# Validation (AC-2 EVENT-DRIVEN / AC-4 UNWANTED)
# ──────────────────────────────────────────────────────────────────────


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def validate_metadata(metadata: Any) -> dict[str, Any]:
    """metadata dict を validate し default を補って返す.

    AC-2 EVENT-DRIVEN: 必須 placeholder が欠けていたら BootstrapError を raise
    (どのファイルも書き出す前に).
    """
    if not isinstance(metadata, dict):
        raise BootstrapError("metadata must be a dict")

    merged: dict[str, Any] = {}
    # まず default で埋める
    for key, dv in DEFAULT_VALUES.items():
        merged[key] = dv
    # caller の値で上書き (None / 空文字は skip して default 維持)
    for key, val in metadata.items():
        if not isinstance(key, str):
            raise BootstrapError("metadata keys must be strings")
        if _is_blank(val) and key in DEFAULT_VALUES:
            continue
        merged[key] = val

    # generated_at は常に runtime で確定 (caller 渡しは無視)
    merged["generated_at"] = str(int(time.time()))

    # 必須欠落チェック
    missing: list[str] = []
    for key in REQUIRED_PLACEHOLDERS:
        if key not in merged or _is_blank(merged[key]):
            missing.append(key)
    if missing:
        raise BootstrapError(
            f"missing required placeholders: {missing}. "
            f"required: {list(REQUIRED_PLACEHOLDERS)}"
        )
    return merged


def _detect_unrendered(text: str) -> list[str]:
    """AC-4 UNWANTED: render 後に残った `{{ }}` パターンを抽出."""
    return UNRENDERED_PATTERN.findall(text)


# ──────────────────────────────────────────────────────────────────────
# Rendering
# ──────────────────────────────────────────────────────────────────────


def _build_environment(template_root: Path) -> "Environment":
    """AC-3 STATE-DRIVEN: autoescape=False で env を作る (Markdown/HTML 保持).

    StrictUndefined を採用し未定義変数は即 raise (AC-2 fail-fast).
    """
    if not _JINJA_AVAILABLE:
        raise BootstrapError("jinja2 SDK is not installed")
    return Environment(
        loader=FileSystemLoader(str(template_root)),
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def render_template_string(
    text: str,
    metadata: dict[str, Any],
    *,
    validate_unrendered: bool = True,
) -> str:
    """単一文字列を Jinja2 render. AC-4 UNWANTED チェック付き."""
    if not _JINJA_AVAILABLE:
        raise BootstrapError("jinja2 SDK is not installed")
    if not isinstance(text, str):
        raise BootstrapError("text must be string")
    env = Environment(
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    try:
        tmpl = env.from_string(text)
        rendered = tmpl.render(**metadata)
    except TemplateError as e:
        raise BootstrapError(f"template render failed: {e}") from e
    if validate_unrendered:
        leftover = _detect_unrendered(rendered)
        if leftover:
            raise BootstrapError(
                f"unrendered placeholders remain after render: {leftover[:5]}"
            )
    return rendered


def _default_template_root() -> Path:
    """repo root / templates/project-bootstrap."""
    return Path(__file__).resolve().parents[2] / "templates" / "project-bootstrap"


def _iter_j2_files(template_root: Path) -> list[Path]:
    """templates/project-bootstrap/**/*.j2 を再帰的に列挙 (sorted, deterministic)."""
    if not template_root.exists() or not template_root.is_dir():
        return []
    return sorted(template_root.rglob("*.j2"))


def render_project_bootstrap(
    metadata: dict[str, Any],
    *,
    output_dir: Path,
    template_root: Optional[Path] = None,
) -> dict[str, Any]:
    """templates/project-bootstrap/ 配下の全 .j2 を render し output_dir に書出.

    AC-2 atomic: 1 ファイルでも render fail / unrendered 残存 / IO 失敗が
    あれば **何も書き出さない** (全 file を in-memory render 後 commit).

    Args:
      metadata     : 必須 placeholders 全 10 件を含む dict
      output_dir   : 書出先ルート (.j2 → .md / .html 等に拡張子を落とす)
      template_root: templates/project-bootstrap/ (None なら default)

    Returns:
      {
        "files_rendered": int,
        "files_written": list[str],       # output_dir 相対 path
        "metadata_used": dict,
        "template_root": str,
      }

    Raises:
      BootstrapError on:
        - metadata 不足 (validate_metadata)
        - .j2 file が存在しない
        - render 失敗 / unrendered 残存
        - output_dir が path traversal を起こす
    """
    if not _JINJA_AVAILABLE:
        raise BootstrapError("jinja2 SDK is not installed")
    if not isinstance(output_dir, Path):
        raise BootstrapError("output_dir must be pathlib.Path")
    merged_metadata = validate_metadata(metadata)

    root = (template_root or _default_template_root()).resolve()
    if not root.exists() or not root.is_dir():
        raise BootstrapError(f"template_root not found: {root}")

    j2_files = _iter_j2_files(root)
    if not j2_files:
        raise BootstrapError(f"no .j2 files under {root}")
    if len(j2_files) > MAX_RENDERED_FILES:
        raise BootstrapError(
            f"too many .j2 files ({len(j2_files)} > {MAX_RENDERED_FILES})"
        )

    env = _build_environment(root)

    # AC-2 atomic: 全 file を先に in-memory render. 1 件でも fail なら全 abort.
    rendered_pairs: list[tuple[Path, str]] = []
    for j2 in j2_files:
        rel = j2.relative_to(root)
        if str(rel).startswith("..") or str(rel).startswith("/"):
            raise BootstrapError(f"unsafe template rel path: {rel}")
        try:
            tmpl = env.get_template(str(rel).replace("\\", "/"))
            rendered = tmpl.render(**merged_metadata)
        except TemplateError as e:
            raise BootstrapError(f"render failed at {rel}: {e}") from e
        # AC-4 UNWANTED
        leftover = _detect_unrendered(rendered)
        if leftover:
            raise BootstrapError(
                f"unrendered placeholders remain in {rel}: {leftover[:5]}"
            )
        # 拡張子の .j2 を剥がす
        out_rel = rel.with_suffix("") if rel.suffix == ".j2" else rel
        # path length 制限
        if len(str(out_rel)) > MAX_OUTPUT_PATH_LEN:
            raise BootstrapError(
                f"output path too long: {out_rel} (> {MAX_OUTPUT_PATH_LEN})"
            )
        rendered_pairs.append((out_rel, rendered))

    # 全 render 成功 → ここで初めて output_dir へ書込 (atomic commit)
    output_root = output_dir.resolve()
    written: list[str] = []
    for out_rel, content in rendered_pairs:
        dst = (output_root / out_rel).resolve()
        # path traversal 防止
        try:
            dst.relative_to(output_root)
        except ValueError:
            raise BootstrapError(f"output path traversal blocked: {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        written.append(str(out_rel))

    return {
        "files_rendered": len(rendered_pairs),
        "files_written": written,
        "metadata_used": {k: merged_metadata[k] for k in REQUIRED_PLACEHOLDERS},
        "template_root": str(root),
    }
