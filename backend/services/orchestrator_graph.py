"""
orchestrator_graph.py — Phase 3: LangGraph で会話オーケストレーション

設計方針:
  - 状態管理（mode / profile / slots / rag / skill）を LangGraph の StateGraph で明示化
  - LLM 実行（Runner.run_streamed）は既存の OpenAI Agents SDK を使用（streaming 維持）
  - Checkpointer (SqliteSaver) で thread_id ごとの状態を自動永続化
  - Langfuse で各ノード遷移を観測

エントリポイント:
  prepare_state(thread_id, employee_id, user_message, history, ...)
    → ConversationState（前処理完了済み）

  → このあと secretary_agent.build_agent_for_employee + Runner.run_streamed で実行
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, TypedDict

# ──────────────────────────────────────────
# State 定義
# ──────────────────────────────────────────

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

    # 最終 instructions（agent に渡される完成プロンプト）
    instructions: str


# ──────────────────────────────────────────
# ノード関数（各々が State を部分更新して返す）
# ──────────────────────────────────────────

async def node_load_employee(state: ConversationState) -> dict:
    """社員情報を読み込む。"""
    import aiosqlite
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
    """ユーザープロファイル更新（バックグラウンド・致命的でない）"""
    try:
        from services.user_profile import update_from_message
        await update_from_message(state["user_message"])
    except Exception as e:
        print(f"[graph.update_profile] {e}")
    return {}


async def node_detect_mode(state: ConversationState) -> dict:
    """雑談 / タスク判別。"""
    try:
        from services.mode_detector import detect_mode
        mode = await detect_mode(state["user_message"], state.get("history") or [])
    except Exception as e:
        print(f"[graph.detect_mode] {e}")
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
        print(f"[graph.detect_skill] {e}")
        skill = None
    return {"triggered_skill": skill}


async def node_update_slots(state: ConversationState) -> dict:
    """スロット更新（rule + Instructor）。"""
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
        print(f"[graph.update_slots] {e}")
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
        print(f"[graph.build_rag] rag {e}")

    # Slot 整形
    if state.get("thread_id"):
        try:
            from services import slot_state as ss
            slots = await ss.get_slots(state["thread_id"])
            slot_text = ss.format_for_prompt(slots)
        except Exception as e:
            print(f"[graph.build_rag] slot {e}")

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
            print(f"[graph.build_rag] summary {e}")

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
            mem_block = "\n\n【長期記憶（Mem0）】\n" + "\n".join(
                f"- {m}" for m in memories
            )
            return {"rag_text": (state.get("rag_text") or "") + mem_block}
    except Exception as e:
        print(f"[graph.long_term_memory] {e}")
    return {}


# ──────────────────────────────────────────
# Graph 構築
# ──────────────────────────────────────────

_GRAPH: Any = None
_CHECKPOINTER_CTX: Any = None       # AsyncSqliteSaver async context manager
_CHECKPOINTER: Any = None           # 取得済み saver
_GRAPH_WITH_CKPT: Any = None        # checkpointer 付き compile 済み graph


def get_graph():
    """LangGraph をシングルトンで構築（初回のみ）。

    Checkpointer 統合方針:
      - 既存の company.db (SQLite) に同居（langgraph_* テーブルを追加するだけ）
      - 別ファイルにしない（運用上1ファイルで完結）
      - schema 衝突は無し（langgraph 側は `checkpoints` / `writes` テーブル等を使う）
    """
    global _GRAPH
    if _GRAPH is not None:
        return _GRAPH

    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        print("[graph] langgraph 未インストール")
        return None

    workflow = StateGraph(ConversationState)
    workflow.add_node("load_employee", node_load_employee)
    workflow.add_node("update_profile", node_update_profile)
    workflow.add_node("detect_mode", node_detect_mode)
    workflow.add_node("detect_skill", node_detect_skill)
    workflow.add_node("update_slots", node_update_slots)
    workflow.add_node("build_rag", node_build_rag)
    workflow.add_node("long_term_memory", node_long_term_memory)

    workflow.set_entry_point("load_employee")
    workflow.add_edge("load_employee", "update_profile")
    workflow.add_edge("update_profile", "detect_mode")
    workflow.add_edge("detect_mode", "detect_skill")
    workflow.add_edge("detect_skill", "update_slots")
    workflow.add_edge("update_slots", "build_rag")
    workflow.add_edge("build_rag", "long_term_memory")
    workflow.add_edge("long_term_memory", END)

    _GRAPH = workflow.compile()
    return _GRAPH


async def _get_checkpointed_graph():
    """company.db に同居する checkpointer 付き graph を返す（async 専用）。"""
    global _CHECKPOINTER_CTX, _CHECKPOINTER, _GRAPH_WITH_CKPT
    if _GRAPH_WITH_CKPT is not None:
        return _GRAPH_WITH_CKPT
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from db.queries import DB_PATH
        # AsyncSqliteSaver は async context manager を返す（with 用途）。
        # シングルトン的に使うため __aenter__ を直接呼んで保持する。
        _CHECKPOINTER_CTX = AsyncSqliteSaver.from_conn_string(str(DB_PATH))
        _CHECKPOINTER = await _CHECKPOINTER_CTX.__aenter__()
    except Exception as e:
        print(f"[graph] checkpointer 初期化失敗（checkpointなしで動作）: {e}")
        return get_graph()

    g = get_graph()
    if g is None:
        return None
    # 同じ workflow を再 compile しても良いが、graph._compile を上書きできるなら回避
    try:
        from langgraph.graph import StateGraph, END
        workflow = StateGraph(ConversationState)
        workflow.add_node("load_employee", node_load_employee)
        workflow.add_node("update_profile", node_update_profile)
        workflow.add_node("detect_mode", node_detect_mode)
        workflow.add_node("detect_skill", node_detect_skill)
        workflow.add_node("update_slots", node_update_slots)
        workflow.add_node("build_rag", node_build_rag)
        workflow.add_node("long_term_memory", node_long_term_memory)
        workflow.set_entry_point("load_employee")
        workflow.add_edge("load_employee", "update_profile")
        workflow.add_edge("update_profile", "detect_mode")
        workflow.add_edge("detect_mode", "detect_skill")
        workflow.add_edge("detect_skill", "update_slots")
        workflow.add_edge("update_slots", "build_rag")
        workflow.add_edge("build_rag", "long_term_memory")
        workflow.add_edge("long_term_memory", END)
        _GRAPH_WITH_CKPT = workflow.compile(checkpointer=_CHECKPOINTER)
    except Exception as e:
        print(f"[graph] checkpoint compile 失敗・通常 graph 利用: {e}")
        _GRAPH_WITH_CKPT = g
    return _GRAPH_WITH_CKPT


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
    """LangGraph で前処理を実行し、agent 実行に必要な状態を返す。

    返り値:
      {
        "employee": dict,
        "mode": str,
        "triggered_skill": Optional[str],
        "rag_text": str,
      }
    """
    # checkpointer 付き graph を優先（thread_id がある時）。失敗時は素の graph
    graph = None
    if thread_id:
        try:
            graph = await _get_checkpointed_graph()
        except Exception as e:
            print(f"[graph.prepare_state] checkpointed graph 失敗: {e}")
    if graph is None:
        graph = get_graph()
    if graph is None:
        return await _prepare_state_fallback(
            thread_id, employee_id, user_message, history,
            provider, model, helper_provider, helper_model,
        )

    initial: ConversationState = {
        "thread_id": thread_id or 0,
        "employee_id": employee_id,
        "user_message": user_message,
        "history": history or [],
        "provider": provider,
        "model": model,
        "helper_provider": helper_provider,
        "helper_model": helper_model,
    }

    # checkpointer を使う場合は thread_id を config として渡す
    invoke_config = (
        {"configurable": {"thread_id": str(thread_id)}} if thread_id else None
    )

    try:
        from services import observability as obs
        with obs.trace("conversation",
                       session_id=str(thread_id) if thread_id else None,
                       metadata={"employee_id": employee_id}):
            if invoke_config:
                result = await graph.ainvoke(initial, config=invoke_config)
            else:
                result = await graph.ainvoke(initial)
    except Exception as e:
        print(f"[graph.prepare_state] {e}・フォールバックへ")
        return await _prepare_state_fallback(
            thread_id, employee_id, user_message, history,
            provider, model, helper_provider, helper_model,
        )

    return {
        "employee": result.get("employee", {}),
        "mode": result.get("mode", "chat"),
        "triggered_skill": result.get("triggered_skill"),
        "rag_text": result.get("rag_text", ""),
    }


async def _prepare_state_fallback(
    thread_id, employee_id, user_message, history,
    provider, model, helper_provider, helper_model,
) -> dict:
    """LangGraph 無しでも動く互換実装（旧 stream_as_employee 相当）。"""
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
    state.update(await node_load_employee(state))
    await node_update_profile(state)
    state.update(await node_detect_mode(state))
    state.update(await node_detect_skill(state))
    await node_update_slots(state)
    state.update(await node_build_rag(state))
    state.update(await node_long_term_memory(state))
    return {
        "employee": state.get("employee", {}),
        "mode": state.get("mode", "chat"),
        "triggered_skill": state.get("triggered_skill"),
        "rag_text": state.get("rag_text", ""),
    }
