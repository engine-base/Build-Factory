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
        audit_hook: Optional["AuditHook"] = None,
        cache_ttl_seconds: int = 300,  # 5min ephemeral (AC-4)
        compaction_threshold: float = 0.95,  # 95% (AC-5)
    ) -> None:
        self.store = store or InMemorySessionStore()
        self.cost_hook = cost_hook or NoopCostHook()
        self.summary_hook = summary_hook or NoopSummaryHook()
        self.audit_hook = audit_hook or NoopAuditHook()
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

        # T-S0-09 AC-5: SandboxViolation を区別して記録するため遅延 import
        try:
            from sandbox import SandboxViolation as _SandboxViolation
        except Exception:  # noqa: BLE001 — sandbox module 未配備でも runner は動く
            _SandboxViolation = None  # type: ignore[assignment]

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
            # T-S0-09 AC-5: sandbox 違反は専用 crash_reason + audit_log エントリを残す
            if _SandboxViolation is not None and isinstance(e, _SandboxViolation):
                record.crash_reason = "sandbox_violation"
                await self.audit_hook.record(
                    AuditEvent(
                        workspace_id=workspace_id,
                        actor_persona=agent_persona,
                        action="sandbox.violation",
                        resource_type="session",
                        resource_id=record.id,
                        payload={
                            "reason": getattr(e, "reason", "unknown"),
                            "returncode": getattr(getattr(e, "result", None), "returncode", None),
                        },
                        success=False,
                    )
                )
            else:
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


# ─────────────────────────────────────────────────────────────────────────────
# AuditHook (T-S0-09 AC-5: sandbox.violation を audit_logs に記録する経路)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AuditEvent:
    """audit_logs テーブル行に対応する DTO (T-S0-09 AC-5)."""

    action: str
    workspace_id: Optional[int] = None
    actor_user_id: Optional[str] = None
    actor_persona: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    payload: dict[str, Any] = field(default_factory=dict)
    success: bool = True


class AuditHook:
    """audit_logs への記録抽象."""

    async def record(self, event: AuditEvent) -> None: raise NotImplementedError


class NoopAuditHook(AuditHook):
    async def record(self, event: AuditEvent) -> None:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed implementations (psycopg via db.async_db)
# 生 SQL ベース。本番 DB では DbSessionStore / DbCostHook / DbSummaryHook を
# 注入し、テスト時は InMemorySessionStore / NoopCostHook / NoopSummaryHook を使う。
# ─────────────────────────────────────────────────────────────────────────────


class DbSessionStore(SessionStore):
    """sessions / session_logs を psycopg 経由で永続化 (T-S0-08 AC-3)."""

    def __init__(self) -> None:
        # connect() は呼び出し時に解決 (env 未設定環境で import が壊れないよう遅延)
        from db.async_db import connect  # noqa: F401

    async def create_session(self, rec: SessionRecord) -> SessionRecord:
        from db.async_db import connect

        async with connect() as db:
            cur = await db.execute(
                """
                INSERT INTO sessions
                  (sdk_session_id, workspace_id, project_id, bf_task_id,
                   agent_persona, skill_name, prompt, status, started_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW(), ?::jsonb)
                RETURNING id
                """,
                (
                    rec.sdk_session_id or f"pending_{int(time.time() * 1000)}",
                    rec.workspace_id,
                    rec.project_id,
                    rec.bf_task_id,
                    rec.agent_persona,
                    rec.skill_name,
                    rec.prompt,
                    rec.status,
                    _json_dumps(rec.metadata),
                ),
            )
            row = await cur.fetchone()
            await db.commit()
            rec.id = int(row["id"])
        return rec

    async def update_sdk_session_id(self, session_id: int, sdk_id: str) -> None:
        from db.async_db import connect

        async with connect() as db:
            await db.execute(
                "UPDATE sessions SET sdk_session_id = ? WHERE id = ?",
                (sdk_id, session_id),
            )
            await db.commit()

    async def append_log(self, session_id: int, content: str) -> None:
        from db.async_db import connect

        async with connect() as db:
            cur = await db.execute(
                "SELECT COALESCE(MAX(line_no), 0) AS n FROM session_logs WHERE session_id = ?",
                (session_id,),
            )
            row = await cur.fetchone()
            next_line = int(row["n"]) + 1
            stream = "stderr" if content.startswith("[stderr]") else "stdout"
            await db.execute(
                """
                INSERT INTO session_logs (session_id, line_no, stream, content)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, next_line, stream, content),
            )
            await db.commit()

    async def finalize_session(self, rec: SessionRecord) -> None:
        from db.async_db import connect

        async with connect() as db:
            await db.execute(
                """
                UPDATE sessions
                   SET status = ?,
                       resume_choice = ?,
                       crash_reason = ?,
                       completed_at = NOW()
                 WHERE id = ?
                """,
                (rec.status, rec.resume_choice, rec.crash_reason, rec.id),
            )
            await db.commit()

    async def get_session(self, session_id: int) -> Optional[SessionRecord]:
        from db.async_db import connect

        async with connect() as db:
            cur = await db.execute(
                """
                SELECT id, sdk_session_id, workspace_id, project_id, bf_task_id,
                       agent_persona, skill_name, prompt, status, resume_choice,
                       crash_reason
                  FROM sessions WHERE id = ?
                """,
                (session_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return SessionRecord(
            id=int(row["id"]),
            sdk_session_id=row["sdk_session_id"] or "",
            workspace_id=row["workspace_id"],
            project_id=row["project_id"],
            bf_task_id=row["bf_task_id"],
            agent_persona=row["agent_persona"],
            skill_name=row["skill_name"],
            prompt=row["prompt"],
            status=row["status"],
            resume_choice=row["resume_choice"],
            crash_reason=row["crash_reason"],
        )


class DbCostHook(CostHook):
    """cost_logs に Anthropic Usage を psycopg 経由で記録 (T-S0-08 AC-4)."""

    async def record(self, cost: CostRecord) -> None:
        from db.async_db import connect

        async with connect() as db:
            await db.execute(
                """
                INSERT INTO cost_logs
                  (session_id, workspace_id, provider, model,
                   input_tokens, output_tokens,
                   cache_read_tokens, cache_write_tokens, cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cost.session_id,
                    cost.workspace_id,
                    cost.provider,
                    cost.model,
                    cost.input_tokens,
                    cost.output_tokens,
                    cost.cache_read_tokens,
                    cost.cache_write_tokens,
                    cost.cost_usd,
                ),
            )
            await db.commit()


class DbSummaryHook(SummaryHook):
    """chat_messages.compressed_summary に 9-section structured summary を記録 (T-S0-08 AC-5)."""

    async def persist(self, thread_id: int, summary: dict[str, Any]) -> None:
        from db.async_db import connect

        async with connect() as db:
            await db.execute(
                """
                INSERT INTO chat_messages (thread_id, role, content, compressed_summary)
                VALUES (?, 'system', '[auto-compaction summary]', ?::jsonb)
                """,
                (thread_id, _json_dumps(summary)),
            )
            await db.commit()


class DbAuditHook(AuditHook):
    """audit_logs に sandbox.violation 等を psycopg 経由で記録 (T-S0-09 AC-5)."""

    async def record(self, event: AuditEvent) -> None:
        from db.async_db import connect

        async with connect() as db:
            await db.execute(
                """
                INSERT INTO audit_logs
                  (workspace_id, actor_user_id, actor_persona,
                   action, resource_type, resource_id, payload, success)
                VALUES (?, ?, ?, ?, ?, ?, ?::jsonb, ?)
                """,
                (
                    event.workspace_id,
                    event.actor_user_id,
                    event.actor_persona,
                    event.action,
                    event.resource_type,
                    event.resource_id,
                    _json_dumps(event.payload),
                    event.success,
                ),
            )
            await db.commit()


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value or {}, ensure_ascii=False)
