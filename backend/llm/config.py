"""
Multi-LLM configuration.
Supports: Anthropic Claude, OpenAI, Ollama (local), LM Studio (local), LiteLLM proxy.
"""

from enum import Enum
from pydantic import BaseModel
from openai import AsyncOpenAI


class LLMProvider(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"
    LITELLM = "litellm"


class LLMProfile(BaseModel):
    provider: LLMProvider
    model: str
    base_url: str
    api_key: str
    label: str
    is_local: bool = False


PROFILES: dict[LLMProvider, LLMProfile] = {
    LLMProvider.CLAUDE: LLMProfile(
        provider=LLMProvider.CLAUDE,
        model="claude-sonnet-4-6",
        base_url="https://api.anthropic.com/v1",
        api_key="${ANTHROPIC_API_KEY}",
        label="Claude Sonnet 4.6 (Anthropic)",
        is_local=False,
    ),
    LLMProvider.OPENAI: LLMProfile(
        provider=LLMProvider.OPENAI,
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
        api_key="${OPENAI_API_KEY}",
        label="GPT-4o (OpenAI)",
        is_local=False,
    ),
    LLMProvider.OLLAMA: LLMProfile(
        provider=LLMProvider.OLLAMA,
        model="qwen2.5:7b",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        label="Qwen 2.5 7B (Ollama Local)",
        is_local=True,
    ),
    LLMProvider.LMSTUDIO: LLMProfile(
        provider=LLMProvider.LMSTUDIO,
        model="local-model",
        base_url="http://localhost:1234/v1",
        api_key="lmstudio",
        label="LM Studio (Local)",
        is_local=True,
    ),
    LLMProvider.LITELLM: LLMProfile(
        provider=LLMProvider.LITELLM,
        model="gpt-4o",
        base_url="http://localhost:4000/v1",
        api_key="sk-litellm",
        label="LiteLLM Proxy",
        is_local=True,
    ),
}


def resolve_key(key: str, env: dict) -> str:
    if key.startswith("${") and key.endswith("}"):
        var = key[2:-1]
        return env.get(var, "")
    return key


def get_openai_client(provider: LLMProvider, env: dict) -> AsyncOpenAI:
    profile = PROFILES[provider]
    return AsyncOpenAI(
        api_key=resolve_key(profile.api_key, env),
        base_url=profile.base_url,
    )


def get_profile(provider: LLMProvider) -> LLMProfile:
    return PROFILES[provider]


def list_profiles() -> list[dict]:
    return [
        {
            "id": p.value,
            "label": PROFILES[p].label,
            "model": PROFILES[p].model,
            "is_local": PROFILES[p].is_local,
        }
        for p in LLMProvider
    ]
