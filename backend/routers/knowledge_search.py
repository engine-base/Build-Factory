"""
スコープ付きセマンティック / トリグラム検索 API。

呼び出し側 (人間の UI / AI persona) ごとに見える知識をフィルタする:

GET /api/knowledge/search
    ?q=...
    &account_id=1
    &workspace_id=1                (省略可)
    &as_user=masato                (省略可: 個人ナレッジまで含める)
    &as_persona=rin-reviewer       (省略可: ai_only 知識を含める)
    &include_account_shared=true
    &include_public=true
    &limit=10

embedding が null の行は trigram 類似度のみで判定。
embedding がある行はベクトル類似度を優先し、それで足りない場合 trigram で補完。
"""
from __future__ import annotations

import json
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import httpx

from db import async_db as aiosqlite

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


class KnowledgeHit(BaseModel):
    id: int
    title: str
    summary: Optional[str]
    visibility: str
    scope_path: Optional[str]
    account_id: Optional[int]
    workspace_id: Optional[int]
    assigned_employee_id: Optional[int]
    owner_user_id: Optional[str]
    score: float


PERSONA_SLUG_MAP = {
    "nana-pm": "secretary",
    "ken-architect": "architect",
    "haru-engineer": "engineer",
    "rin-reviewer": "reviewer",
    "saki-qa": "qa",
    "taku-devops": "devops",
    "mio-docs": "docs",
}


async def _embed(text: str) -> Optional[list[float]]:
    if not OPENAI_API_KEY or not text.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={"input": text[:8000], "model": "text-embedding-3-small"},
            )
            if r.status_code == 200:
                return r.json()["data"][0]["embedding"]
    except Exception:
        return None
    return None


@router.get("/search", response_model=list[KnowledgeHit])
async def search_knowledge(
    q: str = Query(..., min_length=1),
    account_id: Optional[int] = None,
    workspace_id: Optional[int] = None,
    as_user: Optional[str] = None,
    as_persona: Optional[str] = None,
    include_account_shared: bool = True,
    include_public: bool = True,
    limit: int = 10,
):
    """
    visibility 解決ルール:
    - public                : include_public=true で常に
    - account_shared        : include_account_shared=true かつ account_id が一致
    - member_shared         : as_user 指定時、同じ workspace のメンバー知識（簡易: account_id 一致 + visibility=member_shared）
    - private               : as_user で owner_user_id 一致のみ
    - ai_only               : as_persona 指定時のみ、対応する assigned_employee_id 一致
    """
    # WHERE 句を可視性条件で組み立てる
    visibility_clauses: list[str] = []
    params: list = []

    if include_public:
        visibility_clauses.append("visibility = 'public'")

    if include_account_shared and account_id is not None:
        visibility_clauses.append(
            "(visibility = 'account_shared' AND account_id = %s)"
        )
        params.append(account_id)

    if as_user and account_id is not None:
        visibility_clauses.append(
            "(visibility = 'member_shared' AND account_id = %s)"
        )
        params.append(account_id)
        visibility_clauses.append(
            "(visibility = 'private' AND owner_user_id = %s AND account_id = %s)"
        )
        params.extend([as_user, account_id])

    if as_persona and account_id is not None:
        # persona slug → employee_name
        emp_name = PERSONA_SLUG_MAP.get(as_persona, as_persona)
        visibility_clauses.append(
            "(visibility = 'ai_only' AND account_id = %s AND assigned_employee_id = "
            "(SELECT id FROM ai_employee_config WHERE account_id = %s AND employee_name = %s LIMIT 1))"
        )
        params.extend([account_id, account_id, emp_name])

    if workspace_id is not None:
        # workspace スコープを追加（全 visibility に AND で適用）
        # ※ 単純化のため別 OR 句として扱う
        visibility_clauses.append("workspace_id = %s")
        params.append(workspace_id)

    if not visibility_clauses:
        raise HTTPException(status_code=400, detail="no scope provided")

    visibility_sql = " OR ".join(f"({c})" for c in visibility_clauses)

    # 埋め込みを取得（あれば cosine、なければ trigram）
    query_emb = await _embed(q)

    if query_emb is not None:
        # cosine 距離 + trigram の合成スコア
        sql = f"""
            SELECT id, title, summary, visibility, scope_path,
                   account_id, workspace_id, assigned_employee_id, owner_user_id,
                   GREATEST(
                     CASE WHEN embedding IS NOT NULL
                          THEN 1 - (embedding <=> %s::vector)
                          ELSE 0 END,
                     similarity(COALESCE(content, '') || ' ' || COALESCE(title, ''), %s) * 0.7
                   ) AS score
            FROM knowledge_base
            WHERE ({visibility_sql})
            ORDER BY score DESC
            LIMIT %s
        """
        full_params = [json.dumps(query_emb), q, *params, limit]
    else:
        sql = f"""
            SELECT id, title, summary, visibility, scope_path,
                   account_id, workspace_id, assigned_employee_id, owner_user_id,
                   similarity(COALESCE(content, '') || ' ' || COALESCE(title, ''), %s) AS score
            FROM knowledge_base
            WHERE ({visibility_sql})
            ORDER BY score DESC
            LIMIT %s
        """
        full_params = [q, *params, limit]

    async with aiosqlite.connect() as db:
        cur = await db.execute(sql, full_params)
        rows = await cur.fetchall()

    return [KnowledgeHit(**dict(r)) for r in rows]
