"""Design 会话绑定规则（学习用，贴合 gateway/common/work_mode.py 语义）。

真实产品里 session ↔ project ↔ graph 的装配分散在 gateway / team_bridge；
这里把「一项目一会话一画布」收成可单测的纯函数，方便动手。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gateway.common.work_mode import (
    DESIGN_WORK_MODE,
    EXECUTION_WORK_MODES,
    is_default_project_id,
    normalize_work_mode,
)


@dataclass(frozen=True)
class BindingResult:
    ok: bool
    reason: str


def uses_execution_profile(work_mode: str) -> bool:
    """design 不进 work/code 的 Agent 执行 profile / mode_matrix。"""
    return normalize_work_mode(work_mode) in EXECUTION_WORK_MODES


def validate_design_binding(
    *,
    work_mode: Any,
    project_id: str | None,
    session_id: str | None,
    graph_id: str | None,
    graph_project_id: str | None = None,
) -> BindingResult:
    """校验 design 工作区绑定是否合法。

    规则（来自 work_mode 注释 + 领域不变量）：
    1. work_mode 必须是 design
    2. 必须有真实 session_id / project_id / graph_id
    3. project_id 不能是虚拟默认项目（default / default_code）
    4. 若提供 graph.project_id，必须与会话 project_id 一致
    """
    mode = normalize_work_mode(work_mode, default="")
    if mode != DESIGN_WORK_MODE:
        return BindingResult(False, f"work_mode 必须是 {DESIGN_WORK_MODE!r}，实际 {mode!r}")

    if not isinstance(session_id, str) or not session_id.strip():
        return BindingResult(False, "session_id 必填")
    if not isinstance(project_id, str) or not project_id.strip():
        return BindingResult(False, "project_id 必填（design 无虚拟默认项目）")
    if is_default_project_id(project_id):
        return BindingResult(
            False,
            f"design 禁止虚拟默认项目: {project_id!r}",
        )
    if not isinstance(graph_id, str) or not graph_id.strip():
        return BindingResult(False, "graph_id 必填（一会话一画布）")

    if graph_project_id is not None:
        if not isinstance(graph_project_id, str) or not graph_project_id.strip():
            return BindingResult(False, "graph.project_id 非法")
        if graph_project_id.strip() != project_id.strip():
            return BindingResult(
                False,
                f"graph.project_id={graph_project_id!r} 与 session.project_id={project_id!r} 不一致",
            )

    return BindingResult(True, "ok")
