# coding: utf-8
"""从示例根目录 .env 构造一份可复用的模型实例。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from openjiuwen.core.foundation.llm import Model, init_model

# common/model.py 的上一级就是 learn_note/example。
EXAMPLE_ROOT = Path(__file__).resolve().parents[1]

_REQUIRED = ("API_BASE", "API_KEY", "MODEL_NAME", "MODEL_PROVIDER")
_shared: SharedModel | None = None


def _load_env() -> None:
    """读取示例根目录 .env。已经导出的环境变量保持不变。"""
    load_dotenv(EXAMPLE_ROOT / ".env")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"示例根目录 .env 缺少 {name}")
    return value


class SharedModel:
    """各 demo 共用的模型。配置只来自示例根目录 .env。"""

    def __init__(self) -> None:
        _load_env()
        settings = {name: _required(name) for name in _REQUIRED}
        self.api_base = settings["API_BASE"]
        self.model_name = settings["MODEL_NAME"]
        self.provider = settings["MODEL_PROVIDER"]
        self.model: Model = init_model(
            provider=self.provider,
            model_name=self.model_name,
            api_key=settings["API_KEY"],
            api_base=self.api_base,
            timeout=120,
            verify_ssl=False,
        )

    async def ainvoke(self, messages, **kwargs):
        """非流式调用，参数原样交给 openjiuwen Model.invoke。"""
        return await self.model.invoke(messages, **kwargs)

    def astream(self, messages, **kwargs):
        """流式调用，返回 Model.stream 的异步迭代器。"""
        return self.model.stream(messages, **kwargs)


def get_shared_model() -> SharedModel:
    """进程内只建一次，后续 demo 拿到同一个实例。"""
    global _shared
    if _shared is None:
        _shared = SharedModel()
    return _shared
