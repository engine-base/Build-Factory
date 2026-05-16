"""T-V3-B-07 / F-005: Hearing save / Spec / Comment in-memory CRUD store.

実装方針:
  - 既存 routers/hearing.py (4STEP 対話駆動) は不変. 本タスクの目的は v3 phase 1
    F-005 API contract に従う 4 endpoint (hearing/save, specs list,
    spec comments list/add) のサーバ側実装である.
  - hearings / specs / comments テーブルは現時点で migration 化されていない.
    本タスクでは in-memory thread-safe store を提供し、API contract と AC
    (slot_state 永続化 / monotonic version / paused→resume / 10000 char limit)
    の振る舞いを満たす. Postgres 実装は Phase 1.5 で置き換え.

スレッド安全性:
  - 単一プロセス内の RLock で保護. テストは reset_store() でクリア可.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

# ----------------------------------------------------------------
# Validation / quota
# ----------------------------------------------------------------

MAX_TRANSCRIPT_CHARS = 200_000  # hearing.transcript
MAX_COMMENT_BODY_CHARS = 10_000  # F-005 AC-F3: > 10000 chars → 422
MAX_COMMENT_ANCHOR_CHARS = 500
VALID_HEARING_STATUS = ("active", "paused", "completed")


class SpecsStoreError(RuntimeError):
    """T-V3-B-07: invalid input or quota violation."""


# ----------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------


@dataclass
class Hearing:
    """E-009 Hearing (in-memory; v3 phase 1.0)."""

    id: str
    workspace_id: str
    slot_state: dict = field(default_factory=dict)
    transcript: str = ""
    version: int = 1
    status: str = "active"
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "slot_state": dict(self.slot_state),
            "transcript": self.transcript,
            "version": self.version,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Spec:
    """E-010 Spec (in-memory; v3 phase 1.0)."""

    id: str
    workspace_id: str
    hearing_id: Optional[str]
    title: str
    html_url: Optional[str]
    body_md: Optional[str]
    version: int = 1
    status: str = "draft"
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "hearing_id": self.hearing_id,
            "title": self.title,
            "html_url": self.html_url,
            "body_md": self.body_md,
            "version": self.version,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Comment:
    """E-030 Comment (in-memory; v3 phase 1.0)."""

    id: str
    workspace_id: str
    spec_id: str
    author_user_id: Optional[str]
    body: str
    anchor: Optional[str]
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "spec_id": self.spec_id,
            "author_user_id": self.author_user_id,
            "body": self.body,
            "anchor": self.anchor,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ----------------------------------------------------------------
# Validation helpers
# ----------------------------------------------------------------


def _validate_workspace_id(workspace_id: str) -> str:
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise SpecsStoreError("workspace_id must be a non-empty string")
    return workspace_id


def _validate_slot_state(slot_state: object) -> dict:
    if slot_state is None:
        return {}
    if not isinstance(slot_state, dict):
        raise SpecsStoreError("slot_state must be an object")
    return dict(slot_state)


def _validate_transcript(transcript: object) -> str:
    if transcript is None:
        return ""
    if not isinstance(transcript, str):
        raise SpecsStoreError("transcript must be a string")
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise SpecsStoreError(
            f"transcript must be <= {MAX_TRANSCRIPT_CHARS} chars"
        )
    return transcript


def _validate_comment_body(body: object) -> str:
    if not isinstance(body, str):
        raise SpecsStoreError("body must be a string")
    if not body.strip():
        raise SpecsStoreError("body must not be empty")
    # AC-F3: UNWANTED — body > 10000 chars → 422
    if len(body) > MAX_COMMENT_BODY_CHARS:
        raise SpecsStoreError(
            f"body must be <= {MAX_COMMENT_BODY_CHARS} chars"
        )
    return body


def _validate_comment_anchor(anchor: object) -> Optional[str]:
    if anchor is None:
        return None
    if not isinstance(anchor, str):
        raise SpecsStoreError("anchor must be a string or null")
    if len(anchor) > MAX_COMMENT_ANCHOR_CHARS:
        raise SpecsStoreError(
            f"anchor must be <= {MAX_COMMENT_ANCHOR_CHARS} chars"
        )
    return anchor


def _validate_hearing_status(status: object) -> str:
    if not isinstance(status, str):
        raise SpecsStoreError("status must be a string")
    if status not in VALID_HEARING_STATUS:
        raise SpecsStoreError(
            f"status must be one of {VALID_HEARING_STATUS}, got {status!r}"
        )
    return status


# ----------------------------------------------------------------
# Store
# ----------------------------------------------------------------


class SpecsStore:
    """T-V3-B-07: hearings / specs / comments in-memory CRUD.

    F-005 contract:
      - POST /hearing/save: persist slot_state, monotonic version,
        accept while status='paused' to resume.
      - GET /specs: list specs for workspace.
      - GET /specs/{spec_id}/comments: list comments for spec.
      - POST /specs/{spec_id}/comments: add comment (body <= 10000 chars).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._hearings: dict[str, Hearing] = {}
        # workspace -> latest hearing id (active or paused)
        self._latest_hearing_per_workspace: dict[str, str] = {}
        self._specs: dict[str, Spec] = {}
        self._comments: dict[str, Comment] = {}
        # spec_id -> ordered list of comment_ids
        self._comments_by_spec: dict[str, list[str]] = {}

    # ── Hearing ──────────────────────────────────────────────────────────

    def save_hearing(
        self,
        workspace_id: str,
        *,
        slot_state: object = None,
        transcript: object = None,
        hearing_id: Optional[str] = None,
        target_status: Optional[str] = None,
    ) -> Hearing:
        """Persist hearing slot_state with monotonically increasing version.

        AC-F1 (EVENT-DRIVEN): version is incremented on each save.
        AC-F2 (STATE-DRIVEN): accept while status='paused' to resume.
        """
        ws = _validate_workspace_id(workspace_id)
        state = _validate_slot_state(slot_state)
        ts = _validate_transcript(transcript)
        new_status: Optional[str] = None
        if target_status is not None:
            new_status = _validate_hearing_status(target_status)

        with self._lock:
            now = time.time()
            # Determine which hearing to update
            existing: Optional[Hearing] = None
            if hearing_id is not None:
                if not isinstance(hearing_id, str) or not hearing_id.strip():
                    raise SpecsStoreError("hearing_id must be a non-empty string")
                existing = self._hearings.get(hearing_id)
                if existing is None:
                    raise SpecsStoreError(f"hearing not found: {hearing_id}")
                if existing.workspace_id != ws:
                    raise SpecsStoreError(
                        f"hearing {hearing_id} does not belong to workspace {ws}"
                    )
            else:
                # Reuse the latest hearing for this workspace if present
                latest_id = self._latest_hearing_per_workspace.get(ws)
                if latest_id:
                    existing = self._hearings.get(latest_id)

            if existing is None:
                # Create new hearing
                new_id = str(uuid.uuid4())
                h = Hearing(
                    id=new_id,
                    workspace_id=ws,
                    slot_state=state,
                    transcript=ts,
                    version=1,
                    status=new_status or "active",
                    created_at=now,
                    updated_at=now,
                )
                self._hearings[new_id] = h
                self._latest_hearing_per_workspace[ws] = new_id
                return h

            # Update existing: monotonic version
            existing.slot_state = state
            existing.transcript = ts
            existing.version += 1
            existing.updated_at = now
            if new_status is not None:
                existing.status = new_status
            elif existing.status == "paused":
                # AC-F2: resume from paused
                existing.status = "active"
            return existing

    def get_hearing(self, hearing_id: str) -> Optional[Hearing]:
        with self._lock:
            return self._hearings.get(hearing_id)

    def get_latest_hearing(self, workspace_id: str) -> Optional[Hearing]:
        with self._lock:
            ws = _validate_workspace_id(workspace_id)
            hid = self._latest_hearing_per_workspace.get(ws)
            if not hid:
                return None
            return self._hearings.get(hid)

    def set_hearing_status(
        self, hearing_id: str, status: str, workspace_id: Optional[str] = None,
    ) -> Hearing:
        """Test/admin helper to put hearing into a specific status."""
        new_status = _validate_hearing_status(status)
        with self._lock:
            h = self._hearings.get(hearing_id)
            if h is None:
                raise SpecsStoreError(f"hearing not found: {hearing_id}")
            if workspace_id is not None and h.workspace_id != workspace_id:
                raise SpecsStoreError(
                    f"hearing {hearing_id} does not belong to workspace {workspace_id}"
                )
            h.status = new_status
            h.updated_at = time.time()
            return h

    # ── Spec ─────────────────────────────────────────────────────────────

    def create_spec(
        self,
        workspace_id: str,
        *,
        title: str,
        hearing_id: Optional[str] = None,
        html_url: Optional[str] = None,
        body_md: Optional[str] = None,
        status: str = "draft",
    ) -> Spec:
        ws = _validate_workspace_id(workspace_id)
        if not isinstance(title, str) or not title.strip():
            raise SpecsStoreError("title must be a non-empty string")
        if len(title) > 500:
            raise SpecsStoreError("title must be <= 500 chars")
        if hearing_id is not None and hearing_id not in self._hearings:
            raise SpecsStoreError(f"hearing not found: {hearing_id}")
        if status not in ("draft", "review", "published", "archived"):
            raise SpecsStoreError(f"invalid spec status: {status!r}")
        with self._lock:
            now = time.time()
            sid = str(uuid.uuid4())
            s = Spec(
                id=sid,
                workspace_id=ws,
                hearing_id=hearing_id,
                title=title,
                html_url=html_url,
                body_md=body_md,
                version=1,
                status=status,
                created_at=now,
                updated_at=now,
            )
            self._specs[sid] = s
            return s

    def list_specs(
        self, workspace_id: str, *, limit: int = 100, offset: int = 0,
    ) -> list[Spec]:
        ws = _validate_workspace_id(workspace_id)
        if not isinstance(limit, int) or limit <= 0 or limit > 1000:
            raise SpecsStoreError("limit must be 1..1000")
        if not isinstance(offset, int) or offset < 0:
            raise SpecsStoreError("offset must be >= 0")
        with self._lock:
            items = [s for s in self._specs.values() if s.workspace_id == ws]
            items.sort(key=lambda s: s.updated_at, reverse=True)
            return items[offset : offset + limit]

    def get_spec(self, spec_id: str) -> Optional[Spec]:
        with self._lock:
            return self._specs.get(spec_id)

    # ── Comment ──────────────────────────────────────────────────────────

    def add_comment(
        self,
        workspace_id: str,
        spec_id: str,
        *,
        body: str,
        anchor: Optional[str] = None,
        author_user_id: Optional[str] = None,
    ) -> Comment:
        """AC-F3 (UNWANTED): body > 10000 chars → SpecsStoreError → 422."""
        ws = _validate_workspace_id(workspace_id)
        if not isinstance(spec_id, str) or not spec_id.strip():
            raise SpecsStoreError("spec_id must be a non-empty string")
        b = _validate_comment_body(body)
        anc = _validate_comment_anchor(anchor)
        with self._lock:
            spec = self._specs.get(spec_id)
            if spec is None:
                raise SpecsStoreError(f"spec not found: {spec_id}")
            if spec.workspace_id != ws:
                raise SpecsStoreError(
                    f"spec {spec_id} does not belong to workspace {ws}"
                )
            now = time.time()
            cid = str(uuid.uuid4())
            c = Comment(
                id=cid,
                workspace_id=ws,
                spec_id=spec_id,
                author_user_id=author_user_id,
                body=b,
                anchor=anc,
                created_at=now,
                updated_at=now,
            )
            self._comments[cid] = c
            self._comments_by_spec.setdefault(spec_id, []).append(cid)
            return c

    def list_comments(
        self,
        workspace_id: str,
        spec_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Comment]:
        ws = _validate_workspace_id(workspace_id)
        if not isinstance(spec_id, str) or not spec_id.strip():
            raise SpecsStoreError("spec_id must be a non-empty string")
        if not isinstance(limit, int) or limit <= 0 or limit > 1000:
            raise SpecsStoreError("limit must be 1..1000")
        if not isinstance(offset, int) or offset < 0:
            raise SpecsStoreError("offset must be >= 0")
        with self._lock:
            spec = self._specs.get(spec_id)
            if spec is None:
                raise SpecsStoreError(f"spec not found: {spec_id}")
            if spec.workspace_id != ws:
                raise SpecsStoreError(
                    f"spec {spec_id} does not belong to workspace {ws}"
                )
            ids = list(self._comments_by_spec.get(spec_id, []))
            items = [self._comments[cid] for cid in ids if cid in self._comments]
            return items[offset : offset + limit]


# ----------------------------------------------------------------
# Singleton + reset helpers
# ----------------------------------------------------------------

_store: Optional[SpecsStore] = None
_singleton_lock = threading.Lock()


def get_store() -> SpecsStore:
    global _store
    with _singleton_lock:
        if _store is None:
            _store = SpecsStore()
        return _store


def reset_store() -> None:
    global _store
    with _singleton_lock:
        _store = None
