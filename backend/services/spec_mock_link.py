"""T-005b-04: 仕様 ↔ モック双方向リンク サービス.

仕様 (requirements section) と モック (design_mocks) の many-to-many リンクを管理する.
1 リンクは "spec_section_id" (string slug like 'overview.目的') と "mock_id" (int) を紐付ける.

storage は in-memory (DB バックエンドは将来差し替え可能).
公開 API:
  - create_link(workspace_id, spec_section_id, mock_id, *, created_by) -> dict
  - list_links_for_spec(spec_section_id) -> list[dict]
  - list_links_for_mock(mock_id) -> list[dict]
  - delete_link(link_id) -> bool
  - get_link(link_id) -> Optional[dict]
  - reset_store() (test 用)
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class SpecMockLinkError(RuntimeError):
    pass


class DuplicateLinkError(SpecMockLinkError):
    pass


class LinkNotFoundError(SpecMockLinkError):
    pass


@dataclass
class _Link:
    id: int
    workspace_id: int
    spec_section_id: str
    mock_id: int
    created_by: Optional[str] = None
    created_at: str = ""


# in-memory store
_lock = threading.Lock()
_links: dict[int, _Link] = {}
_next_id = 1


def reset_store() -> None:
    """test 用 reset."""
    global _next_id
    with _lock:
        _links.clear()
        _next_id = 1


def _serialize(link: _Link) -> dict:
    return {
        "id": link.id,
        "workspace_id": link.workspace_id,
        "spec_section_id": link.spec_section_id,
        "mock_id": link.mock_id,
        "created_by": link.created_by,
        "created_at": link.created_at,
    }


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_link(
    workspace_id: int,
    spec_section_id: str,
    mock_id: int,
    *,
    created_by: Optional[str] = None,
) -> dict:
    """新しいリンクを作る. (workspace_id, spec_section_id, mock_id) の組合せで unique."""
    if workspace_id is None or workspace_id <= 0:
        raise SpecMockLinkError("workspace_id must be > 0")
    if not spec_section_id or not spec_section_id.strip():
        raise SpecMockLinkError("spec_section_id must not be empty")
    if mock_id is None or mock_id <= 0:
        raise SpecMockLinkError("mock_id must be > 0")
    if len(spec_section_id) > 200:
        raise SpecMockLinkError("spec_section_id must be <= 200 chars")

    section = spec_section_id.strip()
    global _next_id
    with _lock:
        # 重複チェック
        for existing in _links.values():
            if (existing.workspace_id == workspace_id
                    and existing.spec_section_id == section
                    and existing.mock_id == mock_id):
                raise DuplicateLinkError(
                    f"link already exists (workspace={workspace_id}, "
                    f"section={section!r}, mock={mock_id})"
                )
        link = _Link(
            id=_next_id,
            workspace_id=workspace_id,
            spec_section_id=section,
            mock_id=mock_id,
            created_by=created_by,
            created_at=_now_iso(),
        )
        _links[_next_id] = link
        _next_id += 1
    return _serialize(link)


def list_links_for_spec(
    spec_section_id: str,
    *,
    workspace_id: Optional[int] = None,
) -> list[dict]:
    """spec section に紐付く mock 一覧."""
    if not spec_section_id or not spec_section_id.strip():
        return []
    section = spec_section_id.strip()
    with _lock:
        return [
            _serialize(link)
            for link in _links.values()
            if link.spec_section_id == section
            and (workspace_id is None or link.workspace_id == workspace_id)
        ]


def list_links_for_mock(
    mock_id: int,
    *,
    workspace_id: Optional[int] = None,
) -> list[dict]:
    """mock に紐付く spec section 一覧."""
    if mock_id is None or mock_id <= 0:
        return []
    with _lock:
        return [
            _serialize(link)
            for link in _links.values()
            if link.mock_id == mock_id
            and (workspace_id is None or link.workspace_id == workspace_id)
        ]


def get_link(link_id: int) -> Optional[dict]:
    with _lock:
        link = _links.get(link_id)
    return _serialize(link) if link else None


def delete_link(link_id: int) -> bool:
    with _lock:
        return _links.pop(link_id, None) is not None
