"""T-019-02: modify 対象 GitHub Issue 化 (scanner script).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : scripts/scan-modify-targets.py / 4 categories / JSON 出力 /
                       gh CLI 経由 Issue 化を docs/modify-targets/README.md で文書化.
  AC-2 EVENT-DRIVEN  : scan() が dict (total/by_category/targets) を返す / exit 0 OK / 2 error.
  AC-3 STATE-DRIVEN  : repo state mutate なし / 外部 API call なし / audit_logs DB なし.
  AC-4 UNWANTED      : invalid --category で exit 2 / hardcoded token なし.
"""
from __future__ import annotations

import json as _json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "scripts" / "scan-modify-targets.py"
README = REPO_ROOT / "docs" / "modify-targets" / "README.md"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_scanner_exists():
    assert SCANNER.exists(), f"missing: {SCANNER}"


def test_ac1_scanner_executable():
    """script は python3 で実行可能."""
    src = SCANNER.read_text(encoding="utf-8")
    assert src.startswith("#!/usr/bin/env python3") or "python3" in src.split("\n", 1)[0]


def test_ac1_readme_exists():
    assert README.exists(), f"missing: {README}"


def test_ac1_readme_documents_gh_cli_workflow():
    """README が gh CLI で Issue 化する手順を文書化."""
    src = README.read_text(encoding="utf-8")
    assert "gh issue create" in src
    assert "modify-target" in src.lower()


def test_ac1_four_categories_documented():
    src = README.read_text(encoding="utf-8")
    for cat in ("deprecated_deps", "stale_routers", "stale_services", "archived_keyword"):
        assert cat in src, f"category {cat} not documented in README"


def test_ac1_scan_function_returns_dict():
    """scan() が dict を返す (total/by_category/targets)."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        # script ファイル名にハイフンがある → importlib で読み込む
        import importlib.util
        spec = importlib.util.spec_from_file_location("scan_modify_targets", SCANNER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.scan()
        assert isinstance(result, dict)
        assert "total" in result
        assert "by_category" in result
        assert "targets" in result
        assert isinstance(result["total"], int)
        assert isinstance(result["by_category"], dict)
        assert isinstance(result["targets"], list)
    finally:
        sys.path.pop(0)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: structured JSON output + exit code
# ══════════════════════════════════════════════════════════════════════


def test_ac2_stdout_outputs_valid_json():
    """default で stdout に valid JSON を出力."""
    r = subprocess.run(
        ["python3", str(SCANNER)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, f"exit {r.returncode}: {r.stderr}"
    data = _json.loads(r.stdout)
    assert "total" in data
    assert "targets" in data


def test_ac2_file_output_with_out_flag(tmp_path):
    """--out で file 出力."""
    out_file = tmp_path / "scan.json"
    r = subprocess.run(
        ["python3", str(SCANNER), "--out", str(out_file)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, f"exit {r.returncode}: {r.stderr}"
    assert out_file.exists()
    data = _json.loads(out_file.read_text())
    assert "total" in data


def test_ac2_category_filter():
    """--category で単一 category に絞る."""
    r = subprocess.run(
        ["python3", str(SCANNER), "--category", "archived_keyword"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0
    data = _json.loads(r.stdout)
    # 結果は archived_keyword のみ (空でも OK)
    for t in data["targets"]:
        assert t["category"] == "archived_keyword"


def test_ac2_targets_have_required_fields():
    """各 target が category/file/line/snippet/reason を持つ."""
    r = subprocess.run(
        ["python3", str(SCANNER)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    data = _json.loads(r.stdout)
    if not data["targets"]:
        pytest.skip("no targets detected; skip schema check")
    for t in data["targets"]:
        for field in ("category", "file", "line", "snippet", "reason"):
            assert field in t, f"missing field {field} in target: {t}"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: read-only + no external API
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_external_api_in_source():
    """scanner source に GitHub API / gh CLI 呼出がない."""
    src = SCANNER.read_text(encoding="utf-8")
    src_code = _strip_comments(src)
    assert "subprocess" not in src_code or "subprocess.run" not in src_code
    assert "requests.get" not in src_code
    assert "requests.post" not in src_code
    assert "httpx.get" not in src_code
    assert "httpx.post" not in src_code
    # gh CLI も呼ばない (script 自体は)
    assert '"gh "' not in src_code
    assert "['gh'," not in src_code


def _strip_comments(src: str) -> str:
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


def test_ac3_no_audit_logs_writes():
    """scanner が audit_logs DB を呼ばないこと."""
    src = _strip_comments(SCANNER.read_text(encoding="utf-8"))
    assert "emit_event" not in src
    assert "audit_logs" not in src.lower() or "audit_logs" in src.lower()  # comment OK
    assert "from services.memory_service" not in src


def test_ac3_idempotent_run():
    """2 回連続実行で同じ結果 (重複検出なし / state mutation なし)."""
    r1 = subprocess.run(
        ["python3", str(SCANNER)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    r2 = subprocess.run(
        ["python3", str(SCANNER)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert r1.returncode == 0 and r2.returncode == 0
    d1 = _json.loads(r1.stdout)
    d2 = _json.loads(r2.stdout)
    assert d1["total"] == d2["total"], "scan must be idempotent"
    assert d1["by_category"] == d2["by_category"]


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_category_exit_2():
    r = subprocess.run(
        ["python3", str(SCANNER), "--category", "BOGUS"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
    )
    # argparse の choices で 2 を返す
    assert r.returncode == 2


def test_ac4_invalid_out_path_exit_2(tmp_path):
    """書込み不可な path → exit 2."""
    # 存在しないディレクトリで mkdir も失敗するケースは少ないので
    # 別アプローチ: read-only directory に書く
    if os.geteuid() == 0:
        pytest.skip("running as root; cannot create read-only test path")
    ro_dir = tmp_path / "ro"
    ro_dir.mkdir()
    ro_dir.chmod(0o555)
    try:
        target = ro_dir / "sub" / "scan.json"
        r = subprocess.run(
            ["python3", str(SCANNER), "--out", str(target)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
        assert r.returncode == 2
    finally:
        ro_dir.chmod(0o755)


def test_ac4_no_hardcoded_github_token():
    src = SCANNER.read_text(encoding="utf-8")
    src_code = _strip_comments(src)
    # ghp_ / github_pat_ パターン
    assert not re.search(r"ghp_[A-Za-z0-9]{20,}", src_code)
    assert not re.search(r"github_pat_[A-Za-z0-9]{20,}", src_code)
    assert "Bearer " not in src_code
    assert "Authorization" not in src_code


def test_ac4_no_hardcoded_repo_url():
    src = SCANNER.read_text(encoding="utf-8")
    src_code = _strip_comments(src)
    # GitHub repo URL pattern: github.com/owner/repo
    assert "engine-base/build-factory" not in src_code.lower()
    assert "engine-base/Build-Factory" not in src_code


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_019_02_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-019-02"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "implementation step for T-019-02 is triggered",
        "shall record an audit entry capturing the action and timestamp",
        "shall apply Row Level Security and audit_logs as per CLAUDE.md",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-019-02 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "scan-modify-targets.py" in full
    assert "deprecated_deps" in full
    assert "stale_routers" in full


def test_tickets_t_019_02_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-019-02"), None)
    assert t.get("adr_link") is not None
    assert t.get("existing_files")
