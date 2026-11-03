"""用户画布手改日志 —— 从前端忠实移植。

源：jiuwenswarm/channels/web/frontend/src/features/designer/designerCanvasNodes.ts
  - UserCanvasEdit
  - appendUserCanvasEdit
"""

from __future__ import annotations

import time
from typing import Any, Literal

CanvasEditOp = Literal["add", "remove", "connect", "disconnect", "replace"]

CANVAS_EDIT_OPS: frozenset[str] = frozenset(
    {"add", "remove", "connect", "disconnect", "replace"}
)

# 与 TS appendUserCanvasEdit 一致：只保留最近 40 条
USER_CANVAS_EDITS_LIMIT = 40


def append_user_canvas_edit(
    metadata: dict[str, Any] | None,
    *,
    op: CanvasEditOp,
    node_id: str,
    peer_id: str | None = None,
    label: str | None = None,
    role: str | None = None,
    type: str | None = None,
    at: int | None = None,
) -> dict[str, Any]:
    """等价于前端 appendUserCanvasEdit。"""
    previous = []
    if isinstance(metadata, dict) and isinstance(metadata.get("user_canvas_edits"), list):
        previous = [
            item
            for item in metadata["user_canvas_edits"]
            if isinstance(item, dict)
        ]
    next_edit: dict[str, Any] = {
        "op": op,
        "node_id": node_id,
        "at": at if isinstance(at, int) else int(time.time() * 1000),
    }
    if peer_id:
        next_edit["peer_id"] = peer_id
    if label:
        next_edit["label"] = label
    if role:
        next_edit["role"] = role
    if type:
        next_edit["type"] = type
    base = dict(metadata or {})
    base["user_topology_edit"] = True
    base["user_canvas_edits"] = [*previous, next_edit][-USER_CANVAS_EDITS_LIMIT:]
    return base


def canvas_edit_glance(edits: Any) -> str:
    """等价于前端 canvasEditGlance：返回最近一次合法 op，否则空串。"""
    if not isinstance(edits, list):
        return ""
    for item in reversed(edits):
        if not isinstance(item, dict):
            continue
        op = str(item.get("op") or "")
        if op in CANVAS_EDIT_OPS:
            return op
    return ""
