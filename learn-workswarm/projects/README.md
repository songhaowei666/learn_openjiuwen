# Design 画布：知识点学习项目

每个项目对应清单一节里的一个知识点。练习脚本优先 **import 仓库真实模块**（经 `_boot.py` 注入路径），只在前端/编排逻辑需要时做忠实移植。

## §1 领域模型（已就绪）

| 项目 | 知识点 | 怎么跑 |
|---|---|---|
| [01-execution-graph](./01-execution-graph/) | 执行图 `designer-execution-graph.v1` | `python learn-workswarm/projects/01-execution-graph/exercise.py` |
| [02-execution-run](./02-execution-run/) | 运行态 `designer-execution-run.v1` | `python learn-workswarm/projects/02-execution-run/exercise.py` |
| [03-work-mode-binding](./03-work-mode-binding/) | 一项目一会话一画布 | `python learn-workswarm/projects/03-work-mode-binding/exercise.py --cases` |
| [04-user-canvas-edits](./04-user-canvas-edits/) | `user_canvas_edits` | `python learn-workswarm/projects/04-user-canvas-edits/exercise.py` |

统一在**仓库根目录**、用 `.vscode/settings.json` 里的解释器执行（当前为 conda `deepstudy`）：

```bash
/Users/song/anaconda3/envs/deepstudy/bin/python learn-workswarm/projects/01-execution-graph/exercise.py
```

不要用 `uv run`，也不要为这些练习新建仓库根 `.venv`。schema 练习经 `_boot.load_designer_graph()` 直载源文件，避免拉全量 openjiuwen 依赖。

## 推荐顺序

1. 读笔记 [`../01-domain-model.md`](../01-domain-model.md)
2. 按 01 → 04 做练习（先跑 demo，再改带 `FIXME` 的作业文件）
3. 回头勾清单 [`../design-canvas-extract-checklist.md`](../design-canvas-extract-checklist.md) §1

## 后续

§2 存储、§3 RPC 等项目按同样模板追加：`NN-<slug>/README.md` + `exercise.py` + `fixtures/`。
