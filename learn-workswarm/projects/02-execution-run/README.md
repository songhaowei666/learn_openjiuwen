# 学习项目 02：运行态契约

对应清单 §1.2 / 笔记 `01-domain-model.md` §1.2。

## 目标

- 理解 graph（配方）与 run（进度/产物）分离
- 会读写 `node_states` / `output_ref` / `trigger_source`
- 知道 `__leader__` 只活在 run 里

## 真实代码入口

| 用途 | 符号 / 路径 |
|---|---|
| Run 归一化 | `normalize_execution_run` |
| 节点活动 | `apply_node_activity` |
| Leader 虚拟节点 | `LEADER_NODE_ID = "__leader__"` |
| 触发来源 | `RUN_TRIGGER_SOURCE_CANVAS` / `LEADER` |
| 文件 | `jiuwenswarm/common/schema/designer_graph.py` |

## 怎么跑

```bash
PY=/Users/song/anaconda3/envs/deepstudy/bin/python   # .vscode 解释器；勿 uv run / 勿新建 .venv
$PY learn-workswarm/projects/02-execution-run/exercise.py
$PY learn-workswarm/projects/02-execution-run/exercise.py --advance
# 改完 exercise_run.json 后
$PY learn-workswarm/projects/02-execution-run/exercise.py --check
```

## 练习任务

1. 对照 `01-execution-graph` 的 graph fixture：nodes 里没有 `__leader__`，run 里有。
2. 跑 `--advance`，打开生成的 `out_advanced_run.json`，看 brief 的 `output_ref` / `history`。
3. 改 `exercise_run.json` 去掉所有 `FIXME_*`，让 `--check` 通过。

## 验收

- [ ] 能说明为何重跑要 bump `version`
- [ ] `--check` 退出码 0
