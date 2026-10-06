# SwarmFlow + A2UI Demo

前后端分离的可运行示例：前端提问，后端用预编写的 SwarmFlow 脚本跑调研流程，SSE 推送进度树；停在 human 节点时用 A2UI 渲染审批、选择和文本输入。

Agent 节点由同进程的确定性后端回答，不需要模型 API Key。human 节点会一直等到页面上提交回复。

## 运行

在仓库根目录启动后端（端口 8000）：

```bash
uv run uvicorn --app-dir learn_note/example/swarmflow_a2ui backend.main:app --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```bash
cd learn_note/example/swarmflow_a2ui/frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173 。输入问题后，在进度树里的人工节点完成「通过 / 驳回」、选择报告风格、补充关注点。
