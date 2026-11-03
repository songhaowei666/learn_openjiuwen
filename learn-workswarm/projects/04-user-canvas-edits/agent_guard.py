"""Agent 是否尊重 user_canvas_edits（学习用守卫）。

对应 Leader prompt 硬规则（agents/swarm/assembly.py）：
  user_canvas_edits 是已发生的事实——不要恢复被删除的节点或被断开的边。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GuardVerdict:
    ok: bool
    reason: str


def _removed_node_ids(edits: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("node_id") or "").strip()
        for item in edits
        if str(item.get("op") or "") == "remove" and str(item.get("node_id") or "").strip()
    }


def _disconnected_pairs(edits: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for item in edits:
        if str(item.get("op") or "") != "disconnect":
            continue
        a = str(item.get("node_id") or "").strip()
        b = str(item.get("peer_id") or "").strip()
        if a and b:
            pairs.add(tuple(sorted((a, b))))
    return pairs


def judge_agent_patch(
    metadata: dict[str, Any] | None,
    *,
    upsert_node_ids: list[str] | None = None,
    upsert_edges: list[dict[str, str]] | None = None,
) -> GuardVerdict:
    """检查一次「拟议 patch」是否在帮用户恢复已删节点/已断边。"""
    edits_raw = (metadata or {}).get("user_canvas_edits")
    edits = [item for item in edits_raw if isinstance(item, dict)] if isinstance(edits_raw, list) else []
    removed = _removed_node_ids(edits)
    disconnected = _disconnected_pairs(edits)

    for node_id in upsert_node_ids or []:
        nid = str(node_id or "").strip()
        if nid and nid in removed:
            return GuardVerdict(
                False,
                f"禁止恢复用户已删除的节点: {nid!r}",
            )

    for edge in upsert_edges or []:
        a = str(edge.get("source") or "").strip()
        b = str(edge.get("target") or "").strip()
        if a and b and tuple(sorted((a, b))) in disconnected:
            return GuardVerdict(
                False,
                f"禁止恢复用户已断开的边: {a!r} ↔ {b!r}",
            )

    return GuardVerdict(True, "ok")
