"""T-016-02: artifact → Markdown 変換 (obsidian_sync 連携).

artifact (dict) を Obsidian 互換 Markdown に整形する.

frontmatter (YAML):
  - id / type / title / created_at / updated_at / workspace_id /
    task_id / artifact_id / tags / status

body:
  - # タイトル
  - メタデータ table
  - data.summary / data.content / data.markdown を優先表示
  - data dict は keys を level-2 heading でレンダリング (再帰なし)

セーフティ:
  - title 200 chars, tags 50 items / each 100 chars
  - body 1MB cap
  - YAML escape (改行 / quote)

公開 API:
  - render_artifact_md(artifact) -> str
  - build_obsidian_path(artifact) -> Path  (data/obsidian/artifacts/<type>/<id>.md)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


class ArtifactMDError(RuntimeError):
    pass


MAX_TITLE_LEN = 200
MAX_TAG_COUNT = 50
MAX_TAG_LEN = 100
MAX_BODY_SIZE = 1_000_000   # 1 MB
MAX_TYPE_LEN = 100

# Obsidian YAML reserved (前後空白 / quote)
_YAML_NEEDS_QUOTE_RE = re.compile(r"[:#&\*!?\|\-\[\]\{\}<>=%@\"\`\n\t]|^\s|\s$")


def _yaml_scalar(value: Any) -> str:
    """単一スカラを YAML safe な文字列に."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        value = str(value)
    s = value
    if "\n" in s:
        # block scalar literal (|)
        indented = "\n".join("  " + ln for ln in s.splitlines())
        return "|\n" + indented
    if _YAML_NEEDS_QUOTE_RE.search(s) or s == "":
        # double-quoted string
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def _yaml_list(items: Iterable[str]) -> str:
    parts = []
    for item in items:
        parts.append(f"  - {_yaml_scalar(item)}")
    if not parts:
        return "[]"
    return "\n" + "\n".join(parts)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_artifact(a: dict) -> dict:
    if not isinstance(a, dict):
        raise ArtifactMDError("artifact must be a dict")
    title = a.get("title")
    if title is not None and not isinstance(title, str):
        raise ArtifactMDError("title must be a string when provided")
    if isinstance(title, str) and len(title) > MAX_TITLE_LEN:
        raise ArtifactMDError(f"title must be <= {MAX_TITLE_LEN} chars")
    typ = a.get("type")
    if typ is not None:
        if not isinstance(typ, str):
            raise ArtifactMDError("type must be a string when provided")
        if len(typ) > MAX_TYPE_LEN:
            raise ArtifactMDError(f"type must be <= {MAX_TYPE_LEN} chars")
    tags = a.get("category_tags") or a.get("tags") or []
    if not isinstance(tags, list):
        raise ArtifactMDError("tags must be a list")
    if len(tags) > MAX_TAG_COUNT:
        raise ArtifactMDError(f"tags must be <= {MAX_TAG_COUNT} items")
    for t in tags:
        if not isinstance(t, str):
            raise ArtifactMDError("each tag must be a string")
        if len(t) > MAX_TAG_LEN:
            raise ArtifactMDError(f"each tag must be <= {MAX_TAG_LEN} chars")
    return a


def _normalize_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def render_artifact_md(artifact: dict) -> str:
    """artifact dict → Obsidian frontmatter + Markdown body."""
    a = _validate_artifact(artifact)
    title = (a.get("title") or "").strip() or "Untitled Artifact"
    artifact_id = _normalize_id(a.get("id") or a.get("artifact_id"))
    typ = (a.get("type") or "artifact").strip()
    workspace_id = a.get("workspace_id")
    task_id = a.get("task_id")
    status = a.get("status") or "draft"
    tags = a.get("category_tags") or a.get("tags") or []
    created_at = a.get("created_at") or _now_iso()
    updated_at = a.get("updated_at") or created_at

    # frontmatter
    lines: list[str] = ["---"]
    lines.append(f"id: {_yaml_scalar(artifact_id)}")
    lines.append(f"type: {_yaml_scalar(typ)}")
    lines.append(f"title: {_yaml_scalar(title)}")
    lines.append(f"status: {_yaml_scalar(status)}")
    if workspace_id is not None:
        lines.append(f"workspace_id: {_yaml_scalar(workspace_id)}")
    if task_id is not None:
        lines.append(f"task_id: {_yaml_scalar(task_id)}")
    lines.append(f"created_at: {_yaml_scalar(created_at)}")
    lines.append(f"updated_at: {_yaml_scalar(updated_at)}")
    lines.append(f"tags:{_yaml_list(tags)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")

    # body — prefer explicit content fields
    data = a.get("data") if isinstance(a.get("data"), dict) else {}
    for key in ("markdown", "content", "summary", "body"):
        v = data.get(key) or a.get(key)
        if isinstance(v, str) and v.strip():
            lines.append(v.rstrip())
            lines.append("")
            break
    else:
        # fallback: data dict を section ごとに render
        if isinstance(data, dict) and data:
            for k, v in data.items():
                lines.append(f"## {k}")
                if isinstance(v, (dict, list)):
                    import json as _json
                    lines.append("```json")
                    lines.append(_json.dumps(v, ensure_ascii=False, indent=2))
                    lines.append("```")
                else:
                    lines.append(str(v) if v is not None else "")
                lines.append("")

    rendered = "\n".join(lines)
    if len(rendered) > MAX_BODY_SIZE:
        raise ArtifactMDError(
            f"rendered Markdown exceeds {MAX_BODY_SIZE} bytes"
        )
    return rendered


# ──────────────────────────────────────────────────────────────────────────
# Obsidian path resolver
# ──────────────────────────────────────────────────────────────────────────


_REPO_ROOT = Path(__file__).resolve().parents[2]
_OBSIDIAN_ROOT = _REPO_ROOT / "data" / "obsidian"


def _safe_segment(s: str) -> str:
    """path traversal 防御."""
    if not isinstance(s, str) or not s.strip():
        raise ArtifactMDError("path segment must not be empty")
    if "/" in s or ".." in s or s.startswith(".") or "\\" in s:
        raise ArtifactMDError(f"unsafe path segment: {s!r}")
    if len(s) > 200:
        raise ArtifactMDError("path segment must be <= 200 chars")
    if not re.match(r"^[A-Za-z0-9_.\-]+$", s):
        raise ArtifactMDError(
            f"path segment contains invalid characters: {s!r}"
        )
    return s


def build_obsidian_path(artifact: dict, *, root: Optional[Path] = None) -> Path:
    """artifact から保存先パスを構築 (data/obsidian/artifacts/<type>/<id>.md)."""
    if not isinstance(artifact, dict):
        raise ArtifactMDError("artifact must be a dict")
    aid = _normalize_id(artifact.get("id") or artifact.get("artifact_id"))
    if not aid:
        raise ArtifactMDError("artifact.id must not be empty")
    typ = (artifact.get("type") or "artifact").strip()
    base = root if root is not None else _OBSIDIAN_ROOT
    return base / "artifacts" / _safe_segment(typ) / f"{_safe_segment(aid)}.md"


# ──────────────────────────────────────────────────────────────────────────
# 高レベル: render + save
# ──────────────────────────────────────────────────────────────────────────


def save_artifact_md(
    artifact: dict,
    *,
    root: Optional[Path] = None,
) -> dict:
    """artifact を Markdown に変換して保存."""
    rendered = render_artifact_md(artifact)
    path = build_obsidian_path(artifact, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return {
        "path": str(path),
        "size": len(rendered),
        "id": str(artifact.get("id") or artifact.get("artifact_id")),
    }
