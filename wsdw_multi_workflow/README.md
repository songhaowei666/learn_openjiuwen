# 基于 openjiuwen multi_workflow_agent_demo 改造的独立多工作流项目。

## 结构

```
wsdw_multi_workflow/
  api/                       # 全部 Python 后端
    __main__.py              # CLI
    server.py                # FastAPI + A2UI SSE
    a2ui_messages.py
    config.py
    agent_factory.py
    handlers/
    executors/
    workflows/
  web/                       # React + A2UI 前端
    src/
```

## 运行

在 `agent-core` 根目录先安装本仓库（提供 openjiuwen）：

```bash
uv sync
```

进入本项目并配置环境变量（参考 `.env.example`）：

```bash
cd learn_note/example/wsdw_multi_workflow
export WSDW_API_KEY=...
export WSDW_MODEL_NAME=...
export WSDW_MODEL_ID=...
export PYTHONPATH=/path/to/agent-core:$PWD
```

CLI：

```bash
python3 -m api
```

Web：先启动后端，再启动前端。

```bash
python3 -m api.server
```

另开终端：

```bash
cd web
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。后端默认监听 `http://127.0.0.1:8765`。

## 说明

源自 `examples/workflow_agent/multi_workflow_agent_demo`，遵循 Apache-2.0。
相对原 demo 的小改动：按 session 过滤任务列表；resume 状态不匹配时显式报错。
Web 端使用 A2UI v0.9 渲染工作流提问表单和办理结果。
