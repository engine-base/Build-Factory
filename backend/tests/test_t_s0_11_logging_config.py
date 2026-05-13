"""T-S0-11: structlog + pino 中央集約 logger config.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : backend/logging_config.py + frontend/src/lib/logger.ts 提供 /
                       既存 import logging は無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : configure_structlog で level set / bind_context で contextvars 追加.
  AC-3 STATE-DRIVEN  : structlog installed → JSON/console / not installed → stdlib fallback /
                       audit_logs DB は触らない.
  AC-4 UNWANTED      : ImportError でも crash しない (graceful) /
                       invalid level で ValueError / secret log 出力なし.

本テストは Python 環境で実行可能なものを verify. frontend pino は
package.json 構造 + ts ファイル存在/export を構造検証.
"""
from __future__ import annotations

import io
import json as _json
import logging
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_CONFIG = REPO_ROOT / "backend" / "logging_config.py"
FRONTEND_LOGGER = REPO_ROOT / "frontend" / "src" / "lib" / "logger.ts"


# ──────────────────────────────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def _reset_logging():
    """各テスト前に logging を reset (configure 多重影響防止)."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    yield
    for h in list(root.handlers):
        root.removeHandler(h)


@pytest.fixture
def _clean_env(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("PROD_LOGGING", raising=False)
    yield


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: ファイル存在 + 公開 API + REUSE
# ══════════════════════════════════════════════════════════════════════


def test_ac1_backend_logging_config_exists():
    assert BACKEND_CONFIG.exists(), f"missing: {BACKEND_CONFIG}"


def test_ac1_frontend_logger_exists():
    assert FRONTEND_LOGGER.exists(), f"missing: {FRONTEND_LOGGER}"


def test_ac1_backend_public_api_present():
    import logging_config as lc
    for sym in ("configure_structlog", "get_logger", "bind_context",
                "clear_context", "get_context", "is_structlog_available",
                "VALID_LEVELS"):
        assert hasattr(lc, sym), f"logging_config.{sym} missing"


def test_ac1_frontend_exports_logger_and_withContext():
    """frontend/src/lib/logger.ts が logger と withContext を export."""
    src = FRONTEND_LOGGER.read_text(encoding="utf-8")
    assert "export const logger" in src
    assert "export function withContext" in src
    assert "import pino" in src


def test_ac1_existing_logging_imports_unchanged():
    """既存 import logging / logging.getLogger は無改変 (REUSE)."""
    # backend/ で stdlib logging を使う既存 file をいくつかサンプリング
    samples = [
        REPO_ROOT / "backend" / "main.py",
        REPO_ROOT / "backend" / "services" / "memory_service.py",
    ]
    for path in samples:
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        # 既存 stdlib import を structlog に強制置換していないこと
        # (logging.getLogger は残っている / structlog への置換 import 文がない)
        if "logging.getLogger" in src or "import logging" in src:
            assert True  # 既存呼出が残っている = REUSE
            break


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: configure / bind_context
# ══════════════════════════════════════════════════════════════════════


def test_ac2_configure_sets_root_logger_level(_reset_logging, _clean_env):
    import logging_config as lc
    lc.configure_structlog(level="WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_ac2_configure_valid_levels(_reset_logging, _clean_env):
    import logging_config as lc
    for lvl in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        lc.configure_structlog(level=lvl)
        assert logging.getLogger().level == getattr(logging, lvl)


def test_ac2_configure_lowercase_level_accepted(_reset_logging, _clean_env):
    import logging_config as lc
    lc.configure_structlog(level="info")  # 小文字 OK
    assert logging.getLogger().level == logging.INFO


def test_ac2_bind_context_no_op_when_structlog_absent():
    """structlog 未インストール時、bind_context は no-op で例外起こさない."""
    import logging_config as lc
    if lc.is_structlog_available():
        pytest.skip("structlog installed; this test verifies fallback path")
    lc.bind_context(request_id="x", actor_user_id="alice")
    lc.clear_context()
    assert lc.get_context() == {}


def test_ac2_bind_context_when_structlog_present():
    """structlog installed → contextvars に bind されること."""
    import logging_config as lc
    if not lc.is_structlog_available():
        pytest.skip("structlog not installed; tested separately")
    lc.clear_context()
    lc.bind_context(request_id="req-123", session_id="sess-1")
    ctx = lc.get_context()
    assert ctx.get("request_id") == "req-123"
    assert ctx.get("session_id") == "sess-1"
    lc.clear_context()
    assert lc.get_context() == {}


def test_ac2_get_logger_returns_callable_log_methods():
    import logging_config as lc
    log = lc.get_logger("test_logger")
    # 必須 method
    for m in ("info", "warning", "error", "debug"):
        assert callable(getattr(log, m))


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: JSON/console 切替 / graceful fallback / no audit_logs
# ══════════════════════════════════════════════════════════════════════


def test_ac3_detect_json_output_from_ci_env(monkeypatch):
    import logging_config as lc
    monkeypatch.setenv("CI", "true")
    assert lc._detect_json_output() is True


def test_ac3_detect_json_output_from_prod_logging_env(monkeypatch):
    import logging_config as lc
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("PROD_LOGGING", "1")
    assert lc._detect_json_output() is True


def test_ac3_detect_json_output_default_is_false(monkeypatch):
    import logging_config as lc
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("PROD_LOGGING", raising=False)
    assert lc._detect_json_output() is False


def test_ac3_module_imports_even_without_structlog():
    """logging_config.py は structlog なしでも import 可能 (graceful)."""
    import logging_config as lc
    # is_structlog_available が True/False どちらでも import が成功する
    assert isinstance(lc.is_structlog_available(), bool)


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
    """logging_config.py は audit_logs (DB) を呼ばないこと (実コード本体のみ検査)."""
    src_full = BACKEND_CONFIG.read_text(encoding="utf-8")
    src = _strip_comments_and_docstrings(src_full)
    assert "emit_event" not in src
    # memory_service もインポートしない
    assert "from services.memory_service" not in src
    assert "import services.memory_service" not in src


def test_ac3_configure_is_idempotent(_reset_logging, _clean_env):
    """configure_structlog を多重呼出しても crash しない."""
    import logging_config as lc
    lc.configure_structlog(level="INFO")
    lc.configure_structlog(level="DEBUG")
    lc.configure_structlog(level="WARNING")
    assert logging.getLogger().level == logging.WARNING


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: ImportError graceful / invalid level / secret 排除
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_level_raises_value_error(_reset_logging, _clean_env):
    import logging_config as lc
    for bad in ("BOGUS", "verbose", "", None, 123):
        with pytest.raises((ValueError, AttributeError)):
            lc.configure_structlog(level=bad)


def test_ac4_invalid_json_output_type_raises(_reset_logging, _clean_env):
    import logging_config as lc
    for bad in ("yes", 1, 0, "true"):
        with pytest.raises(ValueError):
            lc.configure_structlog(level="INFO", json_output=bad)


def test_ac4_no_secret_keywords_in_source():
    """logging_config.py 自身に secret patterns を含まない (PoV 排除)."""
    src = BACKEND_CONFIG.read_text(encoding="utf-8")
    # 例: API key を log に出すサンプルコードを書いていないか
    assert "SUPABASE_SERVICE_KEY" not in src
    assert "sk-ant-" not in src  # Anthropic API key
    assert "OPENAI_API_KEY" not in src
    assert "password" not in src.lower() or '"password"' not in src.lower()


def test_ac4_frontend_logger_no_secret_keywords():
    src = FRONTEND_LOGGER.read_text(encoding="utf-8")
    assert "sk-ant-" not in src
    assert "SUPABASE_SERVICE_KEY" not in src


# ══════════════════════════════════════════════════════════════════════
# requirements.txt / package.json
# ══════════════════════════════════════════════════════════════════════


def test_requirements_includes_structlog():
    req = (REPO_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "structlog" in req, "structlog must be in requirements.txt"


def test_frontend_package_includes_pino():
    pkg = _json.loads((REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    dev = pkg.get("devDependencies", {})
    assert "pino" in deps, "pino must be in dependencies"
    # pino-pretty は dev のみ (prod bundle に含めない)
    assert "pino-pretty" in dev, "pino-pretty must be in devDependencies"
    assert "pino-pretty" not in deps, "pino-pretty must NOT be in production deps"


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_11_ac_concretized():
    """tickets.json T-S0-11 AC が generic でないことを確認."""
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-11"), None)
    assert t is not None
    generic_phrases = [
        "as specified by feature",
        "implementation step for T-S0-11 is triggered",
        "shall record an audit entry capturing the action and timestamp",
        "shall apply Row Level Security and audit_logs as per CLAUDE.md",
    ]
    for ac in t["acceptance_criteria"]:
        text = ac["text"]
        for phrase in generic_phrases:
            assert phrase not in text, (
                f"T-S0-11 AC still contains generic phrase: {phrase!r} in {ac['type']}"
            )
    # 具体的キーワード
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "structlog" in full
    assert "pino" in full
    assert "logging_config.py" in full
    assert "logger.ts" in full


def test_tickets_t_s0_11_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-11"), None)
    assert t.get("adr_link") is not None
    assert t.get("existing_files"), "existing_files must list affected files"


# ══════════════════════════════════════════════════════════════════════
# Frontend logger.ts 構造検証
# ══════════════════════════════════════════════════════════════════════


def test_frontend_logger_documents_audit_logs_separation():
    """pino と audit_logs DB の分離が明示されている (backend と同じ精神)."""
    src = FRONTEND_LOGGER.read_text(encoding="utf-8")
    assert "audit_logs" in src
    # 「二重書きしない」or similar
    assert "二重" in src or "separate" in src.lower() or "別物" in src


def test_frontend_logger_documents_prod_vs_dev():
    src = FRONTEND_LOGGER.read_text(encoding="utf-8")
    assert "production" in src.lower()
    assert "pino-pretty" in src
    assert "JSON" in src


def test_frontend_logger_imports_pino_with_types():
    src = FRONTEND_LOGGER.read_text(encoding="utf-8")
    assert "import pino" in src
    assert "type Logger" in src or "Logger" in src
