"""T-V3-B-08 / F-005b: Mocks backend service (list / detail / html GET/PUT).

F-005b 画面モック自動生成パイプライン (M-5b) — backend service layer.

公開 API:
  - list_mocks(workspace_id) -> dict {mocks: [...], total: int}
  - get_mock(workspace_id, screen_id) -> dict {screen, html_url, version}
  - get_mock_html(workspace_id, screen_id) -> dict {html}
  - put_mock_html(workspace_id, screen_id, html, *, actor_user_id) ->
        dict {new_version, updated_at}
  - reset_store()  (test 用)

スコープ entities: E-011 Screen / E-012 Component / E-013 ScreenComponent /
E-014 Artifact (workspace_scoped).

ストレージ: in-memory store + per-screen lock (concurrent edit 検知).
将来 DB バックエンドへ差し替え可能なように pure-function 化.

AC マッピング (T-V3-B-08):
  AC-F1  EVENT-DRIVEN  : GET html → 最新 version 返却 (get_mock_html)
  AC-F2  EVENT-DRIVEN  : PUT html → version 自動 increment + snapshot 保持
  AC-F3  UNWANTED      : PUT html > 1MB で 422 (size guard)
  AC-F5  STATE-DRIVEN  : 他 actor 編集中なら 409 (lock)
  AC-F6  EVENT-DRIVEN  : GET list → {mocks, total}
  AC-F9  EVENT-DRIVEN  : GET detail → {screen, html_url, version}
  AC-F12 EVENT-DRIVEN  : GET html → {html}
  AC-F14 EVENT-DRIVEN  : PUT html → {new_version, updated_at}
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

MAX_HTML_BYTES = 1 * 1024 * 1024  # 1MB per F-005b policy
LOCK_TTL_SECONDS = 5 * 60  # 5 minutes
SCREEN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-:.]{1,64}$")


# ──────────────────────────────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────────────────────────────


class MockError(RuntimeError):
    """generic mock service error (mapped to 400)."""


class MockValidationError(MockError):
    """invalid input (mapped to 422)."""


class MockNotFoundError(MockError):
    """screen / mock not found (mapped to 404)."""


class MockHtmlTooLargeError(MockValidationError):
    """html body exceeds MAX_HTML_BYTES (mapped to 422)."""


class MockLockedError(MockError):
    """mock is locked by another actor (mapped to 409)."""


# ──────────────────────────────────────────────────────────────────────
# Storage
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _MockSnapshot:
    version: int
    html: str
    updated_at: str
    updated_by: Optional[str] = None


@dataclass
class _MockRecord:
    workspace_id: int
    screen_id: str
    name: str = ""
    versions: list[_MockSnapshot] = field(default_factory=list)
    # lock = (actor_user_id, acquired_at_epoch)
    locked_by: Optional[str] = None
    locked_at: float = 0.0

    @property
    def latest_version(self) -> int:
        return self.versions[-1].version if self.versions else 0

    @property
    def latest_html(self) -> str:
        return self.versions[-1].html if self.versions else ""

    @property
    def latest_updated_at(self) -> str:
        return self.versions[-1].updated_at if self.versions else ""


_lock = threading.Lock()
# key = (workspace_id, screen_id)
_store: dict[tuple[int, str], _MockRecord] = {}


def reset_store() -> None:
    """test 用 reset. workspace 横断で in-memory store を初期化."""
    with _lock:
        _store.clear()


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_epoch() -> float:
    import time
    return time.time()


def _validate_workspace_id(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise MockValidationError("workspace_id must be int")
    if value <= 0:
        raise MockValidationError("workspace_id must be > 0")
    return value


def _validate_screen_id(value: object) -> str:
    if not isinstance(value, str):
        raise MockValidationError("screen_id must be string")
    s = value.strip()
    if not s:
        raise MockValidationError("screen_id must not be empty")
    if not SCREEN_ID_PATTERN.match(s):
        raise MockValidationError(
            "screen_id contains invalid chars (allowed: [A-Za-z0-9_-:.] up to 64)",
        )
    return s


def _validate_html(value: object) -> str:
    if not isinstance(value, str):
        raise MockValidationError("html must be string")
    # size guard (utf-8 byte length)
    try:
        nbytes = len(value.encode("utf-8"))
    except Exception as e:
        raise MockValidationError(f"html encoding failed: {e}") from e
    if nbytes > MAX_HTML_BYTES:
        raise MockHtmlTooLargeError(
            f"html body too large: {nbytes} > {MAX_HTML_BYTES} bytes (1MB max)",
        )
    return value


def _is_lock_expired(record: _MockRecord) -> bool:
    if not record.locked_by:
        return True
    return (_now_epoch() - record.locked_at) > LOCK_TTL_SECONDS


# ──────────────────────────────────────────────────────────────────────
# Public read API
# ──────────────────────────────────────────────────────────────────────


def list_mocks(workspace_id: int) -> dict:
    """workspace 内の全 mock を返す (AC-F6)."""
    ws = _validate_workspace_id(workspace_id)
    with _lock:
        items: list[dict] = []
        for (rec_ws, _sid), rec in _store.items():
            if rec_ws != ws:
                continue
            items.append(_serialize_summary(rec))
        items.sort(key=lambda r: r["screen_id"])
    return {"mocks": items, "total": len(items)}


def get_mock(workspace_id: int, screen_id: str) -> dict:
    """画面詳細 (screen / html_url / version) を返す (AC-F9)."""
    ws = _validate_workspace_id(workspace_id)
    sid = _validate_screen_id(screen_id)
    with _lock:
        rec = _store.get((ws, sid))
    if not rec or not rec.versions:
        raise MockNotFoundError(f"mock not found: workspace={ws} screen={sid}")
    return {
        "screen": {
            "id": rec.screen_id,
            "name": rec.name or rec.screen_id,
            "workspace_id": rec.workspace_id,
        },
        "html_url": _build_html_url(rec),
        "version": rec.latest_version,
    }


def get_mock_html(workspace_id: int, screen_id: str) -> dict:
    """画面 HTML (最新 version) を返す (AC-F1 / AC-F12)."""
    ws = _validate_workspace_id(workspace_id)
    sid = _validate_screen_id(screen_id)
    with _lock:
        rec = _store.get((ws, sid))
    if not rec or not rec.versions:
        raise MockNotFoundError(f"mock not found: workspace={ws} screen={sid}")
    return {"html": rec.latest_html, "version": rec.latest_version}


# ──────────────────────────────────────────────────────────────────────
# Public write API
# ──────────────────────────────────────────────────────────────────────


def put_mock_html(
    workspace_id: int,
    screen_id: str,
    html: str,
    *,
    actor_user_id: Optional[str] = None,
    name: Optional[str] = None,
) -> dict:
    """新 HTML を upsert + version increment (AC-F2 / AC-F14).

    Concurrent edit 検知 (AC-F5): 他 actor が同一 screen を編集中なら 409.
    1MB 超過 (AC-F3): 422.
    """
    ws = _validate_workspace_id(workspace_id)
    sid = _validate_screen_id(screen_id)
    body = _validate_html(html)

    now_iso = _now_iso()
    now_ep = _now_epoch()

    with _lock:
        rec = _store.get((ws, sid))
        if rec is None:
            rec = _MockRecord(workspace_id=ws, screen_id=sid, name=name or sid)
            _store[(ws, sid)] = rec
        else:
            # concurrent edit lock check
            if (
                rec.locked_by
                and actor_user_id is not None
                and rec.locked_by != actor_user_id
                and not _is_lock_expired(rec)
            ):
                raise MockLockedError(
                    f"mock locked by another user: {rec.locked_by!r} "
                    f"(workspace={ws} screen={sid})",
                )
            if name and not rec.name:
                rec.name = name
        new_version = rec.latest_version + 1
        rec.versions.append(_MockSnapshot(
            version=new_version,
            html=body,
            updated_at=now_iso,
            updated_by=actor_user_id,
        ))
        rec.locked_by = actor_user_id
        rec.locked_at = now_ep
    return {"new_version": new_version, "updated_at": now_iso}


# ──────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────


def _serialize_summary(rec: _MockRecord) -> dict:
    return {
        "screen_id": rec.screen_id,
        "name": rec.name or rec.screen_id,
        "workspace_id": rec.workspace_id,
        "version": rec.latest_version,
        "updated_at": rec.latest_updated_at,
        "html_url": _build_html_url(rec),
    }


def _build_html_url(rec: _MockRecord) -> str:
    return (
        f"/api/workspaces/{rec.workspace_id}/mocks/{rec.screen_id}/html"
    )
