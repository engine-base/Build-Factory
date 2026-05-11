"""T-AI-07: claude-agent-sdk → WebSocket bridge.

CLAUDE.md §3 必須 8 項目 #7。 ClaudeAgentRunner (T-S0-08) が emit するメッセージを
WebSocket 経由でフロントエンドに転送し、 切断時は 30s buffer + replay する。

## AC マッピング

- **EVENT-1**: token forward < 50ms (in-memory queue / no extra hop)
- **EVENT-2**: tool_use → 構造化 ws message + session_logs append
- **STATE**:  disconnect 中も 30s buffer (再接続で replay)
- **OPTIONAL**: seq_id 指定 replay (session_logs から)
- **UNWANTED**: buffer > 1MB → drop oldest (低優先度) / tool_use と final は保持 / buffer_overflow event

## メッセージ形式

  {"type": "token", "seq": int, "text": str}
  {"type": "tool_use", "seq": int, "tool": str, "input": dict}
  {"type": "result", "seq": int, "stop_reason": str, "usage": dict}
  {"type": "system", "seq": int, "data": dict}
  {"type": "buffer_overflow", "seq": int, "dropped": int}

## 公開 API

- StreamBridge: process-wide シングルトン
    .subscribe(session_id) -> SubscribedQueue
    .unsubscribe(session_id, queue)
    .publish(session_id, msg)       # 低優先度 (token)
    .publish_priority(session_id, msg)  # 優先度 (tool_use / result)
    .replay_since(session_id, seq_id) -> list[msg]
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional


# 優先度メッセージ (drop されない)
PRIORITY_TYPES = {"tool_use", "result", "buffer_overflow", "system_critical"}

# 1 session あたりの buffer 上限 (T-AI-07 AC-UNWANTED)
DEFAULT_BUFFER_BYTES = 1024 * 1024  # 1MB

# disconnect 後の保持時間 (再接続 replay 用)
DISCONNECT_RETAIN_SECONDS = 30.0


@dataclass
class BufferedMessage:
    seq: int
    type: str
    payload: dict[str, Any]
    bytes_size: int
    timestamp: float = field(default_factory=time.monotonic)

    def to_ws_dict(self) -> dict[str, Any]:
        d = {"type": self.type, "seq": self.seq}
        d.update(self.payload)
        return d


@dataclass
class _SessionState:
    """1 session ごとの subscriber + buffer."""

    subscribers: list[asyncio.Queue] = field(default_factory=list)
    buffer: deque[BufferedMessage] = field(default_factory=deque)
    buffer_bytes: int = 0
    next_seq: int = 1
    last_disconnect_at: Optional[float] = None
    dropped_total: int = 0


class StreamBridge:
    """Process-wide WebSocket bridge for claude-agent-sdk streams."""

    def __init__(
        self,
        *,
        buffer_bytes_limit: int = DEFAULT_BUFFER_BYTES,
        disconnect_retain_sec: float = DISCONNECT_RETAIN_SECONDS,
    ) -> None:
        self._sessions: dict[int, _SessionState] = {}
        self._lock = asyncio.Lock()
        self.buffer_bytes_limit = buffer_bytes_limit
        self.disconnect_retain_sec = disconnect_retain_sec

    # ─── subscribe / unsubscribe ─────────────────────────────────────

    async def subscribe(
        self,
        session_id: int,
        *,
        since_seq: Optional[int] = None,
    ) -> asyncio.Queue:
        """ws connection ごとに queue を割り当てる。

        since_seq が指定された場合、 buffer 内の seq > since_seq を最初に流す
        (AC-OPTIONAL: replay)。
        """
        async with self._lock:
            st = self._sessions.setdefault(session_id, _SessionState())
            q: asyncio.Queue = asyncio.Queue(maxsize=0)
            st.subscribers.append(q)
            # replay (AC-OPTIONAL): since_seq の後のメッセージを buffer から流す
            if since_seq is not None:
                for m in st.buffer:
                    if m.seq > since_seq:
                        q.put_nowait(m.to_ws_dict())
            elif st.last_disconnect_at is not None:
                # AC-STATE: 再接続時は buffer 全件 replay (disconnect 中の取りこぼし)
                for m in st.buffer:
                    q.put_nowait(m.to_ws_dict())
            st.last_disconnect_at = None
        return q

    async def unsubscribe(self, session_id: int, q: asyncio.Queue) -> None:
        async with self._lock:
            st = self._sessions.get(session_id)
            if st is None:
                return
            if q in st.subscribers:
                st.subscribers.remove(q)
            if not st.subscribers:
                st.last_disconnect_at = time.monotonic()

    # ─── publish ───────────────────────────────────────────────────────

    async def publish(self, session_id: int, msg_type: str, payload: dict[str, Any]) -> int:
        """通常メッセージを publish (低優先度、 buffer overflow で drop 対象)。"""
        return await self._publish_internal(session_id, msg_type, payload)

    async def publish_priority(self, session_id: int, msg_type: str, payload: dict[str, Any]) -> int:
        """優先度メッセージ (tool_use / result) を publish。

        buffer overflow 時も drop されない。
        """
        return await self._publish_internal(session_id, msg_type, payload)

    async def _publish_internal(
        self, session_id: int, msg_type: str, payload: dict[str, Any],
    ) -> int:
        size = _estimate_size(msg_type, payload)
        async with self._lock:
            st = self._sessions.setdefault(session_id, _SessionState())
            seq = st.next_seq
            st.next_seq += 1
            buffered = BufferedMessage(seq=seq, type=msg_type, payload=payload, bytes_size=size)
            st.buffer.append(buffered)
            st.buffer_bytes += size

            # AC-UNWANTED: 1MB 超 → 古い非優先メッセージから drop
            await self._enforce_buffer_limit(session_id, st)

        # 全 subscriber に push
        dict_msg = buffered.to_ws_dict()
        for q in list(st.subscribers):
            try:
                q.put_nowait(dict_msg)
            except asyncio.QueueFull:
                pass  # subscriber 側 backpressure (本来 maxsize=0 で起きない)

        # session_logs にも append (AC-EVENT-2 / AC-OPTIONAL replay 用)
        try:
            await _append_session_log(session_id, seq, msg_type, payload)
        except Exception:
            pass  # DB 不在環境でも WS は動かす

        return seq

    async def _enforce_buffer_limit(self, session_id: int, st: _SessionState) -> None:
        if st.buffer_bytes <= self.buffer_bytes_limit:
            return

        dropped = 0
        dropped_bytes = 0
        # 古い順に scan して 非 PRIORITY を drop
        keep: deque[BufferedMessage] = deque()
        for m in st.buffer:
            if st.buffer_bytes <= self.buffer_bytes_limit:
                # 限界以下に戻ったので残り全部 keep
                keep.append(m)
                continue
            if m.type in PRIORITY_TYPES:
                keep.append(m)
                continue
            # drop
            dropped += 1
            dropped_bytes += m.bytes_size
            st.buffer_bytes -= m.bytes_size
        st.buffer = keep
        st.dropped_total += dropped

        if dropped > 0:
            # buffer_overflow event を新規に publish (再帰回避のため直接 append)
            seq = st.next_seq
            st.next_seq += 1
            overflow_msg = BufferedMessage(
                seq=seq, type="buffer_overflow",
                payload={"dropped": dropped, "bytes": dropped_bytes,
                         "session_dropped_total": st.dropped_total},
                bytes_size=64,
            )
            st.buffer.append(overflow_msg)
            st.buffer_bytes += 64
            # 全 subscriber に通知
            for q in list(st.subscribers):
                try:
                    q.put_nowait(overflow_msg.to_ws_dict())
                except Exception:
                    pass

    # ─── replay (AC-OPTIONAL) ─────────────────────────────────────────

    async def replay_since(self, session_id: int, seq_id: int) -> list[dict[str, Any]]:
        """seq_id より後のメッセージを buffer から返す。

        DB の session_logs にもフォールバック (buffer から消えた古いメッセージ用)。
        """
        async with self._lock:
            st = self._sessions.get(session_id)
            if st is None:
                buf_msgs: list[dict[str, Any]] = []
            else:
                buf_msgs = [m.to_ws_dict() for m in st.buffer if m.seq > seq_id]

        # buffer に存在しない古い seq_id は DB から拾う (best effort)
        try:
            db_msgs = await _replay_from_session_logs(session_id, seq_id)
            # buffer に含まれる seq は除外
            buf_seqs = {m["seq"] for m in buf_msgs}
            for d in db_msgs:
                if d["seq"] not in buf_seqs:
                    buf_msgs.append(d)
        except Exception:
            pass

        buf_msgs.sort(key=lambda m: m["seq"])
        return buf_msgs

    # ─── housekeeping ─────────────────────────────────────────────────

    async def cleanup_expired(self) -> int:
        """30s 経過した disconnect-only session の buffer を解放."""
        now = time.monotonic()
        async with self._lock:
            expired = [
                sid for sid, st in self._sessions.items()
                if not st.subscribers
                and st.last_disconnect_at is not None
                and (now - st.last_disconnect_at) > self.disconnect_retain_sec
            ]
            for sid in expired:
                del self._sessions[sid]
        return len(expired)


# ── module-level singleton ──

_default_bridge: Optional[StreamBridge] = None


def get_bridge() -> StreamBridge:
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = StreamBridge()
    return _default_bridge


def reset_bridge() -> None:
    """テスト用: bridge を初期化."""
    global _default_bridge
    _default_bridge = None


# ── helpers ──

def _estimate_size(msg_type: str, payload: dict[str, Any]) -> int:
    try:
        return len(json.dumps({"type": msg_type, **payload}, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return 128  # fallback


async def _append_session_log(session_id: int, seq: int, msg_type: str, payload: dict[str, Any]) -> None:
    """session_logs テーブルに 1 行 append (AC-EVENT-2)."""
    try:
        from db import async_db as adb
        from db.queries import DB_PATH
    except Exception:
        return
    content = json.dumps({"type": msg_type, "seq": seq, **payload}, ensure_ascii=False)
    stream = "stderr" if msg_type == "buffer_overflow" else "stdout"
    async with adb.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO session_logs (session_id, line_no, stream, content)
               VALUES (?, ?, ?, ?)""",
            (session_id, seq, stream, content),
        )
        await db.commit()


async def _replay_from_session_logs(session_id: int, seq_id: int) -> list[dict[str, Any]]:
    """DB session_logs から seq_id より後を取得 (replay backup)."""
    try:
        from db import async_db as adb
        from db.queries import DB_PATH
    except Exception:
        return []
    async with adb.connect(DB_PATH) as db:
        db.row_factory = adb.Row
        cur = await db.execute(
            """SELECT line_no, content FROM session_logs
               WHERE session_id = ? AND line_no > ?
               ORDER BY line_no ASC LIMIT 500""",
            (session_id, seq_id),
        )
        rows = await cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            parsed = json.loads(d.get("content") or "{}")
        except Exception:
            parsed = {"type": "system", "raw": d.get("content")}
        if "seq" not in parsed:
            parsed["seq"] = int(d.get("line_no") or 0)
        out.append(parsed)
    return out
