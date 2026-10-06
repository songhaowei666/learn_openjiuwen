# coding: utf-8
"""FastAPI 入口：提问、SSE 事件、human 回复。"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .event_bridge import EventBridge
from .human_manager import HumanManager
from .swarmflow_runner import run_demo

app = FastAPI(title="SwarmFlow A2UI Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_bridges: dict[str, EventBridge] = {}
_humans = HumanManager()
_tasks: dict[str, asyncio.Task] = {}


class AskRequest(BaseModel):
    """POST /api/ask 的请求体。"""

    question: str = Field(min_length=1)


class ReplyRequest(BaseModel):
    """POST /api/reply 的请求体。"""

    run_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """健康检查。"""
    return {"status": "ok"}


@app.post("/api/ask")
async def ask(body: AskRequest) -> dict[str, str]:
    """接收问题，启动预编写的 SwarmFlow 脚本。"""
    run_id = str(uuid.uuid4())
    bridge = EventBridge()
    _bridges[run_id] = bridge
    _tasks[run_id] = asyncio.create_task(run_demo(run_id, body.question.strip(), bridge, _humans))
    return {"run_id": run_id}


@app.get("/api/events/{run_id}")
async def events(run_id: str, request: Request) -> EventSourceResponse:
    """按 run_id 推送 progress 与 a2ui 事件，支持 Last-Event-ID 续传。"""
    bridge = _bridges.get(run_id)
    if bridge is None:
        raise HTTPException(status_code=404, detail="run_id 不存在")
    last_raw = request.headers.get("last-event-id") or "0"
    try:
        last_event_id = int(last_raw)
    except ValueError:
        last_event_id = 0
    backlog, queue = bridge.subscribe(last_event_id)

    async def generator():
        """先补历史，再推增量，直到 done。"""
        seen = last_event_id
        try:
            pending = list(backlog)
            while True:
                while pending:
                    item = pending.pop(0)
                    if item["id"] <= seen:
                        continue
                    seen = item["id"]
                    yield _sse(item)
                    if item["event"] == "done":
                        return
                if await request.is_disconnected():
                    return
                item = await queue.get()
                if item["id"] <= seen:
                    continue
                pending.append(item)
        finally:
            bridge.unsubscribe(queue)

    return EventSourceResponse(generator())


@app.post("/api/reply")
async def reply(body: ReplyRequest) -> dict[str, bool]:
    """把用户在 A2UI 上的动作交给正在等待的 human 节点。"""
    if body.run_id not in _bridges:
        raise HTTPException(status_code=404, detail="run_id 不存在")
    accepted = _humans.resolve(body.run_id, {"action": body.action, "context": body.context})
    if not accepted:
        raise HTTPException(status_code=409, detail="当前没有等待中的 human 节点")
    return {"ok": True}


def _sse(item: dict[str, Any]) -> dict[str, str]:
    """转成 sse-starlette 的事件字典。"""
    return {
        "id": str(item["id"]),
        "event": item["event"],
        "data": json.dumps(item["data"], ensure_ascii=False),
    }


def run() -> None:
    """启动 HTTP 服务。"""
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
