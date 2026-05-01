"""
SQLite (data/db/build.db) → Supabase Postgres へのデータ移行スクリプト。

使い方:
    cd /Users/masato0420/Documents/Build-Factory/backend
    source .venv/bin/activate
    python scripts/migrate_sqlite_to_postgres.py

前提:
    - supabase start でローカル Supabase が起動済
    - supabase db reset で initial_schema + pgvector migration が適用済
    - SQLite には移行元のデータが残っている

挙動:
    - SQLite の全テーブルを走査し、行があるテーブルだけコピー
    - 列名一致でマッピング、Postgres 側に存在しない列は無視
    - JSON 文字列の列は jsonb キャストを Postgres 側に任せる（TEXT で送る）
    - 各テーブル投入後に SERIAL シーケンスを max(id)+1 に再同期
    - 移行前に対象テーブルを TRUNCATE する（多対多含む。CASCADE 有り）
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
SQLITE_PATH = ROOT / "data" / "db" / "build.db"
PG_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

# 移行スキップ対象（alembic 管理テーブル等）
SKIP_TABLES = {"alembic_version", "sqlite_sequence"}

# 投入順（FK 解決のため親 → 子の順）
PRIORITY = [
    "accounts",
    "account_members",
    "workspaces",
    "workspace_members",
    "workspace_invitations",
    "user_profile",
    "skill_definitions",
    "ai_employee_config",
    "ai_employee_skills",
    "knowledge_base",
    "projects",
    "tasks",
    "task_log",
    "task_questions",
    "task_schedule",
    "threads",
    "conversation_log",
    "conversation_slots",
    "artifacts",
    "artifact_events",
    "approval_queue",
    "repos",
    "pull_requests",
    "reviews",
]


def get_sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return [r[0] for r in cur.fetchall() if r[0] not in SKIP_TABLES]


def get_sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def get_pg_columns(pg: psycopg.Connection, table: str) -> dict[str, str]:
    with pg.cursor() as c:
        c.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
        return {r[0]: r[1] for r in c.fetchall()}


def table_exists_pg(pg: psycopg.Connection, table: str) -> bool:
    with pg.cursor() as c:
        c.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
        return c.fetchone() is not None


def coerce_value(v, pg_type: str):
    """SQLite から取得した値を Postgres 列の型に合わせて整える。"""
    if v is None:
        return None
    # boolean: 0/1 → False/True
    if pg_type == "boolean":
        if isinstance(v, (int, bool)):
            return bool(v)
        if isinstance(v, str):
            return v.lower() in ("1", "true", "t", "yes")
        return bool(v)
    # jsonb / json: SQLite では TEXT で格納されている。CSV や素の文字列が混在するため正規化
    if pg_type in ("jsonb", "json"):
        if isinstance(v, (dict, list)):
            return json.dumps(v)
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            # JSON として解釈できればそのまま
            try:
                json.loads(s)
                return s
            except Exception:
                pass
            # CSV (カンマ区切り) → 配列化
            if "," in s:
                return json.dumps([t.strip() for t in s.split(",") if t.strip()])
            # 単一値 → 1 要素配列
            return json.dumps([s])
        return json.dumps(v)
    # numeric/integer: SQLite で TEXT 化されてる場合に備えて
    if pg_type in ("integer", "bigint", "smallint"):
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v
    # bytea (BLOB) は捨てる（embedding は再生成前提）
    if pg_type == "bytea":
        return None
    if isinstance(v, (int, float, str, bytes)):
        return v
    return str(v)


def migrate_table(
    sqlite_conn: sqlite3.Connection, pg: psycopg.Connection, table: str
) -> int:
    """1 テーブル分のデータをコピーし、行数を返す。"""
    if not table_exists_pg(pg, table):
        print(f"  ⚠ skip: {table} (Postgres 側に存在しない)")
        return 0

    sqlite_cols = get_sqlite_columns(sqlite_conn, table)
    pg_cols = get_pg_columns(pg, table)
    common = [c for c in sqlite_cols if c in pg_cols]
    if not common:
        print(f"  ⚠ skip: {table} (共通列なし)")
        return 0

    cur = sqlite_conn.execute(f"SELECT {', '.join(common)} FROM {table}")
    rows = cur.fetchall()
    if not rows:
        return 0

    types = [pg_cols[c] for c in common]
    placeholders = ",".join(["%s"] * len(common))
    insert = sql.SQL(
        "INSERT INTO {table} ({cols}) VALUES ({ph})"
    ).format(
        table=sql.Identifier(table),
        cols=sql.SQL(",").join(map(sql.Identifier, common)),
        ph=sql.SQL(placeholders),
    )

    with pg.cursor() as c:
        c.execute(
            sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                sql.Identifier(table)
            )
        )
        for row in rows:
            try:
                c.execute(
                    insert,
                    [coerce_value(v, t) for v, t in zip(row, types)],
                )
            except Exception as e:
                print(f"  ✗ {table}: row insert failed: {e}")
                print(f"    row preview: {dict(zip(common, row))}")
                raise
        # シーケンス再同期（id 列が SERIAL の場合のみ）
        if "id" in common:
            try:
                c.execute(
                    sql.SQL(
                        "SELECT setval(pg_get_serial_sequence({tbl}, 'id'), "
                        "COALESCE((SELECT MAX(id) FROM {table}), 1))"
                    ).format(
                        tbl=sql.Literal(table),
                        table=sql.Identifier(table),
                    )
                )
            except Exception:
                # id が SERIAL でないテーブルは無視
                pg.rollback()
                pg.commit()

    pg.commit()
    return len(rows)


def main():
    if not SQLITE_PATH.exists():
        print(f"❌ SQLite DB が見つかりません: {SQLITE_PATH}")
        sys.exit(1)

    print(f"🔌 SQLite : {SQLITE_PATH}")
    print(f"🔌 Postgres: {PG_DSN}")
    print()

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = None

    with psycopg.connect(PG_DSN) as pg:
        all_tables = get_sqlite_tables(sqlite_conn)
        # PRIORITY を先頭に、それ以外を後ろに
        ordered = [t for t in PRIORITY if t in all_tables] + [
            t for t in all_tables if t not in PRIORITY
        ]

        print(f"📦 移行対象 {len(ordered)} テーブル")
        print()

        # FK の都合で、コピー中は外部キー制約を一時無効化
        with pg.cursor() as c:
            c.execute("SET session_replication_role = 'replica'")

        total_rows = 0
        per_table: list[tuple[str, int]] = []
        for t in ordered:
            n = migrate_table(sqlite_conn, pg, t)
            if n > 0:
                print(f"  ✓ {t:35s} {n:>6} rows")
                total_rows += n
                per_table.append((t, n))

        with pg.cursor() as c:
            c.execute("SET session_replication_role = 'origin'")
        pg.commit()

    sqlite_conn.close()

    print()
    print(f"✅ 完了: {total_rows} 行を {len(per_table)} テーブルに移行")


if __name__ == "__main__":
    main()
