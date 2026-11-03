# 学习项目 04：user_canvas_edits

对应清单 §1.4 / 笔记 `01-domain-model.md` §1.4。

## 目标

- 会记账五种 op：`add` / `remove` / `connect` / `disconnect` / `replace`
- 理解 edits 是领域事实，会注入 Director awareness 与节点上下文
- 能判断 Agent patch 是否在「帮用户恢复」

## 真实代码入口

| 用途 | 路径 |
|---|---|
| 前端记账 | `.../designer/designerCanvasNodes.ts` → `appendUserCanvasEdit` |
| Director 摘要 | `.../designer/orchestration.py` → `note_user_canvas_edits` |
| Leader 硬规则 | `jiuwenswarm/agents/swarm/assembly.py`（`user_canvas_edits` 句） |
| 节点上下文注入 | `jiuwenswarm/server/runtime/designer/node_agent.py` |

本目录：

- `canvas_edits.py` — TS 逻辑的 Python 忠实移植
- `awareness.py` — orchestration 精简版
- `agent_guard.py` — 把 prompt 规则收成可执行守卫（学习用）

## 怎么跑

```bash
PY=/Users/song/anaconda3/envs/deepstudy/bin/python   # .vscode 解释器；勿 uv run / 勿新建 .venv
$PY learn-workswarm/projects/04-user-canvas-edits/exercise.py
$PY learn-workswarm/projects/04-user-canvas-edits/exercise.py --check
```

## 练习任务

1. 跑演示：看 `out_graph_with_edits.json` 里的 `user_canvas_edits` 与 `director_canvas_awareness`。
2. 读 assembly.py 里那句「不要恢复…」原文。
3. 填 `my_agent_actions.json` 的 `allow`（true/false），跑 `--check`。

## 验收

- [ ] 知道 edits 最多保留约 40 条，并打 `user_topology_edit`
- [ ] `--check` 退出码 0
