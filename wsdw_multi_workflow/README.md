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

依赖装在示例根目录 `learn_note/example`：共用 `.venv`、根目录 `node_modules`，模型配置写在根目录 `.env`（参考 `.env.example`）。

```bash
cd learn_note/example
source .venv/bin/activate
cd wsdw_multi_workflow
```

CLI：

```bash
python -m api
```

Web：先启动后端，再启动前端。

```bash
python -m api.server
```

另开终端：

```bash
cd learn_note/example
npm run dev:wsdw
```

浏览器打开 `http://127.0.0.1:5173`。后端默认监听 `http://127.0.0.1:8765`。

## 说明

源自 `examples/workflow_agent/multi_workflow_agent_demo`，遵循 Apache-2.0。
相对原 demo 的小改动：按 session 过滤任务列表；resume 状态不匹配时显式报错。
Web 端使用 A2UI v0.9 渲染工作流提问表单和办理结果。
