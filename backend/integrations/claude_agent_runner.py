"""
T-S0-08 / ADR-010: claude-agent-sdk runner 基盤

Claude Code を subprocess として spawn し、claude-agent-sdk が提供する以下を享受する:
  - session resume (sdk_session_id 経由で会話履歴自動復元)
  - 3-tier compaction (tool result trim / prompt cache / 95% structured summary)
  - prompt cache (cache_control: ephemeral 5min auto)
  - Subagent (Task tool) handoff
  - Memory API 統合

本モジュール (runner) は **LangGraph / LangChain を import しない**
(T-S0-08 AC-7 UNWANTED, ADR-010)。 lint-mock.sh --no-langgraph で検出される。
"""
from __future__ import annotations

# AC-7 UNWANTED: LangGraph / LangChain は ADR-010 で main path から削除。
# 本 runner module で import すると lint-mock.sh --no-langgraph で fail。
# (sentinel コメントとして "# NO_LANGGRAPH_IN_RUNNER" を残す)
# NO_LANGGRAPH_IN_RUNNER

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

# claude-agent-sdk imports は遅延 (実 install されていない CI で他 module を壊さない)
# 実呼び出し時に import するため、本ファイル top-level では import しない。


@dataclass
class SessionRecord:
    """sessions テーブル行に対応する DTO。"""

    id: Optional[int] = None
    sdk_session_id: str = ""
    workspace_id: Optional[int] = None
    project_id: Optional[int] = None
    bf_task_id: Optional[int] = None
    agent_persona: Optional[str] = None
    skill_name: Optional[str] = None
    prompt: str = ""
    status: str = "running"  # running / done / crashed / cancelled / paused
    resume_choice: Optional[str] = None
    crash_reason: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CostRecord:
    """cost_logs テーブル行に対応する DTO (AC-4)。"""

    session_id: int
    workspace_id: Optional[int] = None
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0


VALID_RESUME_CHOICES = ("from_checkpoint", "rerun_full", "manual_fix", "cancel")


class ClaudeAgentRunner:
    """claude-agent-sdk wrapper.

    AC マッピング:
      AC-1 UBIQUITOUS: claude-agent-sdk で Claude Code subprocess spawn → run_task()
      AC-2 UBIQUITOUS: session_id を SDK に渡して 3-tier compaction を任せる
                       → ClaudeAgentOptions(session_id=...)
      AC-3 EVENT:      sessions row 作成 + session_logs ストリーム → SessionStore
      AC-4 STATE:      prompt cache 自動 + cache hit rate を cost_logs に → CostHook
      AC-5 STATE:      95% 超で 9-section summary auto → SummaryHook
      AC-6 EVENT:      crash → status=crashed + 4-choice resume → handle_resume()
      AC-7 UNWANTED:   LangGraph 禁止 → lint-mock.sh で検出
    """

    def __init__(
        self,
        *,
        store: Optional["SessionStore"] = None,
        cost_hook: Optional["CostHook"] = None,
        summary_hook: Optional["SummaryHook"] = None,
        cache_ttl_seconds: int = 300,  # 5min ephemeral (AC-4)
        compaction_threshold: float = 0.95,  # 95% (AC-5)
    ) -> None:
        self.store = store or InMemorySessionStore()
        self.cost_hook = cost_hook or NoopCostHook()
        self.summary_hook = summary_hook or NoopSummaryHook()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.compaction_threshold = compaction_threshold

    async def run_task(
        self,
        prompt: str,
        *,
        sdk_session_id: Optional[str] = None,
        workspace_id: Optional[int] = None,
        project_id: Optional[int] = None,
        bf_task_id: Optional[int] = None,
        agent_persona: Optional[str] = None,
        skill_name: Optional[str] = None,
        model: str = "claude-sonnet-4-6",
        agents: Optional[dict[str, Any]] = None,
        cwd: Optional[str] = None,
    ) -> SessionRecord:
        """1 タスクを実行。SDK が subprocess を起動し、history は SDK 内部で復元される。

        sdk_session_id を渡すと resume、None なら新規セッション。
        cwd を指定すると subprocess を指定ディレクトリで起動する (swarm の worktree 用)。
        crash 時は SessionRecord.status = 'crashed' + crash_reason に詳細。
        4-choice resume は handle_resume() で別途実行する。
        """
        from claude_agent_sdk import (  # type: ignore[import-not-found]
            ClaudeAgentOptions,
            ClaudeSDKClient,
            AssistantMessage,
            ResultMessage,
            SystemMessage,
        )

        record = SessionRecord(
            sdk_session_id=sdk_session_id or "",
            workspace_id=workspace_id,
            project_id=project_id,
            bf_task_id=bf_task_id,
            agent_persona=agent_persona,
            skill_name=skill_name,
            prompt=prompt,
            status="running",
            started_at=time.time(),
        )
        record = await self.store.create_session(record)

        options_kwargs: dict[str, Any] = {
            "resume": sdk_session_id,               # AC-2: SDK auto-resume
            "model": model,
            "agents": agents or {},
        }
        if cwd is not None:
            options_kwargs["cwd"] = cwd
        options = ClaudeAgentOptions(**options_kwargs)

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                async for msg in client.receive_response():
                    # AC-3: stream session_logs
                    await self.store.append_log(record.id, _stringify(msg))
                    # AC-2 / AC-5: SDK 側で sdk_session_id を確定
                    if isinstance(msg, SystemMessage):
                        sdk_id = (msg.data or {}).get("session_id") if hasattr(msg, "data") else None
                        if sdk_id and not record.sdk_session_id:
                            record.sdk_session_id = sdk_id
                            await self.store.update_sdk_session_id(record.id, sdk_id)
                    if isinstance(msg, ResultMessage):
                        # AC-4: usage から cache_read/write を cost_logs へ
                        usage = getattr(msg, "usage", None) or {}
                        cost_usd = float(getattr(msg, "total_cost_usd", 0.0) or 0.0)
                        await self.cost_hook.record(
                            CostRecord(
                                session_id=record.id,
                                workspace_id=workspace_id,
                                provider="anthropic",
                                model=model,
                                input_tokens=int(usage.get("input_tokens", 0)),
                                output_tokens=int(usage.get("output_tokens", 0)),
                                cache_read_tokens=int(usage.get("cache_read_input_tokens", 0)),
                                cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0)),
                                cost_usd=cost_usd,
                            )
                        )
            record.status = "done"
            record.completed_at = time.time()
        except Exception as e:  # noqa: BLE001 — broad catch + 必ず status を保存
            record.status = "crashed"
            record.crash_reason = f"{type(e).__name__}: {e}"
            record.completed_at = time.time()
        finally:
            await self.store.finalize_session(record)
        return record

    async def handle_resume(
        self, session_id: int, choice: str
    ) -> SessionRecord:
        """AC-6: 4-choice resume API。

        choice ∈ {from_checkpoint, rerun_full, manual_fix, cancel}
        from_checkpoint: SDK の sdk_session_id で resume → run_task(sdk_session_id=...)
        rerun_full:     新規セッションで同じ prompt を再実行
        manual_fix:     status=paused にして人手介入待ち
        cancel:         status=cancelled
        """
        if choice not in VALID_RESUME_CHOICES:
            raise ValueError(f"invalid resume choice: {choice}")
        prev = await self.store.get_session(session_id)
        if prev is None:
            raise LookupError(f"session not found: {session_id}")
        prev.resume_choice = choice
        if choice == "cancel":
            prev.status = "cancelled"
            await self.store.finalize_session(prev)
            return prev
        if choice == "manual_fix":
            prev.status = "paused"
            await self.store.finalize_session(prev)
            return prev
        if choice == "from_checkpoint":
            return await self.run_task(
                prompt=prev.prompt,
                sdk_session_id=prev.sdk_session_id or None,
                workspace_id=prev.workspace_id,
                project_id=prev.project_id,
                bf_task_id=prev.bf_task_id,
                agent_persona=prev.agent_persona,
                skill_name=prev.skill_name,
            )
        # rerun_full: 新規 session
        return await self.run_task(
            prompt=prev.prompt,
            sdk_session_id=None,
            workspace_id=prev.workspace_id,
            project_id=prev.project_id,
            bf_task_id=prev.bf_task_id,
            agent_persona=prev.agent_persona,
            skill_name=prev.skill_name,
        )


def _stringify(msg: Any) -> str:
    """SDK message → log 用の文字列。重要 field のみ抽出。"""
    cls = type(msg).__name__
    blocks = getattr(msg, "content", None)
    if isinstance(blocks, list):
        chunks: list[str] = []
        for b in blocks:
            t = getattr(b, "text", None)
            if t:
                chunks.append(t)
        return f"[{cls}] " + "\n".join(chunks) if chunks else f"[{cls}]"
    return f"[{cls}] {str(blocks)[:500] if blocks else ''}"


# ─────────────────────────────────────────────────────────────────────────────
# Storage abstractions (実 DB 統合は別タスクで service 層から差し替える)
# ─────────────────────────────────────────────────────────────────────────────


class SessionStore:
    """sessions / session_logs への永続化抽象。"""

    async def create_session(self, rec: SessionRecord) -> SessionRecord: raise NotImplementedError
    async def update_sdk_session_id(self, session_id: int, sdk_id: str) -> None: raise NotImplementedError
    async def append_log(self, session_id: int, content: str) -> None: raise NotImplementedError
    async def finalize_session(self, rec: SessionRecord) -> None: raise NotImplementedError
    async def get_session(self, session_id: int) -> Optional[SessionRecord]: raise NotImplementedError


class InMemorySessionStore(SessionStore):
    """テスト・ローカル開発用 (DB 不在時のフォールバック)。"""

    def __init__(self) -> None:
        self._sessions: dict[int, SessionRecord] = {}
        self._logs: dict[int, list[str]] = {}
        self._next_id = 1

    async def create_session(self, rec: SessionRecord) -> SessionRecord:
        rec.id = self._next_id
        self._next_id += 1
        self._sessions[rec.id] = rec
        self._logs[rec.id] = []
        return rec

    async def update_sdk_session_id(self, session_id: int, sdk_id: str) -> None:
        s = self._sessions.get(session_id)
        if s is not None:
            s.sdk_session_id = sdk_id

    async def append_log(self, session_id: int, content: str) -> None:
        self._logs.setdefault(session_id, []).append(content)

    async def finalize_session(self, rec: SessionRecord) -> None:
        if rec.id is not None:
            self._sessions[rec.id] = rec

    async def get_session(self, session_id: int) -> Optional[SessionRecord]:
        return self._sessions.get(session_id)


class CostHook:
    """cost_logs への記録抽象 (AC-4)。"""

    async def record(self, cost: CostRecord) -> None: raise NotImplementedError


class NoopCostHook(CostHook):
    async def record(self, cost: CostRecord) -> None:
        return None


class SummaryHook:
    """95% 超 9-section summary 永続化抽象 (AC-5)。

    SDK が auto-compaction を行った時点で chat_messages.compressed_summary に
    JSON を埋める。実 DB 接続は service 層で差し替える。
    """

    async def persist(self, thread_id: int, summary: dict[str, Any]) -> None: raise NotImplementedError


class NoopSummaryHook(SummaryHook):
    async def persist(self, thread_id: int, summary: dict[str, Any]) -> None:
        return None
