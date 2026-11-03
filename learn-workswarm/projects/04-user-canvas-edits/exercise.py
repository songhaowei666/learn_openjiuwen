#!/usr/bin/env python3
"""知识点 1.4：user_canvas_edits

移植/对齐：
  - 前端 appendUserCanvasEdit（canvas_edits.py）
  - orchestration.note_user_canvas_edits（awareness.py）
  - Leader prompt：不得恢复删除/断边（agent_guard.py）

用法：
  python learn-workswarm/projects/04-user-canvas-edits/exercise.py
  python learn-workswarm/projects/04-user-canvas-edits/exercise.py --check
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _boot import REPO_ROOT  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agent_guard import judge_agent_patch  # noqa: E402
from awareness import note_user_canvas_edits  # noqa: E402
from canvas_edits import append_user_canvas_edit, canvas_edit_glance  # noqa: E402


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def demo_user_edits() -> dict:
    graph = _load(HERE / "fixtures" / "graph_before_edits.json")
    print("\n=== 模拟用户手改 ===")
    meta = dict(graph.get("metadata") or {})

    # 用户删除 robot 角色
    meta = append_user_canvas_edit(
        meta,
        op="remove",
        node_id="n_character_2",
        label="Character 2: Robot",
        type="image",
        role="image",
    )
    # 用户断开 brief→character_1
    meta = append_user_canvas_edit(
        meta,
        op="disconnect",
        node_id="n_brief",
        peer_id="n_character_1",
    )
    # 用户新加一个 scene
    meta = append_user_canvas_edit(
        meta,
        op="add",
        node_id="n_scene_1",
        label="Scene 1: Hangar",
        type="image",
        role="image",
    )

    graph["metadata"] = meta
    # 同步拓扑（真实前端会改 nodes/edges；这里演示 edits 记账）
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] != "n_character_2"]
    graph["nodes"].append(
        {
            "id": "n_scene_1",
            "type": "image",
            "label": "Scene 1: Hangar",
            "config": {"pipeline": "scene", "prompt": "机库"},
            "layout": {"x": 640, "y": 0},
        }
    )
    graph["edges"] = [
        e
        for e in graph["edges"]
        if not (
            e["source"] == "n_brief"
            and e["target"] in {"n_character_1", "n_character_2"}
        )
    ]

    notes = note_user_canvas_edits(graph)
    print(f"  edits glance = {canvas_edit_glance(graph['metadata']['user_canvas_edits'])!r}")
    print(f"  awareness notes = {notes}")
    print(f"  edits count = {len(graph['metadata']['user_canvas_edits'])}")
    out = HERE / "out_graph_with_edits.json"
    out.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        shown = out.resolve().relative_to(REPO_ROOT)
    except ValueError:
        shown = out
    print(f"  已写出: {shown}")
    return graph


def demo_agent_guard(graph: dict) -> None:
    meta = graph.get("metadata") or {}
    print("\n=== Agent 拟议动作守卫 ===")

    bad_restore_node = judge_agent_patch(
        meta,
        upsert_node_ids=["n_character_2"],
    )
    print(f"  恢复已删节点: ok={bad_restore_node.ok} — {bad_restore_node.reason}")

    bad_restore_edge = judge_agent_patch(
        meta,
        upsert_edges=[{"source": "n_brief", "target": "n_character_1"}],
    )
    print(f"  恢复已断边:   ok={bad_restore_edge.ok} — {bad_restore_edge.reason}")

    good_extend = judge_agent_patch(
        meta,
        upsert_node_ids=["n_storyboard"],
        upsert_edges=[{"source": "n_brief", "target": "n_scene_1"}],
    )
    print(f"  合法继续创作: ok={good_extend.ok} — {good_extend.reason}")

    assert bad_restore_node.ok is False
    assert bad_restore_edge.ok is False
    assert good_extend.ok is True
    print("  OK: 守卫行为符合 Leader 硬规则")
    print(
        "  Prompt 原文见: "
        f"{REPO_ROOT / 'jiuwenswarm/agents/swarm/assembly.py'} （user_canvas_edits 句）"
    )


def check_student_actions() -> int:
    path = HERE / "my_agent_actions.json"
    print(f"\n=== 练习验收: {path.name} ===")
    graph_path = HERE / "out_graph_with_edits.json"
    if not graph_path.exists():
        print("  请先无参运行一次 exercise.py，生成 out_graph_with_edits.json")
        return 1
    graph = _load(graph_path)
    meta = graph.get("metadata") or {}
    raw = _load(path)
    if "FIXME" in json.dumps(raw, ensure_ascii=False):
        print("  还有 FIXME：为每个动作填写 allow=true/false")
        return 1

    failed = 0
    for action in raw.get("actions") or []:
        name = action.get("name")
        expect_allow = bool(action.get("allow"))
        verdict = judge_agent_patch(
            meta,
            upsert_node_ids=action.get("upsert_node_ids") or [],
            upsert_edges=action.get("upsert_edges") or [],
        )
        actual_allow = verdict.ok
        mark = "PASS" if actual_allow == expect_allow else "FAIL"
        print(
            f"  [{mark}] {name}: expect_allow={expect_allow} actual={actual_allow} "
            f"({verdict.reason})"
        )
        if actual_allow != expect_allow:
            failed += 1
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="学习项目 04：user_canvas_edits")
    parser.add_argument("--check", action="store_true", help="验收 my_agent_actions.json")
    args = parser.parse_args()

    if args.check:
        return check_student_actions()

    graph = demo_user_edits()
    demo_agent_guard(graph)
    # 确保练习文件存在提示
    print("\n下一步：编辑 my_agent_actions.json，判断每个动作该不该允许，然后：")
    print("  python learn-workswarm/projects/04-user-canvas-edits/exercise.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
