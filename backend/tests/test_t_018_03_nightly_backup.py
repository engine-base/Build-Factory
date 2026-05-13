"""T-018-03: nightly-backup workflow — 4 AC 機械 invariant 検証.

NEW OPS タスク. .github/workflows/nightly-backup.yml を yaml parse +
static 検査.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : nightly-backup.yml が cron '0 17 * * *' +
                       workflow_dispatch + 3 job (backup-database /
                       backup-storage / verify-backup) +
                       concurrency='nightly-backup' / cancel-in-progress=false /
                       permissions: contents: read.
  AC-2 EVENT-DRIVEN  : backup-database + backup-storage parallel /
                       verify-backup needs: [両方] / artifact 名 db-* /
                       storage-* with retention-days=7 / sha256 出力 +
                       検証.
  AC-3 STATE-DRIVEN  : 全 secret は env: 経由 / no string interpolation
                       in run: / production data に touch しない (read-only).
  AC-4 UNWANTED      : 全 action を specific version で pin (@v4) /
                       no @main / @master / no floating ref / size < 100
                       byte で fail / sha256 mismatch で fail.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "nightly-backup.yml"
DEPLOY_STAGING = REPO_ROOT / ".github" / "workflows" / "deploy-staging.yml"


@pytest.fixture(scope="module")
def workflow():
    if yaml is None:
        pytest.skip("PyYAML not installed")
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — file + trigger + 3 jobs + concurrency + permissions
# ══════════════════════════════════════════════════════════════════════


def test_ac1_workflow_file_exists():
    assert WORKFLOW.exists()


def test_ac1_workflow_yaml_valid(workflow):
    assert isinstance(workflow, dict)


def test_ac1_workflow_name(workflow):
    assert workflow.get("name") == "nightly-backup"


def test_ac1_cron_schedule_jst_2am():
    """0 17 * * * UTC = JST 02:00. yaml.safe_load は 'on' を True (bool)
    に変換するので raw text で確認."""
    src = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r'cron:\s*["\']0\s+17\s+\*\s+\*\s+\*["\']', src), (
        "cron must be '0 17 * * *' (UTC 17:00 = JST 02:00)"
    )


def test_ac1_workflow_dispatch_with_reason_input():
    """workflow_dispatch + reason input (audit trail)."""
    src = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in src
    assert "reason:" in src
    assert "required: true" in src


def test_ac1_three_jobs(workflow):
    jobs = workflow.get("jobs", {})
    expected = {"backup-database", "backup-storage", "verify-backup"}
    assert expected.issubset(set(jobs.keys())), (
        f"missing jobs: {expected - set(jobs.keys())}"
    )


def test_ac1_concurrency_group_set(workflow):
    conc = workflow.get("concurrency", {})
    assert isinstance(conc, dict)
    assert conc.get("group") == "nightly-backup"
    # cancel-in-progress=false (履歴保持)
    assert conc.get("cancel-in-progress") is False


def test_ac1_permissions_contents_read(workflow):
    """最小権限: contents: read のみ (write 不要)."""
    perms = workflow.get("permissions", {})
    assert perms.get("contents") == "read"
    # write 系の権限が含まれていない
    for key, val in perms.items():
        assert val != "write", f"unexpected write permission: {key}"


def test_ac1_db_job_runs_on_ubuntu_latest(workflow):
    db = workflow["jobs"]["backup-database"]
    assert db.get("runs-on") == "ubuntu-latest"


def test_ac1_storage_job_runs_on_ubuntu_latest(workflow):
    s = workflow["jobs"]["backup-storage"]
    assert s.get("runs-on") == "ubuntu-latest"


def test_ac1_verify_job_runs_on_ubuntu_latest(workflow):
    v = workflow["jobs"]["verify-backup"]
    assert v.get("runs-on") == "ubuntu-latest"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — parallel jobs + needs chain + artifact retention 7d
# ══════════════════════════════════════════════════════════════════════


def test_ac2_db_job_has_no_needs(workflow):
    """backup-database は他 job に依存せず parallel 実行."""
    db = workflow["jobs"]["backup-database"]
    assert "needs" not in db, "backup-database must have no needs (parallel)"


def test_ac2_storage_job_has_no_needs(workflow):
    s = workflow["jobs"]["backup-storage"]
    assert "needs" not in s, "backup-storage must have no needs (parallel)"


def test_ac2_verify_job_needs_both(workflow):
    v = workflow["jobs"]["verify-backup"]
    needs = v.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    needs_set = set(needs)
    assert "backup-database" in needs_set
    assert "backup-storage" in needs_set


def test_ac2_db_artifact_uploaded_with_7_day_retention():
    src = WORKFLOW.read_text(encoding="utf-8")
    # actions/upload-artifact@v4 + retention-days: 7
    assert re.search(r"actions/upload-artifact@v4", src)
    assert re.search(r"retention-days:\s*7", src)


def test_ac2_db_artifact_name_uses_date_suffix():
    src = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"db-\$\{?DATE\}?\.sql\.gz", src), (
        "DB artifact filename must include date suffix"
    )


def test_ac2_storage_artifact_name_uses_date_suffix():
    src = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"storage-\$\{?DATE\}?\.tar\.gz", src), (
        "Storage artifact filename must include date suffix"
    )


def test_ac2_db_job_outputs_sha256():
    src = WORKFLOW.read_text(encoding="utf-8")
    # outputs section + sha256 step output
    assert re.search(r"outputs:", src)
    assert re.search(r"sha256:\s*\$\{\{\s*steps\.hash\.outputs\.sha256\s*\}\}", src)


def test_ac2_verify_job_downloads_both_artifacts():
    src = WORKFLOW.read_text(encoding="utf-8")
    assert "actions/download-artifact@v4" in src
    assert re.search(r"name:\s*db-backup", src)
    assert re.search(r"name:\s*storage-backup", src)


def test_ac2_verify_compares_sha256():
    """sha256 mismatch 時に exit 1."""
    src = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r'sha256sum\b', src)
    assert re.search(r'ACTUAL\b.*EXPECTED|EXPECTED\b.*ACTUAL', src, re.DOTALL)
    # 検証失敗で exit 1
    assert "exit 1" in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — secrets via env / no shell injection / read-only
# ══════════════════════════════════════════════════════════════════════


def test_ac3_secrets_passed_via_env_section():
    """secrets は env: 経由で受け取る (shell injection 防止)."""
    src = WORKFLOW.read_text(encoding="utf-8")
    # PGURL: ${{ secrets.SUPABASE_DB_URL }} のように env: の値として宣言
    assert re.search(
        r"env:\s*\n\s+PGURL:\s*\$\{\{\s*secrets\.SUPABASE_DB_URL\s*\}\}",
        src,
    )
    assert re.search(
        r"STORAGE_URL:\s*\$\{\{\s*secrets\.SUPABASE_STORAGE_URL\s*\}\}",
        src,
    )
    assert re.search(
        r"SERVICE_KEY:\s*\$\{\{\s*secrets\.SUPABASE_SERVICE_ROLE_KEY\s*\}\}",
        src,
    )


def test_ac3_no_secret_string_interpolation_in_run():
    """`run:` ブロック直接に ${{ secrets.X }} を書かない (env: 経由のみ)."""
    src = WORKFLOW.read_text(encoding="utf-8")
    # `run:` で始まる行を集めて、 その後 ${{ secrets.X }} が出現しないか確認
    # ※ run: の YAML block scalar の中で `${{ secrets... }}` を書くと
    #    bash の単純な string interpolation でなく Actions 側の事前展開と
    #    なるが、 special char (`;`,`$`,etc.) を含む値が直接 shell に
    #    展開されるので injection リスク. env: 経由で受けるのが best practice.
    lines = src.splitlines()
    in_run_block = False
    indent = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("run:") or stripped.startswith("run: |"):
            in_run_block = True
            indent = len(line) - len(stripped)
            continue
        if in_run_block:
            cur_indent = len(line) - len(line.lstrip())
            if line.strip() and cur_indent <= indent:
                in_run_block = False
                continue
            # run: の本体に secrets.X が直接書かれていないことを確認
            if "secrets." in line:
                # secrets. を直接書くのは禁止
                raise AssertionError(
                    f"secret used inline in run: block (use env: instead):\n  {line}"
                )


def test_ac3_pg_dump_uses_no_owner_no_acl():
    """production data に owner / acl を持ち込まない (clean dump)."""
    src = WORKFLOW.read_text(encoding="utf-8")
    assert "pg_dump --no-owner --no-acl" in src


def test_ac3_storage_uses_list_only_no_object_download():
    """T-018-03 Phase 1: object metadata (list) のみ. 中身は downloadしない."""
    src = WORKFLOW.read_text(encoding="utf-8")
    # /object/list endpoint を使う
    assert "/object/list/" in src
    # /object/download や /object/sign は使わない (Phase 1)
    assert "/object/download" not in src
    assert "/object/sign" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — pinned versions / no @main / size check / hash mismatch
# ══════════════════════════════════════════════════════════════════════


def test_ac4_all_actions_pinned_to_v4():
    """actions/checkout@v4 / actions/upload-artifact@v4 / download-artifact@v4."""
    src = WORKFLOW.read_text(encoding="utf-8")
    # actions/checkout@v4
    assert re.search(r"actions/checkout@v4\b", src)
    assert re.search(r"actions/upload-artifact@v4\b", src)
    assert re.search(r"actions/download-artifact@v4\b", src)


def test_ac4_no_floating_action_refs():
    """@main / @master / @latest / @sha 以外 (float) 禁止."""
    src = WORKFLOW.read_text(encoding="utf-8")
    # uses: org/repo@<ref> パターンを抽出
    refs = re.findall(r"uses:\s*([a-zA-Z0-9_./-]+)@([a-zA-Z0-9_.-]+)", src)
    assert refs, "no actions found in workflow"
    forbidden = {"main", "master", "latest", "develop"}
    for action, ref in refs:
        assert ref not in forbidden, (
            f"action {action} pinned to floating ref @{ref} (forbidden)"
        )
        # v数字 か 40-char SHA か x.y.z 形式
        assert re.match(r"^(v\d+|\d+\.\d+|\d+\.\d+\.\d+|[a-f0-9]{40})$", ref), (
            f"action {action} version {ref} not in pinned format"
        )


def test_ac4_size_check_under_100_bytes_fails():
    """pg_dump / storage tarball 出力 size < 100 byte で fail (corruption 検出)."""
    src = WORKFLOW.read_text(encoding="utf-8")
    # size check pattern
    assert re.search(r"SIZE.*-lt\s+100", src)
    assert "too small" in src or "suspiciously small" in src


def test_ac4_verify_fails_on_hash_mismatch():
    """sha256 mismatch で exit 1."""
    src = WORKFLOW.read_text(encoding="utf-8")
    # ACTUAL != EXPECTED で exit 1
    assert re.search(
        r'\[\s*"\$\{ACTUAL\}"\s*!=\s*"\$\{EXPECTED\}"\s*\]',
        src,
    )


def test_ac4_upload_artifact_fails_if_no_files():
    """if-no-files-found: error (silent skip 防止)."""
    src = WORKFLOW.read_text(encoding="utf-8")
    assert "if-no-files-found: error" in src


def test_ac4_no_hardcoded_secret_in_workflow():
    src = WORKFLOW.read_text(encoding="utf-8")
    # Anthropic / Supabase service-key
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sbp_[A-Za-z0-9]{20,}", src)
    # supabase service key パターン (JWT-like) も直接書かれていない
    assert not re.search(r"eyJ[A-Za-z0-9_=-]{20,}\.[A-Za-z0-9_=-]{20,}\.", src)


def test_ac4_no_t_018_03_dep_in_existing_workflows():
    """既存 workflow に T-018-03 依存追加なし."""
    for path in (REPO_ROOT / ".github" / "workflows" / "ci.yml", DEPLOY_STAGING):
        src = path.read_text(encoding="utf-8")
        assert "T-018-03" not in src


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_018_03_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-018-03"), None)
    assert t is not None
    generic = [
        "as specified by feature F-018",
        "When the implementation step for T-018-03 is triggered",
        "While the new feature for T-018-03 is enabled",
        "If invalid input or unauthorized actor is detected during T-018-03",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-018-03 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "nightly-backup.yml",
        "0 17 * * *",
        "backup-database",
        "backup-storage",
        "verify-backup",
        "pg_dump",
        "sha256",
        "retention-days=7",
        "concurrency",
        "actions/checkout@v4",
    ):
        assert sym in full, f"T-018-03 AC missing concrete symbol: {sym}"


def test_tickets_t_018_03_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-018-03"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("deploy-staging.yml" in f for f in files)
    assert any("ci.yml" in f for f in files)


def test_tickets_t_018_03_canonical_ears_types():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-018-03"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"]
