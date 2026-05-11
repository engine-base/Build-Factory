"""T-013-03: PR 自動作成 + HTML diff 注釈レビュー資料添付.

unified diff (git diff 形式) を構造化し、 HTML レビュー資料を生成する.
注釈ルール:
  - 追加行 (+) は緑、削除行 (-) は赤、@@ hunk header は灰背景
  - file path ごとに section + collapse
  - 各 hunk 単位で行番号付き
  - PR title / body / metadata を上部に summary 表示
  - reviewer 用 checklist (4 AC + cov + regression) を末尾に

セーフティ:
  - diff size 上限 (5MB) で truncate
  - HTML エスケープ済 (XSS 防止)
  - title / body / branch validation

公開 API:
  - parse_unified_diff(diff_text) -> list[FileDiff]
  - render_review_html(meta, file_diffs, *, checklist) -> str
  - DiffStats / FileDiff / Hunk dataclass
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


class PRAnnotatorError(RuntimeError):
    pass


MAX_DIFF_SIZE = 5_000_000      # 5 MB
MAX_TITLE_LEN = 200
MAX_BODY_LEN = 50_000
MAX_BRANCH_LEN = 200
MAX_FILES = 500
MAX_HUNKS_PER_FILE = 200


@dataclass
class HunkLine:
    kind: str  # "context" / "add" / "remove" / "header"
    old_lineno: Optional[int]
    new_lineno: Optional[int]
    text: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "old_lineno": self.old_lineno,
            "new_lineno": self.new_lineno,
            "text": self.text,
        }


@dataclass
class Hunk:
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[HunkLine] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "header": self.header,
            "old_start": self.old_start,
            "old_count": self.old_count,
            "new_start": self.new_start,
            "new_count": self.new_count,
            "lines": [l.to_dict() for l in self.lines],
        }


@dataclass
class FileDiff:
    path: str
    old_path: Optional[str] = None
    is_new: bool = False
    is_deleted: bool = False
    hunks: list[Hunk] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "old_path": self.old_path,
            "is_new": self.is_new,
            "is_deleted": self.is_deleted,
            "additions": self.additions,
            "deletions": self.deletions,
            "hunks": [h.to_dict() for h in self.hunks],
        }


@dataclass
class DiffStats:
    files: int = 0
    additions: int = 0
    deletions: int = 0
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "files": self.files,
            "additions": self.additions,
            "deletions": self.deletions,
            "truncated": self.truncated,
        }


@dataclass
class PRMeta:
    title: str
    body: str = ""
    branch: str = ""
    base_branch: str = "main"
    author: Optional[str] = None
    generated_at: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────
# Unified diff parser
# ──────────────────────────────────────────────────────────────────────────


_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$",
)


def parse_unified_diff(diff_text: str) -> tuple[list[FileDiff], DiffStats]:
    """unified diff (git diff) を FileDiff list + 全体 stats に解析."""
    if not isinstance(diff_text, str):
        raise PRAnnotatorError("diff_text must be a string")
    truncated = False
    if len(diff_text) > MAX_DIFF_SIZE:
        diff_text = diff_text[:MAX_DIFF_SIZE]
        truncated = True

    files: list[FileDiff] = []
    current: Optional[FileDiff] = None
    current_hunk: Optional[Hunk] = None
    old_lineno = 0
    new_lineno = 0

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current = None
            current_hunk = None
            # path 推定は ++ +++ で更新する
            continue
        if line.startswith("--- "):
            # old path
            p = line[4:].strip()
            if p.startswith("a/"):
                p = p[2:]
            elif p == "/dev/null":
                p = None
            if current is None:
                current = FileDiff(path="(unknown)")
                files.append(current)
                if len(files) > MAX_FILES:
                    truncated = True
                    break
            current.old_path = p
            current.is_new = p is None
            continue
        if line.startswith("+++ "):
            p = line[4:].strip()
            if p.startswith("b/"):
                p = p[2:]
            elif p == "/dev/null":
                p = None
            if current is None:
                current = FileDiff(path="(unknown)")
                files.append(current)
                if len(files) > MAX_FILES:
                    truncated = True
                    break
            if p is None:
                current.is_deleted = True
                # deleted file: --- 側のパスを採用
                if current.old_path and current.path == "(unknown)":
                    current.path = current.old_path
            else:
                current.path = p
            continue
        m = _HUNK_RE.match(line)
        if m:
            if current is None:
                continue
            old_start = int(m.group(1))
            old_count = int(m.group(2) or 1)
            new_start = int(m.group(3))
            new_count = int(m.group(4) or 1)
            current_hunk = Hunk(
                header=line,
                old_start=old_start, old_count=old_count,
                new_start=new_start, new_count=new_count,
            )
            current.hunks.append(current_hunk)
            if len(current.hunks) > MAX_HUNKS_PER_FILE:
                truncated = True
                # cap and move on
                current.hunks = current.hunks[:MAX_HUNKS_PER_FILE]
                current_hunk = None
                continue
            old_lineno = old_start
            new_lineno = new_start
            continue
        # body line
        if current is None or current_hunk is None:
            continue
        if line.startswith("+"):
            current_hunk.lines.append(HunkLine(
                kind="add", old_lineno=None,
                new_lineno=new_lineno, text=line[1:],
            ))
            current.additions += 1
            new_lineno += 1
        elif line.startswith("-"):
            current_hunk.lines.append(HunkLine(
                kind="remove", old_lineno=old_lineno,
                new_lineno=None, text=line[1:],
            ))
            current.deletions += 1
            old_lineno += 1
        elif line.startswith(" "):
            current_hunk.lines.append(HunkLine(
                kind="context", old_lineno=old_lineno,
                new_lineno=new_lineno, text=line[1:],
            ))
            old_lineno += 1
            new_lineno += 1
        # else: "\ No newline at end of file" 等は skip

    # files 内で重複した FileDiff を排除しつつ、 += +++ のみで作られたケース
    # ──────────────────────────────────────────────────────────────
    seen_paths: set[str] = set()
    deduped: list[FileDiff] = []
    for f in files or [current] if current else []:
        if f is None:
            continue
        if f.path in seen_paths:
            continue
        seen_paths.add(f.path)
        deduped.append(f)

    # current が files に未挿入なら追加
    if current is not None and current not in files:
        files.append(current)
    # 重複排除
    dedup_files: list[FileDiff] = []
    seen: set[str] = set()
    for f in files:
        if f.path in seen:
            continue
        seen.add(f.path)
        dedup_files.append(f)
    files = dedup_files

    stats = DiffStats(
        files=len(files),
        additions=sum(f.additions for f in files),
        deletions=sum(f.deletions for f in files),
        truncated=truncated,
    )
    return files, stats


# ──────────────────────────────────────────────────────────────────────────
# HTML renderer
# ──────────────────────────────────────────────────────────────────────────

_HTML_STYLE = """
<style>
 body { font-family: 'JetBrains Mono', ui-monospace, monospace;
        color: #0F172A; background: #fafafa; max-width: 1080px;
        margin: 24px auto; padding: 0 16px; line-height: 1.5; }
 header { border-bottom: 4px solid #1a6648; padding-bottom: 12px;
          margin-bottom: 24px; }
 h1 { font-size: 22px; margin: 0 0 6px; color: #1a6648; }
 .meta { color: #475569; font-size: 13px; }
 .stats { background: #fff; padding: 10px 12px;
          border-left: 4px solid #1a6648; margin: 12px 0; font-size: 13px; }
 .file { background: #fff; border: 1px solid #e2e8f0; border-radius: 6px;
         margin: 14px 0; overflow: hidden; }
 .file-head { background: #f1f5f9; padding: 8px 12px;
              font-weight: 600; font-size: 13px; }
 .hunk-head { background: #e2e8f0; padding: 4px 8px;
              font-size: 12px; color: #475569; }
 .line { display: flex; font-size: 13px; }
 .line .ln { width: 50px; text-align: right; color: #94a3b8;
             padding-right: 8px; user-select: none; }
 .line .text { flex: 1; white-space: pre-wrap; padding-left: 4px; }
 .line.add { background: #ecfdf5; }
 .line.add .text { color: #047857; }
 .line.remove { background: #fef2f2; }
 .line.remove .text { color: #b91c1c; }
 .line.context .text { color: #334155; }
 .checklist { background: #fff; border: 1px solid #e2e8f0;
              padding: 12px 16px; border-radius: 6px; margin-top: 24px; }
 .checklist li { margin: 4px 0; }
 footer { margin-top: 32px; color: #94a3b8; font-size: 12px;
          text-align: center; }
</style>
""".strip()


_DEFAULT_CHECKLIST = [
    "AC-1 UBIQUITOUS の機械検証 (pytest test_ac1_*) が PASS",
    "AC-2 EVENT-DRIVEN の機械検証 (2 秒以内 + {detail:{code,message}})",
    "AC-3 STATE-DRIVEN の機械検証 (audit emit + backwards compat)",
    "AC-4 UNWANTED の機械検証 (4xx + structured + state 不変)",
    "cov >= 70% (新規 service/router)",
    "全体 pytest regression なし",
    "bash scripts/pre-commit-check.sh 全項目 PASS",
    "Lucide Icons のみ (絵文字なし)",
    "Tailwind eb-500 / shadcn 規約遵守 (FE のみ)",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _esc(s: Optional[str]) -> str:
    return html.escape(s or "")


def render_review_html(
    meta: PRMeta,
    file_diffs: Iterable[FileDiff],
    *,
    stats: Optional[DiffStats] = None,
    checklist: Optional[list[str]] = None,
) -> str:
    if not isinstance(meta, PRMeta):
        raise PRAnnotatorError("meta must be PRMeta")
    if not meta.title or not meta.title.strip():
        raise PRAnnotatorError("PR title must not be empty")
    if len(meta.title) > MAX_TITLE_LEN:
        raise PRAnnotatorError(f"PR title must be <= {MAX_TITLE_LEN} chars")
    if len(meta.body or "") > MAX_BODY_LEN:
        raise PRAnnotatorError(f"PR body must be <= {MAX_BODY_LEN} chars")
    if meta.branch and len(meta.branch) > MAX_BRANCH_LEN:
        raise PRAnnotatorError(f"branch must be <= {MAX_BRANCH_LEN} chars")

    files = list(file_diffs)
    if stats is None:
        stats = DiffStats(
            files=len(files),
            additions=sum(f.additions for f in files),
            deletions=sum(f.deletions for f in files),
            truncated=False,
        )
    items = checklist or _DEFAULT_CHECKLIST

    parts: list[str] = [
        "<!doctype html>",
        '<html lang="ja"><head>',
        '<meta charset="utf-8">',
        '<meta name="generator" content="Build-Factory T-013-03">',
        f'<title>{_esc(meta.title)} — Review</title>',
        _HTML_STYLE,
        "</head><body>",
        "<header>",
        f'<h1>{_esc(meta.title)}</h1>',
        f'<div class="meta">',
        f'branch: {_esc(meta.branch)} → {_esc(meta.base_branch)} ',
        f'/ author: {_esc(meta.author)} ',
        f'/ generated: {_esc(meta.generated_at or _now_iso())}',
        "</div>",
        "</header>",
        '<div class="stats">',
        f'files: {stats.files} / +{stats.additions} / -{stats.deletions}'
        + (' (TRUNCATED)' if stats.truncated else ''),
        "</div>",
    ]
    if meta.body:
        parts.append(
            f'<section><h2 style="font-size:16px;margin:16px 0 8px;'
            f'border-left:3px solid #1a6648;padding-left:8px;">'
            f'PR Description</h2>'
            f'<pre style="white-space:pre-wrap;background:#fff;'
            f'padding:10px;border:1px solid #e2e8f0;border-radius:4px;">'
            f'{_esc(meta.body)}</pre></section>'
        )

    for f in files:
        head = _esc(f.path)
        if f.is_new:
            head += " (new)"
        if f.is_deleted:
            head += " (deleted)"
        head += f" +{f.additions} -{f.deletions}"
        parts.append(
            f'<div class="file">'
            f'<div class="file-head">{head}</div>'
        )
        for h in f.hunks:
            parts.append(
                f'<div class="hunk-head">{_esc(h.header)}</div>'
            )
            for line in h.lines:
                ln = ""
                if line.kind == "add" and line.new_lineno is not None:
                    ln = f"+{line.new_lineno}"
                elif line.kind == "remove" and line.old_lineno is not None:
                    ln = f"-{line.old_lineno}"
                elif line.kind == "context" and line.new_lineno is not None:
                    ln = str(line.new_lineno)
                parts.append(
                    f'<div class="line {line.kind}">'
                    f'<span class="ln">{ln}</span>'
                    f'<span class="text">{_esc(line.text)}</span>'
                    f'</div>'
                )
        parts.append("</div>")

    parts.append('<div class="checklist"><h2 style="font-size:15px;'
                  'margin:0 0 8px;">Review Checklist</h2><ul>')
    for item in items:
        parts.append(f"<li>{_esc(item)}</li>")
    parts.append("</ul></div>")

    parts.append(
        f'<footer>Generated by Build-Factory (T-013-03) '
        f'/ {_esc(meta.generated_at or _now_iso())}</footer>'
    )
    parts.append("</body></html>")
    return "\n".join(parts)
