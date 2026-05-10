"""
observability.py — Langfuse 観測ラッパー（Phase 1）

全LLM呼び出し・スロット更新・orchestrator ノード遷移を可視化する。

使い方:
  1. Langfuse を self-host で立てる（docker compose）
     LANGFUSE_HOST / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY を .env に設定
  2. 任意の関数に @observe を付ける
  3. ダッシュボード: http://localhost:3000

Langfuse が未設定の場合は no-op で動くため、安全に導入できる。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Callable, Optional

# ──────────────────────────────────────────
# Langfuse 初期化（lazy・失敗してもアプリは止めない）
# ──────────────────────────────────────────

_LF_CLIENT: Any = None
_LF_ENABLED: bool = False


def _init_langfuse() -> None:
    global _LF_CLIENT, _LF_ENABLED
    if _LF_CLIENT is not None:
        return
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        _LF_ENABLED = False
        return
    try:
        from langfuse import Langfuse
        _LF_CLIENT = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
        )
        _LF_ENABLED = True
        print("[observability] Langfuse initialized")
    except Exception as e:
        print(f"[observability] Langfuse init failed: {e}")
        _LF_ENABLED = False


def is_enabled() -> bool:
    if _LF_CLIENT is None:
        _init_langfuse()
    return _LF_ENABLED


# ──────────────────────────────────────────
# トレース API（薄いラッパー）
# ──────────────────────────────────────────

@contextmanager
def trace(name: str, *, user_id: Optional[str] = None,
          session_id: Optional[str] = None, metadata: Optional[dict] = None):
    """1リクエスト全体をくくる最上位トレース。
    orchestrator pipeline の各ノードはこの中で span として記録される。"""
    if not is_enabled():
        yield None
        return
    try:
        t = _LF_CLIENT.trace(
            name=name, user_id=user_id, session_id=session_id,
            metadata=metadata or {},
        )
        yield t
        try:
            _LF_CLIENT.flush()
        except Exception:
            pass
    except Exception as e:
        print(f"[observability] trace failed: {e}")
        yield None


@contextmanager
def span(parent: Any, name: str, *, input_data: Any = None,
         metadata: Optional[dict] = None):
    """ノード単位の span を作る。"""
    if not parent:
        yield None
        return
    try:
        s = parent.span(name=name, input=input_data, metadata=metadata or {})
        yield s
    except Exception as e:
        print(f"[observability] span failed: {e}")
        yield None


def log_generation(
    parent: Any,
    *,
    name: str,
    model: str,
    prompt: Any,
    completion: str,
    usage: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> None:
    """LLM 1回呼び出しのログ。"""
    if not parent or not is_enabled():
        return
    try:
        parent.generation(
            name=name, model=model,
            input=prompt, output=completion,
            usage=usage, metadata=metadata or {},
        )
    except Exception as e:
        print(f"[observability] log_generation failed: {e}")


# ──────────────────────────────────────────
# デコレータ（観測したい関数に付けるだけ）
# ──────────────────────────────────────────

def observe(name: Optional[str] = None) -> Callable:
    """関数の入出力を Langfuse に記録するデコレータ。"""
    def decorator(func: Callable) -> Callable:
        if not is_enabled():
            return func

        try:
            from langfuse.decorators import observe as lf_observe
            return lf_observe(name=name or func.__name__)(func)
        except Exception:
            return func
    return decorator


def shutdown() -> None:
    """アプリ終了時に未送信ログを flush。"""
    global _LF_CLIENT
    if _LF_CLIENT is None:
        return
    try:
        _LF_CLIENT.flush()
    except Exception:
        pass
