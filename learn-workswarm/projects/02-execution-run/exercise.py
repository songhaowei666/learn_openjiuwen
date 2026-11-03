#!/usr/bin/env python3
"""知识点 1.2：运行态契约 designer-execution-run.v1

真实入口：
  normalize_execution_run / apply_node_activity / LEADER_NODE_ID
  jiuwenswarm.common.schema.designer_graph

用法：
  python learn-workswarm/projects/02-execution-run/exercise.py
  python learn-workswarm/projects/02-execution-run/exercise.py --advance
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _boot import REPO_ROOT, load_designer_graph  # noqa: E402

_dg = load_designer_graph()
LEADER_NODE_ID = _dg.LEADER_NODE_ID
NODE_STATUS_COMPLETED = _dg.NODE_STATUS_COMPLETED
NODE_STATUS_RUNNING = _dg.NODE_STATUS_RUNNING
RUN_STATUS_RUNNING = _dg.RUN_STATUS_RUNNING
RUN_TRIGGER_SOURCE_CANVAS = _dg.RUN_TRIGGER_SOURCE_CANVAS
RUN_TRIGGER_SOURCE_LEADER = _dg.RUN_TRIGGER_SOURCE_LEADER
DesignerGraphValidationError = _dg.DesignerGraphValidationError
apply_node_activity = _dg.apply_node_activity
normalize_execution_run = _dg.normalize_execution_run
utc_now_ms = _dg.utc_now_ms

HERE = Path(__file__).resolve().parent
GRAPH_FIXTURE = (
    HERE.parent / "01-execution-graph" / "fixtures" / "good_brief_character.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def demo_normalize() -> dict:
    path = HERE / "fixtures" / "sample_run.json"
    print(f"\n=== 归一化 run: {path.name} ===")
    run = normalize_execution_run(_load(path))
    print(f"  run_id={run['run_id']} status={run['status']}")
    print(f"  trigger_source={run.get('metadata', {}).get('trigger_source')}")
    print(f"  node_states keys = {sorted(run['node_states'])}")
    if LEADER_NODE_ID in run["node_states"]:
        print(f"  注意: {LEADER_NODE_ID!r} 只存在于 run，不应出现在 graph.nodes")
    graph = _load(GRAPH_FIXTURE)
    graph_ids = {n["id"] for n in graph["nodes"]}
    if LEADER_NODE_ID in graph_ids:
        raise SystemExit("graph fixture 不应包含 __leader__")
    print(f"  graph.nodes = {sorted(graph_ids)}（无 leader）")
    print("  OK")
    return run


def advance_once(run: dict) -> dict:
    """模拟：canvas 触发 → brief running → completed + 产出。"""
    now = utc_now_ms()
    next_run = copy.deepcopy(run)
    next_run["status"] = RUN_STATUS_RUNNING
    next_run["metadata"] = {
        **dict(next_run.get("metadata") or {}),
        "trigger_source": RUN_TRIGGER_SOURCE_CANVAS,
    }
    next_run["current_node_ids"] = ["n_brief"]

    brief = dict(next_run["node_states"]["n_brief"])
    brief["status"] = NODE_STATUS_RUNNING
    brief["started_at"] = now
    brief = apply_node_activity(
        brief,
        kind="stage",
        text="generating brief",
        at=now,
    )
    # 完成
    brief["status"] = NODE_STATUS_COMPLETED
    brief["completed_at"] = now + 1
    brief["output_ref"] = {
        "kind": "text",
        "uri": "file://artifacts/n_brief/brief.md",
        "mime_type": "text/markdown",
        "label": "brief",
    }
    brief["text"] = "# Brief\n宇航员发现废弃空间站"
    brief["history"] = [
        {
            "ts": now + 1,
            "text": brief["text"],
            "output_ref": brief["output_ref"],
        }
    ]
    # 单节点重跑会 bump version；这里演示完成后保持 1，重跑示例单独 +1
    brief["version"] = int(brief.get("version") or 1)
    next_run["node_states"]["n_brief"] = brief
    next_run["current_node_ids"] = []
    next_run["updated_at"] = now + 1

    # leader 活动（仍只在 run）
    leader = apply_node_activity(
        next_run["node_states"].get(LEADER_NODE_ID),
        kind="tool_call",
        text="swarmflow accepted",
        tool="swarmflow",
        at=now,
    )
    next_run["node_states"][LEADER_NODE_ID] = leader

    normalized = normalize_execution_run(next_run)
    print("\n=== 推进一轮后 ===")
    print(f"  status={normalized['status']}")
    print(f"  brief.status={normalized['node_states']['n_brief']['status']}")
    print(f"  brief.output_ref={normalized['node_states']['n_brief'].get('output_ref')}")
    print(f"  brief.version={normalized['node_states']['n_brief'].get('version')}")
    print(
        f"  leader.activity={normalized['node_states'][LEADER_NODE_ID].get('activity')}"
    )
    print(f"  trigger_source={normalized['metadata'].get('trigger_source')}")
    out = HERE / "out_advanced_run.json"
    out.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        shown = out.resolve().relative_to(REPO_ROOT)
    except ValueError:
        shown = out
    print(f"  已写出: {shown}")
    return normalized


def demo_leader_trigger_diff() -> None:
    print("\n=== trigger_source 语义 ===")
    print(f"  {RUN_TRIGGER_SOURCE_CANVAS!r}: 画布按钮 / RPC 触发，生命周期独立")
    print(f"  {RUN_TRIGGER_SOURCE_LEADER!r}: Leader 工具触发，随 Leader 轮次消亡")
    print("  对话轮次 ≠ 执行触发：accept 后应尽快返回，媒体在后台跑")


def check_exercise_file() -> int:
    """学生练习：补全 exercise_run.json 使归一化通过且含 completed brief。"""
    path = HERE / "exercise_run.json"
    print(f"\n=== 练习验收: {path.name} ===")
    if not path.exists():
        print("  未找到 exercise_run.json：先复制 fixtures/sample_run.json 再改")
        return 1
    raw = _load(path)
    if "FIXME" in json.dumps(raw, ensure_ascii=False):
        print("  还有 FIXME，请改完再验")
        return 1
    try:
        run = normalize_execution_run(raw)
    except DesignerGraphValidationError as exc:
        print(f"  校验失败: {exc}")
        return 1
    brief = run["node_states"].get("n_brief") or {}
    if brief.get("status") != NODE_STATUS_COMPLETED:
        print("  要求: n_brief.status 必须是 completed")
        return 1
    if not isinstance(brief.get("output_ref"), dict):
        print("  要求: n_brief 必须有 output_ref")
        return 1
    if LEADER_NODE_ID not in run["node_states"]:
        print(f"  要求: 保留 {LEADER_NODE_ID} 节点状态")
        return 1
    print("  OK: run 契约通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="学习项目 02：运行态契约")
    parser.add_argument("--advance", action="store_true", help="演示推进一轮节点状态")
    parser.add_argument("--check", action="store_true", help="验收 exercise_run.json")
    args = parser.parse_args()

    if args.check:
        return check_exercise_file()

    run = demo_normalize()
    demo_leader_trigger_diff()
    if args.advance:
        advance_once(run)
    else:
        print("\n可选：加 --advance 看 pending→completed 模拟")
        print("练习：复制 fixtures/sample_run.json → exercise_run.json，")
        print("      把 n_brief 改成 completed 并补 output_ref，然后：")
        print("  python learn-workswarm/projects/02-execution-run/exercise.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
