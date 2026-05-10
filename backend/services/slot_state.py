"""
slot_state.py — 会話のスロット状態管理。

Claude/ChatGPT 風の slot tracking を明示化:
- スロット = 会話で埋めようとしている個別の情報単位
  例: フルネーム推測 → 苗字スロット, 名前スロット
  例: 採用フロー   → 役職スロット, 名前スロット, 特化スロット
- 各スロットは confirmed / rejected / hints / history を持つ

更新は ハイブリッド:
  1. ルール抽出 (確実): 確定マーカー / 否定マーカー
  2. LLM抽出 (ニュアンス): どのスロットの話か・ヒントの解釈

毎ターン呼ばれる。スレッド単位で永続化（過去の会話状態を引き継ぎ可能）。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from db import async_db as aiosqlite

from db.queries import DB_PATH

# ──────────────────────────────────────────────────────
# データ型
# ──────────────────────────────────────────────────────

@dataclass
class Slot:
    slot_name: str
    confirmed_value: Optional[str] = None
    rejected: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    position: int = 0
    is_resolved: bool = False
    goal: Optional[str] = None


def _row_to_slot(r: dict) -> Slot:
    return Slot(
        slot_name=r.get("slot_name") or "",
        confirmed_value=r.get("confirmed_value"),
        rejected=_loads(r.get("rejected"), []),
        hints=_loads(r.get("hints"), []),
        history=_loads(r.get("history"), []),
        position=int(r.get("position") or 0),
        is_resolved=bool(r.get("is_resolved")),
        goal=r.get("goal"),
    )


def _loads(s: Any, default):
    if not s: return default
    try: return json.loads(s)
    except: return default


# ──────────────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────────────

async def get_slots(thread_id: int) -> list[Slot]:
    if not thread_id:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM conversation_slots WHERE thread_id = ? ORDER BY position, id",
            (thread_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_slot(dict(r)) for r in rows]


async def upsert_slot(
    thread_id: int,
    slot_name: str,
    *,
    goal: Optional[str] = None,
    confirmed_value: Optional[str] = None,
    add_rejected: Optional[str] = None,
    add_hint: Optional[str] = None,
    add_history: Optional[str] = None,
    position: Optional[int] = None,
    is_resolved: Optional[bool] = None,
) -> None:
    """スロットを部分更新（無ければ新規作成）。"""
    if not thread_id or not slot_name:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM conversation_slots WHERE thread_id = ? AND slot_name = ?",
            (thread_id, slot_name),
        )
        row = await cur.fetchone()
        if row:
            r = dict(row)
            rejected = _loads(r.get("rejected"), [])
            hints    = _loads(r.get("hints"), [])
            history  = _loads(r.get("history"), [])

            if add_rejected and add_rejected not in rejected:
                rejected.append(add_rejected)
            if add_hint and add_hint not in hints:
                hints.append(add_hint)
            if add_history and add_history not in history:
                history.append(add_history)

            updates = {
                "rejected": json.dumps(rejected, ensure_ascii=False),
                "hints":    json.dumps(hints, ensure_ascii=False),
                "history":  json.dumps(history, ensure_ascii=False),
                "last_updated": "datetime('now','localtime')",  # 文字列ではなく式
            }
            if goal is not None: updates["goal"] = goal
            if confirmed_value is not None: updates["confirmed_value"] = confirmed_value
            if position is not None: updates["position"] = position
            if is_resolved is not None: updates["is_resolved"] = 1 if is_resolved else 0

            sets = []
            vals = []
            for k, v in updates.items():
                if k == "last_updated":
                    sets.append("last_updated = datetime('now','localtime')")
                else:
                    sets.append(f"{k} = ?")
                    vals.append(v)
            await db.execute(
                f"UPDATE conversation_slots SET {', '.join(sets)} "
                f"WHERE thread_id = ? AND slot_name = ?",
                [*vals, thread_id, slot_name],
            )
        else:
            await db.execute(
                """INSERT INTO conversation_slots
                   (thread_id, slot_name, goal, confirmed_value,
                    rejected, hints, history, position, is_resolved)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    thread_id, slot_name, goal, confirmed_value,
                    json.dumps([add_rejected] if add_rejected else [], ensure_ascii=False),
                    json.dumps([add_hint] if add_hint else [], ensure_ascii=False),
                    json.dumps([add_history] if add_history else [], ensure_ascii=False),
                    position or 0,
                    1 if is_resolved else 0,
                ),
            )
        await db.commit()


async def clear_slots(thread_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversation_slots WHERE thread_id = ?", (thread_id,))
        await db.commit()


# ──────────────────────────────────────────────────────
# ルール抽出（確定/否定マーカー）
# ──────────────────────────────────────────────────────

# 直前 AI 提案のうち、ユーザーが言及した値を抽出する
CONFIRMED_PATTERNS = [
    re.compile(r"([^\s。、！？]+?)\s*(?:は|が)\s*(?:正解|あって(?:る|います)|合って(?:る|います))"),
    re.compile(r"([^\s。、！？]+?)\s*で\s*(?:あって(?:る|います)|合って(?:る|います)|OK|オッケー)"),
]
REJECTED_HINTS_USER = ["違う", "間違い", "違いまーす", "違います", "そうじゃない", "不正解", "ハズレ"]


def _extract_recent_ai_proposals(history: list[dict], limit: int = 3) -> list[str]:
    """直近 AI 発言から提案された候補値を抽出（漢字・名前・選択肢ラベル等）"""
    proposals: list[str] = []
    for h in reversed(history or []):
        if h.get("role") != "assistant":
            continue
        text = h.get("content") or h.get("message") or ""
        # カギ括弧内の文字列は提案候補とみなす
        for m in re.finditer(r"[「『]([^「」『』]{1,40})[」』]", text):
            v = m.group(1).strip()
            if v and v not in proposals:
                proposals.append(v)
        if proposals:
            break  # 直前 AI 発言だけで打ち切り（指示語解決の原則）
    return proposals[:limit]


async def rule_update_slots(thread_id: int, user_message: str, history: list[dict]) -> None:
    """ルールベースで slot 状態を更新（確実な部分のみ）。"""
    if not thread_id or not user_message:
        return
    msg = user_message.strip()
    slots = await get_slots(thread_id)

    # 確定マーカー: "○○はあっている" 等
    for pat in CONFIRMED_PATTERNS:
        for m in pat.finditer(msg):
            value = m.group(1).strip()
            # value がどのスロットに属するか
            target = _find_slot_owning_value(slots, value) or _guess_slot_for_value(slots, value)
            if target:
                await upsert_slot(thread_id, target, confirmed_value=value, is_resolved=True)

    # 否定マーカー: "違う" 等が含まれていれば、直前 AI 提案を rejected へ
    has_rejection = any(neg in msg for neg in REJECTED_HINTS_USER)
    if has_rejection:
        recent = _extract_recent_ai_proposals(history)
        # ユーザーが「○○は合ってる」と部分肯定していたら、その値は対象外
        confirmed_values = {s.confirmed_value for s in slots if s.confirmed_value}
        for v in recent:
            if v in confirmed_values:
                continue
            target = _find_slot_owning_value(slots, v)
            if target:
                await upsert_slot(thread_id, target, add_rejected=v)


def _find_slot_owning_value(slots: list[Slot], value: str) -> Optional[str]:
    """history に value を含むスロットを探す。"""
    for s in slots:
        if value in s.history or value == s.confirmed_value:
            return s.slot_name
        # 部分一致（"高本雅人" のうち "高本" が history にある等）
        for h in s.history:
            if h and h in value:
                return s.slot_name
    return None


def _guess_slot_for_value(slots: list[Slot], value: str) -> Optional[str]:
    """slots が空 or 該当無しの時、最も新しい未確定スロットを返す。"""
    for s in slots:
        if not s.is_resolved:
            return s.slot_name
    return None


# ──────────────────────────────────────────────────────
# LLM 抽出（ニュアンス: ヒント解釈・スロット帰属）
# ──────────────────────────────────────────────────────

LLM_SLOT_PROMPT = """あなたは会話のスロット状態を更新するアシスタントです。
以下は AI と ユーザー の会話履歴と、現在のスロット状態です。

ユーザーの最新発言を読み、以下を JSON で返してください（説明不要・JSONのみ）:
- "new_slots": ゴール達成に必要な新しいスロット（既存に無いもの）
- "additions": 既存スロットへの追加（confirmed_value / add_rejected / add_hint）

出力例:
{
  "goal": "フルネーム漢字推測",
  "new_slots": [
    {"slot_name": "名前（まさと）の漢字", "position": 1}
  ],
  "additions": [
    {"slot_name": "苗字（たかもと）", "confirmed_value": "高本"},
    {"slot_name": "名前（まさと）", "add_hint": "キリスト教の重要な本=聖書→聖"},
    {"slot_name": "名前（まさと）", "add_hint": "7つの星座=北斗七星→斗"}
  ]
}

注意:
- "違う" などの否定は rejected として扱う対象を直前 AI 提案から特定する
- ヒント表現はそれが指すスロットへ add_hint する
- 既に確定したスロットに confirmed_value を上書きしない
- 確実でないものは出力しない（推測 < 確実）

現在のスロット状態:
"""


async def llm_update_slots(
    thread_id: int,
    user_message: str,
    history: list[dict],
    provider: str = "openai",
    model: str = "gpt-4o-mini",
) -> None:
    """LLM でスロット更新（ニュアンス対応）。失敗しても致命的でない。

    Phase 2 (USE_INSTRUCTOR=1): Instructor 経由で構造化抽出（壊れた JSON で詰まらない）
    フォールバック: 旧 手書き JSON パース
    """
    if not thread_id or not user_message:
        return
    if not os.environ.get("OPENAI_API_KEY") and provider == "openai":
        return

    slots = await get_slots(thread_id)
    slots_repr = json.dumps([asdict(s) for s in slots], ensure_ascii=False, indent=2)

    # ── Phase 2: Instructor 経路 ─────────────────
    if os.environ.get("USE_INSTRUCTOR", "1") == "1":
        try:
            from services.slot_extractor import extract_slot_updates
            result = await extract_slot_updates(
                user_message=user_message,
                history=history,
                slots_repr=slots_repr,
                provider=provider,
                model=model,
            )
            if result is None:
                return
            goal = result.goal
            for ns in result.new_slots:
                if ns.slot_name:
                    await upsert_slot(thread_id, ns.slot_name, goal=goal, position=ns.position)
            for add in result.additions:
                if not add.slot_name:
                    continue
                kwargs: dict = {}
                if add.confirmed_value:
                    kwargs["confirmed_value"] = add.confirmed_value
                    kwargs["is_resolved"] = True
                if add.add_rejected:
                    kwargs["add_rejected"] = add.add_rejected
                if add.add_hint:
                    kwargs["add_hint"] = add.add_hint
                if goal:
                    kwargs["goal"] = goal
                if kwargs:
                    await upsert_slot(thread_id, add.slot_name, **kwargs)
            return
        except Exception as e:
            print(f"[slot_state] Instructor 経路失敗・旧経路へフォールバック: {e}")

    # ── 旧経路: 手書き JSON パース ─────────────
    convo = []
    for h in (history or [])[-8:]:
        role = "ユーザー" if h.get("role") == "user" else "AI"
        convo.append(f"[{role}] {(h.get('content') or h.get('message') or '')[:300]}")
    convo.append(f"[ユーザー(最新)] {user_message[:300]}")

    prompt = LLM_SLOT_PROMPT + slots_repr + "\n\n会話:\n" + "\n".join(convo)

    try:
        from llm.config import get_openai_client, LLMProvider
        try:
            provider_enum = LLMProvider(provider)
        except ValueError:
            provider_enum = LLMProvider.OLLAMA
        client = get_openai_client(provider_enum, dict(os.environ))
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[slot_state] LLM抽出失敗: {e}")
        return

    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return
    try:
        data = json.loads(m.group())
    except Exception:
        return

    goal = data.get("goal")

    # 新規スロット
    for ns in data.get("new_slots") or []:
        nm = ns.get("slot_name")
        if not nm: continue
        await upsert_slot(thread_id, nm, goal=goal, position=ns.get("position", 0))

    # 既存追加
    for add in data.get("additions") or []:
        nm = add.get("slot_name")
        if not nm: continue
        kwargs: dict = {}
        if add.get("confirmed_value"):
            kwargs["confirmed_value"] = add["confirmed_value"]
            kwargs["is_resolved"] = True
        if add.get("add_rejected"):
            kwargs["add_rejected"] = add["add_rejected"]
        if add.get("add_hint"):
            kwargs["add_hint"] = add["add_hint"]
        if goal:
            kwargs["goal"] = goal
        if kwargs:
            await upsert_slot(thread_id, nm, **kwargs)


# ──────────────────────────────────────────────────────
# 統合: 毎ターンの更新エントリポイント
# ──────────────────────────────────────────────────────

async def update_slots_from_message(
    thread_id: int,
    user_message: str,
    history: list[dict],
    helper_provider: str = "openai",
    helper_model: str = "gpt-4o-mini",
) -> None:
    """ユーザーメッセージから slot 状態を更新する。
    1) ルール抽出（確実・即時）
    2) LLM抽出（ニュアンス・帰属判断）"""
    if not thread_id:
        return
    try:
        await rule_update_slots(thread_id, user_message, history)
    except Exception as e:
        print(f"[slot_state] rule update 失敗: {e}")
    try:
        await llm_update_slots(thread_id, user_message, history, helper_provider, helper_model)
    except Exception as e:
        print(f"[slot_state] llm update 失敗: {e}")


# ──────────────────────────────────────────────────────
# AI 提案候補の自動 history 記録
# ──────────────────────────────────────────────────────

# 「○○」『○○』 内・全角ダブルクオート内・最大20文字を候補として拾う
_AI_PROPOSAL_PATTERNS = [
    re.compile(r"[「『]([^「」『』]{1,20})[」』]"),
    re.compile(r'"([^"]{1,20})"'),
    re.compile(r'"([^"]{1,20})"'),
]


def extract_ai_proposals(ai_text: str) -> list[str]:
    """AI 応答テキストから提案候補を抽出する。"""
    if not ai_text:
        return []
    seen: list[str] = []
    for pat in _AI_PROPOSAL_PATTERNS:
        for m in pat.finditer(ai_text):
            v = m.group(1).strip()
            # ノイズ除外: 空・記号のみ・「正解」「合ってる」などのメタ語
            if not v or v in seen:
                continue
            if v in ("正解", "確定", "OK", "オッケー", "合ってる", "あってる"):
                continue
            seen.append(v)
    return seen[:10]


async def record_ai_proposals(thread_id: int, ai_text: str) -> None:
    """AI 応答から提案候補を抽出し、最も新しい未確定スロットの history に記録する。
    （次ターンで「違う」と言われた時に rule_update_slots が reject 対象を特定できるようにする）"""
    if not thread_id or not ai_text:
        return
    proposals = extract_ai_proposals(ai_text)
    if not proposals:
        return
    slots = await get_slots(thread_id)
    target = _guess_slot_for_value(slots, "")  # 最も新しい未解決
    if not target:
        return
    for v in proposals:
        # 既に history・rejected・confirmed にあるものはスキップ
        s = next((x for x in slots if x.slot_name == target), None)
        if s and (v in s.history or v in s.rejected or v == s.confirmed_value):
            continue
        try:
            await upsert_slot(thread_id, target, add_history=v)
        except Exception as e:
            print(f"[slot_state.record_ai_proposals] {e}")


# ──────────────────────────────────────────────────────
# 破損スロット検出 & リセット
# ──────────────────────────────────────────────────────

# 破損判定: ヒント/rejected が長すぎる（生発言コピー疑い）or 異常に多い
_LONG_HINT_THRESHOLD = 30
_MANY_HINT_THRESHOLD = 6


def is_corrupt(slot: Slot) -> bool:
    """スロットが破損している可能性を判定する。"""
    long_hints = [h for h in slot.hints if h and len(h) > _LONG_HINT_THRESHOLD]
    long_rejected = [r for r in slot.rejected if r and len(r) > _LONG_HINT_THRESHOLD]
    if len(slot.hints) > _MANY_HINT_THRESHOLD:
        return True
    if len(long_hints) >= 1 or len(long_rejected) >= 1:
        return True
    # スロット名に "/" や全角カッコ重複等の異常
    if slot.slot_name.count("（") > 1 or slot.slot_name.count("(") > 1:
        return True
    return False


async def reset_slots(thread_id: int) -> int:
    """指定スレッドのスロットを全削除する。"""
    if not thread_id:
        return 0
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM conversation_slots WHERE thread_id = ?", (thread_id,)
        )
        await db.commit()
        return cur.rowcount or 0


async def reset_corrupt_slots(thread_id: int) -> int:
    """破損したスロットだけを削除する。"""
    if not thread_id:
        return 0
    slots = await get_slots(thread_id)
    deleted = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for s in slots:
            if is_corrupt(s):
                await db.execute(
                    "DELETE FROM conversation_slots WHERE thread_id = ? AND slot_name = ?",
                    (thread_id, s.slot_name),
                )
                deleted += 1
        await db.commit()
    return deleted


# ──────────────────────────────────────────────────────
# プロンプト用フォーマット
# ──────────────────────────────────────────────────────

def format_for_prompt(slots: list[Slot]) -> str:
    """スロット状態をプロンプトに注入する文字列にする。"""
    if not slots:
        return ""
    lines = ["【会話のスロット状態】"]
    if slots[0].goal:
        lines.append(f"目的: {slots[0].goal}")
    for s in slots:
        body = []
        if s.confirmed_value:
            body.append(f"確定: {s.confirmed_value}")
        if s.rejected:
            body.append(f"×不採用（再提示禁止）: {', '.join(s.rejected)}")
        if s.hints:
            body.append(f"ヒント: {' / '.join(s.hints)}")
        if s.history:
            ph = [h for h in s.history if h not in s.rejected and h != s.confirmed_value]
            if ph:
                body.append(f"履歴: {', '.join(ph[-5:])}")
        status = "[OK]" if s.is_resolved else "[..]"
        lines.append(f"  {status} [{s.slot_name}] " + " / ".join(body))
    return "\n".join(lines)
