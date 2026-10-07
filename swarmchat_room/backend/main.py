# coding: utf-8
"""FastAPI：进程启动时建一间房，之后所有请求共用。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .room import Room

_room: Room | None = None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    global _room
    _room = Room()
    await _room.open()
    yield


app = FastAPI(title="专家协作空间", lifespan=_lifespan)


class MessageIn(BaseModel):
    """POST /api/messages 的请求体。"""

    body: str
    mentions: list[str] = Field(default_factory=list)
    client_message_id: str


def _current() -> Room:
    if _room is None:
        raise RuntimeError("房间尚未建好")
    return _room


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/roster")
async def roster() -> dict[str, list]:
    return {"members": await _current().roster()}


@app.get("/api/history")
async def history() -> dict:
    return await _current().get_history()


@app.post("/api/messages")
async def messages(payload: MessageIn):
    try:
        return await _current().post_user(payload.body, payload.mentions, payload.client_message_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"ok": False, "reason": "invalid_group_chat"})
    except RuntimeError as exc:
        return JSONResponse(status_code=500, content={"ok": False, "reason": "group_send_failed", "error": str(exc)})
