# coding: utf-8
"""CLI：两轮同 conversation_id，权威结果读 structured_output.captured。

用法（仓库根目录已填 .env）：

    cd react_structured_session
    python -m backend.main
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openjiuwen.core.runner import Runner

from .agent_factory import BuiltAgent, create_session_for_agent, create_todo_agent

CONVERSATION_ID = "react_structured_demo"

ROUND1_QUERY = "把明天下午三点的团队周会记成待办，优先级高。"
ROUND2_QUERY = "把优先级改成 medium。"


def _reset_capture(built: BuiltAgent) -> None:
    """每轮开始前清空上一轮提交，避免读到旧 captured。"""
    built.submit_tool.captured = None
    built.submit_tool.called = False


def _print_captured(label: str, conversation_id: str, session_id: str, captured: dict[str, Any]) -> None:
    """只展示 captured，正文不当权威结果。"""
    print(f"=== {label} ===")
    print(f"conversation_id={conversation_id}")
    print(f"session_id={session_id}")
    print("captured=")
    print(json.dumps(captured, ensure_ascii=False, indent=2))


def _assert_todo(captured: dict[str, Any] | None, expect_priority: str) -> dict[str, Any]:
    """验收：captured 含 title/due/priority，且 priority 符合预期。"""
    if not captured:
        raise AssertionError("structured_output 未提交：tool.captured 为空")
    for key in ("title", "due", "priority"):
        if key not in captured:
            raise AssertionError(f"captured 缺少字段 {key}: {captured}")
    if captured["priority"] != expect_priority:
        raise AssertionError(
            f"priority 期望 {expect_priority!r}，实际 {captured['priority']!r}"
        )
    return captured


async def _run_turn(
    built: BuiltAgent,
    *,
    label: str,
    query: str,
    conversation_id: str,
    expect_priority: str,
) -> str:
    """跑一轮：用 Agent 创建 session 并交给 Runner，读 captured 做验收。"""
    _reset_capture(built)

    # 根据 ReActAgent.card 显式建 session，再传给 run_agent（不再只靠 conversation_id 隐式创建）
    session = create_session_for_agent(built.agent, conversation_id)
    inputs = {
        "query": query,
        "conversation_id": conversation_id,
    }
    # 先 pre_run（restore），再写 state，避免检查点覆盖 data_context
    await session.pre_run(inputs=inputs)
    session.update_state({
        "data_context": {
            "file_name": "1234567890.txt",
        }
    })

    # 无参工具：框架会 invoke({}, session=session)；必须用 **kwargs 接 session
    ctx_result = await built.data_context_tool.invoke({}, session=session)
    print(f"[{label}] read_data_context -> {ctx_result}")
    ctx_data = getattr(ctx_result, "data", None) or {}
    if ctx_data.get("file_name") != "1234567890.txt":
        raise AssertionError(f"无参工具未读到 data_context: {ctx_result}")

    session_id = session.get_session_id()
    result = await Runner.run_agent(
        agent=built.agent,
        inputs=inputs,
        session=session,
    )

    captured = _assert_todo(built.submit_tool.captured, expect_priority)
    _print_captured(label, conversation_id, session_id, captured)

    # 自由文本仅作旁路日志，不参与验收
    if isinstance(result, dict):
        output = result.get("output")
        if output:
            print(f"(旁路) runner output 类型={type(output).__name__}，不作为权威结果")
    print()
    return session_id


async def async_main() -> int:
    """两轮同 conversation_id，断言 session_id 一致且 captured 合格。"""
    await Runner.start()
    try:
        built = await create_todo_agent()

        session_id_1 = await _run_turn(
            built,
            label="第一轮",
            query=ROUND1_QUERY,
            conversation_id=CONVERSATION_ID,
            expect_priority="high",
        )
        session_id_2 = await _run_turn(
            built,
            label="第二轮",
            query=ROUND2_QUERY,
            conversation_id=CONVERSATION_ID,
            expect_priority="medium",
        )

        if session_id_1 != session_id_2:
            raise AssertionError(
                f"两轮 session_id 不一致: {session_id_1!r} vs {session_id_2!r}"
            )
        print(f"验收通过：两轮 session_id 均为 {session_id_1!r}")
        return 0
    finally:
        await Runner.stop()


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
