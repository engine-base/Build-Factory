"""LLM provider info & Ollama model listing."""

import httpx
from fastapi import APIRouter
from llm.config import list_profiles, LLMProvider

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/providers")
async def providers():
    return list_profiles()


@router.get("/ollama/models")
async def ollama_models():
    """List locally available Ollama models."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []
