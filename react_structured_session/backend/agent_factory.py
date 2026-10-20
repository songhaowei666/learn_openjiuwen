# coding: utf-8
"""装配 ReActAgent、StructuredOutputTool 与 FinishRail。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openjiuwen.agent_teams.tools.structured_output_tool import (
    StructuredOutputFinishRail,
    StructuredOutputTool,
)
from openjiuwen.core.foundation.tool.base import Tool
from openjiuwen.core.runner import Runner
from openjiuwen.core.single_agent import AgentCard, Session, create_agent_session
from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig

from .session_tools import ReadDataContextTool

# backend/ 的上一级是 demo 根，再上一级是示例仓库根（含 common/）。
_DEMO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE_ROOT = _DEMO_ROOT.parent
if str(_EXAMPLE_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXAMPLE_ROOT))

from common.model import get_shared_model

# 待办结构化输出 schema（与 spec 一致）。
TODO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "due": {"type": "string"},
        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["title", "due", "priority"],
}

SYSTEM_PROMPT = (
    "你是待办助手。用户描述一件事后，你必须调用一次 structured_output，"
    "按工具参数 schema 提交 title、due、priority。"
    "不要用自由文本当最终答案；正文可以简短，但权威结果只能来自工具调用。"
)


@dataclass
class BuiltAgent:
    """工厂产物：Agent、提交工具、无参读 session 工具。"""

    agent: ReActAgent
    submit_tool: StructuredOutputTool
    data_context_tool: Tool


def _register_tool(agent: ReActAgent, tool: Tool) -> None:
    """挂到 resource_mgr 与 ability_manager。"""
    Runner.resource_mgr.add_tool(tool)
    agent.ability_manager.add(tool.card)


async def create_todo_agent() -> BuiltAgent:
    """创建已挂工具与 FinishRail 的 ReActAgent。"""
    shared = get_shared_model()
    api_key = os.environ.get("API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("示例根目录 .env 缺少 API_KEY")

    agent = ReActAgent(
        card=AgentCard(
            id="todo_structured_agent",
            name="TodoStructuredAgent",
            description="用 structured_output 提交待办",
        )
    )
    config = (
        ReActAgentConfig()
        .configure_model_client(
            provider=shared.provider,
            api_key=api_key,
            api_base=shared.api_base,
            model_name=shared.model_name,
            verify_ssl=False,
        )
        .configure_prompt_template([{"role": "system", "content": SYSTEM_PROMPT}])
        .configure_max_iterations(8)
    )
    agent.configure(config)

    submit_tool = StructuredOutputTool(TODO_SCHEMA)
    data_context_tool = ReadDataContextTool()
    _register_tool(agent, submit_tool)
    _register_tool(agent, data_context_tool)
    await agent.register_rail(StructuredOutputFinishRail())

    return BuiltAgent(
        agent=agent,
        submit_tool=submit_tool,
        data_context_tool=data_context_tool,
    )


def create_session_for_agent(agent: ReActAgent, session_id: str) -> Session:
    """按 Agent 的 card 创建 AgentSession（对齐 Runner._create_agent_session）。"""
    return create_agent_session(session_id=session_id, card=agent.card)
