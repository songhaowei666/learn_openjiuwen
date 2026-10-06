# coding: utf-8
"""把 SwarmFlow 脚本跑在同进程引擎里，并把进度事件推入 EventBridge。

agent() 不调用真实模型，由 InteractiveBackend 按 label 返回确定性结果，
这样 Demo 不依赖模型密钥。human() 会阻塞到 HumanManager 收到回复。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from openjiuwen.agent_teams.workflow.engine import run_workflow
from openjiuwen.agent_teams.workflow.engine.backends.base import AgentBackend, AgentResult
from openjiuwen.agent_teams.workflow.engine.progress import ProgressKind, WorkflowProgressEvent

from .a2ui_bridge import build_human_surface, delete_surface, visible_prompt
from .event_bridge import EventBridge
from .human_manager import HumanManager

_SCRIPT = Path(__file__).resolve().parent / "workflows" / "demo_workflow.py"

_AGENT_TOKENS = {
    "架构调研": 320,
    "能力调研": 280,
    "撰写报告": 640,
}


def _topic(prompt: str) -> str:
    """从 agent 提示词里取出用户问题。"""
    marker = "主题："
    if marker in prompt:
        rest = prompt.split(marker, 1)[1]
        for sep in ("。", "\n"):
            if sep in rest:
                rest = rest.split(sep, 1)[0]
                break
        return rest.strip() or "该主题"
    if "：" in prompt:
        return prompt.split("：", 1)[-1].strip() or "该主题"
    return prompt.strip() or "该主题"


def _agent_result(label: str | None, prompt: str) -> dict[str, Any]:
    """按节点 label 生成符合脚本 schema 的结构化结果。"""
    topic = _topic(prompt)
    if label == "架构调研":
        return {
            "summary": f"{topic} 用 SwarmFlow 脚本编排阶段，进度流与人工交互流分开传递。",
            "points": ["phase 划分阶段", "parallel 并行调研", "human 插入人工审批"],
        }
    if label == "能力调研":
        return {
            "summary": f"{topic} 能向前端推送进度树，并在 human 节点用 A2UI 收集回复。",
            "points": ["SSE 进度事件", "审批、选择、文本三种表单", "workflow_token_limit 预算"],
        }
    style = "详细报告" if "detailed" in prompt else "简报"
    focus = ""
    marker = "关注点："
    if marker in prompt:
        focus = prompt.split(marker, 1)[1].strip()
    body = f"主题「{topic}」已完成并行调研，并在人工确认后按{style}整理。"
    if focus:
        body = f"{body}补充关注点：{focus}。"
    return {"title": f"{topic} · {style}", "body": body}


def _first_text(value: Any) -> str:
    """把字符串或单选数组收成一个字符串。"""
    if isinstance(value, list):
        return _first_text(value[0]) if value else ""
    if value is None:
        return ""
    return str(value)


def _human_result(payload: dict[str, Any], schema_json: dict | None) -> Any:
    """把前端 action/context 收成脚本 schema 要求的对象。"""
    action = str(payload.get("action") or "")
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    required = []
    if isinstance(schema_json, dict):
        raw_required = schema_json.get("required")
        if isinstance(raw_required, list):
            required = [str(item) for item in raw_required]
    if "action" in required:
        return {"action": action, "reason": str(context.get("reason") or "")}
    if "style" in required:
        return {"style": _first_text(context.get("style")) or "brief"}
    if "focus" in required:
        return {"focus": str(context.get("focus") or context.get("text") or "")}
    if schema_json is None:
        return str(context.get("text") or action)
    return {"action": action, **{key: context.get(key) for key in required}}


class InteractiveBackend(AgentBackend):
    """离线 agent 执行器，human 会话改为等待真实用户回复。"""

    def __init__(self, humans: HumanManager, run_id: str) -> None:
        super().__init__()
        self._humans = humans
        self._run_id = run_id
        self._sessions: dict[str, str] = {}

    def _bill(self, tokens: int) -> None:
        """同时记入会话账本和本次 workflow 账本。"""
        self.budget.add(tokens)
        if self.workflow_budget is not None:
            self.workflow_budget.add(tokens)

    async def run(
        self,
        prompt: str,
        opts: dict,
        schema_json: dict | None,
        *,
        call_key: str | None = None,
    ) -> AgentResult:
        """执行一次无状态 agent 调用。"""
        label = opts.get("label")
        structured = _agent_result(str(label) if label else None, prompt)
        tokens = _AGENT_TOKENS.get(str(label), 100)
        self._bill(tokens)
        return AgentResult(
            structured=structured,
            text=json.dumps(structured, ensure_ascii=False),
            tokens=tokens,
            input_tokens=tokens // 2,
            output_tokens=tokens - tokens // 2,
        )

    async def ensure_member_name(self, *, kind: str, opts: dict) -> str:
        """给有状态会话一个稳定名字。human() 实际不会走到这里。"""
        return f"demo-{opts.get('label') or kind}"

    async def open_session(
        self,
        *,
        kind: str,
        instructions: str | None,
        opts: dict,
        fork_data: dict | None = None,
        member_name: str | None = None,
    ) -> str:
        """打开 human / agent 会话。Demo 只使用 human 会话。"""
        del instructions, fork_data
        sid = member_name or f"demo-{opts.get('label') or kind}-{len(self._sessions)}"
        self._sessions[sid] = kind
        return sid

    async def send_turn(
        self,
        session_id: str,
        prompt: str,
        opts: dict,
        schema_json: dict | None,
        *,
        history: Any = (),
        correlation_id: str | None = None,
    ) -> AgentResult:
        """推进一轮会话。human 会话阻塞到用户回复。"""
        del history, correlation_id
        kind = self._sessions.get(session_id, "agent")
        if kind == "human":
            payload = await self._humans.wait(self._run_id)
            structured = _human_result(payload if isinstance(payload, dict) else {}, schema_json)
            tokens = 16
            self._bill(tokens)
            if schema_json is None:
                return AgentResult(text=str(structured), tokens=tokens)
            return AgentResult(
                structured=structured,
                text=json.dumps(structured, ensure_ascii=False),
                tokens=tokens,
                input_tokens=8,
                output_tokens=8,
            )
        label = opts.get("label")
        structured = _agent_result(str(label) if label else None, prompt)
        tokens = _AGENT_TOKENS.get(str(label), 100)
        self._bill(tokens)
        return AgentResult(structured=structured, text=json.dumps(structured, ensure_ascii=False), tokens=tokens)

    async def close_session(self, session_id: str) -> None:
        """关闭会话。"""
        self._sessions.pop(session_id, None)

    async def aclose(self) -> None:
        """引擎收尾时清掉会话。未完成的 human 等待留给 runner 取消。"""
        self._sessions.clear()


class _Projector:
    """把引擎进度事件折叠成前端进度树节点。"""

    def __init__(self) -> None:
        self.workflow_id = "workflow"
        self.workflow_label = "workflow"
        self.current_phase_id: str | None = None
        self._human_surfaces: dict[str, str] = {}
        self._seq = 0

    def project(self, event: WorkflowProgressEvent) -> list[dict[str, Any]]:
        """返回零条或多条 progress 载荷。"""
        kind = event.kind
        if kind == ProgressKind.WORKFLOW_STARTED:
            self.workflow_label = event.description or event.name or "workflow"
            return [
                _node(
                    self.workflow_id,
                    "workflow",
                    self.workflow_label,
                    "running",
                    None,
                    detail=event.message,
                )
            ]
        if kind == ProgressKind.PHASE:
            title = event.phase or "阶段"
            phase_id = f"phase:{title}"
            updates = []
            if self.current_phase_id and self.current_phase_id != phase_id:
                updates.append(
                    _node(self.current_phase_id, "phase", _phase_label(self.current_phase_id), "completed", self.workflow_id)
                )
            self.current_phase_id = phase_id
            updates.append(_node(phase_id, "phase", title, "running", self.workflow_id))
            return updates
        if kind == ProgressKind.AGENT_STARTED:
            node_id = event.agent_id or event.label or "agent"
            node_type = "human" if event.node_type in {"human", "human_session"} else "agent"
            status = "waiting_for_human" if node_type == "human" else "running"
            if node_type == "human":
                self._human_surfaces[node_id] = _surface_id(node_id)
            return [
                _node(
                    node_id,
                    node_type,
                    event.label or node_type,
                    status,
                    self.current_phase_id or self.workflow_id,
                    detail=visible_prompt(event.prompt or "") if node_type == "human" else None,
                )
            ]
        if kind == ProgressKind.AGENT_COMPLETED:
            node_id = event.agent_id or event.label or "agent"
            node_type = "human" if node_id in self._human_surfaces else "agent"
            return [
                _node(
                    node_id,
                    node_type,
                    event.label or node_id,
                    "completed",
                    self.current_phase_id or self.workflow_id,
                    tokens=event.tokens,
                    detail=event.outcome,
                )
            ]
        if kind == ProgressKind.AGENT_FAILED:
            node_id = event.agent_id or event.label or "agent"
            return [
                _node(
                    node_id,
                    "agent",
                    event.label or node_id,
                    "failed",
                    self.current_phase_id or self.workflow_id,
                    detail=event.message,
                )
            ]
        if kind == ProgressKind.LOG:
            self._seq += 1
            return [
                _node(
                    f"log:{self._seq}",
                    "log",
                    event.message or "日志",
                    "completed",
                    self.current_phase_id or self.workflow_id,
                )
            ]
        if kind == ProgressKind.WORKFLOW_COMPLETED:
            updates = []
            if self.current_phase_id:
                updates.append(
                    _node(
                        self.current_phase_id,
                        "phase",
                        _phase_label(self.current_phase_id),
                        "completed",
                        self.workflow_id,
                    )
                )
            updates.append(
                _node(self.workflow_id, "workflow", self.workflow_label, "completed", None, detail=event.message)
            )
            return updates
        if kind == ProgressKind.WORKFLOW_FAILED:
            return [
                _node(
                    self.workflow_id,
                    "workflow",
                    event.name or "workflow",
                    "failed",
                    None,
                    detail=event.message,
                )
            ]
        return []

    def surface_for(self, agent_id: str | None) -> str | None:
        """human 节点对应的 A2UI surfaceId。"""
        if not agent_id:
            return None
        return self._human_surfaces.get(agent_id)


def _surface_id(agent_id: str) -> str:
    """把引擎节点 id 收成 A2UI 可用的 surfaceId。"""
    chars: list[str] = []
    prev_dash = False
    for char in agent_id:
        if char.isalnum():
            chars.append(char)
            prev_dash = False
        elif not prev_dash:
            chars.append("-")
            prev_dash = True
    token = "".join(chars).strip("-") or "human"
    return f"surface-{token}"


def _phase_label(phase_id: str) -> str:
    """从 phase:{title} 还原标题。"""
    prefix = "phase:"
    if phase_id.startswith(prefix):
        return phase_id[len(prefix):]
    return phase_id


def _node(
    node_id: str,
    node_type: str,
    label: str,
    status: str,
    parent_id: str | None,
    *,
    tokens: int | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """组装一条前端进度事件。"""
    payload: dict[str, Any] = {
        "type": "progress",
        "nodeId": node_id,
        "nodeType": node_type,
        "label": label,
        "status": status,
        "parentId": parent_id,
        "tokens": tokens,
    }
    if detail:
        payload["detail"] = detail
    return payload


def _jsonable(value: Any) -> Any:
    """把脚本返回值收成可 JSON 序列化的对象。"""
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


async def run_demo(run_id: str, question: str, bridge: EventBridge, humans: HumanManager) -> None:
    """启动预编写脚本，并把进度 / A2UI / 结束事件写入桥。"""
    projector = _Projector()
    backend = InteractiveBackend(humans, run_id)

    def on_progress(event: WorkflowProgressEvent) -> None:
        """同步消费引擎事件，保证 human Future 在 send_turn 之前就位。"""
        if event.kind == ProgressKind.AGENT_STARTED and event.node_type in {"human", "human_session"}:
            humans.begin(run_id)
        for payload in projector.project(event):
            bridge.publish("progress", payload)
        if event.kind == ProgressKind.AGENT_STARTED and event.node_type in {"human", "human_session"}:
            surface_id = projector.surface_for(event.agent_id)
            if surface_id:
                bridge.publish(
                    "a2ui",
                    {
                        "type": "a2ui",
                        "surfaceId": surface_id,
                        "nodeId": event.agent_id,
                        "messages": build_human_surface(surface_id, event.prompt or "", event.label or ""),
                    },
                )
        if event.kind == ProgressKind.AGENT_COMPLETED:
            surface_id = projector.surface_for(event.agent_id)
            if surface_id:
                bridge.publish(
                    "a2ui",
                    {
                        "type": "a2ui",
                        "surfaceId": surface_id,
                        "nodeId": event.agent_id,
                        "messages": delete_surface(surface_id),
                    },
                )

    try:
        result = await run_workflow(
            str(_SCRIPT),
            args=question,
            backend=backend,
            progress_sink=on_progress,
            run_id=run_id,
        )
        bridge.publish("done", {"ok": True, "result": _jsonable(result)})
    except asyncio.CancelledError:
        bridge.publish("done", {"ok": False, "error": "运行已取消"})
        raise
    except Exception as exc:  # noqa: BLE001 - 需要把引擎异常显示到前端
        bridge.publish(
            "progress",
            _node("workflow", "workflow", "workflow", "failed", None, detail=str(exc)),
        )
        bridge.publish("done", {"ok": False, "error": str(exc)})
    finally:
        humans.cancel(run_id)
