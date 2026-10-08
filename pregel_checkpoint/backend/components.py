# -*- coding: UTF-8 -*-
"""学习用自定义组件：无模型、行为确定，方便观察超步与重入。"""

from __future__ import annotations

import json
from pathlib import Path

from openjiuwen.core.context_engine import ModelContext
from openjiuwen.core.graph.executable import Input, Output
from openjiuwen.core.workflow import End, Start, WorkflowComponent
from openjiuwen.core.workflow.components import Session

from .setup import WORKSPACE_DIR


def _log(node: str, msg: str) -> None:
    print(f"  [{node}] {msg}")


class EchoStart(Start):
    """开始节点：透传输入，并记一次调用日志。"""

    async def invoke(self, inputs: Input, session: Session, context: ModelContext) -> Output:
        _log("start", f"收到输入 {inputs}")
        return inputs


class EchoEnd(End):
    """结束节点：把汇合结果原样返回。"""

    async def invoke(self, inputs: Input, session: Session, context: ModelContext) -> Output:
        _log("end", f"最终输出 {inputs}")
        return inputs


class TagNode(WorkflowComponent):
    """并行分支节点：给文本打标签，模拟同超步并行执行。"""

    def __init__(self, tag: str):
        super().__init__()
        self._tag = tag

    async def invoke(self, inputs: Input, session: Session, context: ModelContext) -> Output:
        text = inputs.get("text", "")
        out = {"tag": self._tag, "text": f"{self._tag}:{text}"}
        _log(self._tag, f"处理完成 -> {out}")
        return out


class MergeNode(WorkflowComponent):
    """汇合节点：合并左右分支输出（需 wait_for_all）。

    互斥分支场景下未走的一侧可能是 None，只拼接有值的一侧。
    """

    async def invoke(self, inputs: Input, session: Session, context: ModelContext) -> Output:
        left_text = inputs.get("left_text")
        right_text = inputs.get("right_text")
        parts = [p for p in (left_text, right_text) if p not in (None, "")]
        out = {
            "left_text": left_text,
            "right_text": right_text,
            "merged": " | ".join(parts),
        }
        _log("merge", f"屏障满足，汇合输出 -> {out['merged']!r}")
        return out


class AskHumanNode(WorkflowComponent):
    """人机节点：session.interact 触发中断，外层看到 INPUT_REQUIRED。"""

    async def invoke(self, inputs: Input, session: Session, context: ModelContext) -> Output:
        draft = inputs.get("draft", "")
        _log("ask", f"草稿已就绪，向人提问。draft={draft!r}")
        answer = await session.interact(f"请确认或修改草稿（当前：{draft}）")
        _log("ask", f"收到人工回复 {answer!r}")
        if isinstance(answer, dict):
            final_text = answer.get("text", draft)
        else:
            final_text = answer if answer not in (None, "") else draft
        return {"approved_text": final_text, "raw_answer": answer}


def _charge_ledger_path(session_id: str) -> Path:
    """外部副作用账本：模拟真实扣款不会随工作流事务回滚。"""
    return WORKSPACE_DIR / f"charge_{session_id}.json"


def read_charge_count(session_id: str) -> int:
    path = _charge_ledger_path(session_id)
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    return int(data.get("count", 0))


class SideEffectNode(WorkflowComponent):
    """
    带外部副作用的节点。

    注意：节点内 update_global_state 在同超步抛错时可能被回滚；
    真实副作用（写文件 / 调支付）不会回滚，因此要用外部账本演示重入。
    """

    def __init__(self, *, idempotent: bool, session_id: str):
        super().__init__()
        self._idempotent = idempotent
        self._session_id = session_id

    async def invoke(self, inputs: Input, session: Session, context: ModelContext) -> Output:
        amount = int(inputs.get("amount", 1))
        path = _charge_ledger_path(self._session_id)
        count = read_charge_count(self._session_id)
        done = path.exists() and json.loads(path.read_text(encoding="utf-8")).get("done")
        crashed = path.exists() and json.loads(path.read_text(encoding="utf-8")).get("crashed")

        if self._idempotent and done:
            _log("charge", f"幂等守卫命中，跳过真实扣款。count={count}")
            return {"charged": True, "count": count, "skipped": True}

        count += 1
        record = {
            "count": count,
            "last_amount": amount,
            "done": bool(self._idempotent),
            "crashed": True if not crashed else True,
        }
        # 先落外部账本，再决定是否「崩溃」——模拟扣款 API 已成功、进程随后挂掉
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        _log("charge", f"外部账本已写入 {path.name}，累计次数 count={count}")

        if not crashed:
            raise RuntimeError("模拟扣款后进程崩溃（外部副作用已发生，工作流检查点应保留 pending）")

        return {"charged": True, "count": count, "skipped": False}
