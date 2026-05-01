"""
scoped_knowledge.py — 階層対応のナレッジ検索・追加。

階層スコープ:
  秘書（secretary）   : 共通（00_/01_/02_）+ 振り分け基準MD
  リーダー（leader）   : 共通 + 自部署フォルダ全体（03_スキル別ナレッジ/{部署}/...）
  メンバー（member）   : 共通 + 自部署 + 自分の専門フォルダ + assigned_employee_id=自分

検索:
  search_in_scope(employee_id, query) → 自分が見えるナレッジだけからベクトル検索

追加:
  add_for_employee(content, current_employee_id, target_scope=None)
    1. target_scope 明示なら そこへ
    2. LLM分類で推定（信頼度高ければ採用）
    3. それ以外は current_employee の scope に保存
    4. 最終的な保存先と内容を返す（呼出側で確認カードを出す想定）
"""

from __future__ import annotations

import json
import re
from typing import Optional

from db import async_db as aiosqlite

from db.queries import DB_PATH


# ── 役職・スコープのヘルパ ─────────────────────────────────

async def get_employee(employee_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM ai_employee_config WHERE id = ? AND retired_at IS NULL",
            (employee_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_scope_folders(employee_id: int) -> list[str]:
    """その社員が参照可能な md_path 接頭辞リストを返す。
    親リーダーの knowledge_folders も継承する（メンバーの場合）。"""
    emp = await get_employee(employee_id)
    if not emp:
        return ["00_", "01_", "02_"]

    folders: list[str] = []
    raw = emp.get("knowledge_folders")
    if raw:
        try:
            folders.extend(json.loads(raw))
        except Exception:
            pass

    # 親リーダーがいれば親の knowledge_folders も合算（メンバーは継承）
    parent_id = emp.get("parent_id")
    if parent_id:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT knowledge_folders FROM ai_employee_config WHERE id = ?",
                (parent_id,),
            )
            row = await cur.fetchone()
            if row and row["knowledge_folders"]:
                try:
                    folders.extend(json.loads(row["knowledge_folders"]))
                except Exception:
                    pass

    # 共通は常に保証
    for default in ("00_まさとの思考・価値観", "01_会社・事業", "02_共通ナレッジ"):
        if default not in folders:
            folders.append(default)
    return list(dict.fromkeys(folders))   # 重複排除・順序保持


# ── スコープ付き検索 ─────────────────────────────────────

async def search_in_scope(
    employee_id: Optional[int],
    query: str,
    top_k: int = 10,
    min_score: float = 0.4,
) -> list[dict]:
    """
    指定社員のスコープ内でベクトル検索する。
    employee_id=None なら共通のみ。
    """
    from services.embedding_service import embed, decode, cosine_similarity

    folders = await get_scope_folders(employee_id) if employee_id else \
              ["00_まさとの思考・価値観", "01_会社・事業", "02_共通ナレッジ"]

    query_vec = await embed(query)
    if not query_vec:
        return []

    # 親リーダーIDも所属IDとして許容（メンバーが親のassignedナレッジを参照可能）
    accept_ids: list[int] = []
    if employee_id:
        accept_ids.append(employee_id)
        emp = await get_employee(employee_id)
        if emp and emp.get("parent_id"):
            accept_ids.append(emp["parent_id"])

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # WHERE: (assigned NULL かつ md_path で folders 接頭辞一致)
        #        OR (assigned IN accept_ids)
        path_clauses = " OR ".join(["md_path LIKE ?"] * len(folders))
        path_params = [f"%{f}%" for f in folders]   # 部分一致でVault配下を吸収

        if accept_ids:
            placeholders = ",".join("?" * len(accept_ids))
            sql = (
                "SELECT id, title, category, summary, content, md_path, "
                "       skill_tags, confidence, assigned_employee_id, embedding "
                "FROM knowledge_base "
                f"WHERE embedding IS NOT NULL AND ("
                f"  (assigned_employee_id IS NULL AND ({path_clauses})) "
                f"  OR assigned_employee_id IN ({placeholders}) "
                ")"
            )
            params = path_params + accept_ids
        else:
            sql = (
                "SELECT id, title, category, summary, content, md_path, "
                "       skill_tags, confidence, assigned_employee_id, embedding "
                "FROM knowledge_base "
                f"WHERE embedding IS NOT NULL AND assigned_employee_id IS NULL "
                f"AND ({path_clauses})"
            )
            params = path_params

        rows = await db.execute_fetchall(sql, params)

    scored: list[dict] = []
    for r in rows:
        try:
            row_vec = decode(r["embedding"])
            score = cosine_similarity(query_vec, row_vec)
            adjusted = score * float(r["confidence"] or 1.0)
            if adjusted >= min_score:
                scored.append({
                    "id": r["id"],
                    "title": r["title"],
                    "category": r["category"],
                    "content": (r["content"] or r["summary"] or "")[:300],
                    "md_path": r["md_path"],
                    "assigned_employee_id": r["assigned_employee_id"],
                    "score": round(adjusted, 4),
                })
        except Exception:
            continue

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ── 追加先スコープの自動分類（LLM） ─────────────────────

CLASSIFY_PROMPT = """あなたは社内ナレッジの分類アシスタントです。
以下の本文を読み、最適な保存先カテゴリを1つだけ選び、JSONで返してください。

カテゴリ:
- "common"     : まさとの価値観・全社共通の方針・会社全体の事業情報
- "営業"       : 営業・受注・パイプライン・案件・営業メール
- "経理"       : 経理・請求・支払い・キャッシュフロー・税務・PL
- "マーケティング" : SNS・広告・コンテンツ・SEO・ブランド
- "CS"         : サポート・問い合わせ対応・FAQ・クレーム
- "unknown"    : 上記いずれでもない・判定困難

出力フォーマット（JSONのみ・コードブロック禁止）:
{"category":"営業|経理|マーケティング|CS|common|unknown","confidence":0.0-1.0,"reason":"30字以内"}

本文:
"""


async def classify_target_category(content: str) -> dict:
    """ナレッジ本文から最適保存先カテゴリを LLM 推定する。"""
    try:
        from integrations.skill_runner import invoke_skill
        prompt = CLASSIFY_PROMPT + content[:1500]
        response = await invoke_skill(
            "secretary", prompt,
            provider="ollama", model="qwen2.5:7b",
            triggered_by="system",
        )
        # LLMは複数のJSON断片を返すことがある。最後の {...} を採用
        # （プロンプト中の例スキーマを誤って拾わないため）
        matches = list(re.finditer(r'\{[^{}]*"category"[^{}]*\}', response, re.DOTALL))
        for m in reversed(matches):
            try:
                data = json.loads(m.group())
            except Exception:
                continue
            cat = (data.get("category") or "unknown").strip()
            # 想定外の値（"|" 含む例文等）は unknown 扱い
            if "|" in cat or cat == "":
                continue
            return {
                "category": cat,
                "confidence": float(data.get("confidence", 0.0)),
                "reason": (data.get("reason") or "")[:80],
            }
    except Exception as e:
        print(f"[scoped_knowledge] classify失敗: {e}")
    return {"category": "unknown", "confidence": 0.0, "reason": "判定失敗"}


# ── スコープから保存先 md_path を導く ───────────────────

CATEGORY_TO_FOLDER = {
    "common":         "02_共通ナレッジ",
    "営業":           "03_スキル別ナレッジ/営業",
    "経理":           "03_スキル別ナレッジ/経理",
    "マーケティング": "03_スキル別ナレッジ/マーケティング",
    "CS":             "03_スキル別ナレッジ/CS",
}


async def find_employee_for_category(category: str) -> Optional[int]:
    """カテゴリに対応するリーダーIDを返す（メンバーは親リーダーから抽出）。"""
    if category == "common":
        return None
    name_map = {
        "営業": "sales_01",
        "経理": "finance_02",
        "マーケティング": "marketing_03",
        "CS": "cs_04",
    }
    employee_name = name_map.get(category)
    if not employee_name:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id FROM ai_employee_config WHERE employee_name = ? AND retired_at IS NULL",
            (employee_name,),
        )
        row = await cur.fetchone()
        return row["id"] if row else None


def _normalize(s: str) -> str:
    import unicodedata
    return unicodedata.normalize('NFC', (s or "").strip())


async def propose_save_target(
    content: str,
    current_employee_id: Optional[int] = None,
) -> dict:
    """
    保存先を提案する。実際には保存しない（呼出側で確認後に save_knowledge を呼ぶ）。

    Returns:
        {
          "target_employee_id": int|None,   # None=共通
          "target_folder":      str,         # 保存先 Obsidian フォルダ
          "category":           str,         # "営業"等
          "confidence":         float,
          "reason":             str,
          "source":             "explicit_classify"|"current_employee"|"common_fallback"
        }
    """
    classify = await classify_target_category(content)
    cat  = _normalize(classify["category"])
    conf = classify["confidence"]

    if cat != "unknown" and conf >= 0.7:
        emp_id = await find_employee_for_category(cat)
        folder = CATEGORY_TO_FOLDER.get(cat, "02_共通ナレッジ")
        return {
            "target_employee_id": emp_id,
            "target_folder": folder,
            "category": cat,
            "confidence": conf,
            "reason": classify["reason"],
            "source": "explicit_classify",
        }

    # フォールバック: 現在の会話相手の所属に保存
    if current_employee_id:
        emp = await get_employee(current_employee_id)
        if emp:
            cat = (emp.get("category") or "").replace("01_", "").replace("02_", "") \
                                              .replace("03_", "").replace("04_", "") \
                                              .strip() or "common"
            folder = CATEGORY_TO_FOLDER.get(cat, "02_共通ナレッジ")
            # リーダーなら部署フォルダ・メンバーなら自分の特化フォルダがあれば使う
            scope = await get_scope_folders(current_employee_id)
            personal = [s for s in scope if "/" in s and s.count("/") >= 2]
            if personal:
                folder = personal[0]
            return {
                "target_employee_id": current_employee_id if emp.get("role_level") == "member" else None,
                "target_folder": folder,
                "category": cat or "common",
                "confidence": conf,
                "reason": "現在の会話相手の所属",
                "source": "current_employee",
            }

    # それでも決まらない → 共通
    return {
        "target_employee_id": None,
        "target_folder": "02_共通ナレッジ",
        "category": "common",
        "confidence": conf,
        "reason": "判定困難・共通へ",
        "source": "common_fallback",
    }


# ── 実保存（提案を承認後に呼ぶ） ───────────────────────

async def save_knowledge(
    title: str,
    content: str,
    target_employee_id: Optional[int],
    target_folder: str,
    category: Optional[str] = None,
    source: str = "manual",
    triggered_by: str = "masato",
) -> int:
    """ナレッジを実際に保存する（DB + Obsidian Vault）。"""
    from pathlib import Path
    from datetime import datetime

    vault = Path.home() / "Documents" / "Obsidian" / "ENGINE-BASE"
    folder = vault / target_folder
    folder.mkdir(parents=True, exist_ok=True)

    safe_title = re.sub(r'[^\w\sぁ-んァ-ヶー一-龯]', '_', title)[:60].strip() or "untitled"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    md_file = folder / f"{ts}_{safe_title}.md"

    md_text = (
        f"---\n"
        f"title: {title}\n"
        f"category: {category or ''}\n"
        f"assigned_employee_id: {target_employee_id or ''}\n"
        f"source: {source}\n"
        f"created: {datetime.now().isoformat(timespec='seconds')}\n"
        f"---\n\n"
        f"# {title}\n\n{content}\n"
    )
    md_file.write_text(md_text, encoding="utf-8")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO knowledge_base
                (title, content, summary, category, source, md_path,
                 assigned_employee_id, confidence, use_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1.0, 0, datetime('now','localtime')) RETURNING id""",
            (title, content, content[:200], category, source,
             str(md_file), target_employee_id),
        )
        _row = await cur.fetchone()
        await db.commit()
        knowledge_id = _row["id"]

    # Embedding 計算
    try:
        from services.embedding_service import embed_and_save
        await embed_and_save(knowledge_id)
    except Exception as e:
        print(f"[scoped_knowledge] embed失敗: {e}")

    # 移動ログ（追加もログに残す）
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO knowledge_transfer_log
                (knowledge_id, from_employee, to_employee, reason, triggered_by)
               VALUES (?, NULL, ?, 'add', ?)""",
            (knowledge_id, target_employee_id, triggered_by),
        )
        await db.commit()

    return knowledge_id
