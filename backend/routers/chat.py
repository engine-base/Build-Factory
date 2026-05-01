"""
AI Chat router — SSE streaming with multi-LLM support.
POST /api/chat       → full response (JSON)
GET  /api/chat/stream → SSE stream
"""

import asyncio
import json
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agents import Runner  # openai-agents package

from llm.config import LLMProvider, get_openai_client, get_profile
from company_agent.company_agent import create_agent, stream_response

router = APIRouter(prefix="/api/chat", tags=["chat"])

env = dict(os.environ)


class ChatRequest(BaseModel):
    message: str
    provider: LLMProvider = LLMProvider.CLAUDE
    model: str | None = None


@router.post("")
async def chat(req: ChatRequest):
    profile = get_profile(req.provider)
    model_name = req.model or profile.model
    client = get_openai_client(req.provider, env)
    agent = create_agent(client, model_name)

    try:
        result = await Runner.run(agent, req.message)
        return {"reply": result.final_output, "provider": req.provider, "model": model_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    profile = get_profile(req.provider)
    model_name = req.model or profile.model
    client = get_openai_client(req.provider, env)
    agent = create_agent(client, model_name)

    async def event_generator():
        try:
            async for chunk in stream_response(agent, req.message):
                data = json.dumps({"chunk": chunk}, ensure_ascii=False)
                yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
