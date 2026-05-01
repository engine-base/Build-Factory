"""
llm_providers.py — 利用可能LLMプロバイダー・モデル一覧 API
"""

import os
from fastapi import APIRouter

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/available")
async def list_available_llms():
    """
    使えるLLM（プロバイダ・モデル）の一覧を返す。
    - Ollama: ローカル http://localhost:11434/api/tags から動的取得
    - Claude: ANTHROPIC_API_KEY が有効なら利用可能
    - OpenAI: OPENAI_API_KEY が有効なら利用可能
    """
    providers = []

    # 1. Ollama (ローカル)
    ollama_models = await _fetch_ollama_models()
    providers.append({
        "id": "ollama",
        "name": "Ollama (ローカル)",
        "available": len(ollama_models) > 0,
        "description": "ローカル実行・無料",
        "models": ollama_models,
    })

    # 2. Anthropic Claude
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    claude_available = anthropic_key.startswith("sk-ant-") and len(anthropic_key) >= 50
    providers.append({
        "id": "claude",
        "name": "Anthropic Claude",
        "available": claude_available,
        "description": "Claude API・MaxプランAPIクォータ",
        "models": [
            {"id": "claude-opus-4-5",     "name": "Claude Opus 4.5",    "tier": "深い推論"},
            {"id": "claude-sonnet-4-6",   "name": "Claude Sonnet 4.6",  "tier": "汎用最高"},
            {"id": "claude-haiku-4-5",    "name": "Claude Haiku 4.5",   "tier": "高速・安価"},
        ] if claude_available else [],
    })

    # 3. OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    openai_available = openai_key.startswith("sk-") and len(openai_key) >= 50
    providers.append({
        "id": "openai",
        "name": "OpenAI",
        "available": openai_available,
        "description": "OpenAI API",
        "models": [
            {"id": "gpt-4o",           "name": "GPT-4o",           "tier": "汎用"},
            {"id": "gpt-4o-mini",      "name": "GPT-4o Mini",      "tier": "高速・安価"},
            {"id": "gpt-4-turbo",      "name": "GPT-4 Turbo",      "tier": "高品質"},
        ] if openai_available else [],
    })

    return {"providers": providers}


async def _fetch_ollama_models() -> list[dict]:
    """Ollamaから動的にダウンロード済みモデル一覧を取得する。"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:11434/api/tags",
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                models = []
                for m in data.get("models", []):
                    name = m.get("name", "")
                    # Embedding専用モデルは除外
                    if "embed" in name.lower():
                        continue
                    size_gb = round((m.get("size") or 0) / 1024**3, 1)
                    param_size = m.get("details", {}).get("parameter_size", "")
                    models.append({
                        "id":   name,
                        "name": f"{name}",
                        "tier": f"{param_size} / {size_gb}GB" if param_size else f"{size_gb}GB",
                    })
                return models
    except Exception as e:
        print(f"[llm_providers] Ollama取得失敗: {e}")
        return []
