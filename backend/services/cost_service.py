"""T-AI-05: Cost tracking (Anthropic Usage API + LiteLLM callback で 案件/AI/日次集計).

CLAUDE.md §3 必須 8 項目 #5。 T-S0-08 で実装済みの cost_logs INSERT 経路の上に
集計 + budget enforcement + reconciliation + audit を載せる。

## AC マッピング

- UBIQUITOUS: 全 Claude API call / LiteLLM call → 1 cost_logs row
              (provider, model, in/out, cache_read/write, USD, session, workspace, ai_employee)
- EVENT:     session 完了で Anthropic Usage API と reconcile (>5% discrepancy で flag)
- STATE:     monthly cost > budget → workspace queue pause + notify
- STATE:     prompt cache hit → cache_read_tokens > 0 / displayed cost に 90% 引き反映
- UNWANTED:  cost 記録失敗 → session 継続 + cost_recording_failed audit

## ADR-012 / T-AI-MEM-04 cross-ref (provider 切替時の cost tracking)

provider_adapter_memory.resolve_active_provider() が任意切替 / 障害時 fallback で
Anthropic 以外 (OpenAI / Gemini via LiteLLM) を選択した場合, **その call も
1 row として cost_logs に記録** する (AC-UBIQUITOUS). T-M12-01 LiteLLM Router
の emergency_chat / generate_image / batch_complete 経路は内部で record_cost
を呼ぶ責任を負う.

## price table (USD per 1M tokens, 2025-2026 公開価格)

  claude-opus-4-7  :  input $15.0  output $75.0  cache_read $1.5  cache_write $18.75
  claude-sonnet-4-6:  input $3.0   output $15.0  cache_read $0.30 cache_write $3.75
  claude-haiku-4-5 :  input $0.80  output $4.00  cache_read $0.08 cache_write $1.00
  (cache_read = input × 0.10 / cache_write = input × 1.25)

## 公開 API + audit event 定数

- record_cost(...) -> int      # cost_logs INSERT + 失敗時 audit
- monthly_cost(workspace_id) -> float
- check_budget_pause(workspace_id) -> dict  # 超えてたら True + notify
- reconcile_session(session_id, anthropic_usage_total_usd) -> dict
- compute_display_cost(model, in_tok, out_tok, cache_read, cache_write) -> float
- cached_discount_ratio(in_tok, cache_read) -> float

- EVENT_COST_BUDGET_EXCEEDED       : 'cost.budget_exceeded' (spec 文に整合)
- EVENT_WORKSPACE_BUDGET_EXCEEDED  : 'workspace_budget_exceeded' (既存 alias 後方互換)
- EVENT_COST_RECORDING_FAILED      : 'cost_recording_failed' (既存)
- EVENT_RECONCILE_DISCREPANCY      : 'cost.reconcile_discrepancy' (既存)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# USD per 1M tokens — 2025-2026 Anthropic 公開価格
PRICE_TABLE: dict[str, dict[str, float]] = {
    "claude-opus-4-7": {
        "input": 15.0, "output": 75.0,
        "cache_read": 1.5, "cache_write": 18.75,
    },
    "claude-sonnet-4-6": {
        "input": 3.0, "output": 15.0,
        "cache_read": 0.30, "cache_write": 3.75,
    },
    "claude-haiku-4-5": {
        "input": 0.80, "output": 4.00,
        "cache_read": 0.08, "cache_write": 1.00,
    },
    # legacy / fallback (default rates)
    "default": {
        "input": 3.0, "output": 15.0,
        "cache_read": 0.30, "cache_write": 3.75,
    },
}

# AC-EVENT: discrepancy > 5% で flag
RECONCILE_THRESHOLD = 0.05


# T-AI-05 audit event 公開定数 (spec 文に整合 / 既存 alias 維持)
EVENT_COST_BUDGET_EXCEEDED = "cost.budget_exceeded"
EVENT_WORKSPACE_BUDGET_EXCEEDED = "workspace_budget_exceeded"  # 既存 alias (後方互換)
EVENT_COST_RECORDING_FAILED = "cost_recording_failed"
EVENT_RECONCILE_DISCREPANCY = "cost_reconcile_discrepancy"


def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


# ──────────────────────────────────────────────────────────────────────────
# Pricing
# ──────────────────────────────────────────────────────────────────────────


def compute_display_cost(
    *, model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """AC-STATE (cache): cache_read 分は 90% 引き (input rate の 10%) で計算.

    Returns:
      USD (4 decimal precision)
    """
    rate = PRICE_TABLE.get(model) or PRICE_TABLE["default"]
    per_m = 1_000_000.0
    cost = (
        rate["input"] * (input_tokens / per_m)
        + rate["output"] * (output_tokens / per_m)
        + rate["cache_read"] * (cache_read_tokens / per_m)
        + rate["cache_write"] * (cache_write_tokens / per_m)
    )
    return round(cost, 6)


def cached_discount_ratio(input_tokens: int, cache_read_tokens: int) -> float:
    """AC-STATE: cached input ratio (0.0-1.0) を返す.

    UI 表示用 "X% cached" の元値。 input が 0 なら 0.0。
    """
    if input_tokens + cache_read_tokens <= 0:
        return 0.0
    return cache_read_tokens / (input_tokens + cache_read_tokens)


# ──────────────────────────────────────────────────────────────────────────
# Record (AC-UBIQUITOUS + AC-UNWANTED)
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class CostEntry:
    session_id: Optional[int]
    workspace_id: Optional[int]
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    ai_employee_id: Optional[str] = None


async def record_cost(entry: CostEntry) -> Optional[int]:
    """AC-UBIQUITOUS: 1 call = 1 cost_logs row.

    AC-UNWANTED: INSERT 失敗時は cost_recording_failed audit を emit して None 返却.
    呼び出し元 (runner / litellm callback) は失敗を吸収して session を継続.
    """
    if entry.cost_usd <= 0 and entry.input_tokens + entry.output_tokens == 0:
        # 完全に空のエントリは無視 (誤計測防止)
        return None
    try:
        async with _db().connect(_db_path()) as db:
            cur = await db.execute(
                """INSERT INTO cost_logs
                   (session_id, workspace_id, provider, model,
                    input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, cost_usd, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.session_id, entry.workspace_id,
                    entry.provider, entry.model,
                    entry.input_tokens, entry.output_tokens,
                    entry.cache_read_tokens, entry.cache_write_tokens,
                    entry.cost_usd,
                    _ai_employee_metadata(entry.ai_employee_id),
                ),
            )
            await db.commit()
            return cur.lastrowid or 0
    except Exception as e:
        await _emit_audit("cost_recording_failed", session_id=entry.session_id, detail={
            "error": str(e)[:300],
            "provider": entry.provider, "model": entry.model,
        })
        return None


def _ai_employee_metadata(ai_employee_id: Optional[str]) -> str:
    import json
    if not ai_employee_id:
        return "{}"
    return json.dumps({"ai_employee_id": ai_employee_id}, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────────
# Aggregation
# ──────────────────────────────────────────────────────────────────────────


async def monthly_cost(workspace_id: int, *, month: Optional[str] = None) -> float:
    """指定 workspace の月次合計 USD を返す.

    month: "YYYY-MM" 形式、 省略時は当月.
    """
    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                """SELECT COALESCE(SUM(cost_usd), 0) AS total
                     FROM cost_logs
                    WHERE workspace_id = ?
                      AND substr(occurred_at, 1, 7) = ?""",
                (workspace_id, month),
            )
            rows = await cur.fetchall()
    except Exception as e:
        logger.warning("monthly_cost failed: %s", e)
        return 0.0
    if not rows:
        return 0.0
    return float(dict(rows[0]).get("total") or 0.0)


async def session_cost(session_id: int) -> float:
    """指定 session の累計 USD を返す."""
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_logs WHERE session_id = ?",
                (session_id,),
            )
            rows = await cur.fetchall()
    except Exception:
        return 0.0
    if not rows:
        return 0.0
    return float(dict(rows[0]).get("total") or 0.0)


# ──────────────────────────────────────────────────────────────────────────
# Budget pause (AC-STATE)
# ──────────────────────────────────────────────────────────────────────────


async def check_budget_pause(workspace_id: int) -> dict:
    """AC-STATE: 月次合計が budget 超なら queue pause + notify.

    workspace.budget_jpy_monthly は S-013 で設定される値 (¥)。
    1 USD ≈ 150 JPY で換算 (簡易、 実運用は環境変数で調整)。

    Returns:
      {
        "workspace_id": int,
        "monthly_usd": float,
        "budget_jpy": int,
        "exceeded": bool,
        "pause_triggered": bool,
      }
    """
    out: dict = {
        "workspace_id": workspace_id,
        "monthly_usd": 0.0,
        "budget_jpy": 0,
        "exceeded": False,
        "pause_triggered": False,
    }
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                "SELECT budget_jpy_monthly, status FROM workspaces WHERE id = ?",
                (workspace_id,),
            )
            rows = await cur.fetchall()
            ws = dict(rows[0]) if rows else {}
    except Exception:
        return out

    budget_jpy = int(ws.get("budget_jpy_monthly") or 0)
    out["budget_jpy"] = budget_jpy
    out["monthly_usd"] = await monthly_cost(workspace_id)

    # ¥ → $ で比較 (簡易換算)
    budget_usd = budget_jpy / 150.0 if budget_jpy > 0 else 0.0
    if budget_usd > 0 and out["monthly_usd"] > budget_usd:
        out["exceeded"] = True
        # workspace status を paused に
        try:
            async with _db().connect(_db_path()) as db:
                await db.execute(
                    "UPDATE workspaces SET status='paused' WHERE id=? AND status != 'paused'",
                    (workspace_id,),
                )
                await db.commit()
            out["pause_triggered"] = True
        except Exception as e:
            logger.warning("budget pause failed: %s", e)
        # G2: spec 文 'cost.budget_exceeded' を canonical event として emit.
        # 既存 'workspace_budget_exceeded' は alias として併発し後方互換維持.
        detail = {
            "workspace_id": workspace_id,
            "monthly_usd": out["monthly_usd"],
            "budget_jpy": budget_jpy,
            "exceeded_by_usd": round(out["monthly_usd"] - budget_usd, 4),
        }
        await _emit_audit(EVENT_COST_BUDGET_EXCEEDED, detail=detail)
        await _emit_audit(EVENT_WORKSPACE_BUDGET_EXCEEDED, detail=detail)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Reconciliation (AC-EVENT)
# ──────────────────────────────────────────────────────────────────────────


async def reconcile_session(
    session_id: int, anthropic_usage_total_usd: float,
) -> dict:
    """AC-EVENT: session 完了時に Anthropic Usage API の集計と自前 cost_logs を突合.

    discrepancy > 5% で flag + audit emit。

    Returns:
      {
        "session_id": int,
        "internal_usd": float,
        "anthropic_usd": float,
        "discrepancy_ratio": float,
        "flagged": bool,
      }
    """
    internal = await session_cost(session_id)
    if anthropic_usage_total_usd <= 0:
        ratio = 0.0
    else:
        diff = abs(internal - anthropic_usage_total_usd)
        ratio = diff / anthropic_usage_total_usd
    flagged = ratio > RECONCILE_THRESHOLD

    out = {
        "session_id": session_id,
        "internal_usd": round(internal, 6),
        "anthropic_usd": round(anthropic_usage_total_usd, 6),
        "discrepancy_ratio": round(ratio, 4),
        "flagged": flagged,
    }
    if flagged:
        await _emit_audit(
            "cost_reconcile_discrepancy",
            session_id=session_id,
            detail=out,
        )
    return out


# ──────────────────────────────────────────────────────────────────────────
# audit helpers
# ──────────────────────────────────────────────────────────────────────────


async def _emit_audit(
    event_type: str, *,
    session_id: Optional[int] = None,
    detail: Optional[dict] = None,
) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, session_id=session_id, detail=detail or {})
    except Exception as audit_err:
        logger.warning("audit emit failed: %s", audit_err)
