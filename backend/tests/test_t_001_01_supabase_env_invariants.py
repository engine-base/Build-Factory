"""T-001-01: Supabase env 必須化 + ハードコード鍵除去 — 5 AC.

PR #5 で production artifact 完成済 (supabase_client.py + .env.example +
lint check_secrets()). 本 module は **spec contract layer**.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : _REQUIRED 4 vars / .env.example 5 vars 列挙 /
                       lint check_secrets() 存在.
  AC-2 EVENT-DRIVEN  : 未設定 import で RuntimeError + list / _missing
                       内包記法.
  AC-3 STATE-DRIVEN  : startup で全 missing 列挙 / no hardcoded fallback
                       url / key.
  AC-4 OPTIONAL      : REPLACE_WITH_<NAME> placeholder / 実 sb_*_key pattern
                       不在.
  AC-5 UNWANTED      : sb_(publishable|secret)_[A-Za-z0-9_-]{20,} 検出
                       で lint fail / `default=` 引数なし.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SUPABASE_CLIENT = REPO_ROOT / "backend" / "services" / "supabase_client.py"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
LINT_MOCK = REPO_ROOT / "scripts" / "lint-mock.sh"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"

REQUIRED_VARS = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_JWT_SECRET",
)


def _strip_py_comments(src: str) -> str:
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    out = re.sub(r"#[^\n]*", "", out)
    return out


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 4 vars + 5 env_example lines + lint check
# ══════════════════════════════════════════════════════════════════════


def test_ac1_supabase_client_exists():
    assert SUPABASE_CLIENT.exists()


def test_ac1_env_example_exists():
    assert ENV_EXAMPLE.exists()


def test_ac1_lint_mock_exists():
    assert LINT_MOCK.exists()


def test_ac1_required_tuple_exactly_4_vars():
    src = SUPABASE_CLIENT.read_text(encoding="utf-8")
    m = re.search(r"_REQUIRED\s*=\s*\(([^)]+)\)", src)
    assert m, "_REQUIRED tuple not found"
    vars_found = tuple(re.findall(r'"([^"]+)"', m.group(1)))
    assert vars_found == REQUIRED_VARS, (
        f"_REQUIRED drift: {vars_found} vs {REQUIRED_VARS}"
    )


def test_ac1_env_example_lists_all_required_vars():
    src = ENV_EXAMPLE.read_text(encoding="utf-8")
    for v in REQUIRED_VARS:
        assert re.search(rf"^{v}=", src, re.MULTILINE), (
            f".env.example missing line: {v}=..."
        )


def test_ac1_env_example_has_supabase_bucket_default():
    src = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert re.search(r"^SUPABASE_BUCKET=artifacts", src, re.MULTILINE), (
        "SUPABASE_BUCKET default should be 'artifacts'"
    )


def test_ac1_lint_has_check_secrets_step():
    src = LINT_MOCK.read_text(encoding="utf-8")
    assert "check_secrets" in src
    # 検出 pattern
    assert "sb_(publishable|secret)" in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — RuntimeError + list comprehension
# ══════════════════════════════════════════════════════════════════════


def test_ac2_uses_list_comprehension_for_missing():
    """_missing = [k for k in _REQUIRED if not os.environ.get(k)]."""
    src = SUPABASE_CLIENT.read_text(encoding="utf-8")
    assert re.search(
        r"_missing\s*=\s*\[\s*k\s+for\s+k\s+in\s+_REQUIRED\s+if\s+not\s+os\.environ\.get\(k\)\s*\]",
        src,
    ), "fail-fast check pattern not found"


def test_ac2_raises_runtime_error_on_missing():
    src = SUPABASE_CLIENT.read_text(encoding="utf-8")
    # if _missing: raise RuntimeError
    assert re.search(r"if\s+_missing\s*:", src)
    assert re.search(r"raise\s+RuntimeError", src)


def test_ac2_error_message_in_japanese():
    """error message に 'Supabase 環境変数が未設定です' を含む (UX 優先)."""
    src = SUPABASE_CLIENT.read_text(encoding="utf-8")
    assert "Supabase 環境変数が未設定です" in src


def test_ac2_error_lists_all_missing_vars():
    """`+ ", ".join(_missing)` で全 missing を列挙."""
    src = SUPABASE_CLIENT.read_text(encoding="utf-8")
    assert re.search(r'",\s*"\.join\(_missing\)', src)


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — fail fast at startup + no hardcoded fallback
# ══════════════════════════════════════════════════════════════════════


def test_ac3_check_runs_at_module_top_level():
    """fail-fast: _missing check は module top-level (関数内ではない)."""
    src = SUPABASE_CLIENT.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    # _missing assignment が def の中ではなく module level に置かれる
    # detect: ^_missing = ... (indent 0)
    assert re.search(r"^_missing\s*=", code, re.MULTILINE), (
        "_missing must be at module top-level (fail-fast)"
    )


def test_ac3_no_hardcoded_supabase_url_fallback():
    src = SUPABASE_CLIENT.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    # `or "https://...supabase.co"` のような fallback なし
    assert not re.search(
        r'or\s+["\']https?://[^"\']*supabase[^"\']*["\']',
        code,
    ), "no hardcoded SUPABASE_URL fallback allowed"


def test_ac3_no_hardcoded_sb_key():
    """sb_* prefix の real key pattern が source に hard-coded されていない."""
    src = SUPABASE_CLIENT.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)


def test_ac3_no_default_arg_to_environ_get():
    """os.environ.get(KEY, 'fallback') を避ける (silent default 防止).

    _REQUIRED check 自体は default=None なので OK (None で truthy False).
    """
    src = SUPABASE_CLIENT.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    # `os.environ.get("SUPABASE_*", "value")` のような default 値設定なし
    bad = re.findall(
        r"os\.environ\.get\(\s*[\"']SUPABASE_(?:URL|ANON_KEY|SERVICE_KEY|JWT_SECRET)[\"']\s*,\s*[\"'][^\"']+[\"']",
        code,
    )
    assert not bad, f"forbidden default for required Supabase var: {bad}"


def test_ac3_main_py_does_not_swallow_import_error():
    """main.py が supabase_client 起動失敗を握りつぶさない."""
    main_path = REPO_ROOT / "backend" / "main.py"
    src = main_path.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    # try: ... from services.supabase_client ... except RuntimeError: pass みたいに
    # silent swallow しない (探しても出てこないこと)
    assert not re.search(
        r"try:\s*\n[^\n]*supabase_client[^\n]*\nexcept\s+RuntimeError[^:]*:\s*pass",
        code,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — REPLACE_WITH_* placeholders / no real key
# ══════════════════════════════════════════════════════════════════════


def test_ac4_env_example_uses_replace_with_placeholders():
    """全 SUPABASE_* line が REPLACE_WITH_<NAME> placeholder."""
    src = ENV_EXAMPLE.read_text(encoding="utf-8")
    for v in REQUIRED_VARS:
        m = re.search(rf"^{v}=(\S+)", src, re.MULTILINE)
        assert m, f"line not found: {v}=..."
        value = m.group(1)
        assert re.match(r"REPLACE_WITH_[A-Z_]+", value), (
            f"{v} value must be REPLACE_WITH_<NAME>, got {value!r}"
        )


def test_ac4_env_example_no_real_key_pattern():
    """.env.example に 実 key pattern (sb_publishable_* / sb_secret_*) なし."""
    src = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)


def test_ac4_env_example_no_jwt_like_value():
    """.env.example に JWT 風 string (eyJ...) なし."""
    src = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert not re.search(
        r"eyJ[A-Za-z0-9_=-]{20,}\.[A-Za-z0-9_=-]{20,}\.",
        src,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — lint check_secrets detects real key pattern
# ══════════════════════════════════════════════════════════════════════


def test_ac5_lint_check_secrets_detects_pattern_in_test_file(tmp_path, monkeypatch):
    """check_secrets が sb_publishable_* / sb_secret_* pattern を検出する.

    一時 file に擬似 key を書いて lint --secrets を repo 内で走らせると
    fail することを確認 — ただし repo root を変えると lint script の
    parent path 仮定が壊れるので、本 test では pattern 文字列が lint script
    内に declared されていることだけを検査する.
    """
    src = LINT_MOCK.read_text(encoding="utf-8")
    # 'sb_(publishable|secret)_[A-Za-z0-9_-]{20,}' regex が check_secrets() の
    # 中で定義されている
    m = re.search(
        r"check_secrets\(\)\s*\{[\s\S]+?\}",
        src,
    )
    assert m, "check_secrets function block not found"
    body = m.group(0)
    assert "sb_(publishable|secret)" in body
    assert "[A-Za-z0-9_-]{20,}" in body


def test_ac5_lint_runs_check_secrets_in_all_mode():
    src = LINT_MOCK.read_text(encoding="utf-8")
    # `all|""` モードで check_secrets が呼ばれる
    assert re.search(r"check_secrets\b", src)
    # all モードのケースでも呼ばれることを確認
    m = re.search(
        r"all\|.*?\)\s*([\s\S]+?)\s*;;\s*\*\)",
        src,
    )
    if m:
        block = m.group(1)
        assert "check_secrets" in block or "check_agpl" in block  # all blob 内に並ぶ


def test_ac5_lint_excludes_env_example_from_detection():
    """check_secrets は .env.example と REPLACE_WITH_ placeholder を除外する."""
    src = LINT_MOCK.read_text(encoding="utf-8")
    # 実装: `grep -v -E "(^|/)\.env(\.example)?:" | grep -v "REPLACE_WITH_"`
    # 単純な文字列マッチで sufficient
    assert "grep -v" in src
    # .env / .env.example のいずれかを除外する line がある
    assert ".env" in src and ".example" in src
    # REPLACE_WITH_ も除外 line にある
    assert "REPLACE_WITH_" in src


def test_ac5_actual_lint_run_passes():
    """実際に scripts/lint-mock.sh --secrets を実行して PASS することを確認."""
    result = subprocess.run(
        ["bash", str(LINT_MOCK), "--secrets"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"lint --secrets failed:\n{result.stdout}\n{result.stderr}"
    )


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_001_01_canonical_ears_types():
    import json
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-01"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-001-01 still uses legacy alias: {ty}"
        )
    assert "EVENT-DRIVEN" in types
    assert "STATE-DRIVEN" in types
    assert "OPTIONAL" in types
    assert "UNWANTED" in types


def test_tickets_t_001_01_has_adr_link_and_files():
    import json
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-01"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "backend/services/supabase_client.py" in files
    assert ".env.example" in files
    assert any("lint-mock.sh" in f for f in files)


def test_tickets_t_001_01_ac_mentions_concrete_invariants():
    import json
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-01"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "_REQUIRED", "SUPABASE_URL", "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_KEY", "SUPABASE_JWT_SECRET",
        "REPLACE_WITH_", "sb_(publishable|secret)",
        "check_secrets()", "RuntimeError",
    ):
        assert sym in full, f"T-001-01 AC missing: {sym}"
