"""T-012-02 spec test — red_line pattern detection middleware (approval.py 拡張).

REFACTOR audit: 既存 approval.py は CRUD のみで pattern 検出が不在 → 新規 module
`services/red_line_detector.py` を追加し、approval.py から optional に呼び出される
pre-flight hook として実装する.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : F-012 default_categories 5 種 + CLAUDE.md §5.4 4 種類の
                        red-line pattern を **個別 RedLineRule** として公開.
  AC-2 EVENT-DRIVEN  : detect_patterns(target) / evaluate_approval(title, content)
                        が dict / list を 2 秒以内に返却.
  AC-3 STATE-DRIVEN  : REFACTOR invariant — approval.py CRUD 無改変, no shell=True
                        / no os.system / no langgraph / langchain / litellm.
  AC-4 UNWANTED      : invalid input (空 / 非 str / 200KB 超) は RedLineDetectorError
                        raise. fixture false-positive ("DROP TABLE IF EXISTS" /
                        ".env.example") を hit しない.

Drift guard (anti-spec-drift):
  - 各 red-line pattern は **個別** test で verify. 1 つの汎用 regex で
    "動いた" と称することを禁止.
  - severity (block / warn / log) → action (block / warn / log) の 1:1
    対応を test.
  - `DROP TABLE IF EXISTS` / `.env.example` / `DELETE ... WHERE ...` のような
    fixture-shaped non-violations が false-positive で hit しないこと.
"""
from __future__ import annotations

import inspect
import re
import time
from pathlib import Path

import pytest

from services import red_line_detector as rld

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "backend" / "services" / "red_line_detector.py"
APPROVAL_ROUTER_PATH = REPO_ROOT / "backend" / "routers" / "approval.py"


def _source_code_only(path: Path) -> str:
    """Source with docstrings + comments stripped (forbidden-string checks)."""
    raw = path.read_text(encoding="utf-8")
    no_docstrings = re.sub(r'"""[\s\S]*?"""', "", raw)
    lines = []
    for line in no_docstrings.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        lines.append(line)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — module + public symbols + F-012 default_categories +
#                    CLAUDE.md §5.4 4 種類の red-line pattern が個別 rule
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_file_exists():
    assert MODULE_PATH.exists(), f"missing module: {MODULE_PATH}"


@pytest.mark.parametrize("sym", [
    "PHASE",
    "DEFAULT_RULES",
    "DEFAULT_CATEGORIES",
    "RedLineRule",
    "RedLineDetectorError",
    "detect_patterns",
    "evaluate_approval",
    "severity_to_action",
])
def test_ac1_public_symbols_exposed(sym):
    assert hasattr(rld, sym), f"missing public symbol: {sym}"


@pytest.mark.parametrize("cat", [
    "api_key_leak",
    "db_destructive",
    "force_push",
    "infinite_loop",
    "deploy_decision",
])
def test_ac1_f012_default_categories_present(cat):
    """F-012 features.json default_categories 5 種が DEFAULT_CATEGORIES に存在."""
    assert cat in rld.DEFAULT_CATEGORIES


def test_ac1_phase_identifier_explicit():
    assert rld.PHASE == "1"


def test_ac1_rule_dataclass_shape():
    """RedLineRule は frozen dataclass で 6 field を持つ."""
    fields = {f for f in rld.RedLineRule.__dataclass_fields__}
    assert fields == {
        "rule_key", "category", "pattern",
        "pattern_type", "severity", "description",
    }


@pytest.mark.parametrize("rule_name", [
    "RULE_SQL_DROP",
    "RULE_SQL_TRUNCATE",
    "RULE_SQL_DELETE_STAR",
    "RULE_GIT_FORCE_PUSH",
    "RULE_GIT_NO_VERIFY",
    "RULE_FS_DOTENV_COMMIT",
    "RULE_FS_CREDENTIALS_COMMIT",
    "RULE_FS_API_KEY_LITERAL",
    "RULE_DEP_AGPL",
    "RULE_LOOP_WHILE_TRUE",
    "RULE_DEPLOY_PROD",
])
def test_ac1_individual_rule_instances_exposed(rule_name):
    """drift guard: 各 red-line は **個別** RedLineRule instance.

    1 つの汎用 regex でまとめて detect する偽装を禁止する.
    """
    rule = getattr(rld, rule_name)
    assert isinstance(rule, rld.RedLineRule), f"{rule_name} must be RedLineRule"
    # 個別 rule_key を持つ (uniqueness は別 test)
    assert rule.rule_key, f"{rule_name}.rule_key empty"


def test_ac1_rule_keys_unique():
    """各 rule_key は unique (drift guard: コピペで同 key が増えていないか)."""
    keys = [r.rule_key for r in rld.DEFAULT_RULES]
    assert len(keys) == len(set(keys)), f"duplicate rule_keys: {keys}"


def test_ac1_rules_count_matches_individual_instances():
    """DEFAULT_RULES は 11 件の **個別** rule (drift guard)."""
    assert len(rld.DEFAULT_RULES) >= 11, (
        f"expected >= 11 individual rules (3 SQL + 2 git + 3 fs + 1 dep + "
        f"1 loop + 1 deploy), got {len(rld.DEFAULT_RULES)}"
    )


# ── CLAUDE.md §5.4 literal text mapping ──
# 1. DROP / TRUNCATE / DELETE * = 即セッション kill (3 個別 rule)
# 2. .env / 鍵ファイルのコミット (2 個別 rule: .env + credentials.json)
# 3. --no-verify / --force push (2 個別 rule)
# 4. AGPL 依存追加 (1 rule)


def test_ac1_db_destructive_has_three_individual_rules():
    """DROP / TRUNCATE / DELETE * を **別々の rule** として持つ (drift guard)."""
    db_rules = [r for r in rld.DEFAULT_RULES if r.category == "db_destructive"]
    assert len(db_rules) >= 3, f"db_destructive needs 3 individual rules: {db_rules}"
    keys = {r.rule_key for r in db_rules}
    assert "no_drop_table" in keys
    assert "no_truncate" in keys
    assert "no_delete_star" in keys


def test_ac1_force_push_has_two_individual_rules():
    """--force / --no-verify を **別々の rule** として持つ."""
    fp_rules = [r for r in rld.DEFAULT_RULES if r.category == "force_push"]
    assert len(fp_rules) >= 2
    keys = {r.rule_key for r in fp_rules}
    assert "no_force_push" in keys
    assert "no_skip_hooks" in keys


def test_ac1_api_key_leak_covers_env_and_credentials():
    """.env と credentials.json を **別々の rule** として持つ."""
    keys = {r.rule_key for r in rld.DEFAULT_RULES if r.category == "api_key_leak"}
    assert "no_env_commit" in keys
    assert "no_credentials_commit" in keys


def test_ac1_agpl_dependency_rule_present():
    keys = {r.rule_key for r in rld.DEFAULT_RULES if r.category == "deploy_decision"}
    assert "no_agpl_dependency" in keys


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — detect_patterns / evaluate_approval が dict/list
#                      を ≤2 秒で返却
# ══════════════════════════════════════════════════════════════════════


def test_ac2_detect_patterns_returns_list():
    out = rld.detect_patterns("SELECT 1")
    assert isinstance(out, list)


def test_ac2_evaluate_approval_returns_dict_with_keys():
    res = rld.evaluate_approval("safe title", "SELECT 1 FROM t WHERE id=1;")
    assert isinstance(res, dict)
    for k in ("allowed", "action", "violations", "categories", "phase"):
        assert k in res, f"missing key {k}"


def test_ac2_each_violation_has_required_fields():
    out = rld.detect_patterns("DROP TABLE users;")
    assert len(out) >= 1
    for v in out:
        for k in ("rule_key", "category", "severity", "action",
                  "pattern_type", "description"):
            assert k in v


def test_ac2_individual_drop_table_detected():
    """1 個別 pattern: DROP TABLE."""
    out = rld.detect_patterns("DROP TABLE users;")
    keys = {v["rule_key"] for v in out}
    assert "no_drop_table" in keys


def test_ac2_individual_truncate_detected():
    out = rld.detect_patterns("TRUNCATE TABLE audit_logs;")
    keys = {v["rule_key"] for v in out}
    assert "no_truncate" in keys


def test_ac2_individual_delete_star_detected():
    """WHERE 無しの DELETE FROM = DELETE * 相当."""
    out = rld.detect_patterns("DELETE FROM users;")
    keys = {v["rule_key"] for v in out}
    assert "no_delete_star" in keys


def test_ac2_individual_force_push_detected():
    out = rld.detect_patterns("git push origin main --force")
    keys = {v["rule_key"] for v in out}
    assert "no_force_push" in keys


def test_ac2_individual_force_push_short_flag_detected():
    out = rld.detect_patterns("git push -f origin main")
    keys = {v["rule_key"] for v in out}
    assert "no_force_push" in keys


def test_ac2_individual_no_verify_detected():
    out = rld.detect_patterns("git commit -m 'fix' --no-verify")
    keys = {v["rule_key"] for v in out}
    assert "no_skip_hooks" in keys


def test_ac2_individual_env_commit_detected():
    out = rld.detect_patterns("git add .env")
    keys = {v["rule_key"] for v in out}
    assert "no_env_commit" in keys


def test_ac2_individual_credentials_commit_detected():
    out = rld.detect_patterns("git commit credentials.json")
    keys = {v["rule_key"] for v in out}
    assert "no_credentials_commit" in keys


def test_ac2_individual_api_key_literal_detected():
    out = rld.detect_patterns(
        "API_KEY = sk-ant-abcdefghijklmnopqrstuvwxyz1234567890"
    )
    keys = {v["rule_key"] for v in out}
    assert "no_api_key_literal" in keys


def test_ac2_individual_agpl_detected():
    out = rld.detect_patterns('"license": "AGPL-3.0"')
    keys = {v["rule_key"] for v in out}
    assert "no_agpl_dependency" in keys


def test_ac2_individual_infinite_loop_detected():
    out = rld.detect_patterns("while True:\n    pass")
    keys = {v["rule_key"] for v in out}
    assert "no_infinite_loop" in keys


def test_ac2_individual_deploy_decision_detected():
    out = rld.detect_patterns("deploy to production now")
    keys = {v["rule_key"] for v in out}
    assert "deploy_decision_required" in keys


def test_ac2_severity_to_action_block():
    assert rld.severity_to_action(rld.SEVERITY_BLOCK) == rld.ACTION_BLOCK


def test_ac2_severity_to_action_warn():
    assert rld.severity_to_action(rld.SEVERITY_WARN) == rld.ACTION_WARN


def test_ac2_severity_to_action_log():
    assert rld.severity_to_action(rld.SEVERITY_LOG) == rld.ACTION_LOG


def test_ac2_severity_action_differ_per_violation():
    """severity が違えば action も違う (block != warn != log) — drift guard.

    1 つの severity / action で全部 "blocked" と返す偽装を禁止.
    """
    block_out = rld.detect_patterns("DROP TABLE users;")
    warn_out = rld.detect_patterns("deploy to production now")
    assert any(v["action"] == "block" for v in block_out)
    assert any(v["action"] == "warn" for v in warn_out)
    # 同じ input で違う action が混在しないこと
    block_keys = {v["rule_key"] for v in block_out}
    warn_keys = {v["rule_key"] for v in warn_out}
    assert block_keys.isdisjoint(warn_keys)


def test_ac2_evaluate_approval_block_when_block_severity_hit():
    res = rld.evaluate_approval("delete user data", "DROP TABLE users;")
    assert res["allowed"] is False
    assert res["action"] == "block"
    assert "db_destructive" in res["categories"]


def test_ac2_evaluate_approval_warn_when_only_warn_severity_hit():
    res = rld.evaluate_approval("deploy", "Please deploy to production now")
    assert res["action"] == "warn"
    # warn は allowed=True (承認キューに入る)
    assert res["allowed"] is True


def test_ac2_evaluate_approval_pass_when_no_match():
    res = rld.evaluate_approval(
        "Send weekly newsletter",
        "Compile metrics for this week and send to the team.",
    )
    assert res["allowed"] is True
    assert res["action"] == "pass"
    assert res["violations"] == []
    assert res["categories"] == []


def test_ac2_per_call_timeout_bound():
    """detect_patterns は ≤2 秒 (200KB target)."""
    target = "SELECT 1;\n" * 1000
    t0 = time.perf_counter()
    rld.detect_patterns(target)
    dt = time.perf_counter() - t0
    assert dt < 2.0, f"detect_patterns took {dt:.3f}s > 2s"


def test_ac2_deterministic_order():
    """violations 順は (category asc, rule_key asc) で deterministic."""
    target = (
        "DROP TABLE users;\n"
        "git push -f origin main\n"
        "git add .env\n"
        '"license": "AGPL-3.0"\n'
    )
    out = rld.detect_patterns(target)
    keys = [(v["category"], v["rule_key"]) for v in out]
    assert keys == sorted(keys), f"non-deterministic order: {keys}"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — REFACTOR invariant + no forbidden 依存 + no I/O
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_shell_true_no_os_system():
    src = _source_code_only(MODULE_PATH)
    assert "shell=True" not in src
    assert "os.system" not in src


@pytest.mark.parametrize("forbidden", [
    "langgraph", "langchain", "litellm",
])
def test_ac3_no_forbidden_main_path_deps(forbidden):
    """ADR-010: main path (claude-runner) で禁止. 本 module も同じ."""
    src = _source_code_only(MODULE_PATH)
    assert forbidden.lower() not in src.lower(), (
        f"forbidden dep {forbidden} found in module"
    )


def test_ac3_no_subprocess_no_filesystem_writes():
    """REFACTOR invariant: detector は pure function (副作用無し)."""
    src = _source_code_only(MODULE_PATH)
    assert "subprocess" not in src
    assert "open(" not in src  # ファイル I/O 無し
    assert ".write(" not in src
    assert "Path(" not in src or "Path(__file__)" in src  # __file__ 参照のみ許可


def test_ac3_approval_router_refactor_invariant_unmodified():
    """approval.py CRUD は無改変 (REFACTOR scope は detector 追加のみ).

    `routers/approval.py` の既存 4 endpoint (POST/GET/PATCH/DELETE) symbol は維持.
    """
    src = APPROVAL_ROUTER_PATH.read_text(encoding="utf-8")
    # router 関数 4 種
    assert "async def create_approval" in src
    assert "async def list_approvals" in src
    assert "async def update_approval" in src
    assert "async def delete_approval" in src


def test_ac3_detector_is_pure_function():
    """detect_patterns は同 input → 同 output (idempotent)."""
    target = "DROP TABLE x; git push -f"
    out1 = rld.detect_patterns(target)
    out2 = rld.detect_patterns(target)
    assert out1 == out2


def test_ac3_detect_patterns_is_sync_function():
    """REFACTOR: detector は同期関数 (approval.py async から await 不要)."""
    assert not inspect.iscoroutinefunction(rld.detect_patterns)
    assert not inspect.iscoroutinefunction(rld.evaluate_approval)


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid input rejection + false-positive guard
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad", [None, 123, 0.5, [], {}, b"bytes"])
def test_ac4_invalid_type_raises(bad):
    with pytest.raises(rld.RedLineDetectorError):
        rld.detect_patterns(bad)


def test_ac4_empty_target_raises():
    with pytest.raises(rld.RedLineDetectorError):
        rld.detect_patterns("")


def test_ac4_too_long_target_raises():
    big = "x" * (rld.MAX_TARGET_LEN + 1)
    with pytest.raises(rld.RedLineDetectorError):
        rld.detect_patterns(big)


def test_ac4_evaluate_approval_invalid_title_raises():
    with pytest.raises(rld.RedLineDetectorError):
        rld.evaluate_approval(123, "body")  # type: ignore[arg-type]


def test_ac4_evaluate_approval_invalid_content_raises():
    with pytest.raises(rld.RedLineDetectorError):
        rld.evaluate_approval("title", None)  # type: ignore[arg-type]


def test_ac4_evaluate_approval_both_empty_raises():
    with pytest.raises(rld.RedLineDetectorError):
        rld.evaluate_approval("", "")


def test_ac4_severity_to_action_unknown_raises():
    with pytest.raises(rld.RedLineDetectorError):
        rld.severity_to_action("explode")


# ── False-positive drift guards ──


def test_ac4_drift_guard_drop_table_if_exists_not_flagged():
    """`DROP TABLE IF EXISTS` (migration / test fixture) は false-positive 不可.

    CLAUDE.md §5.4 が殺すのは "本番 DB への DROP" であって、
    `CREATE TABLE IF NOT EXISTS ...; DROP TABLE IF EXISTS ...;` のような
    冪等な fixture 削除は対象外.
    """
    target = "DROP TABLE IF EXISTS migration_temp;"
    out = rld.detect_patterns(target)
    keys = {v["rule_key"] for v in out}
    assert "no_drop_table" not in keys, (
        f"false positive: {target!r} should not trigger no_drop_table"
    )


def test_ac4_drift_guard_drop_database_if_exists_not_flagged():
    target = "DROP DATABASE IF EXISTS shadow_db;"
    out = rld.detect_patterns(target)
    keys = {v["rule_key"] for v in out}
    assert "no_drop_table" not in keys


def test_ac4_drift_guard_dotenv_example_not_flagged():
    """`.env.example` / `.env.sample` は placeholder で許可 (lint-mock.sh §5)."""
    for safe in (".env.example", ".env.sample", ".env.template"):
        target = f"git add {safe}"
        out = rld.detect_patterns(target)
        keys = {v["rule_key"] for v in out}
        assert "no_env_commit" not in keys, (
            f"false positive: {safe} should not trigger no_env_commit"
        )


def test_ac4_drift_guard_delete_with_where_not_flagged():
    """WHERE 句のある DELETE は明示的 row 削除 → log 程度であって block しない."""
    target = "DELETE FROM users WHERE id = 42;"
    out = rld.detect_patterns(target)
    keys = {v["rule_key"] for v in out}
    assert "no_delete_star" not in keys, (
        "false positive: DELETE with WHERE should not trigger no_delete_star"
    )


def test_ac4_drift_guard_normal_text_not_flagged():
    """日常的な文章は何も hit しない."""
    target = "今週のレポートを作成して、チームに送ってください。"
    out = rld.detect_patterns(target)
    assert out == []


def test_ac4_drift_guard_safe_git_push_not_flagged():
    """通常の `git push origin main` は force_push に該当しない."""
    out = rld.detect_patterns("git push origin main")
    keys = {v["rule_key"] for v in out}
    assert "no_force_push" not in keys


def test_ac4_drift_guard_mit_license_not_flagged():
    """MIT / BSD / Apache license は AGPL に該当しない."""
    for safe in ('"license": "MIT"', '"license": "BSD-3-Clause"',
                 '"license": "Apache-2.0"'):
        out = rld.detect_patterns(safe)
        keys = {v["rule_key"] for v in out}
        assert "no_agpl_dependency" not in keys, (
            f"false positive: {safe} should not trigger AGPL rule"
        )


def test_ac4_no_state_mutation_on_invalid_input():
    """invalid input でも DB / 外部状態を mutate しない (pure func なので自明だが明示)."""
    src = _source_code_only(MODULE_PATH)
    # detector は db / 外部接続を持たない
    assert "aiosqlite" not in src
    assert "asyncpg" not in src
    assert "requests.post" not in src
    assert "httpx.post" not in src


def test_ac4_pattern_severity_block_implies_allowed_false():
    """block 系 hit があれば evaluate_approval.allowed=False を保証 (drift guard)."""
    # 全 block-severity rule を 1 件ずつ trigger
    triggers = [
        ("DROP TABLE x;", "no_drop_table"),
        ("TRUNCATE TABLE x;", "no_truncate"),
        ("DELETE FROM x;", "no_delete_star"),
        ("git push -f origin main", "no_force_push"),
        ("git commit --no-verify", "no_skip_hooks"),
        ("git add .env", "no_env_commit"),
        ("git add credentials.json", "no_credentials_commit"),
        ("sk-ant-abcdefghijklmnopqrstuvwxyz1234567890", "no_api_key_literal"),
        ('"license": "AGPL-3.0"', "no_agpl_dependency"),
    ]
    for target, expected_key in triggers:
        res = rld.evaluate_approval("op", target)
        keys = {v["rule_key"] for v in res["violations"]}
        assert expected_key in keys, f"{target!r} → expected {expected_key} hit"
        assert res["allowed"] is False, (
            f"{target!r} → block severity but allowed=True"
        )
        assert res["action"] == "block"
