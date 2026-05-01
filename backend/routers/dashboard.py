"""Dashboard data endpoints."""

from fastapi import APIRouter, HTTPException
from db.queries import (
    get_kpi_summary,
    get_revenue_trend,
    get_pipeline_by_stage,
    get_active_pipeline,
    get_contacts,
    get_tasks,
    get_expenses_by_category,
    run_query,
)
from pydantic import BaseModel

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/kpi")
async def kpi():
    return await get_kpi_summary()


@router.get("/revenue-trend")
async def revenue_trend():
    return await get_revenue_trend()


@router.get("/pipeline-by-stage")
async def pipeline_by_stage():
    return await get_pipeline_by_stage()


@router.get("/pipeline")
async def pipeline(limit: int = 20):
    return await get_active_pipeline(limit)


@router.get("/contacts")
async def contacts(limit: int = 50):
    return await get_contacts(limit)


@router.get("/tasks")
async def tasks(limit: int = 30):
    return await get_tasks(limit)


@router.get("/expenses")
async def expenses():
    return await get_expenses_by_category()


class QueryRequest(BaseModel):
    sql: str


@router.post("/query")
async def custom_query(req: QueryRequest):
    try:
        return await run_query(req.sql)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
