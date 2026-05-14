#!/usr/bin/env python3
"""T-BTSTRAP-05: テンプレ更新時に全 workspace へ PR 自動作成 (CI 統合).

dry-run / apply / post-summary の 3 mode で動作する.
.github/workflows/template-propagation.yml から呼び出される.

AC マッピング:
  AC-1 EVENT     : --dry-run mode で全 workspace の差分件数を計算
  AC-2 UBIQUITOUS: 各 workspace の "would-change file count" を report
  AC-3 EVENT     : --apply mode で各 workspace に PR 作成
  AC-4 STATE     : 同 template version の PR 重複検出 (idempotent)
  AC-5 UNWANTED  : --continue-on-error で 1 失敗時も他は継続
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates/project-bootstrap"
CHANGELOG = ROOT / "templates/CHANGELOG.md"


def get_template_version() -> str:
    """templates/CHANGELOG.md の latest version を抽出.

    フォーマット例: "## v1.2 (2026-05-14)" → "v1.2"
    """
    if not CHANGELOG.exists():
        return "v0.0"
    content = CHANGELOG.read_text(encoding="utf-8")
    m = re.search(r"^##\s+(v\d+\.\d+)", content, re.MULTILINE)
    return m.group(1) if m else "v0.0"


def list_template_files() -> list[Path]:
    if not TEMPLATE_DIR.is_dir():
        return []
    return sorted(p for p in TEMPLATE_DIR.rglob("*") if p.is_file())


def list_active_workspaces(target: str = "") -> list[dict]:
    """active workspace のリストを返す.

    実運用では DB から SELECT id, name, github_repo FROM workspaces WHERE deleted_at IS NULL.
    現状は CI で動かない (DB なし) ので env 経由で固定リストを受ける.
    """
    if target:
        return [
            {"id": int(t.strip()), "name": f"ws-{t.strip()}", "github_repo": ""}
            for t in target.split(",") if t.strip()
        ]
    # CI/local stub: env から JSON 受ける
    raw = os.environ.get("ACTIVE_WORKSPACES_JSON", "[]")
    try:
        return json.loads(raw)
    except Exception:
        return []


def compute_diff_count(workspace: dict, files: list[Path]) -> int:
    """workspace に対する would-change file 数を計算 (stub).

    実運用では: clone workspace repo → diff template files → count changes.
    現状: file count を返す (== 全 file 上書き候補).
    """
    return len(files)


def cmd_dry_run() -> int:
    version = get_template_version()
    files = list_template_files()
    workspaces = list_active_workspaces()
    print(f"=== Template propagation dry-run ({version}) ===")
    print(f"Template files: {len(files)}")
    print(f"Active workspaces: {len(workspaces)}")
    if not workspaces:
        print("(no workspaces — env ACTIVE_WORKSPACES_JSON empty)")
        return 0
    summary = []
    for ws in workspaces:
        diff = compute_diff_count(ws, files)
        summary.append({"workspace_id": ws["id"], "name": ws.get("name", "?"), "would_change": diff})
        print(f"  ws #{ws['id']} ({ws.get('name','?')}): {diff} files would change")
    out = ROOT / ".propagation-dry-run.json"
    out.write_text(json.dumps({"version": version, "summary": summary}, indent=2))
    print(f"\nSummary written to {out}")
    return 0


def cmd_apply(continue_on_error: bool = False, target: str = "") -> int:
    """各 workspace に PR を作成 (idempotent).

    実運用では PyGithub で repo.create_pull() する.
    現状: 計画の出力のみ.
    """
    version = get_template_version()
    workspaces = list_active_workspaces(target)
    print(f"=== Template propagation apply ({version}) ===")
    if not workspaces:
        print("(no workspaces)")
        return 0
    failures = []
    for ws in workspaces:
        try:
            pr_title = f"chore: migrate to template {version}"
            print(f"  ws #{ws['id']}: would create PR '{pr_title}'")
            # 実装: PyGithub で github_repo に PR 作成
            # idempotent: 既に同タイトル PR があれば skip
        except Exception as e:
            failures.append({"workspace_id": ws["id"], "error": str(e)[:200]})
            if not continue_on_error:
                print(f"  ws #{ws['id']}: FAILED - {e}")
                return 1
            print(f"  ws #{ws['id']}: FAILED (continue) - {e}")
    if failures:
        print(f"\n{len(failures)}/{len(workspaces)} workspaces failed:")
        for f in failures:
            print(f"  - ws #{f['workspace_id']}: {f['error']}")
        return 0 if continue_on_error else 1
    print(f"\nAll {len(workspaces)} workspaces processed.")
    return 0


def cmd_post_summary() -> int:
    """commit comment として summary を post する (CI step)."""
    out = ROOT / ".propagation-dry-run.json"
    if not out.exists():
        print("(no dry-run summary to post)")
        return 0
    data = json.loads(out.read_text())
    print("=== Summary ===")
    print(f"Version: {data['version']}")
    for s in data["summary"]:
        print(f"  ws #{s['workspace_id']} ({s['name']}): {s['would_change']} files")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--post-summary", action="store_true")
    ap.add_argument("--continue-on-error", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        return cmd_dry_run()
    if args.apply:
        target = os.environ.get("TARGET_WORKSPACES", "")
        return cmd_apply(continue_on_error=args.continue_on_error, target=target)
    if args.post_summary:
        return cmd_post_summary()
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
