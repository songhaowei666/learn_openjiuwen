# -*- coding: UTF-8 -*-
"""三课可运行脚本：并行汇合、人机续跑、异常重入与幂等。"""

from __future__ import annotations

import uuid
from typing import Any

from openjiuwen.core.session.checkpointer import CheckpointerFactory
from openjiuwen.core.session.interaction.interactive_input import InteractiveInput
from openjiuwen.core.workflow import (
    WorkflowExecutionState,
    create_workflow_session,
)

from .components import read_charge_count
from .setup import summarize_graph_state
from .workflows import (
    build_interrupt_workflow,
    build_parallel_workflow,
    build_side_effect_workflow,
)


def _banner(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


async def _peek_graph(session_id: str, workflow_id: str) -> dict:
    """从 Checkpointer 读取 workflow-graph 命名空间里的 GraphState。"""
    cp = CheckpointerFactory.get_checkpointer()
    state = await cp.graph_store().get(session_id, workflow_id)
    summary = summarize_graph_state(state)
    print(f"  [checkpoint] session={session_id} workflow={workflow_id}")
    print(f"  [checkpoint] graph_state = {summary}")
    return summary


async def lesson_parallel(query: str = "合同审查") -> Any:
    """课 1：并行分支 + wait_for_all 汇合。"""
    _banner("课 1：并行汇合（多出边 + wait_for_all）")
    print("图：start -> left & right -> merge -> end")
    print("说明：left/right 同超步可并行；merge 等两侧都完成后才跑。")

    flow = build_parallel_workflow()
    session_id = f"parallel-{uuid.uuid4().hex[:8]}"
    session = create_workflow_session(session_id=session_id)
    result = await flow.invoke({"query": query}, session)
    print(f"状态: {result.state}")
    print(f"结果: {result.result}")
    # 正常结束应清理图检查点
    await _peek_graph(session_id, "lesson_parallel")
    return result


async def lesson_interrupt(
    query: str = "初稿：付款净30天",
    reply: str | None = None,
    *,
    interactive: bool = False,
) -> Any:
    """课 2：人机中断 + 同 session_id 续跑，并偷看 GraphState。"""
    _banner("课 2：人机中断与 InteractiveInput 续跑")
    print("图：start -> ask -> end")
    print("说明：ask 调用 session.interact；返回 INPUT_REQUIRED 时检查点保留。")

    flow = build_interrupt_workflow()
    session_id = f"interrupt-{uuid.uuid4().hex[:8]}"

    first = await flow.invoke(
        {"query": query},
        create_workflow_session(session_id=session_id),
    )
    print(f"第一次状态: {first.state}")
    print(f"第一次结果: {first.result}")
    assert first.state == WorkflowExecutionState.INPUT_REQUIRED

    graph_summary = await _peek_graph(session_id, "lesson_interrupt")
    assert graph_summary.get("exists"), "中断后应存在 workflow-graph 检查点"

    # 构造人工回复
    if interactive and reply is None:
        reply = input("请输入人工回复（回车则沿用草稿）: ").strip() or query
    if reply is None:
        reply = f"已确认：{query}"

    user_input = InteractiveInput()
    for item in first.result:
        payload = item.payload
        user_input.update(payload.id, {"text": reply})

    print(f"续跑回复: {reply!r}（同一 session_id={session_id}）")
    second = await flow.invoke(
        user_input,
        create_workflow_session(session_id=session_id),
    )
    print(f"续跑状态: {second.state}")
    print(f"续跑结果: {second.result}")
    await _peek_graph(session_id, "lesson_interrupt")
    return second


async def lesson_side_effect(*, idempotent: bool) -> Any:
    """课 3：异常后节点重入；对比有无幂等守卫。"""
    title = "幂等守卫（跳过重复扣款）" if idempotent else "异常重入（会重复扣款）"
    _banner(f"课 3：{title}")
    print("图：start -> charge -> end")
    print("说明：charge 先写外部账本再抛错；恢复时引擎重入 charge。")
    print("要点：节点内 session 状态在同超步失败时可能回滚；外部副作用不会。")

    session_id = f"charge-{uuid.uuid4().hex[:8]}"
    flow = build_side_effect_workflow(idempotent=idempotent, session_id=session_id)
    workflow_id = "lesson_idempotent" if idempotent else "lesson_reenter"

    try:
        await flow.invoke(
            {"amount": 10},
            create_workflow_session(session_id=session_id),
        )
        raise AssertionError("第一次应当抛出模拟崩溃异常")
    except Exception as exc:
        print(f"第一次异常（预期）: {type(exc).__name__}: {exc}")

    print(f"崩溃后外部账本 count={read_charge_count(session_id)}")
    await _peek_graph(session_id, workflow_id)

    print("用空 InteractiveInput 触发从检查点恢复（失败节点会重入）...")
    result = await flow.invoke(
        InteractiveInput(),
        create_workflow_session(session_id=session_id),
    )
    print(f"恢复后状态: {result.state}")
    print(f"恢复后结果: {result.result}")
    print(f"恢复后外部账本 count={read_charge_count(session_id)}")
    await _peek_graph(session_id, workflow_id)

    payload = result.result
    if isinstance(payload, dict) and "result" in payload:
        charge = payload["result"]
        print(f"扣款结果摘要: {charge}")
        if idempotent:
            assert charge.get("count") == 1, "幂等路径累计扣款应为 1"
            assert charge.get("skipped") is True
            assert read_charge_count(session_id) == 1
        else:
            assert charge.get("count") == 2, "非幂等路径恢复后会再扣一次，累计应为 2"
            assert read_charge_count(session_id) == 2
    return result


async def run_all(*, interactive: bool = False) -> None:
    """按顺序跑完三课。"""
    await lesson_parallel()
    await lesson_interrupt(interactive=interactive)
    await lesson_side_effect(idempotent=False)
    await lesson_side_effect(idempotent=True)
    _banner("全部课程结束")
    print("对照 spec/断点续传与Pregel图模型.md 阅读 channel / pending / 命名空间。")
