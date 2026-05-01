"""
Async SQLite queries for company.db.
All reads are read-only — no writes from dashboard.
"""

import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
RECORDS_PATH = Path(__file__).resolve().parents[2] / "data" / "records"


async def get_connection():
    return await aiosqlite.connect(DB_PATH)


# ── KPI Summary ──────────────────────────────────────────────────────────────

async def get_kpi_summary() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Pipeline
        cur = await db.execute(
            "SELECT COUNT(*) as cnt, SUM(amount*probability/100) as weighted "
            "FROM pipeline WHERE stage NOT IN ('won','lost')"
        )
        pipeline = dict(await cur.fetchone())

        # Revenue this month (invoices: issued_date, total)
        cur = await db.execute(
            "SELECT SUM(total) as revenue FROM invoices "
            "WHERE strftime('%Y-%m', issued_date) = strftime('%Y-%m','now')"
        )
        row = await cur.fetchone()
        revenue = row[0] or 0

        # Expenses this month (expenses: expense_date, amount)
        cur = await db.execute(
            "SELECT SUM(amount) as expenses FROM expenses "
            "WHERE strftime('%Y-%m', expense_date) = strftime('%Y-%m','now')"
        )
        row = await cur.fetchone()
        expenses = row[0] or 0

        # Active tasks (task_log has no status col — count all today's records)
        cur = await db.execute(
            "SELECT COUNT(*) as cnt FROM task_log "
            "WHERE task1_done=0 OR task2_done=0 OR task3_done=0"
        )
        tasks = (await cur.fetchone())[0]

        # Contacts
        cur = await db.execute("SELECT COUNT(*) FROM contacts")
        contacts = (await cur.fetchone())[0]

        # Won deals this month
        cur = await db.execute(
            "SELECT COUNT(*) as cnt, SUM(amount) as total FROM pipeline "
            "WHERE stage='won' AND strftime('%Y-%m', updated_at) = strftime('%Y-%m','now')"
        )
        won = dict(await cur.fetchone())

        return {
            "pipeline_count": pipeline["cnt"] or 0,
            "pipeline_weighted": pipeline["weighted"] or 0,
            "revenue_month": revenue,
            "expenses_month": expenses,
            "profit_month": revenue - expenses,
            "active_tasks": tasks,
            "contacts": contacts,
            "won_count": won["cnt"] or 0,
            "won_amount": won["total"] or 0,
        }


# ── Revenue trend (6 months) ──────────────────────────────────────────────────

async def get_revenue_trend() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT strftime('%Y-%m', issued_date) as month, SUM(total) as revenue "
            "FROM invoices GROUP BY month ORDER BY month DESC LIMIT 6"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]


# ── Pipeline by stage ────────────────────────────────────────────────────────

async def get_pipeline_by_stage() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT stage, COUNT(*) as count, SUM(amount) as total "
            "FROM pipeline WHERE stage NOT IN ('won','lost') "
            "GROUP BY stage"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ── Active pipeline ───────────────────────────────────────────────────────────

async def get_active_pipeline(limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, client, project, stage, amount, probability, "
            "next_action, next_action_date, last_contact "
            "FROM pipeline WHERE stage NOT IN ('won','lost') "
            "ORDER BY amount DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ── Contacts ──────────────────────────────────────────────────────────────────

async def get_contacts(limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM contacts ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ── Tasks ─────────────────────────────────────────────────────────────────────

async def get_tasks(limit: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM task_log ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ── Expenses by category ──────────────────────────────────────────────────────

async def get_expenses_by_category() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT category, SUM(amount) as total FROM expenses "
            "WHERE strftime('%Y-%m', expense_date) = strftime('%Y-%m','now') "
            "GROUP BY category ORDER BY total DESC"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ── Generic table query (for agent tool use) ──────────────────────────────────

async def run_query(sql: str) -> list[dict]:
    """Execute a read-only SELECT query. Raises on non-SELECT."""
    normalized = sql.strip().upper()
    if not normalized.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ── MD Records listing ────────────────────────────────────────────────────────

def list_records(folder: str | None = None) -> list[dict]:
    base = RECORDS_PATH / folder if folder else RECORDS_PATH
    if not base.exists():
        return []
    files = sorted(base.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "path": str(f.relative_to(RECORDS_PATH)),
            "name": f.stem,
            "folder": str(f.parent.relative_to(RECORDS_PATH)),
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        }
        for f in files[:100]
    ]


def read_record(relative_path: str) -> str:
    path = RECORDS_PATH / relative_path
    if not path.exists() or not path.suffix == ".md":
        raise FileNotFoundError(relative_path)
    return path.read_text(encoding="utf-8")
