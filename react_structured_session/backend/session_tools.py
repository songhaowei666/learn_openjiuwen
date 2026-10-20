# coding: utf-8
"""无 LLM 参数、从 session 读状态的示例工具。

两种写法：

1. 继承 ``Tool``：``invoke(self, inputs, **kwargs)``，用 ``kwargs.get("session")``。
   框架调用是 ``await tool.invoke(args, session=session)``；没有 ``**kwargs``
   会报 ``unexpected keyword argument 'session'``。

2. ``@tool`` 注解：``LocalFunction.invoke`` 只做 ``_func(**inputs)``，**不会**
   把 kwargs 里的 session 传进函数。正确做法是函数内
   ``get_current_session()``（ReActAgent._inner_invoke 有 ``@with_session``，
   会把当前 session 放进 ContextVar）。

不要把 ``session`` 写进 ``@tool`` 函数签名：会进 JSON Schema，且框架也不会注入。
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from openjiuwen.core.foundation.tool import ToolCard, tool
from openjiuwen.core.foundation.tool.base import Tool
from openjiuwen.core.session import get_current_session
from openjiuwen.harness.tools.base_tool import ToolOutput


class ReadDataContextTool(Tool):
    """无参数工具（Tool 子类）：从 kwargs['session'] 读 data_context。"""

    def __init__(self) -> None:
        super().__init__(
            ToolCard(
                id="demo.read_data_context",
                name="read_data_context",
                description=(
                    "读取会话里预先写入的 data_context（如 file_name）。"
                    "本工具无需参数，直接调用即可。"
                ),
                # 无 LLM 参数：空 object schema
                input_params={"type": "object", "properties": {}},
            )
        )

    async def invoke(self, inputs: dict[str, Any], **kwargs: Any) -> ToolOutput:
        """session 由框架经 kwargs 注入，不要写进 input_params。"""
        session = kwargs.get("session")
        if session is None:
            return ToolOutput(success=False, data={"error": "session 未注入"})

        data_context = session.get_state("data_context") or {}
        file_name = data_context.get("file_name") if isinstance(data_context, dict) else None
        return ToolOutput(
            success=True,
            data={
                "file_name": file_name,
                "data_context": data_context,
                "session_id": session.get_session_id(),
            },
        )

    async def stream(self, inputs: dict[str, Any], **kwargs: Any) -> AsyncIterator[ToolOutput]:
        """流式不支持，走一次 invoke。"""
        yield await self.invoke(inputs, **kwargs)


@tool(
    name="read_data_context_via_ctx",
    description="无参：用 get_current_session 读 data_context（@tool 写法）。",
)
async def read_data_context_via_ctx() -> dict[str, Any]:
    """@tool 无参工具：不写 session 参数，从 ContextVar 取当前会话。"""
    session = get_current_session()
    if session is None:
        return {"error": "get_current_session() 为空（不在 Agent invoke 上下文内）"}
    data_context = session.get_state("data_context") or {}
    file_name = data_context.get("file_name") if isinstance(data_context, dict) else None
    return {
        "file_name": file_name,
        "data_context": data_context,
        "session_id": session.get_session_id(),
    }
