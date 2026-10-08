# -*- coding: UTF-8 -*-
"""初始化持久化 Checkpointer，落盘到本 demo 的 workspace。"""

from __future__ import annotations

from pathlib import Path

from openjiuwen.core.session.checkpointer import CheckpointerFactory
from openjiuwen.core.session.checkpointer.checkpointer import CheckpointerConfig

# 检查点文件目录，相对本包上级（shelve 不依赖 aiosqlite）
WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "workspace"
CHECKPOINT_DB = WORKSPACE_DIR / "checkpointer"


async def ensure_checkpointer() -> None:
    """使用 shelve 持久化检查点，进程重启后同一 session_id 仍可续跑。"""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    checkpointer = await CheckpointerFactory.create(
        CheckpointerConfig(
            type="persistence",
            conf={
                "db_type": "shelve",
                "db_path": str(CHECKPOINT_DB),
            },
        )
    )
    CheckpointerFactory.set_default_checkpointer(checkpointer)


def summarize_graph_state(state) -> dict:
    """把 GraphState 收成可读摘要，方便对照 Pregel 运行时字段。"""
    if state is None:
        return {"exists": False}
    pending_names = list(state.pending_node.keys()) if state.pending_node else []
    return {
        "exists": True,
        "ns": state.ns,
        "step": state.step,
        "pending_nodes": pending_names,
        "pending_buffer_len": len(state.pending_buffer or []),
        "channel_keys": list((state.channel_values or {}).keys()),
        "node_version": dict(state.node_version or {}),
    }
