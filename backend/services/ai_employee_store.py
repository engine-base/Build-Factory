"""T-022-03: AI 社員 CRUD store (M-22 schema; existing employees.py 拡張).

既存の legacy routers/employees.py (company-os, employees + chat) は不変.
Build-Factory M-22 schema (ai_employees + ai_personas,
supabase migration 20260512200000) に対応する CRUD store を追加する.

設計:
  - ai_employees: (workspace_id, employee_key) UNIQUE
  - role_level: secretary / leader / member (CHECK 制約)
  - persona は別エンティティで FK SET NULL (delete 時)
  - is_active = false + retired_at で論理削除 (BMAD 10 ペルソナの引き継ぎ
    と整合)
  - thread-safe in-memory; production は Supabase Postgres
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class AIEmployeeError(RuntimeError):
    pass


VALID_ROLE_LEVELS = ("secretary", "leader", "member")
MAX_KEY_LEN = 64
MAX_NAME_LEN = 200
MAX_PERSONA_LEN = 500
MAX_EMPLOYEES_PER_WORKSPACE = 200
MAX_EMPLOYEES_TOTAL = 100_000
MAX_PERSONAS_TOTAL = 10_000


@dataclass
class Persona:
    id: int
    persona_key: str
    persona_name: str
    personality: Optional[str] = None
    tone_style: Optional[str] = None
    catchphrase: Optional[str] = None
    specialty: Optional[str] = None
    handles: Optional[str] = None
    avatar_lucide: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "persona_key": self.persona_key,
            "persona_name": self.persona_name,
            "personality": self.personality,
            "tone_style": self.tone_style,
            "catchphrase": self.catchphrase,
            "specialty": self.specialty,
            "handles": self.handles,
            "avatar_lucide": self.avatar_lucide,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


@dataclass
class AIEmployee:
    id: int
    workspace_id: Optional[int]
    employee_key: str
    display_name: str
    persona_id: Optional[int] = None
    role_level: str = "leader"
    is_active: bool = True
    retired_at: Optional[float] = None
    retire_reason: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "employee_key": self.employee_key,
            "display_name": self.display_name,
            "persona_id": self.persona_id,
            "role_level": self.role_level,
            "is_active": self.is_active,
            "retired_at": self.retired_at,
            "retire_reason": self.retire_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _validate_key(key: str, *, field_name: str = "key") -> str:
    if not isinstance(key, str) or not key.strip():
        raise AIEmployeeError(f"{field_name} must not be empty")
    key = key.strip()
    if len(key) > MAX_KEY_LEN:
        raise AIEmployeeError(f"{field_name} must be <= {MAX_KEY_LEN} chars")
    # snake_case / kebab-case 風: 英数字 + - _
    if not all(c.isalnum() or c in "-_" for c in key):
        raise AIEmployeeError(
            f"{field_name} must contain only alphanumeric, '-', '_'"
        )
    return key


def _validate_optional_str(value, *, field_name: str, max_len: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AIEmployeeError(f"{field_name} must be string or null")
    if not value.strip():
        raise AIEmployeeError(f"{field_name} must not be empty when provided")
    if len(value) > max_len:
        raise AIEmployeeError(f"{field_name} must be <= {max_len} chars")
    return value.strip()


def _validate_required_str(value, *, field_name: str, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AIEmployeeError(f"{field_name} must not be empty")
    value = value.strip()
    if len(value) > max_len:
        raise AIEmployeeError(f"{field_name} must be <= {max_len} chars")
    return value


def _validate_role_level(role: str) -> str:
    if not isinstance(role, str) or role not in VALID_ROLE_LEVELS:
        raise AIEmployeeError(
            f"role_level must be one of {VALID_ROLE_LEVELS}"
        )
    return role


def _validate_optional_positive(v, *, field_name: str) -> Optional[int]:
    if v is None:
        return None
    if not isinstance(v, int) or v <= 0:
        raise AIEmployeeError(f"{field_name} must be > 0")
    return v


class AIEmployeeStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._employees: dict[int, AIEmployee] = {}
        self._personas: dict[int, Persona] = {}
        self._persona_by_key: dict[str, int] = {}
        self._by_workspace: dict[Optional[int], list[int]] = {}
        self._by_ws_key: dict[tuple[Optional[int], str], int] = {}
        self._next_employee_id = 1
        self._next_persona_id = 1

    # ── persona CRUD ────────────────────────────────────────────────────

    def create_persona(
        self,
        persona_key: str,
        persona_name: str,
        *,
        personality: Optional[str] = None,
        tone_style: Optional[str] = None,
        catchphrase: Optional[str] = None,
        specialty: Optional[str] = None,
        handles: Optional[str] = None,
        avatar_lucide: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Persona:
        persona_key = _validate_key(persona_key, field_name="persona_key")
        persona_name = _validate_required_str(
            persona_name, field_name="persona_name", max_len=MAX_NAME_LEN,
        )
        personality = _validate_optional_str(
            personality, field_name="personality", max_len=MAX_PERSONA_LEN,
        )
        tone_style = _validate_optional_str(
            tone_style, field_name="tone_style", max_len=MAX_PERSONA_LEN,
        )
        catchphrase = _validate_optional_str(
            catchphrase, field_name="catchphrase", max_len=MAX_PERSONA_LEN,
        )
        specialty = _validate_optional_str(
            specialty, field_name="specialty", max_len=MAX_PERSONA_LEN,
        )
        handles = _validate_optional_str(
            handles, field_name="handles", max_len=MAX_PERSONA_LEN,
        )
        avatar_lucide = _validate_optional_str(
            avatar_lucide, field_name="avatar_lucide", max_len=64,
        )
        if metadata is not None and not isinstance(metadata, dict):
            raise AIEmployeeError("metadata must be a dict or null")
        with self._lock:
            if persona_key in self._persona_by_key:
                raise AIEmployeeError(
                    f"persona_key already exists: {persona_key}"
                )
            if len(self._personas) >= MAX_PERSONAS_TOTAL:
                raise AIEmployeeError(
                    f"max personas total reached: {MAX_PERSONAS_TOTAL}"
                )
            pid = self._next_persona_id
            self._next_persona_id += 1
            now = time.time()
            p = Persona(
                id=pid,
                persona_key=persona_key,
                persona_name=persona_name,
                personality=personality,
                tone_style=tone_style,
                catchphrase=catchphrase,
                specialty=specialty,
                handles=handles,
                avatar_lucide=avatar_lucide,
                metadata=dict(metadata or {}),
                created_at=now,
            )
            self._personas[pid] = p
            self._persona_by_key[persona_key] = pid
            return p

    def get_persona(self, persona_id: int) -> Optional[Persona]:
        if not isinstance(persona_id, int) or persona_id <= 0:
            raise AIEmployeeError("persona_id must be > 0")
        with self._lock:
            return self._personas.get(persona_id)

    def get_persona_by_key(self, persona_key: str) -> Optional[Persona]:
        persona_key = _validate_key(persona_key, field_name="persona_key")
        with self._lock:
            pid = self._persona_by_key.get(persona_key)
            return self._personas.get(pid) if pid else None

    def list_personas(self) -> list[Persona]:
        with self._lock:
            return sorted(self._personas.values(), key=lambda p: p.id)

    def delete_persona(self, persona_id: int) -> bool:
        if not isinstance(persona_id, int) or persona_id <= 0:
            raise AIEmployeeError("persona_id must be > 0")
        with self._lock:
            p = self._personas.pop(persona_id, None)
            if p is None:
                return False
            self._persona_by_key.pop(p.persona_key, None)
            # FK SET NULL: 引用先 employee の persona_id を None に
            for emp in self._employees.values():
                if emp.persona_id == persona_id:
                    emp.persona_id = None
                    emp.updated_at = time.time()
            return True

    # ── employee CRUD ───────────────────────────────────────────────────

    def create_employee(
        self,
        employee_key: str,
        display_name: str,
        *,
        workspace_id: Optional[int] = None,
        persona_id: Optional[int] = None,
        role_level: str = "leader",
    ) -> AIEmployee:
        employee_key = _validate_key(employee_key, field_name="employee_key")
        display_name = _validate_required_str(
            display_name, field_name="display_name", max_len=MAX_NAME_LEN,
        )
        workspace_id = _validate_optional_positive(
            workspace_id, field_name="workspace_id",
        )
        persona_id = _validate_optional_positive(
            persona_id, field_name="persona_id",
        )
        role_level = _validate_role_level(role_level)
        with self._lock:
            if persona_id is not None and persona_id not in self._personas:
                raise AIEmployeeError(f"persona_id not found: {persona_id}")
            key = (workspace_id, employee_key)
            if key in self._by_ws_key:
                raise AIEmployeeError(
                    f"employee_key already exists in workspace: {employee_key}"
                )
            if len(self._by_workspace.get(workspace_id, [])) >= MAX_EMPLOYEES_PER_WORKSPACE:
                raise AIEmployeeError(
                    f"max employees per workspace reached: {MAX_EMPLOYEES_PER_WORKSPACE}"
                )
            if len(self._employees) >= MAX_EMPLOYEES_TOTAL:
                raise AIEmployeeError(
                    f"max employees total reached: {MAX_EMPLOYEES_TOTAL}"
                )
            eid = self._next_employee_id
            self._next_employee_id += 1
            now = time.time()
            e = AIEmployee(
                id=eid,
                workspace_id=workspace_id,
                employee_key=employee_key,
                display_name=display_name,
                persona_id=persona_id,
                role_level=role_level,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            self._employees[eid] = e
            self._by_workspace.setdefault(workspace_id, []).append(eid)
            self._by_ws_key[key] = eid
            return e

    def get_employee(self, employee_id: int) -> Optional[AIEmployee]:
        if not isinstance(employee_id, int) or employee_id <= 0:
            raise AIEmployeeError("employee_id must be > 0")
        with self._lock:
            return self._employees.get(employee_id)

    def get_employee_by_key(
        self, employee_key: str, *, workspace_id: Optional[int] = None,
    ) -> Optional[AIEmployee]:
        employee_key = _validate_key(employee_key, field_name="employee_key")
        workspace_id = _validate_optional_positive(
            workspace_id, field_name="workspace_id",
        )
        with self._lock:
            eid = self._by_ws_key.get((workspace_id, employee_key))
            return self._employees.get(eid) if eid else None

    def list_employees(
        self,
        *,
        workspace_id: Optional[int] = None,
        role_level: Optional[str] = None,
        include_inactive: bool = False,
        limit: int = 200,
    ) -> list[AIEmployee]:
        if workspace_id is not None:
            workspace_id = _validate_optional_positive(
                workspace_id, field_name="workspace_id",
            )
        if role_level is not None:
            role_level = _validate_role_level(role_level)
        if not isinstance(limit, int) or limit <= 0 or limit > 10_000:
            raise AIEmployeeError("limit must be 1..10000")
        with self._lock:
            if workspace_id is not None:
                ids = list(self._by_workspace.get(workspace_id, []))
                items = [self._employees[i] for i in ids if i in self._employees]
            else:
                items = list(self._employees.values())
        if role_level is not None:
            items = [e for e in items if e.role_level == role_level]
        if not include_inactive:
            items = [e for e in items if e.is_active]
        items.sort(key=lambda e: e.id)
        return items[:limit]

    def update_employee(
        self,
        employee_id: int,
        *,
        display_name: Optional[str] = None,
        persona_id: Optional[int] = None,
        role_level: Optional[str] = None,
    ) -> AIEmployee:
        if not isinstance(employee_id, int) or employee_id <= 0:
            raise AIEmployeeError("employee_id must be > 0")
        if display_name is None and persona_id is None and role_level is None:
            raise AIEmployeeError("at least one field must be provided")
        if display_name is not None:
            display_name = _validate_required_str(
                display_name, field_name="display_name", max_len=MAX_NAME_LEN,
            )
        if persona_id is not None:
            persona_id = _validate_optional_positive(
                persona_id, field_name="persona_id",
            )
        if role_level is not None:
            role_level = _validate_role_level(role_level)
        with self._lock:
            e = self._employees.get(employee_id)
            if e is None:
                raise AIEmployeeError(f"employee not found: {employee_id}")
            if persona_id is not None and persona_id not in self._personas:
                raise AIEmployeeError(f"persona_id not found: {persona_id}")
            if display_name is not None:
                e.display_name = display_name
            if persona_id is not None:
                e.persona_id = persona_id
            if role_level is not None:
                e.role_level = role_level
            e.updated_at = time.time()
            return e

    def retire_employee(
        self,
        employee_id: int,
        *,
        reason: Optional[str] = None,
    ) -> AIEmployee:
        if not isinstance(employee_id, int) or employee_id <= 0:
            raise AIEmployeeError("employee_id must be > 0")
        reason = _validate_optional_str(
            reason, field_name="reason", max_len=500,
        )
        with self._lock:
            e = self._employees.get(employee_id)
            if e is None:
                raise AIEmployeeError(f"employee not found: {employee_id}")
            if not e.is_active:
                raise AIEmployeeError(f"employee already retired: {employee_id}")
            e.is_active = False
            e.retired_at = time.time()
            e.retire_reason = reason
            e.updated_at = e.retired_at
            return e

    def reactivate_employee(self, employee_id: int) -> AIEmployee:
        if not isinstance(employee_id, int) or employee_id <= 0:
            raise AIEmployeeError("employee_id must be > 0")
        with self._lock:
            e = self._employees.get(employee_id)
            if e is None:
                raise AIEmployeeError(f"employee not found: {employee_id}")
            if e.is_active:
                raise AIEmployeeError(f"employee already active: {employee_id}")
            e.is_active = True
            e.retired_at = None
            e.retire_reason = None
            e.updated_at = time.time()
            return e

    def delete_employee(self, employee_id: int) -> bool:
        if not isinstance(employee_id, int) or employee_id <= 0:
            raise AIEmployeeError("employee_id must be > 0")
        with self._lock:
            e = self._employees.pop(employee_id, None)
            if e is None:
                return False
            self._by_ws_key.pop((e.workspace_id, e.employee_key), None)
            ids = self._by_workspace.get(e.workspace_id, [])
            if employee_id in ids:
                ids.remove(employee_id)
            return True


# ──────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────


_store: Optional[AIEmployeeStore] = None
_singleton_lock = threading.Lock()


def get_store() -> AIEmployeeStore:
    global _store
    with _singleton_lock:
        if _store is None:
            _store = AIEmployeeStore()
        return _store


def reset_store() -> None:
    global _store
    with _singleton_lock:
        _store = AIEmployeeStore()
