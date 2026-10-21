# coding: utf-8
"""同一 session_id 下挂两个 ModelContext，证明消息互不污染（无模型）。

session_id = 会话身份；context_id = 该会话里的哪一块消息视野。
"""

from __future__ import annotations

from openjiuwen.core.context_engine import ContextEngine, ContextEngineConfig
from openjiuwen.core.foundation.llm import AssistantMessage, UserMessage
from openjiuwen.core.single_agent import AgentCard, create_agent_session

SESSION_ID = "multi_context_demo"
MAIN_CONTEXT_ID = "main"
SIDE_CONTEXT_ID = "side_task"


def _summarize_messages(messages) -> list[str]:
    """打印用：role + 正文摘要。"""
    lines: list[str] = []
    for msg in messages:
        role = getattr(msg, "role", type(msg).__name__)
        content = getattr(msg, "content", "") or ""
        if isinstance(content, str) and len(content) > 40:
            content = content[:40] + "..."
        lines.append(f"{role}: {content}")
    return lines


async def demo_multi_context() -> None:
    """同一 session 建 main / side_task 两个 context，分别写消息后验收隔离与落盘。"""
    print("=== 多 ModelContext 演示（无模型）===")
    print(f"session_id={SESSION_ID}")
    print(f"context_id: {MAIN_CONTEXT_ID!r} 与 {SIDE_CONTEXT_ID!r}")
    print()

    session = create_agent_session(
        session_id=SESSION_ID,
        card=AgentCard(
            id="multi_context_agent",
            name="MultiContextDemo",
            description="演示同一 session 下多个 ModelContext",
        ),
    )
    await session.pre_run(inputs={"query": "multi_context_demo"})

    engine = ContextEngine(ContextEngineConfig())
    main_ctx = await engine.create_context(session=session, context_id=MAIN_CONTEXT_ID)
    side_ctx = await engine.create_context(session=session, context_id=SIDE_CONTEXT_ID)

    await main_ctx.add_messages(UserMessage(content="主对话：安排明天下午的团队周会"))
    await main_ctx.add_messages(AssistantMessage(content="好的，已记下周会安排"))
    await side_ctx.add_messages(UserMessage(content="旁路任务：查一下天气"))
    await side_ctx.add_messages(AssistantMessage(content="今天晴，适合开会"))

    main_msgs = main_ctx.get_messages()
    side_msgs = side_ctx.get_messages()

    print(f"[{MAIN_CONTEXT_ID}] 消息数={len(main_msgs)}")
    for line in _summarize_messages(main_msgs):
        print(f"  {line}")
    print(f"[{SIDE_CONTEXT_ID}] 消息数={len(side_msgs)}")
    for line in _summarize_messages(side_msgs):
        print(f"  {line}")
    print()

    main_text = " ".join(str(getattr(m, "content", "")) for m in main_msgs)
    side_text = " ".join(str(getattr(m, "content", "")) for m in side_msgs)
    if "周会" not in main_text:
        raise AssertionError(f"main context 应含周会相关消息: {main_text}")
    if "天气" not in side_text:
        raise AssertionError(f"side context 应含天气相关消息: {side_text}")
    if "天气" in main_text:
        raise AssertionError("main context 不应混入 side 的天气消息")
    if "周会" in side_text:
        raise AssertionError("side context 不应混入 main 的周会消息")

    await engine.save_contexts(session)
    persisted = session.get_state("context") or {}
    keys = sorted(persisted.keys())
    print(f"save_contexts 后 session.state['context'] keys={keys}")

    expected = {MAIN_CONTEXT_ID, SIDE_CONTEXT_ID}
    if not expected.issubset(set(keys)):
        raise AssertionError(f"期望 keys 含 {expected}，实际 {keys}")

    for cid in (MAIN_CONTEXT_ID, SIDE_CONTEXT_ID):
        bucket = persisted.get(cid) or {}
        msg_count = len(bucket.get("messages") or [])
        print(f"  落盘 {cid}: messages={msg_count}")
        if msg_count < 2:
            raise AssertionError(f"{cid} 落盘消息过少: {bucket}")

    print()
    print(
        f"验收通过：同一 session_id={SESSION_ID!r} 下 "
        f"{MAIN_CONTEXT_ID!r} 与 {SIDE_CONTEXT_ID!r} 消息隔离且均已落盘"
    )
