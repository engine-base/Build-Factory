"""
knowledge_transfer.py — ナレッジの引継・分割・移動。

採用時:  親リーダーから新メンバーへ ナレッジを類似度ベースで引継
退職時:  退職者のナレッジを 主たる引継先 or 共通へ 一括移動
編集時:  knowledge_folders 変更に伴うナレッジの再帰的再配置（オプション）

すべての移動は knowledge_transfer_log に記録。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import aiosqlite

from db.queries import DB_PATH

VAULT = Path.home() / "Documents" / "Obsidian" / "ENGINE-BASE"


# ── 引継候補の抽出（採用時） ──────────────────────────

async def propose_transfer(
    from_employee_id: int,
    to_employee_id: int,
    query_text: str,                 # 例: 特化分野の自然文
    top_k: int = 30,
    min_score: float = 0.6,
) -> list[dict]:
    """
    親（from）が抱えるナレッジから、特化分野（query_text）に類似する候補を抽出する。
    実際の移動はしない（呼出側で確認後に execute_transfer を呼ぶ）。
    """
    from services.embedding_service import embed, decode, cosine_similarity

    qv = await embed(query_text)
    if not qv:
        return []

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id, title, summary, content, md_path, embedding,
                      assigned_employee_id
               FROM knowledge_base
               WHERE embedding IS NOT NULL
                 AND (assigned_employee_id = ? OR
                      (assigned_employee_id IS NULL AND md_path LIKE ?))
            """,
            (from_employee_id, f"%03_スキル別ナレッジ%"),
        )
        rows = await cur.fetchall()

    scored = []
    for r in rows:
        try:
            v = decode(r["embedding"])
            s = cosine_similarity(qv, v)
            if s >= min_score:
                scored.append({
                    "id": r["id"],
                    "title": r["title"],
                    "preview": (r["summary"] or r["content"] or "")[:120],
                    "md_path": r["md_path"],
                    "current_owner": r["assigned_employee_id"],
                    "score": round(s, 4),
                })
        except Exception:
            continue
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ── 引継実行 ─────────────────────────────────────────

async def execute_transfer(
    knowledge_ids: list[int],
    from_employee_id: Optional[int],
    to_employee_id: Optional[int],   # None=共通
    reason: str = "manual",
    triggered_by: str = "staff_management",
    move_md_to_folder: Optional[str] = None,
) -> dict:
    """指定ナレッジを from→to に移管する。
    move_md_to_folder が指定されたら Obsidian上のMDも移動する。"""
    if not knowledge_ids:
        return {"transferred": 0}

    moved_md = 0
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 移動前の md_path 取得（MD移動用）
        placeholders = ",".join("?" * len(knowledge_ids))
        cur = await db.execute(
            f"SELECT id, md_path FROM knowledge_base WHERE id IN ({placeholders})",
            knowledge_ids,
        )
        path_map = {r["id"]: r["md_path"] for r in await cur.fetchall()}

        # DB更新
        await db.execute(
            f"UPDATE knowledge_base SET assigned_employee_id = ? WHERE id IN ({placeholders})",
            [to_employee_id, *knowledge_ids],
        )

        # ログ
        for kid in knowledge_ids:
            await db.execute(
                """INSERT INTO knowledge_transfer_log
                    (knowledge_id, from_employee, to_employee, reason, triggered_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (kid, from_employee_id, to_employee_id, reason, triggered_by),
            )
        await db.commit()

    # Obsidian MD 移動（任意）
    if move_md_to_folder:
        target_dir = VAULT / move_md_to_folder
        target_dir.mkdir(parents=True, exist_ok=True)
        for kid, md_path in path_map.items():
            if not md_path:
                continue
            src = Path(md_path)
            if not src.exists():
                continue
            try:
                shutil.move(str(src), str(target_dir / src.name))
                moved_md += 1
                # DB の md_path も更新
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE knowledge_base SET md_path = ? WHERE id = ?",
                        (str(target_dir / src.name), kid),
                    )
                    await db.commit()
            except Exception as e:
                print(f"[knowledge_transfer] MD移動失敗 #{kid}: {e}")

    return {
        "transferred": len(knowledge_ids),
        "from": from_employee_id,
        "to": to_employee_id,
        "moved_md_files": moved_md,
        "reason": reason,
    }


# ── 退職時の一括移管 ──────────────────────────────────

async def execute_retirement_transfer(
    retiring_employee_id: int,
    inheritance_to: Optional[int] = None,
    promote_to_common: bool = False,
    triggered_by: str = "staff_management",
) -> dict:
    """退職社員のナレッジを引継先 or 共通へ一括移動する。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id FROM knowledge_base WHERE assigned_employee_id = ?",
            (retiring_employee_id,),
        )
        ids = [r["id"] for r in await cur.fetchall()]

    if not ids:
        return {"transferred": 0, "note": "対象ナレッジなし"}

    target = None if promote_to_common else inheritance_to
    return await execute_transfer(
        knowledge_ids=ids,
        from_employee_id=retiring_employee_id,
        to_employee_id=target,
        reason="retire",
        triggered_by=triggered_by,
    )
