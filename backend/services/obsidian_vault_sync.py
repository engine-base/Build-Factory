"""
Obsidian vault → Supabase Postgres (knowledge_base) 同期サービス。

機能:
- vault 内の .md ファイルを走査
- パスから scope_path / visibility / account_id / workspace_id / owner_user_id /
  assigned_employee_id を導出
- 内容の SHA256 で差分検知（同じハッシュなら skip）
- INSERT / UPDATE / DELETE を knowledge_base に反映
- OPENAI_API_KEY があれば embedding 生成して vector 列に書き込み

使い方（CLI）:
    python -m services.obsidian_vault_sync sync       # ワンショット同期
    python -m services.obsidian_vault_sync watch      # ファイル変更を監視して継続同期

PATH → SCOPE 規則:
    accounts/{account_slug}/shared/...                  → account_shared
    accounts/{account_slug}/members/{user}/private/...  → private
    accounts/{account_slug}/members/{user}/shared-...   → member_shared
    accounts/{account_slug}/ai-personas/{persona}/...   → ai_only (assigned_employee_id 解決)
    workspaces/{workspace_slug}/shared/...              → account_shared (workspace_id 指定)
    workspaces/{workspace_slug}/ai-personas/{persona}/.. → ai_only (workspace+persona)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("obsidian_sync")

ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = ROOT / "data" / "obsidian-vault"
DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# README.md は同期対象から除外（ナレッジではなく説明文）
EXCLUDE_FILE_NAMES = {"README.md", ".obsidian"}


# ──────────────────────────────────────────────
# パス解析: scope_path から各種スコープ ID を導出
# ──────────────────────────────────────────────

PERSONA_SLUG_MAP = {
    "nana-pm": "secretary",
    "ken-architect": "architect",
    "haru-engineer": "engineer",
    "rin-reviewer": "reviewer",
    "saki-qa": "qa",
    "taku-devops": "devops",
    "mio-docs": "docs",
}


def slugify(s: str) -> str:
    return s.replace(" ", "-").replace("/", "-").replace(".", "-").lower().strip("-")


def parse_scope(rel_path: Path) -> dict[str, Any]:
    """
    vault root からの相対パスを受け取り、スコープ情報を返す。
    例: accounts/engine-base/ai-personas/rin-reviewer/rules/review-rule-01.md
    """
    parts = rel_path.parts
    info: dict[str, Any] = {
        "scope_path": str(rel_path.parent).replace(os.sep, "/"),
        "visibility": "account_shared",
        "account_slug": None,
        "workspace_slug": None,
        "owner_user_slug": None,
        "persona_slug": None,
    }
    if not parts:
        return info

    if parts[0] == "accounts" and len(parts) >= 3:
        info["account_slug"] = parts[1]
        kind = parts[2]
        if kind == "shared":
            info["visibility"] = "account_shared"
        elif kind == "members" and len(parts) >= 5:
            info["owner_user_slug"] = parts[3]
            sub = parts[4]
            info["visibility"] = "private" if sub == "private" else "member_shared"
        elif kind == "ai-personas" and len(parts) >= 4:
            info["persona_slug"] = parts[3]
            info["visibility"] = "ai_only"

    elif parts[0] == "workspaces" and len(parts) >= 3:
        info["workspace_slug"] = parts[1]
        kind = parts[2]
        if kind == "ai-personas" and len(parts) >= 4:
            info["persona_slug"] = parts[3]
            info["visibility"] = "ai_only"
        else:
            info["visibility"] = "account_shared"

    return info


# ──────────────────────────────────────────────
# DB 解決: slug → ID
# ──────────────────────────────────────────────


class IdResolver:
    def __init__(self):
        self.accounts: dict[str, int] = {}
        self.workspaces: dict[str, dict[str, int]] = {}  # slug -> {id, account_id}
        self.personas: dict[tuple[Optional[int], str], int] = {}  # (account_id, slug) -> id

    async def load(self, conn: psycopg.AsyncConnection):
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, name FROM accounts")
            for r in await cur.fetchall():
                self.accounts[slugify(r["name"])] = r["id"]
            await cur.execute("SELECT id, name, account_id FROM workspaces")
            for r in await cur.fetchall():
                self.workspaces[slugify(r["name"])] = {
                    "id": r["id"],
                    "account_id": r["account_id"],
                }
            await cur.execute(
                "SELECT id, employee_name, account_id FROM ai_employee_config"
            )
            for r in await cur.fetchall():
                name = r["employee_name"]
                # PERSONA_SLUG_MAP は persona_slug → employee_name の辞書
                # 逆向きマップを作って employee_name → persona_slug に変換
                reverse = {v: k for k, v in PERSONA_SLUG_MAP.items()}
                slug = reverse.get(name) or slugify(name)
                self.personas[(r["account_id"], slug)] = r["id"]

    def resolve(self, scope: dict[str, Any]) -> dict[str, Any]:
        out = {
            "account_id": None,
            "workspace_id": None,
            "owner_user_id": None,
            "assigned_employee_id": None,
        }
        if scope["account_slug"]:
            out["account_id"] = self.accounts.get(scope["account_slug"])
        if scope["workspace_slug"]:
            ws = self.workspaces.get(scope["workspace_slug"])
            if ws:
                out["workspace_id"] = ws["id"]
                out["account_id"] = out["account_id"] or ws["account_id"]
        if scope["owner_user_slug"]:
            out["owner_user_id"] = scope["owner_user_slug"]
        if scope["persona_slug"]:
            out["assigned_employee_id"] = self.personas.get(
                (out["account_id"], scope["persona_slug"])
            )
        return out


# ──────────────────────────────────────────────
# Embedding（OpenAI 利用、未設定なら NULL）
# ──────────────────────────────────────────────


async def _generate_embedding(text: str) -> Optional[list[float]]:
    if not OPENAI_API_KEY or not text.strip():
        return None
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"input": text[:8000], "model": "text-embedding-3-small"},
            )
            if resp.status_code == 200:
                return resp.json()["data"][0]["embedding"]
            log.warning("embedding API failed: %s %s", resp.status_code, resp.text[:200])
            return None
    except Exception as e:
        log.warning("embedding generation error: %s", e)
        return None


# ──────────────────────────────────────────────
# 同期本体
# ──────────────────────────────────────────────


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _extract_title(md: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    return m.group(1).strip() if m else fallback


def _extract_summary(md: str, max_chars: int = 200) -> str:
    # Frontmatter を剥がし、最初の段落を返す
    body = re.sub(r"^---.*?---\s*", "", md, count=1, flags=re.DOTALL)
    paras = [p.strip() for p in body.split("\n\n") if p.strip() and not p.startswith("#")]
    if not paras:
        return ""
    return paras[0][:max_chars]


async def sync_once(vault: Path = VAULT_ROOT) -> dict[str, int]:
    if not vault.exists():
        log.error("vault が見つかりません: %s", vault)
        return {"upserted": 0, "skipped": 0, "deleted": 0}

    stats = {"upserted": 0, "skipped": 0, "deleted": 0}

    async with await psycopg.AsyncConnection.connect(DSN, row_factory=dict_row) as conn:
        resolver = IdResolver()
        await resolver.load(conn)

        # 既存の vault 由来エントリを取得
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, source_path, file_hash FROM knowledge_base "
                "WHERE source = 'obsidian'"
            )
            existing = {r["source_path"]: r for r in await cur.fetchall()}

        seen_paths: set[str] = set()

        # vault 走査
        for md_path in vault.rglob("*.md"):
            if md_path.name in EXCLUDE_FILE_NAMES:
                continue
            rel = md_path.relative_to(vault)
            rel_str = str(rel).replace(os.sep, "/")
            seen_paths.add(rel_str)

            content = md_path.read_text(encoding="utf-8")
            file_hash = _hash_content(content)

            prev = existing.get(rel_str)
            if prev and prev["file_hash"] == file_hash:
                stats["skipped"] += 1
                continue

            scope = parse_scope(rel)
            ids = resolver.resolve(scope)
            title = _extract_title(content, fallback=md_path.stem)
            summary = _extract_summary(content)
            embedding = await _generate_embedding(f"{title}\n\n{content}")

            tags_json = json.dumps([])
            skill_tags_json = json.dumps([])

            async with conn.cursor() as cur:
                if prev:
                    await cur.execute(
                        """
                        UPDATE knowledge_base SET
                          title = %s, content = %s, summary = %s,
                          file_hash = %s, scope_path = %s, visibility = %s,
                          account_id = %s, workspace_id = %s,
                          owner_user_id = %s, assigned_employee_id = %s,
                          source = 'obsidian', md_path = %s,
                          embedding = %s::vector,
                          last_updated = CURRENT_DATE
                        WHERE id = %s
                        """,
                        (
                            title, content, summary, file_hash,
                            scope["scope_path"], scope["visibility"],
                            ids["account_id"], ids["workspace_id"],
                            ids["owner_user_id"], ids["assigned_employee_id"],
                            str(md_path),
                            json.dumps(embedding) if embedding else None,
                            prev["id"],
                        ),
                    )
                else:
                    await cur.execute(
                        """
                        INSERT INTO knowledge_base
                          (title, content, summary, source, source_path, file_hash,
                           scope_path, visibility,
                           account_id, workspace_id, owner_user_id, assigned_employee_id,
                           md_path, tags, skill_tags, knowledge_type, embedding)
                        VALUES
                          (%s, %s, %s, 'obsidian', %s, %s,
                           %s, %s,
                           %s, %s, %s, %s,
                           %s, %s::jsonb, %s::jsonb, 'note', %s::vector)
                        """,
                        (
                            title, content, summary, rel_str, file_hash,
                            scope["scope_path"], scope["visibility"],
                            ids["account_id"], ids["workspace_id"],
                            ids["owner_user_id"], ids["assigned_employee_id"],
                            str(md_path), tags_json, skill_tags_json,
                            json.dumps(embedding) if embedding else None,
                        ),
                    )
            stats["upserted"] += 1
            log.info("✓ %s (%s)", rel_str, scope["visibility"])

        # 削除検知（既存エントリで vault に存在しないものを削除）
        to_delete = [r["id"] for path, r in existing.items() if path not in seen_paths]
        if to_delete:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM knowledge_base WHERE id = ANY(%s)", (to_delete,)
                )
            stats["deleted"] = len(to_delete)
            log.info("✗ deleted %d entries", len(to_delete))

        await conn.commit()

    return stats


# ──────────────────────────────────────────────
# Watch モード（差分監視）
# ──────────────────────────────────────────────


async def watch_loop(interval_sec: float = 5.0):
    log.info("👀 watching %s (interval=%ss)", VAULT_ROOT, interval_sec)
    while True:
        try:
            stats = await sync_once()
            if stats["upserted"] or stats["deleted"]:
                log.info("📊 %s", stats)
        except Exception as e:
            log.exception("sync failed: %s", e)
        await asyncio.sleep(interval_sec)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    if cmd == "sync":
        stats = asyncio.run(sync_once())
        log.info("✅ done: %s", stats)
    elif cmd == "watch":
        try:
            asyncio.run(watch_loop())
        except KeyboardInterrupt:
            log.info("👋 stopped")
    else:
        print(f"unknown command: {cmd}")
        print("usage: python -m services.obsidian_vault_sync [sync|watch]")
        sys.exit(2)


if __name__ == "__main__":
    main()
