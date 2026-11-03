# 学习项目 01：执行图契约

对应清单 §1.1 / 笔记 `01-domain-model.md` §1.1。

## 目标

- 分清 `node.type`（模态）与 `config.pipeline`（生成配方）
- 能手写一张过真实 `normalize_execution_graph` 的 JSON

## 真实代码入口

| 用途 | 路径 |
|---|---|
| 契约权威 | `jiuwenswarm/common/schema/designer_graph.py` |
| 前端镜像 | `jiuwenswarm/channels/web/frontend/src/features/designer/executionGraphTypes.ts` |
| 字面量钉死 | `tests/unit_tests/design/test_designer_execution_graph_contract.py` |

本练习 **不复制** 整份 schema，直接 import 仓库模块，保证和线上一致。

## 怎么跑

在仓库根目录，用 `.vscode` 解释器（勿 `uv run` / 勿新建 `.venv`）：

```bash
PY=/Users/song/anaconda3/envs/deepstudy/bin/python
$PY learn-workswarm/projects/01-execution-graph/exercise.py
# 编辑 my_graph.json 后验收
$PY learn-workswarm/projects/01-execution-graph/exercise.py --mine
```

## 练习任务

1. 跑一遍 `exercise.py`，看合法样例摘要，以及两份坏图各自报什么错。
2. 打开 `fixtures/bad_type_is_pipeline.json`：为什么 `type: "character"` 非法？
3. 改 `my_graph.json`：把 `FIXME_*` 换成正确模态/pipeline，使 `--mine` 通过。
4. （加分）再加一个 `storyboard` 节点（`type=table`）并接到 brief。

## 验收

- [ ] 能口头解释 character 节点的 type/pipeline
- [ ] `exercise.py --mine` 退出码 0
