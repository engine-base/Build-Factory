"""
slot_extractor.py — Phase 2 V2: 分類駆動・部分一致対応

旧版の問題:
  - ユーザーの生発言を hints に丸コピー
  - 確定/否定/ヒント/メタ指示の区別なし
  - 「聖人」と提案 → 違う と言われた時、「聖」も REJECTED に入る

V2 の改善:
  1. ユーザー発言を最初に「タイプ分類」する
  2. ヒントは原文ではなく**解釈した漢字候補**を保存
  3. 否定は AI 提案そのままを reject、ただし**部分的に正しい漢字は keep_partial_chars** に分離
  4. 既存スロット名を厳密に再利用（ゆるい新規作成を抑制）
  5. メタ指示・雑談では slot 更新しない

返り値:
  SlotResultV2(type=..., confirm_*, reject_*, hint_*, ...)
"""

from __future__ import annotations

import os
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────
# V2 スキーマ
# ──────────────────────────────────────────

MessageType = Literal[
    "confirmation",   # 「○○は合ってる」「正解」
    "rejection",      # 「違う」「不正解」「○の字は違う」
    "hint",           # 「キリスト教の重要な本に含まれてる」
    "new_goal",       # 新しい話題開始（漢字推測 / 採用フロー等）
    "meta",           # 「ちゃんと当てて」「質問してもいい」（応答方針への要請）
    "smalltalk",      # 雑談・関係ない発言
]


class SlotResultV2(BaseModel):
    type: MessageType = Field(..., description="ユーザー発言のタイプ")

    # ── confirmation ──
    confirm_slot: Optional[str] = Field(None, description="既存スロット名（厳密一致）")
    confirm_value: Optional[str] = Field(None, description="確定値")

    # ── rejection（部分一致対応）──
    reject_slot: Optional[str] = Field(None, description="既存スロット名")
    reject_full_value: Optional[str] = Field(None, description="AI が提案して却下された候補そのまま（例: 聖人）")
    keep_partial_chars: list[str] = Field(
        default_factory=list,
        description="部分的に正しかった漢字（例: ['聖']）。これは rejected には入れない・hints として保持",
    )

    # ── hint ──
    hint_slot: Optional[str] = Field(None, description="ヒント対象スロット名")
    hint_kanji_candidates: list[str] = Field(
        default_factory=list,
        description="ユーザー発言を解釈した漢字候補（原文ではない）。例: 'キリスト教の重要な本' → ['聖']",
    )

    # ── new_goal ──
    new_goal: Optional[str] = Field(None, description="目的の説明（例: フルネーム漢字推測）")
    new_slot_names: list[str] = Field(
        default_factory=list,
        description="新規作成するスロット名（既存に該当無い時のみ）",
    )

    reasoning: str = Field("", description="なぜそう分類したか（デバッグ用・短く）")


# ──────────────────────────────────────────
# プロンプト
# ──────────────────────────────────────────

SYSTEM_PROMPT = """あなたは会話のスロット状態抽出器です。

会話履歴と現在のスロット状態を見て、**ユーザー最新発言**だけから slot 更新情報を抽出します。

## 重要な原則

1. **発言タイプを最初に分類**:
   - confirmation: 「○○は合ってる」「正解」
   - rejection:    「違う」「不正解」「その漢字じゃない」
   - hint:         「○○に含まれる」「○○のような意味」（解釈が必要なヒント）
   - new_goal:     新しい話題（漢字推測したい・採用したい等）
   - meta:         応答方針への要請（「ちゃんと当てて」「質問してもいい」「聞き続けて」）
   - smalltalk:    その他（雑談・関係ない・挨拶など）

2. **meta / smalltalk のときは slot を一切更新しない**:
   - ユーザーの叱責・指示・雑談を hints に保存しない
   - 該当フィールドはすべて空にして type だけ返す

3. **hint の解釈ルール**:
   - 原文を hints に保存してはいけない
   - 「キリスト教の重要な本」→ "聖"（聖書）
   - 「7つの星座/北斗七星」→ "斗"
   - 「太陽」→ "日" or "陽"
   - 解釈できない場合は hint_kanji_candidates を空にして type=meta にダウングレード

4. **rejection の部分一致処理（最重要）**:
   - AI が単一候補「聖人」を提案 → ユーザー「違う」 のとき:
     - reject_slot=該当スロット名・reject_full_value="聖人"・keep_partial_chars=[]
   - ユーザー「聖は合ってるけど人は違う」のとき:
     - reject_full_value="聖人"・keep_partial_chars=["聖"]
   - ユーザー「聖の字は違う」のとき:
     - reject_full_value="聖"・keep_partial_chars=[]
   - **AI が複数スロットの候補を一度に提案** したターン（例「苗字は『高本』、名前は『聖斗』」）の直後に
     ユーザー「違う」とだけ言った場合:
     - **どのスロットが違うか曖昧なので何も reject しない**
     - type="meta" にダウングレード（応答方針として「どこが違うか聞き直す」を示唆）
     - confirm_*・reject_*・hint_* すべて null/空
   - 曖昧な「違う」で安易に確定値を rejected に押し込まない（誤って正解を消さない）

5. **既存スロット名の厳守**:
   - スロット状態に存在する slot_name を**そのまま**使う
   - 「苗字（たかもと）」と「苗字」と「たかもと（高本）」は別物として扱わない
   - 既存に近いものがあれば必ず再利用、本当に新しい場合のみ new_slot_names

6. **確実でなければ出さない**:
   - 推測 < 確実
   - 不明な部分は null/空配列のまま
"""


PROMPT_TEMPLATE = """## 現在のスロット状態
{slots_repr}

## 会話履歴（古い順）
{convo}

## 抽出対象（ユーザーの最新発言）
「{user_message}」

タイプを分類し、必要なフィールドのみ埋めてください。
meta / smalltalk なら type だけ返して他は空。
"""


# ──────────────────────────────────────────
# 抽出関数
# ──────────────────────────────────────────

async def extract_slot_updates_v2(
    user_message: str,
    history: list[dict],
    slots_repr: str,
    *,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
) -> Optional[SlotResultV2]:
    """V2: 分類駆動・部分一致対応のスロット抽出。"""
    if not user_message:
        return None
    if provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
        return None

    convo_lines = []
    for h in (history or [])[-6:]:
        role = "ユーザー" if h.get("role") == "user" else "AI"
        text = (h.get("content") or h.get("message") or "")[:240]
        convo_lines.append(f"[{role}] {text}")

    user_prompt = PROMPT_TEMPLATE.format(
        slots_repr=slots_repr or "(まだスロット無し)",
        convo="\n".join(convo_lines) or "(履歴無し)",
        user_message=user_message[:400],
    )

    try:
        import instructor
        from llm.config import get_openai_client, LLMProvider
        try:
            provider_enum = LLMProvider(provider)
        except ValueError:
            provider_enum = LLMProvider.OLLAMA
        raw_client = get_openai_client(provider_enum, dict(os.environ))
        client = instructor.from_openai(raw_client, mode=instructor.Mode.JSON)

        result: SlotResultV2 = await client.chat.completions.create(
            model=model,
            response_model=SlotResultV2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=600,
            temperature=0,
            max_retries=2,
        )
        return result
    except ImportError:
        print("[slot_extractor.v2] instructor 未インストール")
        return None
    except Exception as e:
        print(f"[slot_extractor.v2] 抽出失敗: {e}")
        return None


# ──────────────────────────────────────────
# 旧 V1 互換（slot_state.py が古い名前で import している場合に備えて残す）
# ──────────────────────────────────────────

class NewSlot(BaseModel):
    slot_name: str
    position: int = 0


class SlotAddition(BaseModel):
    slot_name: str
    confirmed_value: Optional[str] = None
    add_rejected: Optional[str] = None
    add_hint: Optional[str] = None


class SlotUpdateResult(BaseModel):
    goal: Optional[str] = None
    new_slots: list[NewSlot] = Field(default_factory=list)
    additions: list[SlotAddition] = Field(default_factory=list)


async def extract_slot_updates(
    user_message: str,
    history: list[dict],
    slots_repr: str,
    *,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
) -> Optional[SlotUpdateResult]:
    """V1 互換ラッパー: 内部で V2 を呼び、V1 形式に変換する。"""
    v2 = await extract_slot_updates_v2(
        user_message=user_message, history=history, slots_repr=slots_repr,
        provider=provider, model=model,
    )
    if v2 is None:
        return None

    if v2.type in ("meta", "smalltalk"):
        return SlotUpdateResult()  # 空 = 更新なし

    additions: list[SlotAddition] = []

    if v2.type == "confirmation" and v2.confirm_slot:
        additions.append(SlotAddition(
            slot_name=v2.confirm_slot, confirmed_value=v2.confirm_value,
        ))

    if v2.type == "rejection" and v2.reject_slot:
        if v2.reject_full_value:
            additions.append(SlotAddition(
                slot_name=v2.reject_slot, add_rejected=v2.reject_full_value,
            ))
        for kanji in v2.keep_partial_chars:
            additions.append(SlotAddition(
                slot_name=v2.reject_slot, add_hint=f"部分的に正しかった: {kanji}",
            ))

    if v2.type == "hint" and v2.hint_slot:
        for k in v2.hint_kanji_candidates:
            additions.append(SlotAddition(slot_name=v2.hint_slot, add_hint=k))

    new_slots = [NewSlot(slot_name=n, position=i) for i, n in enumerate(v2.new_slot_names)]

    return SlotUpdateResult(goal=v2.new_goal, new_slots=new_slots, additions=additions)
