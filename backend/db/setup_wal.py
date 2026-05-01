"""
WAL モード設定・確認スクリプト
company.db のジャーナルモードを WAL に設定し確認する
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

conn = sqlite3.connect(DB_PATH)
result = conn.execute("PRAGMA journal_mode=WAL;").fetchone()
print(f"journal_mode: {result[0]}")  # → "wal" と出ること

# 同時書き込み許容数も確認
busy = conn.execute("PRAGMA busy_timeout;").fetchone()
conn.execute("PRAGMA busy_timeout=5000;")  # 5秒待機に設定
print(f"busy_timeout: 5000ms（設定済み）")
conn.commit()
conn.close()
print("WAL モード設定完了")
