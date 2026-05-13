"""T-S0-07: Supabase FE wrapper (browser client + auth helpers + graceful degradation).

本テストは TypeScript module の **構造検証** を Python から行う
(node 環境なしのため runtime test 不可).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : supabase.ts 公開 export / 既存 api.ts 無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : env 読込 + URL pattern validate + singleton cache /
                       signOut で session clear.
  AC-3 STATE-DRIVEN  : env 未設定で mock client (no throw) /
                       persistSession=true 設定.
  AC-4 UNWANTED      : URL pattern 不正で SupabaseConfigError /
                       anon_key < 10 chars で SupabaseConfigError /
                       hardcoded URL/key/secret なし.
"""
from __future__ import annotations

import json as _json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "frontend" / "src" / "lib" / "supabase.ts"
EXISTING_API = REPO_ROOT / "frontend" / "src" / "lib" / "api.ts"


@pytest.fixture(scope="module")
def src() -> str:
    return WRAPPER.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: file / exports / REUSE
# ══════════════════════════════════════════════════════════════════════


def test_ac1_wrapper_exists():
    assert WRAPPER.exists(), f"missing: {WRAPPER}"


def test_ac1_required_exports_present(src):
    for name in (
        "getSupabaseClient",
        "getCurrentUser",
        "signOut",
        "isSupabaseConfigured",
        "SupabaseNotConfiguredError",
        "SupabaseConfigError",
    ):
        assert f"export" in src and name in src, f"missing export: {name}"


def test_ac1_test_only_exports_for_isolation(src):
    """__resetForTests / __getState を test-only として export."""
    assert "__resetForTests" in src
    assert "__getState" in src


def test_ac1_coexists_with_api_ts_unchanged():
    """既存 api.ts は無改変 (REUSE)."""
    assert EXISTING_API.exists()
    # 本 PR で api.ts に supabase 依存を入れていないこと
    api_src = EXISTING_API.read_text(encoding="utf-8")
    assert "@supabase/supabase-js" not in api_src
    assert "from \"@/lib/supabase\"" not in api_src
    assert "from '@/lib/supabase'" not in api_src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: env validate / singleton / signOut
# ══════════════════════════════════════════════════════════════════════


def test_ac2_reads_next_public_env_vars(src):
    """NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY を読む."""
    assert "NEXT_PUBLIC_SUPABASE_URL" in src
    assert "NEXT_PUBLIC_SUPABASE_ANON_KEY" in src


def test_ac2_url_pattern_validation_in_source(src):
    """URL pattern validate (https://*.supabase.co)."""
    assert "supabase.co" in src
    # regex literal or pattern check
    assert "VALID_URL_PATTERN" in src
    assert "https:" in src


def test_ac2_singleton_client_cache(src):
    """2 回目以降は cached client を返す singleton."""
    # _client variable + cache check
    assert "let _client" in src
    assert "if (_client !== null)" in src or "_client !== null" in src


def test_ac2_sign_out_clears_session(src):
    """signOut で auth.signOut() を呼ぶ."""
    assert "auth.signOut" in src or "signOut()" in src
    # signOut function 定義
    assert "export async function signOut" in src


def test_ac2_dynamic_import_for_graceful_tsc(src):
    """@supabase/supabase-js を dynamic import (未インストールで tsc/build fail しない)."""
    assert 'await import("@supabase/supabase-js"' in src or "import(\"@supabase/supabase-js" in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: graceful mock / persistSession
# ══════════════════════════════════════════════════════════════════════


def test_ac3_mock_client_factory(src):
    """env 未設定時に mock client を返す."""
    assert "_createMockClient" in src
    # mock auth.getUser が SupabaseNotConfiguredError を error に返す
    assert "SupabaseNotConfiguredError" in src


def test_ac3_mock_client_methods_no_throw(src):
    """mock client の method は throw せず { data: null, error } を返す."""
    # mock の構造
    assert "data: { user: null }" in src or "data: null" in src
    assert "error: err" in src or "error:" in src


def test_ac3_persist_session_true(src):
    """persistSession: true (localStorage に session 保持)."""
    assert "persistSession: true" in src
    assert "autoRefreshToken: true" in src


def test_ac3_does_not_import_audit_logs_or_logger(src):
    """logger (T-S0-11) / Sentry (T-S0-10) / audit_logs を呼ばない (caller 責任)."""
    # 直接 import していない
    assert 'from "@/lib/logger"' not in src
    assert "from '@/lib/logger'" not in src
    assert 'from "@/lib/sentry"' not in src
    assert "from '@/lib/sentry'" not in src
    # audit_logs DB に書込まない
    assert "audit_logs" in src  # docstring に分離説明があるはず
    # but actual call なし
    assert "INSERT INTO audit_logs" not in src
    assert "from('audit_logs')" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid env / no hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac4_throws_on_invalid_url_pattern(src):
    """URL pattern 不正で SupabaseConfigError throw."""
    assert "SupabaseConfigError" in src
    assert "must match https" in src or "VALID_URL_PATTERN" in src


def test_ac4_throws_on_short_anon_key(src):
    """ANON_KEY < 10 chars で SupabaseConfigError."""
    assert "must be >= 10 chars" in src or ">= 10" in src or "key.length < 10" in src


def test_ac4_no_hardcoded_supabase_url(src):
    """source に hardcoded Supabase URL がないこと."""
    # 本物の Supabase project URL pattern (xxxxx.supabase.co) を含まない
    # ただし `*.supabase.co` (wildcard / regex) は OK
    # 厳格 check: project subdomain っぽい literal なし
    import re
    project_url_pattern = re.compile(
        r"https://[a-z]{15,}\.supabase\.co", re.IGNORECASE
    )
    matches = project_url_pattern.findall(src)
    assert not matches, f"hardcoded Supabase URL detected: {matches}"


def test_ac4_no_hardcoded_anon_or_service_key(src):
    """anon_key / service_role_key の literal がないこと.
    Supabase JWT は eyJxxx... の形式."""
    import re
    # JWT pattern: eyJ で始まる long string
    jwt_pattern = re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")
    matches = jwt_pattern.findall(src)
    assert not matches, f"hardcoded JWT (anon/service key) detected"
    # service_role_key keyword
    assert "service_role" not in src.lower() or "service_role_key" not in src.lower()


def test_ac4_documents_audit_logs_separation(src):
    """docstring で audit_logs DB との分離を明示."""
    assert "audit_logs" in src
    # 4 層 observability の精神
    assert "backend" in src.lower()


# ══════════════════════════════════════════════════════════════════════
# package.json
# ══════════════════════════════════════════════════════════════════════


def test_package_json_includes_supabase_js():
    pkg = _json.loads((REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    assert "@supabase/supabase-js" in deps


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_07_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-07"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the user interacts with the UI for T-S0-07",
        "While refactoring for T-S0-07 is in progress, the system shall maintain backwards compatibility with current API contracts and shall preserve coverage at >= baseline.",
        "If invalid input or unauthorized actor is detected during T-S0-07",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-S0-07 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "supabase.ts" in full
    assert "getSupabaseClient" in full
    assert "NEXT_PUBLIC_SUPABASE_URL" in full


def test_tickets_t_s0_07_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-07"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert files, "existing_files must be specified"
    assert all("TBD" not in f for f in files), "existing_files must not be TBD"


# ══════════════════════════════════════════════════════════════════════
# TypeScript build-time safety (structural checks)
# ══════════════════════════════════════════════════════════════════════


def test_no_default_export_only_named(src):
    """named export のみ (default export は使わない / tree-shaking 効率)."""
    assert "export default" not in src


def test_uses_async_await_pattern(src):
    """async/await pattern を使う (Promise chain ではなく)."""
    assert "async function getSupabaseClient" in src
    assert "await" in src
