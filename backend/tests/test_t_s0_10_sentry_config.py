"""T-S0-10: Sentry 設定 (Backend / FastAPI + Frontend Next.js).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : backend/sentry_config.py + frontend/src/lib/sentry.ts /
                       公開 API (init / capture / setUser / setTag) /
                       structlog (T-S0-11) と audit_logs と独立した 3 層構成.
  AC-2 EVENT-DRIVEN  : init_sentry で param validate + idempotent /
                       capture が event_id を返す or None (no-op).
  AC-3 STATE-DRIVEN  : sentry-sdk / @sentry/nextjs 未インストール時 graceful no-op /
                       send_default_pii default False / max_breadcrumbs 50.
  AC-4 UNWANTED      : invalid sample_rate / environment で ValueError /
                       audit_logs DB に書込まない / hardcoded DSN なし.
"""
from __future__ import annotations

import json as _json
import logging
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SENTRY = REPO_ROOT / "backend" / "sentry_config.py"
FRONTEND_SENTRY = REPO_ROOT / "frontend" / "src" / "lib" / "sentry.ts"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_sentry():
    """各テスト前に _INITIALIZED を reset."""
    import sentry_config as sc
    sc.reset_for_tests()
    yield
    sc.reset_for_tests()


@pytest.fixture
def _clean_env(monkeypatch):
    for k in ("SENTRY_DSN", "SENTRY_ENVIRONMENT", "SENTRY_TRACES_SAMPLE_RATE", "SENTRY_RELEASE"):
        monkeypatch.delenv(k, raising=False)
    yield


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: ファイル / 公開 API / 3 層 observability 分離
# ══════════════════════════════════════════════════════════════════════


def test_ac1_backend_sentry_config_exists():
    assert BACKEND_SENTRY.exists(), f"missing: {BACKEND_SENTRY}"


def test_ac1_frontend_sentry_exists():
    assert FRONTEND_SENTRY.exists(), f"missing: {FRONTEND_SENTRY}"


def test_ac1_backend_public_api_present():
    import sentry_config as sc
    for sym in (
        "init_sentry", "capture_exception", "capture_message",
        "set_user", "set_tag", "add_breadcrumb",
        "is_sentry_available", "VALID_ENVIRONMENTS", "reset_for_tests",
    ):
        assert hasattr(sc, sym), f"sentry_config.{sym} missing"


def test_ac1_frontend_exports_required_api():
    src = FRONTEND_SENTRY.read_text(encoding="utf-8")
    for export in (
        "initSentry", "captureException", "captureMessage",
        "setUser", "setTag", "isSentryAvailable", "VALID_ENVIRONMENTS",
    ):
        assert f"export" in src and export in src, f"sentry.ts missing export: {export}"


def test_ac1_three_layer_observability_documented():
    """structlog / audit_logs / Sentry の 3 層が docstring で説明されている."""
    src = BACKEND_SENTRY.read_text(encoding="utf-8")
    assert "structlog" in src
    assert "audit_logs" in src
    assert "Sentry" in src
    # 「3 層」or 同等の文言
    assert "3 層" in src or "3 layers" in src.lower()


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: init / capture / idempotent
# ══════════════════════════════════════════════════════════════════════


def test_ac2_init_no_dsn_returns_false(_clean_env):
    import sentry_config as sc
    # DSN なし → graceful no-op で False
    result = sc.init_sentry()
    assert result is False


def test_ac2_init_idempotent(_clean_env):
    import sentry_config as sc
    r1 = sc.init_sentry()
    r2 = sc.init_sentry()
    # idempotent: 2 回目も同じ戻り値で crash しない
    assert r1 == r2


def test_ac2_capture_exception_returns_none_when_no_sdk():
    import sentry_config as sc
    if sc.is_sentry_available():
        pytest.skip("sentry-sdk installed; test verifies no-sdk fallback")
    assert sc.capture_exception(RuntimeError("test")) is None


def test_ac2_capture_message_returns_none_when_no_sdk():
    import sentry_config as sc
    if sc.is_sentry_available():
        pytest.skip("sentry-sdk installed")
    assert sc.capture_message("test message") is None


def test_ac2_capture_message_validates_level():
    import sentry_config as sc
    for bad_level in ("BOGUS", "verbose", "", "fatal2"):
        with pytest.raises(ValueError):
            sc.capture_message("msg", level=bad_level)


def test_ac2_capture_message_rejects_empty():
    import sentry_config as sc
    for bad in ("", "   ", None, 123):
        with pytest.raises((ValueError, TypeError)):
            sc.capture_message(bad)


def test_ac2_set_tag_validates_key():
    import sentry_config as sc
    for bad in ("", "   ", None, 123):
        with pytest.raises((ValueError, TypeError)):
            sc.set_tag(bad, "value")


def test_ac2_add_breadcrumb_validates_category():
    import sentry_config as sc
    for bad in ("", "   ", None):
        with pytest.raises((ValueError, TypeError)):
            sc.add_breadcrumb(category=bad, message="x")


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: graceful no-op / pii off / breadcrumbs cap
# ══════════════════════════════════════════════════════════════════════


def test_ac3_module_imports_without_sentry_sdk():
    import sentry_config as sc
    # boolean を返す
    assert isinstance(sc.is_sentry_available(), bool)


def test_ac3_init_warns_when_dsn_missing(caplog, _clean_env):
    import sentry_config as sc
    with caplog.at_level(logging.WARNING):
        sc.init_sentry()
    # warning メッセージが出る (sentry-sdk なし OR DSN なし)
    assert any(
        "Sentry" in r.message or "sentry" in r.message.lower()
        for r in caplog.records
    )


def test_ac3_send_default_pii_defaults_false():
    """sentry_config.py の init_sentry default で send_default_pii=False."""
    import inspect
    import sentry_config as sc
    sig = inspect.signature(sc.init_sentry)
    assert sig.parameters["send_default_pii"].default is False


def test_ac3_max_breadcrumbs_capped_in_source():
    """source で max_breadcrumbs=50 が指定されている."""
    src = BACKEND_SENTRY.read_text(encoding="utf-8")
    assert "max_breadcrumbs" in src
    assert "50" in src


def test_ac3_module_does_not_write_to_audit_logs():
    """audit_logs DB を呼ばないこと (実コード本体のみ検査)."""
    src_full = BACKEND_SENTRY.read_text(encoding="utf-8")
    src = _strip_comments_and_docstrings(src_full)
    assert "emit_event" not in src
    assert "from services.memory_service" not in src
    assert "import services.memory_service" not in src


def _strip_comments_and_docstrings(src: str) -> str:
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


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid params / no hardcoded DSN
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_sample_rate_raises(_clean_env):
    import sentry_config as sc
    for bad in (-0.1, 1.1, 2.0, -1.0):
        sc.reset_for_tests()
        with pytest.raises(ValueError):
            sc.init_sentry(traces_sample_rate=bad)


def test_ac4_invalid_sample_rate_type_raises(_clean_env):
    import sentry_config as sc
    for bad in ("0.5", None, [0.5], {"rate": 0.5}):
        sc.reset_for_tests()
        with pytest.raises((ValueError, TypeError)):
            sc.init_sentry(traces_sample_rate=bad)


def test_ac4_invalid_environment_raises(_clean_env):
    """invalid environment 値で ValueError.
    None は env fallback ('development') が走るため除外.
    """
    import sentry_config as sc
    for bad in ("BOGUS", "stage", "prod", 123, [], {}):
        sc.reset_for_tests()
        with pytest.raises((ValueError, TypeError)):
            sc.init_sentry(environment=bad)


def test_ac4_invalid_pii_type_raises(_clean_env):
    import sentry_config as sc
    for bad in (1, 0, "yes", "true"):
        sc.reset_for_tests()
        with pytest.raises(ValueError):
            sc.init_sentry(send_default_pii=bad)


def test_ac4_no_hardcoded_dsn_in_source():
    """source に hardcoded DSN / API key がない."""
    src = BACKEND_SENTRY.read_text(encoding="utf-8")
    # Sentry DSN は https://xxx@xxx.ingest.sentry.io/ 形式
    assert "ingest.sentry.io" not in src, "hardcoded Sentry DSN detected"
    assert "sk-ant-" not in src
    assert "SUPABASE_SERVICE_KEY" not in src


def test_ac4_frontend_no_hardcoded_dsn():
    src = FRONTEND_SENTRY.read_text(encoding="utf-8")
    assert "ingest.sentry.io" not in src
    assert "sk-ant-" not in src


def test_ac4_frontend_validates_environment_in_init():
    """frontend sentry.ts も environment を validate する."""
    src = FRONTEND_SENTRY.read_text(encoding="utf-8")
    assert "VALID_ENVIRONMENTS" in src
    # validation check
    assert "environment must be" in src.lower()


def test_ac4_frontend_validates_sample_rate():
    src = FRONTEND_SENTRY.read_text(encoding="utf-8")
    # 0.0 / 1.0 range check
    assert "tracesSampleRate must be in" in src or "[0.0, 1.0]" in src


# ══════════════════════════════════════════════════════════════════════
# Requirements / package.json
# ══════════════════════════════════════════════════════════════════════


def test_requirements_includes_sentry_sdk():
    req = (REPO_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "sentry-sdk" in req, "sentry-sdk must be in requirements.txt"


def test_frontend_package_includes_sentry_nextjs():
    pkg = _json.loads((REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    assert "@sentry/nextjs" in deps, "@sentry/nextjs must be in dependencies"


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_10_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-10"), None)
    assert t is not None
    generic_phrases = [
        "as specified by feature",
        "implementation step for T-S0-10 is triggered",
        "shall record an audit entry capturing the action and timestamp",
        "shall apply Row Level Security and audit_logs as per CLAUDE.md",
    ]
    for ac in t["acceptance_criteria"]:
        text = ac["text"]
        for phrase in generic_phrases:
            assert phrase not in text, f"T-S0-10 AC still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "sentry_config.py" in full
    assert "sentry.ts" in full
    assert "send_default_pii" in full


def test_tickets_t_s0_10_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-10"), None)
    assert t.get("adr_link") is not None
    assert t.get("existing_files")


# ══════════════════════════════════════════════════════════════════════
# Frontend structure
# ══════════════════════════════════════════════════════════════════════


def test_frontend_dynamic_import_for_graceful_degradation():
    """@sentry/nextjs 未インストール時に build/tsc が落ちないよう dynamic import."""
    src = FRONTEND_SENTRY.read_text(encoding="utf-8")
    # dynamic import 利用
    assert 'await import("@sentry/nextjs"' in src or "import(\"@sentry/nextjs" in src


def test_frontend_documents_audit_logs_separation():
    src = FRONTEND_SENTRY.read_text(encoding="utf-8")
    assert "audit_logs" in src
    # 「3 層」分離が明示
    assert "3 層" in src or "3 layers" in src.lower()
