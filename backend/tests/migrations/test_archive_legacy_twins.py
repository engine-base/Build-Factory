"""T-V3-D-04: legacy twin tables ARCHIVE batch — static AC validation.

検証対象 migration:
    supabase/migrations/20260516140000_archive_legacy_twins.sql

AC マッピング (docs/audit/2026-05-16_v3/T-V3-D-04.md):
    AC-F1 UBIQUITOUS : 4 legacy table を _archived_<name> へ RENAME (DROP しない)
    AC-F2 EVENT      : legacy router 経路は backend に存在しない (HTTP 410 Gone は
                       FastAPI 全 404 を返す既定挙動で代替. 静的に「ファイルがない」を
                       確認する. AC-F3 と重複するが意図確認のため別 test を立てる.)
    AC-F3 EVENT      : lint-mock.sh rule #3 が legacy router 残留を検出しない
                       (= backend/routers/legacy_*.py と backend/app/models/legacy/
                       の 0 残留)
    AC-F4 UNWANTED   : 残存 active FK があれば migration が raise exception で abort

DB を立てずに SQL テキストと repo file layout を静的検証する.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MIGS = ROOT / "supabase" / "migrations"
MIG_FILE = MIGS / "20260516140000_archive_legacy_twins.sql"

LEGACY_TABLES = ["tasks", "ai_employee_config", "pull_requests", "repos"]
ARCHIVED_NAMES = [f"_archived_{t}" for t in LEGACY_TABLES]
MODERN_TABLES = ["bf_tasks", "ai_employees", "prs", "github_repos"]


@pytest.fixture(scope="module")
def src() -> str:
    assert MIG_FILE.exists(), f"migration file missing: {MIG_FILE}"
    return MIG_FILE.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# AC-F1 UBIQUITOUS: rename to _archived_<name> (not DROP)
# ──────────────────────────────────────────────────────────────────────────


def test_migration_does_not_drop_legacy_tables(src: str) -> None:
    """AC-F1: DROP TABLE は使用禁止 (audit history 保全のため RENAME 必須)."""
    # 純 DROP TABLE 行 (コメント除く) の検出
    lines = [
        ln for ln in src.splitlines()
        if not ln.lstrip().startswith("--")
    ]
    body = "\n".join(lines)
    assert not re.search(
        r"\bDROP\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)", body, re.IGNORECASE,
    ), "DROP TABLE 検出: ARCHIVE migration は RENAME のみ許可"


@pytest.mark.parametrize("src_t,dst_t", list(zip(LEGACY_TABLES, ARCHIVED_NAMES, strict=True)))
def test_each_legacy_table_is_renamed(src: str, src_t: str, dst_t: str) -> None:
    """AC-F1: 4 件すべてが _archived_<name> へ rename される.

    DO ブロック内の `pairs` 配列 (src,dst) のペアを文字列で確認.
    """
    pattern = rf"\[\s*'{re.escape(src_t)}'\s*,\s*'{re.escape(dst_t)}'\s*\]"
    assert re.search(pattern, src), (
        f"rename pair missing: {src_t} -> {dst_t}"
    )


def test_uses_alter_table_rename_to(src: str) -> None:
    """AC-F1: 実 rename は ALTER TABLE ... RENAME TO 構文."""
    assert re.search(
        r"ALTER\s+TABLE\s+%I\s+RENAME\s+TO\s+%I", src, re.IGNORECASE,
    ), "ALTER TABLE ... RENAME TO statement missing"


def test_idempotent_skip_check(src: str) -> None:
    """AC-F1 (idempotent): 既に _archived_<name> が存在したら CONTINUE."""
    assert "already archived as" in src
    assert "CONTINUE" in src


# ──────────────────────────────────────────────────────────────────────────
# AC-F2 EVENT-DRIVEN: legacy router/model paths are gone (returns 410/404 via
# FastAPI default). 静的に「ファイルが存在しない」を確認する.
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("router_name", [
    "legacy_tasks.py",
    "legacy_pull_requests.py",
    "legacy_repos.py",
    "legacy_ai_employee_config.py",
])
def test_legacy_router_file_absent(router_name: str) -> None:
    """AC-F2: 4 legacy router file は backend/routers/ に存在しない."""
    p = ROOT / "backend" / "routers" / router_name
    assert not p.exists(), f"legacy router still present: {p}"


def test_legacy_models_directory_absent() -> None:
    """AC-F2 / AC-F3: backend/app/models/legacy/ ディレクトリは削除済."""
    legacy_dir = ROOT / "backend" / "app" / "models" / "legacy"
    assert not legacy_dir.exists(), (
        f"legacy models directory still present: {legacy_dir}"
    )


# ──────────────────────────────────────────────────────────────────────────
# AC-F3 EVENT-DRIVEN: lint-mock.sh rule #3 (archive-residue) 0 residue
# ──────────────────────────────────────────────────────────────────────────


def test_lint_mock_rule3_aware_of_legacy_routers() -> None:
    """AC-F3: lint-mock.sh rule #3 (ARCHIVE 残留) に legacy_* router 検査が含まれる."""
    lint = (ROOT / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "T-V3-D-04" in lint, (
        "lint-mock.sh rule #3 must reference T-V3-D-04 to assert "
        "legacy router/model residue is 0"
    )
    # 検査対象 path のリテラル参照を保証
    assert "legacy_tasks.py" in lint
    assert "legacy_pull_requests.py" in lint
    assert "legacy_repos.py" in lint
    assert "legacy_ai_employee_config.py" in lint


# ──────────────────────────────────────────────────────────────────────────
# AC-F4 UNWANTED: active external FK が残れば migration が abort
# ──────────────────────────────────────────────────────────────────────────


def test_migration_has_pre_archive_fk_guard(src: str) -> None:
    """AC-F4: rename 前に active 外部 FK を列挙し 1 件でも残れば RAISE EXCEPTION."""
    assert "RAISE EXCEPTION" in src, "guard EXCEPTION raise missing"
    # 4 legacy table すべてを guard 対象に含むこと
    for t in LEGACY_TABLES:
        assert f"'{t}'" in src, f"legacy table {t} not in guard list"
    # FK 走査ロジック (pg_constraint contype='f') の存在
    assert "pg_constraint" in src
    assert "contype = 'f'" in src
    # legacy 群内 FK は除外する条件
    assert "<> ALL (legacy_tables)" in src


def test_migration_uses_format_for_safe_identifier(src: str) -> None:
    """AC-F4 (safety): rename / alter は format(%I) で identifier-quoted."""
    assert re.search(r"format\([^)]*%I", src), (
        "format(%I) で identifier escape されていない. SQL injection 余地あり."
    )


def test_pr_comments_fk_is_repointed_to_prs(src: str) -> None:
    """AC-F4 (active FK remap): pr_comments.pr_id を modern prs(id) に再配線する."""
    assert "pr_comments" in src
    assert "REFERENCES prs(id)" in src
    assert "pr_comments_pr_id_fkey" in src


def test_post_repoint_guard_runs(src: str) -> None:
    """AC-F4 (post check): repoint 後にもう一度 FK 残留を再確認する guard が存在."""
    assert "archive_guard_post" in src
    assert "POST-REPOINT residual FK" in src


# ──────────────────────────────────────────────────────────────────────────
# 追加: ARCHIVE marker comment + RLS lockdown
# ──────────────────────────────────────────────────────────────────────────


def test_archived_tables_have_comment_marker(src: str) -> None:
    """ARCHIVED comment marker (audit forensic 用) が COMMENT ON TABLE で付く."""
    assert "ARCHIVED 2026-05-16 by T-V3-D-04" in src
    assert "COMMENT ON TABLE" in src


@pytest.mark.parametrize("arch", ARCHIVED_NAMES)
def test_archived_table_rls_locked_to_service_role(src: str, arch: str) -> None:
    """_archived_* は service_role のみアクセス可."""
    # archived_tables 配列に含まれる
    assert f"'{arch}'" in src
    # service_role only policy 名規約
    assert "_service_role_only" in src


def test_modern_table_names_are_documented_in_header(src: str) -> None:
    """header コメントで modern 対応表 (legacy -> modern) を明示."""
    for legacy, modern in zip(LEGACY_TABLES, MODERN_TABLES, strict=True):
        # 同一行に legacy と modern が両方出ること
        pattern = rf"`{re.escape(legacy)}`.*`{re.escape(modern)}`"
        assert re.search(pattern, src), (
            f"header mapping missing: {legacy} -> {modern}"
        )
