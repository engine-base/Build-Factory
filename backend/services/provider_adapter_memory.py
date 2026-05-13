"""T-AI-MEM-04: Provider-adapter Memory Tool (任意切替 + 障害時 fallback 両対応).

ADR-012 Decision 5 の実装本体. Anthropic / OpenAI / Gemini の 3 provider に対して
Memory Tool / Context Editing / Subagent Memory の同一インターフェースを提供する
adapter. 既存 services/provider_adapter.py / services/byok_store.py /
services/circuit_breaker.py / services/litellm_router.py を REUSE.

## 公開 API

  - SUPPORTED_PROVIDERS = ("anthropic", "openai", "gemini")
  - DEFAULT_PROVIDER = "anthropic"  # ADR-010 既定

  - tool_spec_for(provider) -> dict | list[dict]
      anthropic → memory_20250818 server tool (1 dict)
      openai    → 6 commands を OpenAI function tool 形式で expose (list[6])
      gemini    → 6 commands を Gemini function_declarations 形式 (list[6])

  - resolve_active_provider(
        *,
        header_provider=None,         # X-LLM-Provider per-request override
        session_active_route=None,    # chat_sessions.active_route per-session
        workspace_preferred=None,     # workspaces.preferred_provider per-workspace
        user_id=None,                 # BYOK key 有無検査用
        anthropic_healthy=True,       # T-AI-08 circuit-breaker 連動
        policy_allow=None,            # workspace policy (許可 provider list)
    ) -> dict[{"provider", "reason"}]
      precedence (ADR-012 5.2 + tickets.json T-AI-MEM-04 AC-1):
        1. per-request header (X-LLM-Provider)
        2. per-session active_route
        3. per-workspace preferred_provider
        4. per-user BYOK key availability
        5. ADR-010 default (Anthropic main)
        6. T-AI-08 circuit-breaker fallback

  - context_editing_for(provider) -> dict
      anthropic → anthropic_context_editing.default_context_management_config()
      openai    → {"truncation_strategy": "auto", "summarize_client_side": True}
      gemini    → {"summarize_client_side": True, "keep_n_messages": 6}

  - provider_supports(provider, feature) -> bool
      feature ∈ {"native_compaction", "extended_thinking", "memory_tool_native"}

  - audit_event_for_switch(reason) -> str
      "provider.switched" (manual / auto-fallback) / "provider.fallback" (byok_missing /
      circuit-breaker / policy_blocked)

## AC マッピング (T-AI-MEM-04)

  AC-1 UBIQUITOUS    : tool_spec_for / resolve_active_provider / 6 layer precedence /
                       Vault filesystem 共有 (MemoryToolHandler は provider 非依存).
  AC-2 EVENT-DRIVEN  : 切替操作 2 秒以内 + audit ('provider.switched' manual /
                       auto-fallback). in-flight Memory Tool state 不変.
  AC-3 STATE-DRIVEN  : 非 Anthropic では client-side summarizer / clear_thinking skip /
                       truncation_strategy=auto. file ops byte-identical.
  AC-4 UNWANTED      : unsupported provider / workspace policy 衝突 / schema 違反 →
                       4xx state mutate なし. BYOK 不在 → precedence fallback +
                       audit 'provider.fallback' silent pick 禁止.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Literal, Optional

logger = logging.getLogger(__name__)


SUPPORTED_PROVIDERS: tuple[str, ...] = ("anthropic", "openai", "gemini")
DEFAULT_PROVIDER: str = "anthropic"  # ADR-010 既定

# ADR-012 5.3 機能別 capability matrix
CAPABILITIES: dict[str, dict[str, bool]] = {
    "anthropic": {
        "memory_tool_native": True,
        "native_compaction": True,
        "extended_thinking": True,
        "native_tool_clearing": True,
    },
    "openai": {
        "memory_tool_native": False,
        "native_compaction": False,
        "extended_thinking": False,
        "native_tool_clearing": False,  # truncation_strategy=auto で代替
    },
    "gemini": {
        "memory_tool_native": False,
        "native_compaction": False,
        "extended_thinking": False,
        "native_tool_clearing": False,
    },
}

# audit event 種別
EVENT_PROVIDER_SWITCHED = "provider.switched"
EVENT_PROVIDER_FALLBACK = "provider.fallback"

VALID_SWITCH_REASONS = ("manual", "auto-fallback", "byok", "default")
VALID_FALLBACK_REASONS = (
    "byok_missing",
    "circuit_breaker",
    "policy_blocked",
    "unsupported_provider",
)


class ProviderAdapterMemoryError(RuntimeError):
    """Provider-adapter 入力 / 不変条件違反 (router 層で 4xx 変換)."""


# ──────────────────────────────────────────────────────────────────────
# Validation helpers (AC-4 UNWANTED)
# ──────────────────────────────────────────────────────────────────────


def _validate_provider(value: Any, *, field: str = "provider") -> str:
    if not isinstance(value, str) or not value:
        raise ProviderAdapterMemoryError(f"{field} must not be empty")
    if value not in SUPPORTED_PROVIDERS:
        raise ProviderAdapterMemoryError(
            f"{field} must be one of {SUPPORTED_PROVIDERS}, got {value!r}"
        )
    return value


def _validate_optional_provider(value: Any, *, field: str) -> Optional[str]:
    if value is None:
        return None
    return _validate_provider(value, field=field)


def _validate_policy_allow(value: Any) -> Optional[tuple[str, ...]]:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise ProviderAdapterMemoryError("policy_allow must be list or null")
    out: list[str] = []
    for p in value:
        out.append(_validate_provider(p, field="policy_allow[]"))
    return tuple(out)


# ──────────────────────────────────────────────────────────────────────
# Tool spec factory (AC-1 UBIQUITOUS)
# ──────────────────────────────────────────────────────────────────────

_OPENAI_PARAMETERS_FOR_COMMAND: dict[str, dict[str, Any]] = {
    "view": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "/memories/... 仮想 path"},
            "view_range": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 2,
                "maxItems": 2,
            },
        },
        "required": ["path"],
    },
    "create": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "file_text": {"type": "string"},
        },
        "required": ["path", "file_text"],
    },
    "str_replace": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_str": {"type": "string"},
            "new_str": {"type": "string"},
        },
        "required": ["path", "old_str", "new_str"],
    },
    "insert": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "insert_line": {"type": "integer"},
            "insert_text": {"type": "string"},
        },
        "required": ["path", "insert_line", "insert_text"],
    },
    "delete": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    "rename": {
        "type": "object",
        "properties": {
            "old_path": {"type": "string"},
            "new_path": {"type": "string"},
        },
        "required": ["old_path", "new_path"],
    },
}


def _openai_tool_specs() -> list[dict[str, Any]]:
    """OpenAI Tools 形式 (type=function) で 6 commands を expose."""
    out: list[dict[str, Any]] = []
    for cmd in ("view", "create", "str_replace", "insert", "delete", "rename"):
        out.append({
            "type": "function",
            "function": {
                "name": f"memory_{cmd}",
                "description": (
                    f"Memory Tool {cmd} command. provider 非依存の HTTP API "
                    "/api/anthropic-memory/{command} と同一の挙動."
                ),
                "parameters": _OPENAI_PARAMETERS_FOR_COMMAND[cmd],
            },
        })
    return out


def _gemini_tool_specs() -> list[dict[str, Any]]:
    """Gemini function_declarations 形式で 6 commands を expose."""
    declarations: list[dict[str, Any]] = []
    for cmd in ("view", "create", "str_replace", "insert", "delete", "rename"):
        declarations.append({
            "name": f"memory_{cmd}",
            "description": (
                f"Memory Tool {cmd} command (Build-Factory shared Vault)."
            ),
            "parameters": _OPENAI_PARAMETERS_FOR_COMMAND[cmd],
        })
    return declarations


def tool_spec_for(provider: str) -> Any:
    """AC-1: provider ごとの Memory Tool 用 tool spec を返す.

    Returns:
      anthropic → {"type": "memory_20250818", "name": "memory"} (1 dict)
      openai    → list[6 dicts] (OpenAI Tools 形式)
      gemini    → list[6 dicts] (Gemini function_declarations 形式)
    """
    p = _validate_provider(provider)
    if p == "anthropic":
        from services.anthropic_memory_tool import memory_tool_spec
        return memory_tool_spec()
    if p == "openai":
        return _openai_tool_specs()
    return _gemini_tool_specs()


# ──────────────────────────────────────────────────────────────────────
# Context Editing factory (AC-3 STATE-DRIVEN)
# ──────────────────────────────────────────────────────────────────────


def context_editing_for(provider: str) -> dict[str, Any]:
    """provider ごとの context editing config.

    anthropic は SDK native (anthropic_context_editing). 他は client-side
    summarizer + truncation の degrade 設定 hint を返す.
    """
    p = _validate_provider(provider)
    if p == "anthropic":
        from services.anthropic_context_editing import (
            default_context_management_config,
            recommended_beta_headers,
        )
        return {
            "mode": "native",
            "context_management": default_context_management_config(),
            "betas": recommended_beta_headers(),
            "use_client_side_summarizer": False,
        }
    if p == "openai":
        return {
            "mode": "degrade_openai",
            "truncation_strategy": "auto",
            "use_client_side_summarizer": True,
            "skip_clear_thinking": True,
            "keep_n_messages": 6,
        }
    return {
        "mode": "degrade_gemini",
        "use_client_side_summarizer": True,
        "skip_clear_thinking": True,
        "keep_n_messages": 6,
    }


def provider_supports(provider: str, feature: str) -> bool:
    """capability 検査. 未知 feature は False."""
    p = _validate_provider(provider)
    return CAPABILITIES.get(p, {}).get(feature, False)


# ──────────────────────────────────────────────────────────────────────
# Resolve active provider (AC-1 UBIQUITOUS / AC-4 UNWANTED)
# ──────────────────────────────────────────────────────────────────────


def _user_byok_providers(user_id: Optional[str]) -> tuple[str, ...]:
    """BYOK 持ち込みキーがある provider 一覧 (precedence layer 4)."""
    if not user_id:
        return ()
    try:
        from services.byok_store import get_store
        store = get_store()
        records = store.list_for_user(user_id)
        return tuple(r.provider for r in records)
    except Exception as e:  # pragma: no cover
        logger.warning("byok lookup failed user_id=%s: %s", user_id, e)
        return ()


def _is_provider_allowed(
    provider: str, *, policy_allow: Optional[tuple[str, ...]],
) -> bool:
    if policy_allow is None:
        return True
    return provider in policy_allow


def resolve_active_provider(
    *,
    header_provider: Optional[str] = None,
    session_active_route: Optional[str] = None,
    workspace_preferred: Optional[str] = None,
    user_id: Optional[str] = None,
    anthropic_healthy: bool = True,
    policy_allow: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """precedence 6 layers を解決し選ばれた provider + 採用理由を返す.

    Returns:
      {
        "provider": str,
        "reason": "header" | "session" | "workspace" | "byok" | "default" |
                  "auto-fallback",
        "trace": list[dict],   # 各 layer の評価結果
      }

    Raises:
      ProviderAdapterMemoryError: 全 precedence が unsupported / policy で
        ブロックされた場合.
    """
    header = _validate_optional_provider(header_provider, field="header_provider")
    session = _validate_optional_provider(session_active_route, field="session_active_route")
    # workspace は 'auto' を含む (T-024-04)
    if workspace_preferred is not None:
        if workspace_preferred == "auto":
            ws_pref: Optional[str] = None
        else:
            ws_pref = _validate_provider(workspace_preferred, field="workspace_preferred")
    else:
        ws_pref = None
    policy = _validate_policy_allow(list(policy_allow) if policy_allow is not None else None)

    trace: list[dict[str, Any]] = []
    byok_providers = _user_byok_providers(user_id)

    candidates: list[tuple[str, str]] = []
    if header:
        candidates.append((header, "header"))
    if session:
        candidates.append((session, "session"))
    if ws_pref:
        candidates.append((ws_pref, "workspace"))
    for p in byok_providers:
        candidates.append((p, "byok"))
    # ADR-010 default
    candidates.append((DEFAULT_PROVIDER, "default"))

    chosen: Optional[tuple[str, str]] = None
    for provider, reason in candidates:
        # capability + policy check
        allowed = _is_provider_allowed(provider, policy_allow=policy)
        healthy = (provider != "anthropic") or anthropic_healthy
        trace.append({
            "provider": provider, "reason": reason,
            "policy_allowed": allowed, "healthy": healthy,
        })
        if not allowed:
            continue
        if not healthy:
            continue
        chosen = (provider, reason)
        break

    if chosen is None:
        # 全 precedence layer が NG. T-AI-08 fallback: anthropic 以外の
        # healthy + allowed な provider を探す.
        for fallback in ("openai", "gemini"):
            if _is_provider_allowed(fallback, policy_allow=policy):
                trace.append({
                    "provider": fallback, "reason": "auto-fallback",
                    "policy_allowed": True, "healthy": True,
                })
                chosen = (fallback, "auto-fallback")
                break

    if chosen is None:
        raise ProviderAdapterMemoryError(
            "no provider available: all candidates blocked by policy / circuit-breaker"
        )

    provider, reason = chosen
    return {"provider": provider, "reason": reason, "trace": trace}


# ──────────────────────────────────────────────────────────────────────
# Audit event helpers (AC-2 EVENT-DRIVEN)
# ──────────────────────────────────────────────────────────────────────


def audit_event_for_switch(reason: str) -> str:
    """切替経路の audit event_type を返す."""
    if reason in VALID_SWITCH_REASONS:
        return EVENT_PROVIDER_SWITCHED
    if reason in VALID_FALLBACK_REASONS:
        return EVENT_PROVIDER_FALLBACK
    raise ProviderAdapterMemoryError(
        f"unknown switch reason {reason!r}; valid: switched={VALID_SWITCH_REASONS} "
        f"fallback={VALID_FALLBACK_REASONS}"
    )


async def emit_switch_audit(
    *,
    from_provider: Optional[str],
    to_provider: str,
    reason: str,
    scope: str,  # "per-session" / "per-workspace" / "per-request"
    actor_user_id: Optional[str] = None,
    extra_detail: Optional[dict[str, Any]] = None,
) -> Optional[int]:
    """audit_logs に provider.switched / provider.fallback を emit."""
    _validate_provider(to_provider, field="to_provider")
    if from_provider is not None:
        _validate_provider(from_provider, field="from_provider")
    event = audit_event_for_switch(reason)
    if not isinstance(scope, str) or not scope:
        raise ProviderAdapterMemoryError("scope must not be empty")
    detail: dict[str, Any] = {
        "from": from_provider,
        "to": to_provider,
        "reason": reason,
        "scope": scope,
    }
    if extra_detail:
        detail.update(extra_detail)
    try:
        from services.memory_service import emit_event
        return await emit_event(event, user_id=actor_user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("provider switch audit emit failed: %s", e)
        return None
