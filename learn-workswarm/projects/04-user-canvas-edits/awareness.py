"""Director / Agent 侧如何「看见」用户手改。

源：jiuwenswarm/server/runtime/designer/orchestration.py::note_user_canvas_edits
（学习精简版：只生成 awareness 摘要与 notes，不回写无关 metadata 清理分支之外的逻辑）
"""

from __future__ import annotations

from typing import Any


def note_user_canvas_edits(graph: dict[str, Any]) -> list[str]:
    """把 metadata.user_canvas_edits 收成 director_canvas_awareness + 短 notes。"""
    meta = dict(graph.get("metadata") or {})
    raw = meta.get("user_canvas_edits")
    edits = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    added = [item for item in edits if str(item.get("op") or "") == "add"]
    removed = [item for item in edits if str(item.get("op") or "") == "remove"]
    connected = [item for item in edits if str(item.get("op") or "") == "connect"]
    disconnected = [item for item in edits if str(item.get("op") or "") == "disconnect"]
    replaced = [item for item in edits if str(item.get("op") or "") == "replace"]

    if not edits:
        if "director_canvas_awareness" in meta:
            meta.pop("director_canvas_awareness", None)
            graph["metadata"] = meta
        return []

    def _brief(item: dict[str, Any]) -> dict[str, str]:
        brief = {
            "node_id": str(item.get("node_id") or ""),
            "label": str(item.get("label") or ""),
            "role": str(item.get("role") or ""),
            "type": str(item.get("type") or ""),
        }
        peer = str(item.get("peer_id") or "").strip()
        if peer:
            brief["peer_id"] = peer
        return brief

    meta["director_canvas_awareness"] = {
        "added": [_brief(item) for item in added[-20:]],
        "removed": [_brief(item) for item in removed[-20:]],
        "connected": [_brief(item) for item in connected[-20:]],
        "disconnected": [_brief(item) for item in disconnected[-20:]],
        "replaced": [_brief(item) for item in replaced[-20:]],
    }
    graph["metadata"] = meta

    notes: list[str] = []
    if added:
        notes.append(
            "canvas_added:" + ",".join(str(item.get("node_id") or "") for item in added[-8:])
        )
    if removed:
        notes.append(
            "canvas_removed:" + ",".join(str(item.get("node_id") or "") for item in removed[-8:])
        )
    if connected:
        notes.append(
            "canvas_connected:"
            + ",".join(str(item.get("node_id") or "") for item in connected[-8:])
        )
    if disconnected:
        notes.append(
            "canvas_disconnected:"
            + ",".join(str(item.get("node_id") or "") for item in disconnected[-8:])
        )
    if replaced:
        notes.append(
            "canvas_replaced:"
            + ",".join(str(item.get("node_id") or "") for item in replaced[-8:])
        )
    return notes
