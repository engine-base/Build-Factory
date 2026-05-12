"""T-S0-11: structlog + pino 中央集約 logger config (Backend Python).

## 目的

Build-Factory 全 backend で構造化ログを統一する. production では JSON 出力
(GitHub Actions log / Sentry breadcrumbs / クラウド log 取込みに耐える形式),
development では人間可読 colored 出力.

## ADR-010 / audit_logs との関係

structlog (本 module) と audit_logs (DB) は **別物**:

  - structlog : 人間 / 監視ツール / Sentry 向け. ephemeral / 非永続. 全ログ.
  - audit_logs: 監査 trail. DB 永続. 重要イベントのみ (m27.handoff /
                memory.compacted / intent.classified 等).

structlog 出力に audit_logs を二重書きしない (audit_logs は memory_service の
emit_event 経由のみ).

## Graceful degradation

structlog が未インストール (例: minimal CI runtime / 環境構築前) でも import 可能で、
自動的に stdlib logging fallback に切替わる. 既存 `import logging` /
`logging.getLogger(__name__)` 呼び出しは触らない (REUSE).

## Bindings (recommended)

  - request_id : per-request UUID (auto via middleware, T-S0-11 範囲外で別途追加)
  - session_id : claude-agent-sdk session_id (when available)
  - actor_user_id : 認証 user id (when authenticated)
  - task_id    : T-task ID when in task execution context

context は `bind_context(**kwargs)` で thread-local / contextvar に set し,
`clear_context()` で request 終了時に clear する.

## AC マッピング

  AC-1 UBIQUITOUS    : configure_structlog() で全 backend ログ統一 (JSON/console).
                       既存 logging.getLogger は無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : bind_context() で per-request context 追加,
                       log 出力に自動 merge.
  AC-3 STATE-DRIVEN  : structlog 未インストール時は stdlib logging に自動
                       fallback (graceful degradation). audit_logs DB は触らない.
  AC-4 UNWANTED      : log 出力で secret / 認証情報を含めない (caller 責任).
                       structlog import 失敗で本 module の import が落ちない.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

try:
    import structlog as _structlog
    _STRUCTLOG_AVAILABLE = True
except ImportError:  # pragma: no cover (CI で structlog 入れる)
    _structlog = None
    _STRUCTLOG_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────
# Public flags
# ──────────────────────────────────────────────────────────────────────


def is_structlog_available() -> bool:
    """structlog がインストール済か."""
    return _STRUCTLOG_AVAILABLE


VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────


def _detect_json_output() -> bool:
    """環境変数から JSON 出力すべきか判定.

    CI=true / PROD_LOGGING=1 で JSON. それ以外は console.
    """
    return bool(
        os.environ.get("CI") or os.environ.get("PROD_LOGGING")
    )


def _validate_level(level: str) -> str:
    if not isinstance(level, str):
        raise ValueError("level must be string")
    upper = level.upper()
    if upper not in VALID_LEVELS:
        raise ValueError(f"level must be one of {VALID_LEVELS}, got {level!r}")
    return upper


def configure_structlog(
    level: str = "INFO",
    json_output: Optional[bool] = None,
) -> None:
    """Configure structlog + stdlib logging integration.

    Idempotent: safe to call multiple times.

    Args:
        level: minimum log level (DEBUG / INFO / WARNING / ERROR / CRITICAL).
        json_output: True for JSON, False for console. None で自動判定 (CI / PROD_LOGGING).
    """
    level = _validate_level(level)
    if json_output is None:
        json_output = _detect_json_output()
    if not isinstance(json_output, bool):
        raise ValueError("json_output must be bool or None")

    log_level = getattr(logging, level)

    # stdlib root logger も整合させる (既存 logging.getLogger 呼出も同じ level)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,  # 多重 configure 防止
    )

    if not _STRUCTLOG_AVAILABLE:
        # graceful degradation: stdlib logging のみ
        logging.getLogger(__name__).info(
            "structlog not installed; falling back to stdlib logging"
        )
        return

    processors = [
        _structlog.contextvars.merge_contextvars,
        _structlog.processors.add_log_level,
        _structlog.processors.TimeStamper(fmt="iso", utc=True),
        _structlog.processors.StackInfoRenderer(),
        _structlog.processors.format_exc_info,
    ]
    if json_output:
        processors.append(_structlog.processors.JSONRenderer())
    else:
        processors.append(
            _structlog.dev.ConsoleRenderer(colors=False)
        )

    _structlog.configure(
        processors=processors,
        wrapper_class=_structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=_structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


# ──────────────────────────────────────────────────────────────────────
# Logger factory (graceful degradation)
# ──────────────────────────────────────────────────────────────────────


def get_logger(name: str = "") -> Any:
    """Get a structlog logger (or stdlib fallback).

    既存 logging.getLogger と互換性のある log methods (info/warning/error/debug)
    を提供. structlog 利用時は kwargs が context として merge される.
    """
    if _STRUCTLOG_AVAILABLE:
        return _structlog.get_logger(name)
    return logging.getLogger(name)


# ──────────────────────────────────────────────────────────────────────
# Context bindings (per-request / per-session)
# ──────────────────────────────────────────────────────────────────────


def bind_context(**kwargs: Any) -> None:
    """Bind request-scoped context (request_id / session_id / actor_user_id 等).

    structlog 利用時は contextvars に bind, 以降の log 出力に自動 merge.
    structlog 未インストール時は no-op (silent).
    """
    if not _STRUCTLOG_AVAILABLE:
        return
    _structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear request-scoped context. request 終了時に呼ぶ."""
    if not _STRUCTLOG_AVAILABLE:
        return
    _structlog.contextvars.clear_contextvars()


def get_context() -> dict:
    """Get current bound context (for debugging / testing)."""
    if not _STRUCTLOG_AVAILABLE:
        return {}
    return dict(_structlog.contextvars.get_contextvars())
