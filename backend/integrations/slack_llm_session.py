"""
slack_llm_session.py — Slack ユーザーごとの LLM セッション管理

Slack ユーザーごとに「現在使用中のLLM」を保持し、
delegation や @社員 呼び出し時に取得できるようにする。

優先順位:
  1. ユーザーごとのセッション設定（/llm コマンドで設定）
  2. .env の SLACK_DEFAULT_LLM_PROVIDER / SLACK_DEFAULT_LLM_MODEL
  3. デフォルト値（ollama / qwen2.5:7b）
"""

import os
from threading import Lock

# ユーザーID → {"provider": ..., "model": ...}
_sessions: dict[str, dict] = {}
_lock = Lock()


def get_user_llm(user_id: str) -> tuple[str, str]:
    """指定Slackユーザーの現在のLLM設定を返す。"""
    with _lock:
        if user_id in _sessions:
            s = _sessions[user_id]
            return s.get("provider", "ollama"), s.get("model", "qwen2.5:7b")

    # .env のデフォルト
    default_provider = os.environ.get("SLACK_DEFAULT_LLM_PROVIDER", "ollama")
    default_model    = os.environ.get("SLACK_DEFAULT_LLM_MODEL", "qwen2.5:7b")
    return default_provider, default_model


def set_user_llm(user_id: str, provider: str, model: str) -> None:
    """ユーザーのLLM設定を更新する。"""
    with _lock:
        _sessions[user_id] = {"provider": provider, "model": model}


def reset_user_llm(user_id: str) -> None:
    """ユーザーのLLM設定をデフォルトに戻す。"""
    with _lock:
        _sessions.pop(user_id, None)


def list_available_models() -> str:
    """選択可能なLLM一覧をテキストで返す（ヘルプ用）。"""
    lines = ["利用可能なモデル（環境次第）:"]
    lines.append("  - ollama / qwen2.5:7b（推奨・無料）")
    lines.append("  - ollama / gemma3:4b（高速・軽量）")
    lines.append("  - ollama / gemma3:12b（高品質）")
    lines.append("  - ollama / gemma4:latest")
    lines.append("  - claude / claude-sonnet-4-6（API課金）")
    lines.append("  - claude / claude-haiku-4-5（API課金・高速）")
    lines.append("  - openai / gpt-4o（API課金）")
    return "\n".join(lines)


def parse_llm_command(text: str) -> tuple[str | None, str | None]:
    """
    /llm コマンドのテキストを解析する。
    例: "/llm claude-sonnet-4-6" → ("claude", "claude-sonnet-4-6")
    例: "/llm ollama gemma3:12b" → ("ollama", "gemma3:12b")
    例: "/llm reset" → (None, "reset")
    """
    parts = text.strip().split()
    if not parts:
        return None, None

    if parts[0] == "reset":
        return None, "reset"

    # 1引数: "claude-sonnet-4-6" or "qwen2.5:7b" → モデル名から推定
    if len(parts) == 1:
        model = parts[0]
        if model.startswith("claude"):
            return "claude", model
        if model.startswith("gpt"):
            return "openai", model
        return "ollama", model

    # 2引数: "claude claude-sonnet-4-6"
    return parts[0], parts[1]
