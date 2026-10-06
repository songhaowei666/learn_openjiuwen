# coding: utf-8
"""FastAPI 服务：把金融智能体的流式输出转为 A2UI SSE。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
import warnings
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

warnings.filterwarnings("ignore")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from openjiuwen.core.common.logging import llm_logger, logger, prompt_logger
from openjiuwen.core.runner import Runner

from .a2ui_messages import chunk_to_a2ui_messages
from .agent_factory import create_financial_agent

llm_logger.set_level(logging.CRITICAL)
logger.set_level(logging.CRITICAL)
prompt_logger.set_level(logging.CRITICAL)

HOST = "127.0.0.1"
PORT = 8765


class ChatRequest(BaseModel):
    """前端对话请求。"""

    query: str = Field(min_length=1)
    conversation_id: Optional[str] = None


def _sse(payload: dict[str, Any]) -> str:
    """编码一条 SSE data 行。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """进程启动时创建一次智能体。"""
    app.state.agent = create_financial_agent()
    app.state.locks: dict[str, asyncio.Lock] = {}
    yield


app = FastAPI(title="wsdw_multi_workflow A2UI API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _lock_for(conversation_id: str) -> asyncio.Lock:
    locks: dict[str, asyncio.Lock] = app.state.locks
    if conversation_id not in locks:
        locks[conversation_id] = asyncio.Lock()
    return locks[conversation_id]


@app.get("/api/health")
async def health() -> dict[str, str]:
    """健康检查。"""
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """接收用户输入，以 SSE 推送 A2UI 消息。"""
    conversation_id = request.conversation_id or str(uuid.uuid4())[:8]
    query = request.query.strip()

    async def event_stream() -> AsyncIterator[str]:
        async with _lock_for(conversation_id):
            try:
                result = Runner.run_agent_streaming(
                    app.state.agent,
                    inputs={
                        "query": query,
                        "conversation_id": conversation_id,
                    },
                )
                async for chunk in result:
                    messages = chunk_to_a2ui_messages(chunk)
                    if messages:
                        yield _sse({"kind": "data", "messages": messages})
                yield _sse({"kind": "done", "conversation_id": conversation_id})
            except Exception as exc:
                logger.error(f"处理对话时发生错误: {exc}")
                yield _sse({"kind": "error", "text": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def run() -> None:
    """启动 HTTP 服务。"""
    import uvicorn

    uvicorn.run("api.server:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    run()
