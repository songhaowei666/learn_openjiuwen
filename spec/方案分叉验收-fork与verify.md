# 方案分叉验收：用 SwarmFlow 的 fork 和 verify 做一条可演示进度树

不改现有 `swarmflow_a2ui`。新建 `learn_note/example/swarmflow_verify_fork`，不接真实模型。脚本用 `agent_session.fork` 从同一份需求理解分出两套方案，再用 `verify` 做一轮验收。页面进度树画出分叉边和裁决结果。

## 演示脚本

`backend/workflows/design_fork.py` 的 `run(args)`：

1. `agent_session(label="分析师")` 发一轮，产出约束摘要。
2. 对分析师 `fork(fork_mode="full")` 出「方案甲」「方案乙」。两条线 `parallel` 各 `send` 一版方案。甲满足约束，乙故意漏掉一条，正文里带固定标记供后端识别。
3. 对两份方案各调用一次 `verify(build_reviewers(...))`，组合为 `verifier` + `inspector`。甲通过，乙被 verifier 一票否决。
4. 返回 `{winner, designs, verdicts}`。

`build_reviewers` 从 `openjiuwen.agent_teams.workflow.review` 导入。

```text
分析师会话
  ├─ 方案甲 fork ── verify 甲 pass
  └─ 方案乙 fork ── verify 乙 fail
```

## 离线后端

仿照 `swarmflow_a2ui/backend/swarmflow_runner.py`，去掉 human / A2UI。

- `capture_fork` 返回 `None`（引擎允许的镜像兜底）。不实现会在 `fork()` 处抛 `NotImplementedError`。`parent_session_id` 仍由引擎写在子会话的 `AGENT_STARTED` 上，不依赖 `fork_data`。
- `run()` 识别 verify 的 verdict / score schema：甲返回 `decision=pass` 与 `score=0.92`，乙返回 `decision=fail` 与 `score=0.55`。
- 会话 `send_turn` 按 label 返回分析师摘要和两版方案。

入口只有 `POST /api/ask` 和 `GET /api/events/{run_id}`，端口 `8001`。

## 进度树

`_Projector` 补两类现有 demo 丢掉的事件：

- `VERIFY_STARTED` / `VERIFY_COMPLETED`：用 `verify_id` 建节点。`verify_reviewer_labels` 把随后的 reviewer `agent` 挂到该节点下。完成时把 `verify_verdict` 和逐票 `feedback` 写入 detail。`verify_settled` 与 completed 走同一处理。
- `AGENT_STARTED` 带 `member_name` 时记下「成员名 → 节点」。子节点若有 `parent_session_id`，`parentId` 指向父会话节点，`nodeType` 标成 `fork`。

前端是精简 React 进度树（无 A2UI 依赖），状态增加 `passed`。端口 `5174`，把 `/api` 代理到 `8001`。页面一个「开始演示」按钮，默认需求文案可改。结果面板展示胜出方案和两轮裁决。

## 运行

仓库根目录：

```bash
uv run uvicorn --app-dir learn_note/example/swarmflow_verify_fork backend.main:app --host 127.0.0.1 --port 8001
```

另开终端进入 `learn_note/example/swarmflow_verify_fork/frontend`，执行 `npm install && npm run dev`，打开 http://127.0.0.1:5174 。点开始后应看到：分析师 → 两个 fork 子节点 → 两棵 verify 子树（甲 pass、乙 fail）→ 底部结果里 winner 为方案甲。
