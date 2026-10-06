# coding: utf-8
"""预编写的调研报告 SwarmFlow 脚本。

覆盖并行 agent、审批 / 选择 / 文本三类 human 节点，以及 META 里的阶段和预算上限。
agent 节点由同进程 InteractiveBackend 返回确定性结果；human 节点阻塞等待前端回复。
"""

from swarmflow import agent, budget, human, log, parallel, phase

META = {
    "name": "research-report",
    "description": "并行调研后经人工审批，再按选定风格生成报告",
    "phases": [
        {"title": "调研", "description": "并行收集架构与能力要点"},
        {"title": "审批", "description": "人工确认是否继续"},
        {"title": "撰写", "description": "按选定风格生成报告"},
    ],
    "workflow_token_limit": 2000,
}

_FINDING = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "points"],
    "properties": {
        "summary": {"type": "string"},
        "points": {"type": "array", "items": {"type": "string"}},
    },
}

_APPROVAL = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "reason"],
    "properties": {
        "action": {"type": "string"},
        "reason": {"type": "string"},
    },
}

_STYLE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["style"],
    "properties": {"style": {"type": "string"}},
}

_FOCUS = {
    "type": "object",
    "additionalProperties": False,
    "required": ["focus"],
    "properties": {"focus": {"type": "string"}},
}

_REPORT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "body"],
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
    },
}


def _summary(result: object) -> str:
    """取出结构化结果里的摘要，缺省时给空串。"""
    if isinstance(result, dict):
        return str(result.get("summary") or "")
    return ""


async def run(args):
    """执行调研、审批、撰写。args 为用户在前端输入的问题。"""
    question = args if isinstance(args, str) else ""
    phase("调研")
    log(f"开始调研：{question}")
    architecture, capability = await parallel(
        [
            lambda: agent(
                f"请调研该主题的架构设计：{question}",
                label="架构调研",
                schema=_FINDING,
            ),
            lambda: agent(
                f"请调研该主题的核心能力：{question}",
                label="能力调研",
                schema=_FINDING,
            ),
        ]
    )
    phase("审批")
    decision = await human(
        "[approval]\n调研结果已就绪，是否继续生成报告？\n"
        f"主题：{question}\n"
        f"架构：{_summary(architecture)}\n"
        f"能力：{_summary(capability)}",
        label="审批调研",
        schema=_APPROVAL,
    )
    action = decision.get("action") if isinstance(decision, dict) else ""
    if action != "approve":
        reason = decision.get("reason") if isinstance(decision, dict) else ""
        log(f"已驳回：{reason or '未填写理由'}")
        return {"status": "rejected", "reason": reason}

    phase("撰写")
    style = await human(
        "[choice:brief=简报|detailed=详细报告]\n请选择报告风格",
        label="选择风格",
        schema=_STYLE,
    )
    style_name = style.get("style") if isinstance(style, dict) else "brief"
    focus = await human(
        "[text]\n如需补充关注点，请填写后提交；没有可直接提交",
        label="补充关注点",
        schema=_FOCUS,
    )
    focus_text = focus.get("focus") if isinstance(focus, dict) else ""
    log(f"当前剩余预算：{budget.remaining()}")
    report = await agent(
        f"按风格 {style_name} 撰写报告。主题：{question}。关注点：{focus_text}",
        label="撰写报告",
        schema=_REPORT,
    )
    log("报告已生成")
    return report
