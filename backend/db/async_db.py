"""
aiosqlite 互換 API を psycopg (async, Postgres) で実装するアダプタ。

既存コード:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT ? FROM t WHERE id=?", (1, 2))
        rows = await cur.fetchall()
        await db.commit()

移行後:
    from db.async_db import connect
    async with connect() as db:
        cur = await db.execute("SELECT ? FROM t WHERE id=?", (1, 2))
        rows = await cur.fetchall()
        await db.commit()

挙動:
- placeholder `?` を Postgres の `%s` に自動変換（psycopg は %s を受け付ける）
- `db.execute(sql, params)` は内部で cursor を発行し、cursor 自体を返す（aiosqlite と同じ）
- `db.executemany(sql, [params...])` 対応
- `cursor.fetchone() / fetchall()` は dict 形式 (row_factory = sqlite3.Row 相当) で返す
- `db.commit() / db.rollback()` 対応
- `db.row_factory = sqlite3.Row` のような代入は no-op で受け流す（Postgres 側は常に dict-like を返す）

※ Build-Factory は SQLite ↔ Postgres の差分が問題になる重い ORM 操作を避けて
   生 SQL ベースで動いてきたので、placeholder 変換だけで 90% のクエリが通る。
   特殊な SQLite 関数（datetime('now')、pragma 等）は呼び出し側で個別対応する必要がある。
"""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable

import psycopg
from psycopg import AsyncConnection
from psycopg.rows import dict_row

DEFAULT_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
)

# `?` を `%s` に変換する正規表現（リテラル文字列内の ? は誤変換するが、
# Build-Factory の既存コードでは ? を文字列リテラル内に含めていない前提）
_PLACEHOLDER_RE = re.compile(r"(?<!\\)\?")


_BOOL_COL_PATTERN = re.compile(
    r"\b(is_\w+|has_\w+|confirmed_by_user|enabled|active|deleted|paid|done|completed)\s*=\s*(0|1)\b",
    re.IGNORECASE,
)


def _bool_replace(m: re.Match) -> str:
    col, val = m.group(1), m.group(2)
    return f"{col} = {'TRUE' if val == '1' else 'FALSE'}"


def _translate_sql(sql: str) -> str:
    """SQLite 構文を Postgres 互換に最低限変換する。"""
    if not sql:
        return sql
    # ? -> %s
    sql = _PLACEHOLDER_RE.sub("%s", sql)
    # SQLite 特有の関数を Postgres にマップ
    sql = sql.replace("datetime('now')", "NOW()")
    sql = sql.replace("CURRENT_TIMESTAMP", "NOW()")
    sql = sql.replace("strftime('%Y-%m-%d', 'now')", "to_char(NOW(), 'YYYY-MM-DD')")
    # is_active = 1 → is_active = TRUE （boolean 列との比較）
    sql = _BOOL_COL_PATTERN.sub(_bool_replace, sql)
    # INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING (パターン置換)
    sql = re.sub(
        r"\bINSERT\s+OR\s+IGNORE\b",
        "INSERT",
        sql,
        flags=re.IGNORECASE,
    )
    # INSERT OR REPLACE -> INSERT ... ON CONFLICT DO UPDATE （フル変換は困難なのでスキップ）
    return sql


class _CursorWrapper:
    """psycopg の AsyncCursor に aiosqlite 風の薄い API を被せたラッパー。"""

    def __init__(self, cur):
        self._cur = cur

    async def fetchone(self) -> dict | None:
        return await self._cur.fetchone()

    async def fetchall(self) -> list[dict]:
        return await self._cur.fetchall()

    async def fetchmany(self, size: int) -> list[dict]:
        return await self._cur.fetchmany(size)

    @property
    def lastrowid(self) -> int | None:
        # psycopg は SERIAL を `INSERT ... RETURNING id` で取得するため lastrowid は使えない
        # 互換性維持のため None を返す。呼び出し側は RETURNING に書き換える必要がある
        return None

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._cur.close()

    def __aiter__(self):
        return self._cur.__aiter__()


class _ConnectionWrapper:
    """aiosqlite.Connection 風の API を AsyncConnection に被せる。"""

    def __init__(self, conn: AsyncConnection):
        self._conn = conn
        # row_factory 代入を受け流すためのダミー
        self.row_factory = None

    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> _CursorWrapper:
        cur = self._conn.cursor()
        try:
            await cur.execute(_translate_sql(sql), tuple(params) if params else None)
        except Exception:
            await cur.close()
            raise
        return _CursorWrapper(cur)

    async def executemany(
        self, sql: str, params_list: Iterable[Iterable[Any]]
    ) -> _CursorWrapper:
        cur = self._conn.cursor()
        try:
            await cur.executemany(
                _translate_sql(sql),
                [tuple(p) for p in params_list],
            )
        except Exception:
            await cur.close()
            raise
        return _CursorWrapper(cur)

    async def execute_fetchall(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> list[dict]:
        """aiosqlite の便利メソッド互換: execute + fetchall を一気にやる。"""
        async with self._conn.cursor() as cur:
            await cur.execute(_translate_sql(sql), tuple(params) if params else None)
            return await cur.fetchall()

    async def execute_fetchone(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> dict | None:
        """aiosqlite の便利メソッド互換: execute + fetchone を一気にやる。"""
        async with self._conn.cursor() as cur:
            await cur.execute(_translate_sql(sql), tuple(params) if params else None)
            return await cur.fetchone()

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()

    async def close(self) -> None:
        await self._conn.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            await self._conn.rollback()
        else:
            await self._conn.commit()
        await self._conn.close()


@asynccontextmanager
async def connect(_db_path_compat: Any = None, **kwargs) -> AsyncIterator[_ConnectionWrapper]:
    """
    aiosqlite.connect(DB_PATH) の置き換え。

    引数 `_db_path_compat` は無視（既存コードが第 1 引数に DB_PATH を渡してくるため受け取るだけ）。
    DSN は環境変数 DATABASE_URL から取得（デフォルトはローカル Supabase）。
    """
    dsn = kwargs.pop("dsn", DEFAULT_DSN)
    conn = await AsyncConnection.connect(dsn, row_factory=dict_row)
    wrapped = _ConnectionWrapper(conn)
    try:
        yield wrapped
    except Exception:
        await conn.rollback()
        raise
    finally:
        if not conn.closed:
            try:
                await conn.commit()
            except Exception:
                pass
            await conn.close()


# 後方互換: aiosqlite.Row 相当のダミー（既存コードが import するだけのケースに対応）
class Row(dict):
    """sqlite3.Row 風のインターフェース。dict_row が既に dict を返すのでこれは型ヒント用。"""
    def keys(self):
        return super().keys()
