#!/usr/bin/env python3
"""知识点 1.1：执行图契约 designer-execution-graph.v1

直接调用仓库真实归一化入口：
  jiuwenswarm.common.schema.designer_graph.normalize_execution_graph

用法（仓库根目录，.vscode / conda deepstudy）：
  /Users/song/anaconda3/envs/deepstudy/bin/python \\
    learn-workswarm/projects/01-execution-graph/exercise.py
  .../python learn-workswarm/projects/01-execution-graph/exercise.py --mine
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _boot import REPO_ROOT, load_designer_graph  # noqa: E402

_dg = load_designer_graph()
PIPELINE_TO_TYPE = _dg.PIPELINE_TO_TYPE
DesignerGraphValidationError = _dg.DesignerGraphValidationError
normalize_execution_graph = _dg.normalize_execution_graph
node_pipeline = _dg.node_pipeline

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summarize(graph: dict) -> None:
    print(f"  title      = {graph.get('title')!r}")
    print(f"  graph_id   = {graph.get('graph_id')}")
    print(f"  project_id = {graph.get('project_id')}")
    print(f"  nodes ({len(graph['nodes'])}):")
    for node in graph["nodes"]:
        pipe = node_pipeline(node) or "(none)"
        expected = PIPELINE_TO_TYPE.get(pipe, "?")
        print(
            f"    - {node['id']}: type={node['type']!r} pipeline={pipe!r} "
            f"(PIPELINE_TO_TYPE→{expected!r}) label={node['label']!r}"
        )
    print(f"  edges ({len(graph['edges'])}):")
    for edge in graph["edges"]:
        print(f"    - {edge['id']}: {edge['source']} -> {edge['target']} ({edge.get('kind')})")


def demo_good() -> None:
    path = FIXTURES / "good_brief_character.json"
    print(f"\n=== 合法样例: {path.name} ===")
    graph = normalize_execution_graph(_load(path))
    _summarize(graph)
    print("  OK: normalize_execution_graph 通过")


def demo_bad(name: str) -> None:
    path = FIXTURES / name
    print(f"\n=== 应失败: {path.name} ===")
    try:
        normalize_execution_graph(_load(path))
    except DesignerGraphValidationError as exc:
        print(f"  预期错误: {exc}")
    else:
        raise SystemExit(f"  未报错，但这份 fixture 本应失败: {path}")


def check_mine() -> int:
    path = HERE / "my_graph.json"
    print(f"\n=== 练习验收: {path.name} ===")
    raw = _load(path)
    # 故意留下的占位符，提醒先改再跑
    blob = json.dumps(raw, ensure_ascii=False)
    if "FIXME" in blob:
        print("  未完成：请先把 my_graph.json 里的 FIXME_* 改成真实 type/pipeline")
        print("  提示：scene → type=image, pipeline=scene；brief → type=text")
        return 1
    try:
        graph = normalize_execution_graph(raw)
    except DesignerGraphValidationError as exc:
        print(f"  校验失败: {exc}")
        return 1
    _summarize(graph)
    # 额外要求：至少 brief→某 pipeline 节点的一条边
    if len(graph["nodes"]) < 2 or len(graph["edges"]) < 1:
        print("  再加一点：至少 2 个节点 + 1 条边")
        return 1
    print("  OK: 你的图已通过真实 schema 归一化")
    print(f"  对照源码: {REPO_ROOT / 'jiuwenswarm/common/schema/designer_graph.py'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="学习项目 01：执行图契约")
    parser.add_argument(
        "--mine",
        action="store_true",
        help="只验收 my_graph.json",
    )
    args = parser.parse_args()
    if args.mine:
        return check_mine()

    demo_good()
    demo_bad("bad_type_is_pipeline.json")
    demo_bad("broken_edge.json")
    print("\n下一步：编辑 my_graph.json，然后运行：")
    print("  python learn-workswarm/projects/01-execution-graph/exercise.py --mine")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
