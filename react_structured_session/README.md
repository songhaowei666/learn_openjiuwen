# ReActAgent 结构化输出与 Runner Session

对照 `spec/ReActAgent结构化输出与Runner会话.md` 的 CLI demo。

1. `ReActAgent` + `StructuredOutputTool` / `StructuredOutputFinishRail`（真实模型）：权威结果读 `captured`
2. 用 `create_agent_session(..., card=agent.card)` 建 session，再交给 `Runner.run_agent`
3. 无参工具读 `session`：`Tool` 子类用 `kwargs["session"]`；`@tool` 用 `get_current_session()`
4. **多 ModelContext**（无模型）：同一 `session_id` 下 `main` / `side_task` 两套消息互不污染

## 运行

依赖使用仓库根目录共用环境与 `.env`（`structured` / `all` 需要 API）：

```bash
# 仓库根目录
source .venv/bin/activate   # 或 conda activate deepstudy
cd react_structured_session
python -m backend.main                 # 默认 all
python -m backend.main structured      # 仅结构化输出两轮
python -m backend.main multi_context   # 仅多 ModelContext（可不接模型）
```

### structured 预期

- 每轮先打印 `read_data_context`（能读到 `file_name=1234567890.txt`）
- 第一轮 `captured.priority=high`，第二轮 `medium`
- 两侧 `session_id` 均为 `react_structured_demo`

### multi_context 预期

- 同一 `session_id=multi_context_demo`
- `main` 只有周会相关消息，`side_task` 只有天气相关消息
- `save_contexts` 后 `session.state["context"]` 含 `main`、`side_task` 两个 key
