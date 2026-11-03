# 学习项目 03：一项目一会话一画布

对应清单 §1.3 / 笔记 `01-domain-model.md` §1.3。

## 目标

- 理解 `work_mode=design` 与 Agent `mode`（work/code）正交
- 知道 design **没有** `default` / `default_code` 虚拟项目
- 能校验 `session ↔ project ↔ graph` 绑定

## 真实代码入口

| 用途 | 路径 |
|---|---|
| work_mode 常量与工具 | `gateway/common/work_mode.py` |
| 会话侧封装 | `jiuwenswarm/server/runtime/session/work_mode.py` |
| 图绑定推送 | `jiuwenswarm/server/runtime/design/team_bridge.py`（后续 §3） |

本目录 `binding.py` 是学习用纯函数，规则对齐上述模块语义，不替代生产装配。

## 怎么跑

```bash
PY=/Users/song/anaconda3/envs/deepstudy/bin/python   # .vscode 解释器；勿 uv run / 勿新建 .venv
$PY learn-workswarm/projects/03-work-mode-binding/exercise.py
$PY learn-workswarm/projects/03-work-mode-binding/exercise.py --cases
$PY learn-workswarm/projects/03-work-mode-binding/exercise.py --check
```

## 练习任务

1. 读 `gateway/common/work_mode.py` 文件头注释（10 行内说清正交关系）。
2. 跑 `--cases`，确认「误用 default 项目」被拒绝。
3. 改 `my_session.json`，让 `--check` 通过。

## 验收

- [ ] 能说明为何 design 不进 `EXECUTION_WORK_MODES`
- [ ] `--cases` 与 `--check` 均为 0
