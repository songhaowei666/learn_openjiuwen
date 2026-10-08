# -*- coding: UTF-8 -*-
"""三张学习用静态工作流图。"""

from __future__ import annotations

from openjiuwen.core.workflow import Workflow, WorkflowCard

from .components import (
    AskHumanNode,
    EchoEnd,
    EchoStart,
    MergeNode,
    SideEffectNode,
    TagNode,
)


def build_parallel_workflow() -> Workflow:
    """
    start ──► left ──► merge(wait_for_all) ──► end
         └─► right ─┘

    演示：多出边并行 + wait_for_all 汇合（底层是 BarrierChannel）。
    """
    flow = Workflow(card=WorkflowCard(id="lesson_parallel", name="并行汇合"))
    flow.set_start_comp(
        "start",
        EchoStart(),
        inputs_schema={"text": "${query}"},
    )
    flow.add_workflow_comp(
        "left",
        TagNode("left"),
        inputs_schema={"text": "${start.text}"},
    )
    flow.add_workflow_comp(
        "right",
        TagNode("right"),
        inputs_schema={"text": "${start.text}"},
    )
    flow.add_workflow_comp(
        "merge",
        MergeNode(),
        wait_for_all=True,
        inputs_schema={
            "left_text": "${left.text}",
            "right_text": "${right.text}",
        },
    )
    flow.set_end_comp(
        "end",
        EchoEnd(),
        inputs_schema={"result": "${merge}"},
    )
    flow.add_connection("start", "left")
    flow.add_connection("start", "right")
    flow.add_connection("left", "merge")
    flow.add_connection("right", "merge")
    flow.add_connection("merge", "end")
    return flow


def build_interrupt_workflow() -> Workflow:
    """
    start ──► ask ──► end

    演示：session.interact 中断 + InteractiveInput 同 session_id 续跑。
    """
    flow = Workflow(card=WorkflowCard(id="lesson_interrupt", name="人机中断续跑"))
    flow.set_start_comp(
        "start",
        EchoStart(),
        inputs_schema={"draft": "${query}"},
    )
    flow.add_workflow_comp(
        "ask",
        AskHumanNode(),
        inputs_schema={"draft": "${start.draft}"},
    )
    flow.set_end_comp(
        "end",
        EchoEnd(),
        inputs_schema={"result": "${ask}"},
    )
    flow.add_connection("start", "ask")
    flow.add_connection("ask", "end")
    return flow


def build_side_effect_workflow(*, idempotent: bool, session_id: str) -> Workflow:
    """
    start ──► charge ──► end

    演示：异常后 pending 节点重入；幂等守卫避免重复副作用。
    session_id 用于外部账本文件名，模拟不会随超步回滚的真实副作用。
    """
    card_id = "lesson_idempotent" if idempotent else "lesson_reenter"
    flow = Workflow(
        card=WorkflowCard(
            id=card_id,
            name="幂等守卫" if idempotent else "异常重入",
        )
    )
    flow.set_start_comp(
        "start",
        EchoStart(),
        inputs_schema={"amount": "${amount}"},
    )
    flow.add_workflow_comp(
        "charge",
        SideEffectNode(idempotent=idempotent, session_id=session_id),
        inputs_schema={"amount": "${start.amount}"},
    )
    flow.set_end_comp(
        "end",
        EchoEnd(),
        inputs_schema={"result": "${charge}"},
    )
    flow.add_connection("start", "charge")
    flow.add_connection("charge", "end")
    return flow
