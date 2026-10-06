# coding: utf-8
"""human 节点的等待与回复。

进度回调先 begin()，backend 再 wait()。两者拿到同一个 Future，
即使用户回复发生在 wait() 之前，结果也不会丢。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class _Wait:
    """一轮 human 等待。consumed 表示 backend 已经取走这个 Future。"""

    future: asyncio.Future
    consumed: bool = False


class HumanManager:
    """按 run_id 阻塞 SwarmFlow 的 human 节点，直到 POST /api/reply。"""

    def __init__(self) -> None:
        self._waits: dict[str, _Wait] = {}

    def begin(self, run_id: str) -> asyncio.Future:
        """为一轮尚未被 backend 取走的 human 等待建 Future。"""
        current = self._waits.get(run_id)
        if current is not None and not current.consumed:
            return current.future
        future = asyncio.get_running_loop().create_future()
        self._waits[run_id] = _Wait(future)
        return future

    def wait(self, run_id: str) -> asyncio.Future:
        """取走本轮 Future。调用方负责 await。"""
        current = self._waits.get(run_id)
        if current is None or current.consumed:
            self.begin(run_id)
            current = self._waits[run_id]
        current.consumed = True
        return current.future

    def resolve(self, run_id: str, payload: dict[str, Any]) -> bool:
        """用用户回复唤醒等待中的 human 节点。"""
        current = self._waits.get(run_id)
        if current is None or current.future.done():
            return False
        current.future.set_result(payload)
        return True

    def cancel(self, run_id: str) -> None:
        """运行结束时取消仍在等待的回复。"""
        current = self._waits.pop(run_id, None)
        if current is not None and not current.future.done():
            current.future.cancel()
