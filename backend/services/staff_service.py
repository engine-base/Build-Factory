"""
staff_service.py — AI社員（秘書 / リーダー / メンバー）の CRUD + Obsidian同期。

責務:
  - 採用 (create_employee)
  - 編集 (update_employee)
  - 退職 (retire_employee) ※ナレッジ引継は knowledge_transfer.py で実行
  - 一覧 (list_employees / get_employee)
  - 組織図 (build_orgchart)

Obsidianフォルダ操作:
  採用時: 03_スキル別ナレッジ/{部署}/{特化}/   ← メンバーの場合
  退職時: _アーカイブ/退職社員/{name}_{date}/  にフォルダ移動
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from db import async_db as aiosqlite

from db.queries import DB_PATH

VAULT = Path.home() / "Documents" / "Obsidian" / "ENGINE-BASE"
PERSONA_DIR = VAULT / "04_AI社員フィードバック" / "_persona"
HIRE_LOG_DIR = VAULT / "04_AI社員フィードバック" / "採用記録"
ARCHIVE_DIR  = VAULT / "_アーカイブ" / "退職社員"


def _ensure_dirs():
    for d in (PERSONA_DIR, HIRE_LOG_DIR, ARCHIVE_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ── 一覧・取得 ─────────────────────────────────────

async def list_employees(include_retired: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if include_retired:
            cur = await db.execute(
                "SELECT * FROM ai_employee_config ORDER BY id"
            )
        else:
            cur = await db.execute(
                "SELECT * FROM ai_employee_config WHERE retired_at IS NULL ORDER BY id"
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_employee(employee_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM ai_employee_config WHERE id = ?", (employee_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_employee_by_name(name: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM ai_employee_config WHERE employee_name = ?", (name,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


# ── 採用 ───────────────────────────────────────────

async def create_employee(
    persona_name: str,
    role_level: str,                       # 'leader' | 'member'
    category: str,                         # '01_営業' 等（リーダー）/ メンバーは親の category 継承推奨
    parent_id: Optional[int] = None,       # メンバーの場合は必須
    specialty: Optional[str] = None,       # メンバーの特化分野
    handles: str = "",
    personality: str = "",
    tone_style: str = "",
    catchphrase: str = "",
    avatar_emoji: str = "👤",
    knowledge_folders: Optional[list[str]] = None,
    primary_skill: str = "",
    triggered_by: str = "staff_management",
) -> dict:
    """新規社員を登録する。Obsidianフォルダ・persona MD も作成。"""
    _ensure_dirs()

    if role_level == "member" and not parent_id:
        raise ValueError("メンバーには parent_id（親リーダーID）が必要")

    # employee_name はシステムキー: 名前から生成（重複時は数字付与）
    base_key = persona_name.replace(" ", "_").replace("　", "_")
    employee_name = base_key
    suffix = 1
    while await get_employee_by_name(employee_name):
        suffix += 1
        employee_name = f"{base_key}_{suffix}"

    display_name = f"{category} {persona_name}" if role_level == "leader" else f"{specialty or ''}のメンバー {persona_name}"

    # knowledge_folders 既定値
    if not knowledge_folders:
        knowledge_folders = [
            "00_まさとの思考・価値観",
            "01_会社・事業",
            "02_共通ナレッジ",
        ]
        if role_level == "leader" and category:
            cat_short = category.replace("01_", "").replace("02_", "") \
                                .replace("03_", "").replace("04_", "")
            knowledge_folders.append(f"03_スキル別ナレッジ/{cat_short}")
        elif role_level == "member" and parent_id:
            parent = await get_employee(parent_id)
            if parent and parent.get("knowledge_folders"):
                try:
                    knowledge_folders = json.loads(parent["knowledge_folders"])
                except Exception:
                    pass
            if specialty and parent and parent.get("category"):
                cat_short = (parent["category"] or "").replace("01_", "") \
                            .replace("02_", "").replace("03_", "").replace("04_", "")
                knowledge_folders.append(f"03_スキル別ナレッジ/{cat_short}/{specialty}")

    # DB挿入
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO ai_employee_config
                (employee_name, display_name, category, primary_skill,
                 role_level, parent_id,
                 persona_name, personality, tone_style, catchphrase,
                 avatar_emoji, specialty, handles, knowledge_folders,
                 llm_provider, llm_model, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ollama', 'qwen2.5:7b', 1) RETURNING id""",
            (employee_name, display_name, category, primary_skill,
             role_level, parent_id,
             persona_name, personality, tone_style, catchphrase,
             avatar_emoji, specialty, handles, json.dumps(knowledge_folders, ensure_ascii=False)),
        )
        _row = await cur.fetchone()
        await db.commit()
        employee_id = _row["id"]

    # Obsidianフォルダ作成
    for folder in knowledge_folders:
        (VAULT / folder).mkdir(parents=True, exist_ok=True)

    # persona MD 作成
    persona_path = PERSONA_DIR / f"{persona_name}.md"
    persona_path.write_text(
        f"""---
employee_id: {employee_id}
persona_name: {persona_name}
role_level: {role_level}
category: {category or ''}
specialty: {specialty or ''}
created_at: {datetime.now().isoformat(timespec='seconds')}
---

# {avatar_emoji} {persona_name}

## 役職
{role_level} （{category or ''}）

## 担当範囲
{handles}

## 性格
{personality}

## 口調
{tone_style}

## 口癖
{catchphrase}

## ナレッジスコープ
{chr(10).join('- ' + f for f in knowledge_folders)}
""",
        encoding="utf-8",
    )

    # 採用記録 MD
    hire_log = HIRE_LOG_DIR / f"{datetime.now().strftime('%Y%m%d')}_{persona_name}.md"
    hire_log.write_text(
        f"""# 採用記録: {persona_name}
- ID: {employee_id}
- 役職: {role_level}
- 所属: {category}
- 特化: {specialty or '-'}
- 採用日: {datetime.now().strftime('%Y-%m-%d')}
- 採用者: {triggered_by}
""",
        encoding="utf-8",
    )

    return await get_employee(employee_id)


# ── 編集 ───────────────────────────────────────────

async def update_employee(employee_id: int, updates: dict) -> dict:
    """個性・担当・ナレッジスコープ等を更新する。"""
    allowed = {
        "persona_name", "personality", "tone_style", "catchphrase", "avatar_emoji",
        "specialty", "handles", "knowledge_folders", "category", "parent_id",
        "role_level", "primary_skill", "display_name",
        "llm_provider", "llm_model",
    }
    payload = {k: v for k, v in updates.items() if k in allowed}
    if not payload:
        raise ValueError("更新可能な項目がありません")

    if "knowledge_folders" in payload and isinstance(payload["knowledge_folders"], list):
        payload["knowledge_folders"] = json.dumps(payload["knowledge_folders"], ensure_ascii=False)

    sets = ", ".join(f"{k} = ?" for k in payload)
    sets += ", updated_at = datetime('now','localtime')"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE ai_employee_config SET {sets} WHERE id = ?",
            [*payload.values(), employee_id],
        )
        await db.commit()
    return await get_employee(employee_id)


# ── 退職 ───────────────────────────────────────────

async def list_active_members_of(leader_id: int) -> list[dict]:
    """指定リーダー配下の在籍中メンバーを返す。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM ai_employee_config "
            "WHERE parent_id = ? AND retired_at IS NULL AND role_level = 'member' "
            "ORDER BY id",
            (leader_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def retire_employee(
    employee_id: int,
    inheritance_to: Optional[int] = None,   # 主たる引継先（リーダー or 別メンバー）
    promote_to_common: bool = False,         # True なら共通ナレッジへ昇格
    reason: str = "",
    triggered_by: str = "staff_management",
    member_reassign_to: Optional[int] = None,   # リーダー退職時、メンバーを誰に移すか
    retire_members_too: bool = False,           # True なら配下メンバーも一括退職
) -> dict:
    """社員を退職処理する。
    リーダーが配下メンバーを抱えている場合は member_reassign_to または
    retire_members_too のどちらかが必須。
    ナレッジ引継の実行は knowledge_transfer.execute_retirement_transfer で別途行う。
    """
    emp = await get_employee(employee_id)
    if not emp:
        raise ValueError("社員が見つかりません")
    if emp.get("retired_at"):
        raise ValueError("既に退職済みです")
    # 既存5名 + 人事AI hr_05 は保護
    protected = ("secretary", "sales_01", "finance_02", "marketing_03", "cs_04", "hr_05")
    if emp["employee_name"] in protected:
        raise ValueError(f"基幹社員（{emp['employee_name']}）は退職処理できません")

    # ── リーダーが配下メンバーを抱えている場合の事前処理 ──
    members = []
    if emp.get("role_level") == "leader":
        members = await list_active_members_of(employee_id)
        if members and not retire_members_too and not member_reassign_to:
            raise ValueError(
                f"このリーダーには配下メンバーが {len(members)}名 在籍しています。"
                f"member_reassign_to（移管先リーダーID）か "
                f"retire_members_too=True を指定してください。"
            )
        if member_reassign_to:
            target = await get_employee(member_reassign_to)
            if not target or target.get("retired_at"):
                raise ValueError("移管先リーダーが在籍していません")
            if target.get("role_level") != "leader":
                raise ValueError("移管先はリーダーのみ指定可能")

    now = datetime.now().isoformat(timespec="seconds")

    # ── 配下メンバーの処理 ──
    async with aiosqlite.connect(DB_PATH) as db:
        if members:
            if retire_members_too:
                # 一緒に退職
                ids = [m["id"] for m in members]
                placeholders = ",".join("?" * len(ids))
                await db.execute(
                    f"UPDATE ai_employee_config "
                    f"SET retired_at = ?, retire_reason = ?, is_active = 0 "
                    f"WHERE id IN ({placeholders})",
                    [now, f"親リーダー退職に伴う一括退職: {reason}", *ids],
                )
            elif member_reassign_to:
                # 別リーダー配下に再配置
                ids = [m["id"] for m in members]
                placeholders = ",".join("?" * len(ids))
                await db.execute(
                    f"UPDATE ai_employee_config SET parent_id = ? "
                    f"WHERE id IN ({placeholders})",
                    [member_reassign_to, *ids],
                )
        await db.commit()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE ai_employee_config SET retired_at = ?, retire_reason = ?, "
            "inherited_to = ?, is_active = 0 WHERE id = ?",
            (now, reason, inheritance_to, employee_id),
        )
        await db.commit()

    # Obsidian の persona MD をアーカイブへ
    persona_md = PERSONA_DIR / f"{emp['persona_name']}.md"
    archive_target = ARCHIVE_DIR / f"{emp['persona_name']}_{datetime.now().strftime('%Y%m%d')}"
    archive_target.mkdir(parents=True, exist_ok=True)
    if persona_md.exists():
        try:
            shutil.move(str(persona_md), str(archive_target / persona_md.name))
        except Exception as e:
            print(f"[staff_service] persona MD移動失敗: {e}")

    # 退職証明書 MD
    cert = archive_target / "退職証明書.md"
    cert.write_text(
        f"""# 退職証明書: {emp['persona_name']}
- ID: {employee_id}
- 役職: {emp.get('role_level')}
- 所属: {emp.get('category')}
- 特化: {emp.get('specialty') or '-'}
- 退職日: {now[:10]}
- 退職理由: {reason}
- 主な引継先: {inheritance_to or ('共通ナレッジ' if promote_to_common else '未指定')}
- 処理者: {triggered_by}
""",
        encoding="utf-8",
    )

    return await get_employee(employee_id)


# ── 組織図 ──────────────────────────────────────────

async def build_orgchart() -> dict:
    """秘書 → リーダー → メンバー の階層ツリー + ナレッジ件数を返す。"""
    employees = await list_employees(include_retired=False)

    # ナレッジ件数を社員別に集計
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT assigned_employee_id, COUNT(*) as cnt FROM knowledge_base "
            "WHERE assigned_employee_id IS NOT NULL GROUP BY assigned_employee_id"
        )
        kn_counts = {r["assigned_employee_id"]: r["cnt"] for r in await cur.fetchall()}

    # md_path 接頭辞で各リーダーの部署ナレッジ件数も集計
    folder_counts: dict[str, int] = {}
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT md_path, COUNT(*) as cnt FROM knowledge_base "
            "WHERE md_path IS NOT NULL GROUP BY md_path"
        )
        for r in await cur.fetchall():
            folder_counts[r["md_path"] or ""] = r["cnt"]

    # ツリー構築
    by_id = {e["id"]: {**e, "children": [], "knowledge_count": kn_counts.get(e["id"], 0)} for e in employees}

    secretary = None
    leaders   = []
    members_by_parent: dict[int, list[dict]] = {}

    for e in by_id.values():
        if e["role_level"] == "secretary":
            secretary = e
        elif e["role_level"] == "leader":
            leaders.append(e)
        elif e["role_level"] == "member" and e.get("parent_id"):
            members_by_parent.setdefault(e["parent_id"], []).append(e)

    for leader in leaders:
        leader["children"] = members_by_parent.get(leader["id"], [])
        # 部署フォルダのナレッジ件数（自分専属 + 部署フォルダ全体 - メンバー専属を引く）
        if leader.get("knowledge_folders"):
            try:
                folders = json.loads(leader["knowledge_folders"])
            except Exception:
                folders = []
            dept_count = 0
            for f in folders:
                if f.startswith("03_"):
                    for path, cnt in folder_counts.items():
                        if f in (path or ""):
                            dept_count += cnt
            leader["dept_knowledge_count"] = dept_count

    # 共通ナレッジ件数（assigned NULL）
    common_count = sum(c for path, c in folder_counts.items()
                       if any(p in (path or "") for p in ["00_", "01_", "02_"]))

    # キャパシティ警告
    warnings = []
    for leader in leaders:
        cnt = leader.get("dept_knowledge_count", 0)
        if cnt > 500 and not leader["children"]:
            warnings.append({
                "type": "knowledge_overflow",
                "employee_id": leader["id"],
                "persona_name": leader["persona_name"],
                "count": cnt,
                "message": f"{leader['persona_name']} のナレッジが {cnt} 件。メンバー追加 + 細分化を推奨",
            })

    return {
        "secretary": secretary,
        "leaders": leaders,
        "common_knowledge_count": common_count,
        "warnings": warnings,
        "totals": {
            "headcount":  len(employees),
            "leaders":    len(leaders),
            "members":    sum(len(v) for v in members_by_parent.values()),
        },
    }
