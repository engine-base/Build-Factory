"""
staff.py — AI社員管理 API（採用・編集・退職・組織図 + ナレッジ引継・スコープ追加）

UI / Slack / MCP / 秘書ツール からこのAPIを呼ぶ。
最終承認はクライアント側で取る前提（このAPIは即時実行）。
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import staff_service, knowledge_transfer, scoped_knowledge

router = APIRouter(prefix="/api/staff", tags=["staff"])


# ── 一覧・詳細・組織図 ─────────────────────────

@router.get("")
async def list_staff(include_retired: bool = False):
    return {"employees": await staff_service.list_employees(include_retired=include_retired)}


@router.get("/orgchart")
async def orgchart():
    return await staff_service.build_orgchart()


@router.get("/{employee_id}")
async def get_staff(employee_id: int):
    emp = await staff_service.get_employee(employee_id)
    if not emp:
        raise HTTPException(404, "社員が見つかりません")
    return emp


# ── 採用 ───────────────────────────────────────

class HireBody(BaseModel):
    persona_name: str
    role_level:   str                       # 'leader' | 'member'
    category:     str
    parent_id:    Optional[int] = None
    specialty:    Optional[str] = None
    handles:      str = ""
    personality:  str = ""
    tone_style:   str = ""
    catchphrase:  str = ""
    avatar_emoji: str = ""
    knowledge_folders: Optional[list[str]] = None
    primary_skill: str = ""
    inherit_knowledge_ids: Optional[list[int]] = None
    triggered_by: str = "ui"


@router.post("/hire")
async def hire(body: HireBody):
    try:
        emp = await staff_service.create_employee(
            persona_name=body.persona_name,
            role_level=body.role_level,
            category=body.category,
            parent_id=body.parent_id,
            specialty=body.specialty,
            handles=body.handles,
            personality=body.personality,
            tone_style=body.tone_style,
            catchphrase=body.catchphrase,
            avatar_emoji=body.avatar_emoji,
            knowledge_folders=body.knowledge_folders,
            primary_skill=body.primary_skill,
            triggered_by=body.triggered_by,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    transferred = 0
    if body.inherit_knowledge_ids and body.parent_id:
        result = await knowledge_transfer.execute_transfer(
            knowledge_ids=body.inherit_knowledge_ids,
            from_employee_id=body.parent_id,
            to_employee_id=emp["id"],
            reason="hire",
            triggered_by=body.triggered_by,
        )
        transferred = result.get("transferred", 0)

    return {"employee": emp, "knowledge_transferred": transferred}


# ── 編集 ───────────────────────────────────────

class UpdateBody(BaseModel):
    updates: dict


@router.patch("/{employee_id}")
async def update(employee_id: int, body: UpdateBody):
    try:
        return await staff_service.update_employee(employee_id, body.updates)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── 退職 ───────────────────────────────────────

class RetireBody(BaseModel):
    inheritance_to:      Optional[int] = None
    promote_to_common:   bool = False
    reason:              str = ""
    triggered_by:        str = "ui"
    member_reassign_to:  Optional[int] = None    # 配下メンバーの新リーダー
    retire_members_too:  bool = False            # 配下メンバーも一括退職


@router.get("/{employee_id}/members")
async def list_members(employee_id: int):
    """指定リーダー配下のメンバー一覧（退職前確認用）。"""
    return {"members": await staff_service.list_active_members_of(employee_id)}


@router.post("/{employee_id}/retire")
async def retire(employee_id: int, body: RetireBody):
    try:
        emp = await staff_service.retire_employee(
            employee_id=employee_id,
            inheritance_to=body.inheritance_to,
            promote_to_common=body.promote_to_common,
            reason=body.reason,
            triggered_by=body.triggered_by,
            member_reassign_to=body.member_reassign_to,
            retire_members_too=body.retire_members_too,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    transfer = await knowledge_transfer.execute_retirement_transfer(
        retiring_employee_id=employee_id,
        inheritance_to=body.inheritance_to,
        promote_to_common=body.promote_to_common,
        triggered_by=body.triggered_by,
    )
    return {"employee": emp, "transfer": transfer}


# ── ナレッジ引継候補（採用時の事前確認用） ──────────

class TransferProposeBody(BaseModel):
    from_employee_id: int
    to_employee_id:   Optional[int] = None    # 採用前なら未指定でOK
    query_text:       str
    top_k:            int = 30
    min_score:        float = 0.6


@router.post("/transfer/propose")
async def transfer_propose(body: TransferProposeBody):
    candidates = await knowledge_transfer.propose_transfer(
        from_employee_id=body.from_employee_id,
        to_employee_id=body.to_employee_id or 0,
        query_text=body.query_text,
        top_k=body.top_k,
        min_score=body.min_score,
    )
    return {"candidates": candidates, "count": len(candidates)}


class TransferExecuteBody(BaseModel):
    knowledge_ids:    list[int]
    from_employee_id: Optional[int] = None
    to_employee_id:   Optional[int] = None
    reason:           str = "manual"
    triggered_by:     str = "ui"
    move_md_to_folder: Optional[str] = None


@router.post("/transfer/execute")
async def transfer_execute(body: TransferExecuteBody):
    return await knowledge_transfer.execute_transfer(
        knowledge_ids=body.knowledge_ids,
        from_employee_id=body.from_employee_id,
        to_employee_id=body.to_employee_id,
        reason=body.reason,
        triggered_by=body.triggered_by,
        move_md_to_folder=body.move_md_to_folder,
    )


# ── スコープ付きナレッジ操作 ─────────────────────

class ScopedSearchBody(BaseModel):
    employee_id: Optional[int] = None
    query:       str
    top_k:       int = 10
    min_score:   float = 0.4


@router.post("/knowledge/search")
async def scoped_search(body: ScopedSearchBody):
    results = await scoped_knowledge.search_in_scope(
        employee_id=body.employee_id,
        query=body.query,
        top_k=body.top_k,
        min_score=body.min_score,
    )
    return {"results": results, "count": len(results)}


class ScopedAddProposeBody(BaseModel):
    content: str
    current_employee_id: Optional[int] = None


@router.post("/knowledge/propose-target")
async def scoped_add_propose(body: ScopedAddProposeBody):
    proposal = await scoped_knowledge.propose_save_target(
        content=body.content,
        current_employee_id=body.current_employee_id,
    )
    return proposal


class ScopedSaveBody(BaseModel):
    title: str
    content: str
    target_employee_id: Optional[int] = None
    target_folder: str = "02_共通ナレッジ"
    category: Optional[str] = None
    source: str = "manual"
    triggered_by: str = "masato"


@router.post("/knowledge/save")
async def scoped_save(body: ScopedSaveBody):
    knowledge_id = await scoped_knowledge.save_knowledge(
        title=body.title,
        content=body.content,
        target_employee_id=body.target_employee_id,
        target_folder=body.target_folder,
        category=body.category,
        source=body.source,
        triggered_by=body.triggered_by,
    )
    return {"id": knowledge_id, "status": "saved"}
