#!/usr/bin/env python3
"""T-001-06 AC-5: RLS coverage 静的検証

実 DB に接続せず、supabase/migrations/*.sql を解析して各 CREATE TABLE に
対応する `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` が存在するか検証する。

対応していない table があれば exit 1。

使い方:
    python3 scripts/verify-rls-coverage.py
"""
from __future__ import annotations
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIG_DIR = ROOT / "supabase" / "migrations"

# RLS coverage の例外として明示的に許可するテーブル (現状なし、必要時に追加)
EXCLUSIONS: set[str] = set()


def collect_tables() -> set[str]:
    tables: set[str] = set()
    for f in sorted(MIG_DIR.glob("*.sql")):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", text):
            tables.add(m.group(1))
    return tables


def collect_rls_enabled() -> set[str]:
    """ALTER TABLE [IF EXISTS] <name> ENABLE ROW LEVEL SECURITY を全 migration から拾う。
    DO ブロック内の動的 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t)
    パターンも、配列内の table 名を文字列リテラルとして抽出する。
    """
    enabled: set[str] = set()
    for f in sorted(MIG_DIR.glob("*.sql")):
        text = f.read_text(encoding="utf-8")

        # 1. 通常の ALTER TABLE
        for m in re.finditer(
            r"ALTER TABLE\s+(?:IF EXISTS\s+)?([a-z_][a-z0-9_]*)\s+ENABLE ROW LEVEL SECURITY",
            text,
        ):
            enabled.add(m.group(1))

        # 2. DO ブロックの動的 EXECUTE format('ALTER TABLE %I ENABLE ...', t)
        # 配列定義 ARRAY[ 'a', 'b', ... ] の中の文字列を抽出
        for arr_block in re.finditer(
            r"legacy_tables\s+TEXT\[\]\s*:=\s*ARRAY\[(.*?)\]\s*;",
            text,
            re.DOTALL,
        ):
            for s in re.finditer(r"'([a-z_][a-z0-9_]*)'", arr_block.group(1)):
                enabled.add(s.group(1))
    return enabled


def main() -> int:
    tables = collect_tables()
    rls = collect_rls_enabled()
    missing = sorted(tables - rls - EXCLUSIONS)

    print(f"Total CREATE TABLE in migrations: {len(tables)}")
    print(f"Tables with RLS enabled:         {len(rls & tables)}")
    print(f"Exclusions (allowlist):          {len(EXCLUSIONS)}")
    print(f"Missing RLS:                     {len(missing)}")

    if missing:
        print("\nFAIL: 以下の table に RLS が設定されていません (T-001-06 AC-5 違反):")
        for t in missing:
            print(f"  - {t}")
        return 1

    print("\nOK: 全 table に RLS が設定されています")
    return 0


if __name__ == "__main__":
    sys.exit(main())
