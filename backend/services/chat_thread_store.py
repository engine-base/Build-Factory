"""T-M30-01: ChatThread / ChatMessage CRUD (M-30 schema).

既存の legacy `routers/threads.py` (company-os pattern with conversation_log) は
不変のまま、Build-Factory M-30 schema (chat_threads / chat_messages,
supabase migration 20260510000003) に対応する CRUD store + service を追加する.

chat_threads (id, workspace_id, session_id, title, persona, is_archived,
              created_at, updated_at)
chat_messages (id, thread_id, role, content, compressed_summary, token_count,
               created_at)

設計:
  - in-memory thread-safe store (production では Supabase Postgres を介するが
    本タスクは application 層 API のみ; DDL は migration 済み)
  - role は 'user' / 'assistant' / 'system' / 'tool' (CHECK 制約と一致)
  - workspace_id を持つ thread は workspace 単位の list で取得可能
  - persistent state mutation は失敗時にロールバック
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class ChatThreadError(RuntimeError):
    pass


VALID_ROLES = ("user", "assistant", "system", "tool")
MAX_TITLE_LEN = 200
MAX_PERSONA_LEN = 100
MAX_CONTENT_CHARS = 200_000
MAX_THREADS_PER_WORKSPACE = 10_000
MAX_MESSAGES_PER_THREAD = 100_000
MAX_THREADS_TOTAL = 1_000_000


@dataclass
class ChatThread:
    id: int
    workspace_id: Optional[int]
    session_id: Optional[int]
    title: Optional[str]
    persona: Optional[str]
    is_archived: bool
    created_at: float
    updated_at: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
            "title": self.title,
            "persona": self.persona,
            "is_archived": self.is_archived,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ChatMessage:
    id: int
    thread_id: int
    role: str
    content: str
    compressed_summary: Optional[dict]
    token_count: Optional[int]
    created_at: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "role": self.role,
            "content": self.content,
            "compressed_summary": dict(self.compressed_summary) if self.compressed_summary else None,
            "token_count": self.token_count,
            "created_at": self.created_at,
        }


class ChatThreadStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._threads: dict[int, ChatThread] = {}
        self._messages: dict[int, ChatMessage] = {}
        self._by_thread: dict[int, list[int]] = {}
        self._by_workspace: dict[int, list[int]] = {}
        self._next_thread_id = 1
        self._next_message_id = 1

    # ── validation helpers ──────────────────────────────────────────────

    @staticmethod
    def _validate_title(title: Optional[str]) -> Optional[str]:
        if title is None:
            return None
        if not isinstance(title, str):
            raise ChatThreadError("title must be string or null")
        if len(title) > MAX_TITLE_LEN:
            raise ChatThreadError(f"title must be <= {MAX_TITLE_LEN} chars")
        return title

    @staticmethod
    def _validate_persona(persona: Optional[str]) -> Optional[str]:
        if persona is None:
            return None
        if not isinstance(persona, str):
            raise ChatThreadError("persona must be string or null")
        if not persona.strip():
            raise ChatThreadError("persona must not be empty when provided")
        if len(persona) > MAX_PERSONA_LEN:
            raise ChatThreadError(f"persona must be <= {MAX_PERSONA_LEN} chars")
        return persona.strip()

    @staticmethod
    def _validate_workspace_id(ws: Optional[int]) -> Optional[int]:
        if ws is None:
            return None
        if not isinstance(ws, int) or ws <= 0:
            raise ChatThreadError("workspace_id must be > 0")
        return ws

    @staticmethod
    def _validate_session_id(sid: Optional[int]) -> Optional[int]:
        if sid is None:
            return None
        if not isinstance(sid, int) or sid <= 0:
            raise ChatThreadError("session_id must be > 0")
        return sid

    @staticmethod
    def _validate_role(role: str) -> str:
        if not isinstance(role, str) or role not in VALID_ROLES:
            raise ChatThreadError(f"role must be one of {VALID_ROLES}")
        return role

    @staticmethod
    def _validate_content(content: str) -> str:
        if not isinstance(content, str):
            raise ChatThreadError("content must be string")
        if not content.strip():
            raise ChatThreadError("content must not be empty")
        if len(content) > MAX_CONTENT_CHARS:
            raise ChatThreadError(
                f"content must be <= {MAX_CONTENT_CHARS} chars"
            )
        return content

    @staticmethod
    def _validate_token_count(tc: Optional[int]) -> Optional[int]:
        if tc is None:
            return None
        if not isinstance(tc, int) or tc < 0:
            raise ChatThreadError("token_count must be >= 0")
        return tc

    @staticmethod
    def _validate_compressed_summary(s: Optional[dict]) -> Optional[dict]:
        if s is None:
            return None
        if not isinstance(s, dict):
            raise ChatThreadError("compressed_summary must be a dict or null")
        return s

    # ── thread CRUD ──────────────────────────────────────────────────────

    def create_thread(
        self,
        *,
        workspace_id: Optional[int] = None,
        session_id: Optional[int] = None,
        title: Optional[str] = None,
        persona: Optional[str] = None,
    ) -> ChatThread:
        workspace_id = self._validate_workspace_id(workspace_id)
        session_id = self._validate_session_id(session_id)
        title = self._validate_title(title)
        persona = self._validate_persona(persona)
        with self._lock:
            if len(self._threads) >= MAX_THREADS_TOTAL:
                raise ChatThreadError(
                    f"max threads total reached: {MAX_THREADS_TOTAL}"
                )
            if workspace_id is not None:
                if len(self._by_workspace.get(workspace_id, [])) >= MAX_THREADS_PER_WORKSPACE:
                    raise ChatThreadError(
                        f"max threads per workspace reached: {MAX_THREADS_PER_WORKSPACE}"
                    )
            now = time.time()
            tid = self._next_thread_id
            self._next_thread_id += 1
            t = ChatThread(
                id=tid,
                workspace_id=workspace_id,
                session_id=session_id,
                title=title,
                persona=persona,
                is_archived=False,
                created_at=now,
                updated_at=now,
            )
            self._threads[tid] = t
            self._by_thread[tid] = []
            if workspace_id is not None:
                self._by_workspace.setdefault(workspace_id, []).append(tid)
            return t

    def get_thread(self, thread_id: int) -> Optional[ChatThread]:
        if not isinstance(thread_id, int) or thread_id <= 0:
            raise ChatThreadError("thread_id must be > 0")
        with self._lock:
            return self._threads.get(thread_id)

    def list_threads(
        self,
        *,
        workspace_id: Optional[int] = None,
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[ChatThread]:
        if workspace_id is not None:
            workspace_id = self._validate_workspace_id(workspace_id)
        if not isinstance(limit, int) or limit <= 0 or limit > 10_000:
            raise ChatThreadError("limit must be 1..10000")
        with self._lock:
            if workspace_id is not None:
                ids = list(self._by_workspace.get(workspace_id, []))
                threads = [self._threads[i] for i in ids if i in self._threads]
            else:
                threads = list(self._threads.values())
        if not include_archived:
            threads = [t for t in threads if not t.is_archived]
        threads.sort(key=lambda t: t.updated_at, reverse=True)
        return threads[:limit]

    def update_thread(
        self,
        thread_id: int,
        *,
        title: Optional[str] = None,
        persona: Optional[str] = None,
        is_archived: Optional[bool] = None,
    ) -> ChatThread:
        if not isinstance(thread_id, int) or thread_id <= 0:
            raise ChatThreadError("thread_id must be > 0")
        if title is None and persona is None and is_archived is None:
            raise ChatThreadError("at least one field must be provided")
        if title is not None:
            title = self._validate_title(title)
        if persona is not None:
            persona = self._validate_persona(persona)
        if is_archived is not None and not isinstance(is_archived, bool):
            raise ChatThreadError("is_archived must be bool")
        with self._lock:
            t = self._threads.get(thread_id)
            if t is None:
                raise ChatThreadError(f"thread not found: {thread_id}")
            if title is not None:
                t.title = title
            if persona is not None:
                t.persona = persona
            if is_archived is not None:
                t.is_archived = is_archived
            t.updated_at = time.time()
            return t

    def delete_thread(self, thread_id: int) -> bool:
        if not isinstance(thread_id, int) or thread_id <= 0:
            raise ChatThreadError("thread_id must be > 0")
        with self._lock:
            t = self._threads.pop(thread_id, None)
            if t is None:
                return False
            for mid in self._by_thread.pop(thread_id, []):
                self._messages.pop(mid, None)
            if t.workspace_id is not None:
                ids = self._by_workspace.get(t.workspace_id, [])
                if thread_id in ids:
                    ids.remove(thread_id)
            return True

    # ── message CRUD ─────────────────────────────────────────────────────

    def add_message(
        self,
        thread_id: int,
        role: str,
        content: str,
        *,
        compressed_summary: Optional[dict] = None,
        token_count: Optional[int] = None,
    ) -> ChatMessage:
        if not isinstance(thread_id, int) or thread_id <= 0:
            raise ChatThreadError("thread_id must be > 0")
        role = self._validate_role(role)
        content = self._validate_content(content)
        compressed_summary = self._validate_compressed_summary(compressed_summary)
        token_count = self._validate_token_count(token_count)
        with self._lock:
            if thread_id not in self._threads:
                raise ChatThreadError(f"thread not found: {thread_id}")
            mids = self._by_thread.setdefault(thread_id, [])
            if len(mids) >= MAX_MESSAGES_PER_THREAD:
                raise ChatThreadError(
                    f"max messages per thread reached: {MAX_MESSAGES_PER_THREAD}"
                )
            now = time.time()
            mid = self._next_message_id
            self._next_message_id += 1
            m = ChatMessage(
                id=mid,
                thread_id=thread_id,
                role=role,
                content=content,
                compressed_summary=compressed_summary,
                token_count=token_count,
                created_at=now,
            )
            self._messages[mid] = m
            mids.append(mid)
            self._threads[thread_id].updated_at = now
            return m

    def get_message(self, message_id: int) -> Optional[ChatMessage]:
        if not isinstance(message_id, int) or message_id <= 0:
            raise ChatThreadError("message_id must be > 0")
        with self._lock:
            return self._messages.get(message_id)

    def list_messages(
        self,
        thread_id: int,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ChatMessage]:
        if not isinstance(thread_id, int) or thread_id <= 0:
            raise ChatThreadError("thread_id must be > 0")
        if not isinstance(limit, int) or limit <= 0 or limit > 10_000:
            raise ChatThreadError("limit must be 1..10000")
        if not isinstance(offset, int) or offset < 0:
            raise ChatThreadError("offset must be >= 0")
        with self._lock:
            if thread_id not in self._threads:
                raise ChatThreadError(f"thread not found: {thread_id}")
            mids = list(self._by_thread.get(thread_id, []))
        items = [self._messages[m] for m in mids if m in self._messages]
        return items[offset:offset + limit]

    def delete_message(self, message_id: int) -> bool:
        if not isinstance(message_id, int) or message_id <= 0:
            raise ChatThreadError("message_id must be > 0")
        with self._lock:
            m = self._messages.pop(message_id, None)
            if m is None:
                return False
            mids = self._by_thread.get(m.thread_id, [])
            if message_id in mids:
                mids.remove(message_id)
            return True

    def count_messages(self, thread_id: int) -> int:
        if not isinstance(thread_id, int) or thread_id <= 0:
            raise ChatThreadError("thread_id must be > 0")
        with self._lock:
            return len(self._by_thread.get(thread_id, []))


# ──────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────


_store: Optional[ChatThreadStore] = None
_singleton_lock = threading.Lock()


def get_store() -> ChatThreadStore:
    global _store
    with _singleton_lock:
        if _store is None:
            _store = ChatThreadStore()
        return _store


def reset_store() -> None:
    global _store
    with _singleton_lock:
        _store = ChatThreadStore()
