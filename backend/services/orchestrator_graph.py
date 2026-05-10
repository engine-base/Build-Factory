"""
orchestrator_graph.py — 会話オーケストレーション (sequential pipeline)

ADR-010 (AI スタック再設計、2026-05-10) により、メイン経路で LangGraph /
LangChain を使うことは禁止された。本ファイルは元 LangGraph 実装を sequential
async pipeline に置き換えたもの。ファイル名 / 関数名は import 互換のために維持。

設計方針:
  - 状態管理 (mode / profile / slots / rag / skill) は ConversationState TypedDict
  - 各ノードは独立した async 関数として実装、prepare_state が逐次実行
  - LangGraph / langgraph.* / langchain.* は import しない (lint で検出)

エントリポイント:
  prepare_state(thread_id, employee_id, user_message, history, ...)
    → dict (employee / mode / triggered_skill / rag_text)

  → このあと secretary_agent.build_agent_for_employee + Runner.run_streamed で実行
"""

from __future__ import annotations

import os
from typing import Optional, TypedDict


class ConversationState(TypedDict, total=False):
    # 入力
    thread_id: int
    employee_id: int
    user_message: str
    history: list[dict]
    provider: str
    model: str
    helper_provider: Optional[str]
    helper_model: Optional[str]

    # 処理結果
    employee: dict                 # ai_employee_config の row
    mode: str                      # "chat" | "task"
    triggered_skill: Optional[str]
    rag_text: str
    slot_text: str
    summary_text: str

    # 最終 instructions (agent に渡される完成プロンプト)
    instructions: str


# ──────────────────────────────────────────
# ノード関数 (各々が State を部分更新して返す)
# ──────────────────────────────────────────

async def node_load_employee(state: ConversationState) -> dict:
    """社員情報を読み込む。"""
    from db import async_db as aiosqlite
    from db.queries import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM ai_employee_config WHERE id = ?",
            (state["employee_id"],),
        )
        row = await cur.fetchone()
    emp = dict(row) if row else {
        "persona_name": "秘書",
        "role_level": "secretary",
        "primary_skill": "secretary",
    }
    return {"employee": emp}


async def node_update_profile(state: ConversationState) -> dict:
    """ユーザープロファイル更新 (バックグラウンド・致命的でない)"""
    try:
        from services.user_profile import update_from_message
        await update_from_message(state["user_message"])
    except Exception as e:
        print(f"[orchestrator.update_profile] {e}")
    return {}


async def node_detect_mode(state: ConversationState) -> dict:
    """雑談 / タスク判別。"""
    try:
        from services.mode_detector import detect_mode
        mode = await detect_mode(state["user_message"], state.get("history") or [])
    except Exception as e:
        print(f"[orchestrator.detect_mode] {e}")
        mode = "chat"
    return {"mode": mode}


async def node_detect_skill(state: ConversationState) -> dict:
    """タスク時のみスキル発火検知。"""
    if state.get("mode") != "task":
        return {"triggered_skill": None}
    try:
        from services.skill_detector import detect_skill
        emp = state.get("employee", {})
        skill = detect_skill(
            message=state["user_message"],
            history=state.get("history") or [],
            employee_primary_skill=emp.get("primary_skill"),
        )
    except Exception as e:
        print(f"[orchestrator.detect_skill] {e}")
        skill = None
    return {"triggered_skill": skill}


async def node_update_slots(state: ConversationState) -> dict:
    """スロット更新 (rule + Instructor)。"""
    thread_id = state.get("thread_id")
    history = state.get("history") or []
    if not thread_id or len(history) < 1:
        return {}
    try:
        from services import slot_state as ss
        provider = state.get("provider", "ollama")
        model = state.get("model", "qwen2.5:7b")
        hp = state.get("helper_provider") or (
            "openai" if os.environ.get("OPENAI_API_KEY") else provider
        )
        hm = state.get("helper_model") or (
            "gpt-4o-mini" if hp == "openai" else model
        )
        await ss.update_slots_from_message(
            thread_id=thread_id,
            user_message=state["user_message"],
            history=history,
            helper_provider=hp,
            helper_model=hm,
        )
    except Exception as e:
        print(f"[orchestrator.update_slots] {e}")
    return {}


async def node_build_rag(state: ConversationState) -> dict:
    """RAG コンテキスト + スロット + サマリを統合した instructions 末尾を作る。"""
    rag_text = ""
    slot_text = ""
    summary_text = ""

    # RAG
    try:
        from services.rag_context import build_context, format_for_prompt
        ctx = await build_context(
            message=state["user_message"],
            thread_id=state.get("thread_id"),
            employee_id=state["employee_id"],
            mode=state.get("mode", "chat"),
        )
        rag_text = format_for_prompt(ctx, mode=state.get("mode", "chat"))
    except Exception as e:
        print(f"[orchestrator.build_rag] rag {e}")

    # Slot 整形
    if state.get("thread_id"):
        try:
            from services import slot_state as ss
            slots = await ss.get_slots(state["thread_id"])
            slot_text = ss.format_for_prompt(slots)
        except Exception as e:
            print(f"[orchestrator.build_rag] slot {e}")

    # Summary
    history = state.get("history") or []
    if len(history) >= 2:
        try:
            from services.conversation_summarizer import (
                generate_summary, format_for_prompt as fmt_summary,
            )
            summary = await generate_summary(
                history=history,
                main_provider=state.get("provider", "ollama"),
                main_model=state.get("model", "qwen2.5:7b"),
                helper_provider=state.get("helper_provider"),
                helper_model=state.get("helper_model"),
            )
            summary_text = fmt_summary(summary)
        except Exception as e:
            print(f"[orchestrator.build_rag] summary {e}")

    combined_parts = [t for t in [rag_text, slot_text, summary_text] if t]
    return {
        "rag_text": "\n\n".join(combined_parts),
        "slot_text": slot_text,
        "summary_text": summary_text,
    }


async def node_long_term_memory(state: ConversationState) -> dict:
    """Phase 4: Mem0 から関連記憶を取得して rag_text に追加。"""
    if os.environ.get("USE_MEM0", "0") != "1":
        return {}
    try:
        from services.long_term_memory import search_relevant_memories
        memories = await search_relevant_memories(
            user_id="masato",  # 単一ユーザー前提
            query=state["user_message"],
            limit=5,
        )
        if memories:
            mem_block = "\n\n【長期記憶 (Mem0)】\n" + "\n".join(
                f"- {m}" for m in memories
            )
            return {"rag_text": (state.get("rag_text") or "") + mem_block}
    except Exception as e:
        print(f"[orchestrator.long_term_memory] {e}")
    return {}


# ──────────────────────────────────────────
# 公開 API: 前処理を実行して State を返す
# ──────────────────────────────────────────

async def prepare_state(
    thread_id: Optional[int],
    employee_id: int,
    user_message: str,
    history: Optional[list[dict]],
    provider: str = "ollama",
    model: str = "qwen2.5:7b",
    helper_provider: Optional[str] = None,
    helper_model: Optional[str] = None,
) -> dict:
    """Sequential async pipeline で前処理を実行し、agent 実行に必要な状態を返す。

    返り値:
      {
        "employee": dict,
        "mode": str,
        "triggered_skill": Optional[str],
        "rag_text": str,
      }
    """
    state: ConversationState = {
        "thread_id": thread_id or 0,
        "employee_id": employee_id,
        "user_message": user_message,
        "history": history or [],
        "provider": provider,
        "model": model,
        "helper_provider": helper_provider,
        "helper_model": helper_model,
    }

    try:
        from services import observability as obs
        ctx = obs.trace(
            "conversation",
            session_id=str(thread_id) if thread_id else None,
            metadata={"employee_id": employee_id},
        )
    except Exception:
        ctx = None

    async def _run() -> None:
        state.update(await node_load_employee(state))
        await node_update_profile(state)
        state.update(await node_detect_mode(state))
        state.update(await node_detect_skill(state))
        await node_update_slots(state)
        state.update(await node_build_rag(state))
        state.update(await node_long_term_memory(state))

    if ctx is not None:
        with ctx:
            await _run()
    else:
        await _run()

    return {
        "employee": state.get("employee", {}),
        "mode": state.get("mode", "chat"),
        "triggered_skill": state.get("triggered_skill"),
        "rag_text": state.get("rag_text", ""),
    }
