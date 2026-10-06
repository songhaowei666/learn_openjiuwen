# coding: utf-8
"""一次运行的事件日志与订阅队列。

进度事件和 A2UI 消息都写进同一份带序号的日志，SSE 断线后用 Last-Event-ID 续传。
"""

from __future__ import annotations

import asyncio
from typing import Any


class EventBridge:
    """进程内事件桥：同步发布，异步订阅。"""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._queues: list[asyncio.Queue] = []
        self._next_id = 1

    def publish(self, event_name: str, data: dict[str, Any]) -> dict[str, Any]:
        """追加一条事件，并投递给当前所有订阅者。"""
        item = {"id": self._next_id, "event": event_name, "data": data}
        self._next_id += 1
        self._events.append(item)
        for queue in self._queues:
            queue.put_nowait(item)
        return item

    def subscribe(self, last_event_id: int) -> tuple[list[dict[str, Any]], asyncio.Queue]:
        """注册订阅者，并返回 last_event_id 之后的历史事件。"""
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.append(queue)
        backlog = [item for item in self._events if item["id"] > last_event_id]
        return backlog, queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """移除订阅者。"""
        if queue in self._queues:
            self._queues.remove(queue)
