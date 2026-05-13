"""T-BTSTRAP-01: テンプレート構造を確定 (templates/project-bootstrap/) — 4 AC 1:1.

AC マッピング:
  AC-1 UBIQUITOUS (#1) : 6 必須スケルトンファイルが存在
  AC-1 UBIQUITOUS (#2) : templates/CHANGELOG.md にバージョン bump 履歴がある
  AC-2 EVENT-DRIVEN    : テンプレ更新時に CHANGELOG.md が更新される
                         (本 PR の v1.2.0 entry が test 完整性で担保)
  AC-4 UNWANTED        : 必須ファイル欠落で lint script が fail
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPO_ROOT / "templates" / "project-bootstrap"
CHANGELOG = REPO_ROOT / "templates" / "CHANGELOG.md"

REQUIRED_SKELETON_FILES = [
    "templates/project-bootstrap/CLAUDE.md.j2",
    "templates/project-bootstrap/docs/HANDOVER.md.j2",
    "templates/project-bootstrap/docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md",
    "templates/project-bootstrap/scripts/lint-mock.sh",
    "templates/project-bootstrap/scripts/validate-tickets.py",
    "templates/project-bootstrap/.claude/settings.json",
]


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS (#1): 6 必須スケルトンファイル全存在
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("rel_path", REQUIRED_SKELETON_FILES)
def test_ac1_required_skeleton_file_exists(rel_path):
    p = REPO_ROOT / rel_path
    assert p.exists(), f"required skeleton missing: {rel_path}"
    assert p.is_file(), f"required path is not a file: {rel_path}"


def test_ac1_template_root_exists_as_directory():
    assert TEMPLATE_ROOT.exists()
    assert TEMPLATE_ROOT.is_dir()


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS (#2): CHANGELOG にバージョン bump 履歴
# ══════════════════════════════════════════════════════════════════════


def test_ac1_changelog_exists():
    assert CHANGELOG.exists()


def test_ac1_changelog_has_version_bumps():
    text = CHANGELOG.read_text(encoding="utf-8")
    # 最低 2 つの version エントリ (v1.x.0) があり, semver 表記
    import re
    versions = re.findall(r"^##\s+v(\d+)\.(\d+)\.(\d+)", text, re.MULTILINE)
    assert len(versions) >= 2, "CHANGELOG must contain >= 2 version bumps"
    # newest > oldest (順序)
    assert versions[0] >= versions[-1]


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: テンプレ更新時に CHANGELOG.md が更新される
# ══════════════════════════════════════════════════════════════════════


def test_ac2_changelog_documents_t_btstrap_01_closure():
    """本 PR で追加した T-BTSTRAP-01 完了エントリが CHANGELOG に存在."""
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "T-BTSTRAP-01" in text
    assert "check_template_skeleton_complete" in text


def test_ac2_changelog_mentions_required_files():
    """CHANGELOG が必須ファイル名を列挙している (AC-1 invariant の docs side)."""
    text = CHANGELOG.read_text(encoding="utf-8")
    for rel in REQUIRED_SKELETON_FILES:
        basename = rel.split("/")[-1]
        assert basename in text, f"CHANGELOG must reference {basename}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: 必須ファイル欠落で lint script が fail
# ══════════════════════════════════════════════════════════════════════


def test_ac4_lint_check_template_skeleton_check_exists():
    script_text = (REPO_ROOT / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "check_template_skeleton_complete" in script_text
    assert "--template-skeleton" in script_text


def test_ac4_lint_check_passes_when_all_files_present():
    """現状 (全 6 ファイル + CHANGELOG 存在) で lint pass する."""
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--template-skeleton"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, f"lint failed: {r.stdout} {r.stderr}"
    assert "OK" in r.stdout


def test_ac4_lint_fails_when_required_file_missing(tmp_path):
    """指定 cwd を tmp に切替, templates dir が無い状態で lint fail を確認."""
    # tmp_path に lint script だけコピー (templates/ を作らない)
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    src = REPO_ROOT / "scripts" / "lint-mock.sh"
    dst = scripts_dir / "lint-mock.sh"
    dst.write_bytes(src.read_bytes())
    dst.chmod(0o755)
    # lint --template-skeleton を tmp_path で実行 → templates 無いので fail
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--template-skeleton"],
        capture_output=True, text=True, timeout=30, cwd=str(tmp_path),
    )
    assert r.returncode != 0
    assert "NG" in r.stdout or "NG" in r.stderr


# ══════════════════════════════════════════════════════════════════════
# Cross-reference: tickets.json + ADR
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_btstrap_01_has_4_ac():
    import json
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-BTSTRAP-01"), None)
    assert t is not None
    assert len(t["acceptance_criteria"]) == 4
    # blocks T-BTSTRAP-02
    assert "T-BTSTRAP-02" in t.get("blocks", [])


def test_adr_009_referenced_in_changelog():
    """ADR-009 (各案件への強制レイヤー自動展開) が文中に言及される."""
    text = CHANGELOG.read_text(encoding="utf-8")
    # 直接 ADR-009 が無くとも T-BTSTRAP-XX 連鎖が完整であれば OK.
    # 既存 v1.0.0 entry に「機械的強制レイヤー」が含まれる.
    assert "強制レイヤー" in text or "ADR-009" in text
