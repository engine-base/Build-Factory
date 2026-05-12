"""T-S0-12: Better Stack uptime monitor (pull /health + push heartbeat).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : uptime_heartbeat.py 公開 API / 既存 /health 無改変.
  AC-2 EVENT-DRIVEN  : send_heartbeat() URL form validate + httpx GET/POST +
                       2xx/3xx で True / 4xx/5xx/network で False / 例外 raise なし.
  AC-3 STATE-DRIVEN  : URL 未設定で no-op / state mutate なし / audit_logs DB 書込なし.
  AC-4 UNWANTED      : invalid url / timeout / extra_payload で ValueError /
                       network failure で log + False return / hardcoded URL なし.
"""
from __future__ import annotations

import json as _json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HEARTBEAT_MODULE = REPO_ROOT / "backend" / "uptime_heartbeat.py"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BETTER_STACK_HEARTBEAT_URL", raising=False)
    yield


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_exists():
    assert HEARTBEAT_MODULE.exists()


def test_ac1_public_api_present():
    import uptime_heartbeat as uh
    for sym in (
        "send_heartbeat", "is_configured", "get_heartbeat_url",
        "APSCHEDULER_INTEGRATION_GUIDE", "ALLOWED_SCHEMES",
        "DEFAULT_TIMEOUT_SEC",
    ):
        assert hasattr(uh, sym), f"uptime_heartbeat.{sym} missing"


def test_ac1_existing_health_endpoint_unchanged():
    """既存 /health endpoint (backend/main.py) を活用 (REUSE)."""
    main_src = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    assert '@app.get("/health")' in main_src or '@app.get(\'/health\')' in main_src


def test_ac1_apscheduler_integration_documented():
    import uptime_heartbeat as uh
    assert "APScheduler" in uh.APSCHEDULER_INTEGRATION_GUIDE
    assert "send_heartbeat" in uh.APSCHEDULER_INTEGRATION_GUIDE


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: send_heartbeat
# ══════════════════════════════════════════════════════════════════════


def test_ac2_send_heartbeat_no_url_returns_false():
    """URL 未設定で no-op + False return."""
    import uptime_heartbeat as uh
    assert uh.send_heartbeat() is False


def test_ac2_send_heartbeat_success_returns_true(monkeypatch):
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL",
                       "https://uptime.betterstack.com/api/v1/heartbeat/test123")

    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("httpx.get", return_value=mock_response) as mock_get:
        result = uh.send_heartbeat()
    assert result is True
    mock_get.assert_called_once()


def test_ac2_send_heartbeat_with_payload_uses_post(monkeypatch):
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL",
                       "https://uptime.betterstack.com/h/abc")
    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = uh.send_heartbeat(extra_payload={"status": "healthy"})
    assert result is True
    mock_post.assert_called_once()
    # payload 渡されている
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs.get("json") == {"status": "healthy"}


def test_ac2_send_heartbeat_4xx_returns_false(monkeypatch):
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "https://uptime.betterstack.com/h/x")
    mock_response = MagicMock()
    mock_response.status_code = 404
    with patch("httpx.get", return_value=mock_response):
        result = uh.send_heartbeat()
    assert result is False


def test_ac2_send_heartbeat_5xx_returns_false(monkeypatch):
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "https://uptime.betterstack.com/h/x")
    mock_response = MagicMock()
    mock_response.status_code = 503
    with patch("httpx.get", return_value=mock_response):
        result = uh.send_heartbeat()
    assert result is False


def test_ac2_send_heartbeat_network_exception_returns_false(monkeypatch, caplog):
    """network 失敗で False (例外を raise しない / graceful)."""
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "https://uptime.betterstack.com/h/x")
    with patch("httpx.get", side_effect=ConnectionError("network down")):
        with caplog.at_level("WARNING"):
            result = uh.send_heartbeat()
    assert result is False
    # warning が log に残る
    assert any("heartbeat" in r.message.lower() for r in caplog.records)


def test_ac2_send_heartbeat_timeout_exception_returns_false(monkeypatch):
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "https://uptime.betterstack.com/h/x")
    with patch("httpx.get", side_effect=TimeoutError("timed out")):
        result = uh.send_heartbeat()
    assert result is False


def test_ac2_send_heartbeat_explicit_url_overrides_env(monkeypatch):
    """url 引数指定で env を上書き."""
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "https://from-env.example.com/h")

    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("httpx.get", return_value=mock_response) as mock_get:
        uh.send_heartbeat(url="https://explicit.example.com/h")
    called_url = mock_get.call_args.args[0] if mock_get.call_args.args else mock_get.call_args.kwargs["url"]
    assert "explicit" in called_url


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: graceful + no audit_logs
# ══════════════════════════════════════════════════════════════════════


def test_ac3_is_configured_reflects_env(monkeypatch):
    import uptime_heartbeat as uh
    assert uh.is_configured() is False
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "https://example.com/h")
    assert uh.is_configured() is True


def test_ac3_is_configured_false_for_empty_or_whitespace(monkeypatch):
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "")
    assert uh.is_configured() is False
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "   ")
    assert uh.is_configured() is False


def test_ac3_get_heartbeat_url_strips_whitespace(monkeypatch):
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "  https://example.com/h  ")
    assert uh.get_heartbeat_url() == "https://example.com/h"


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


def test_ac3_module_does_not_write_to_audit_logs():
    """audit_logs DB を呼ばないこと (実コード本体のみ検査)."""
    src_full = HEARTBEAT_MODULE.read_text(encoding="utf-8")
    src = _strip_comments_and_docstrings(src_full)
    assert "emit_event" not in src
    assert "from services.memory_service" not in src
    assert "import services.memory_service" not in src


def test_ac3_no_apscheduler_auto_wire():
    """APScheduler integration は docstring のみで自動 wire しない."""
    src_full = HEARTBEAT_MODULE.read_text(encoding="utf-8")
    src = _strip_comments_and_docstrings(src_full)
    # APScheduler を実際には import しない
    assert "from apscheduler" not in src.lower()
    assert "import apscheduler" not in src.lower()
    # scheduler.add_job も呼ばない
    assert "scheduler.add_job" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid input
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_url_scheme_raises(monkeypatch):
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "ftp://example.com/h")
    with pytest.raises(ValueError, match="scheme"):
        uh.send_heartbeat()


def test_ac4_invalid_url_no_netloc_raises(monkeypatch):
    import uptime_heartbeat as uh
    monkeypatch.setenv("BETTER_STACK_HEARTBEAT_URL", "https://")
    with pytest.raises(ValueError, match="netloc"):
        uh.send_heartbeat()


def test_ac4_explicit_url_empty_raises():
    import uptime_heartbeat as uh
    with pytest.raises(ValueError):
        uh.send_heartbeat(url="")


def test_ac4_explicit_url_non_string_raises():
    import uptime_heartbeat as uh
    for bad in (123, [], {}):
        with pytest.raises(ValueError):
            uh.send_heartbeat(url=bad)


def test_ac4_invalid_timeout_raises():
    import uptime_heartbeat as uh
    for bad in (0, -1, 61, 100):
        with pytest.raises(ValueError):
            uh.send_heartbeat(url="https://x.com/h", timeout_sec=bad)


def test_ac4_invalid_timeout_type_raises():
    import uptime_heartbeat as uh
    for bad in ("10", None, [10]):
        with pytest.raises((ValueError, TypeError)):
            uh.send_heartbeat(url="https://x.com/h", timeout_sec=bad)


def test_ac4_invalid_extra_payload_raises():
    import uptime_heartbeat as uh
    for bad in ("not dict", [1, 2], 123):
        with pytest.raises(ValueError):
            uh.send_heartbeat(url="https://x.com/h", extra_payload=bad)


def test_ac4_no_hardcoded_url_in_source():
    """source に hardcoded heartbeat URL / token がないこと."""
    src = HEARTBEAT_MODULE.read_text(encoding="utf-8")
    src_code = _strip_comments_and_docstrings(src)
    # 実コード本体に Better Stack の実 URL は無い
    # (docstring の example は OK)
    # 厳格 check: code 内に "betterstack.com" の literal URL なし
    assert "https://uptime.betterstack.com" not in src_code, (
        "hardcoded Better Stack URL detected in code (must come from env)"
    )
    assert "https://betterstack.com" not in src_code


def test_ac4_no_hardcoded_secret_in_source():
    src = HEARTBEAT_MODULE.read_text(encoding="utf-8")
    src_code = _strip_comments_and_docstrings(src)
    assert "sk-ant-" not in src_code
    assert "SUPABASE_SERVICE_KEY" not in src_code
    # token-like
    assert "Bearer " not in src_code


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_12_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-12"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "implementation step for T-S0-12 is triggered",
        "shall record an audit entry capturing the action and timestamp",
        "shall apply Row Level Security and audit_logs as per CLAUDE.md",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-S0-12 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "send_heartbeat" in full
    assert "BETTER_STACK_HEARTBEAT_URL" in full
    assert "httpx" in full


def test_tickets_t_s0_12_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-12"), None)
    assert t.get("adr_link") is not None
    assert t.get("existing_files")
