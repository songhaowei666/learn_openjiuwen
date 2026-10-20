# ReActAgent 结构化输出与 Runner Session

对照 `spec/ReActAgent结构化输出与Runner会话.md` 的 CLI demo。接真实模型，验证：

1. `ReActAgent` 能跑通
2. `StructuredOutputTool` + `StructuredOutputFinishRail`：权威结果读 `captured`，不解析正文；没调工具则失败，不解析正文兜底
3. 用 `create_agent_session(..., card=agent.card)` 建 session，再交给 `Runner.run_agent`；两轮同 `conversation_id` / `session_id`
4. 无参工具读 `session`：`Tool` 子类用 `kwargs["session"]`；`@tool` 用 `get_current_session()`

## 运行

依赖使用仓库根目录共用环境与 `.env`（`API_BASE` / `API_KEY` / `MODEL_NAME` / `MODEL_PROVIDER`）：

```bash
# 仓库根目录
source .venv/bin/activate   # 或 conda activate deepstudy
cd react_structured_session
python -m backend.main
```

预期：

- 每轮先打印 `read_data_context`（能读到 `file_name=1234567890.txt`）
- 第一轮 `captured.priority=high`，第二轮 `medium`
- 两侧 `session_id` 均为 `react_structured_demo`
- 最后打印「验收通过」
