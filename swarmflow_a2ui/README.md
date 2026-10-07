# SwarmFlow + A2UI Demo

前后端分离的可运行示例：前端提问，后端用预编写的 SwarmFlow 脚本跑调研流程，SSE 推送进度树；停在 human 节点时用 A2UI 渲染审批、选择和文本输入。

Agent 节点由同进程的确定性后端回答，不需要模型 API Key。human 节点会一直等到页面上提交回复。

## 运行

依赖装在示例根目录 `learn_note/example` 的共用 `.venv` 和 `node_modules`。本示例不调用模型，可以不填 `.env`。

在本目录启动后端（端口 8000）：

```bash
cd learn_note/example
source .venv/bin/activate
cd swarmflow_a2ui
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```bash
cd learn_note/example
npm run dev:swarmflow
```

浏览器打开 http://127.0.0.1:5173 。输入问题后，在进度树里的人工节点完成「通过 / 驳回」、选择报告风格、补充关注点。
