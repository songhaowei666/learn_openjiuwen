# Day 9：Service 层约定——进程里的 HTTP 就是这一个 AgentApp

Day 8 停在 `Popen`：`{venv}/bin/python -m <模块> --host 0.0.0.0 --port <port>`。  
Day 9 只回答这个进程起来之后的约定：**装饰器什么时候跑、`/query` 线上长什么样、自己执行 `app.run()` 和 Runtime 托管差在进程外面。**

精读：

- `service/openjiuwen_runtime/service/app/base_app.py`
- `service/openjiuwen_runtime/service/app/agent_app.py`
- `service/examples/simple_agent_app.py`

`models/request.py`、`app/middleware.py` 只作为 `/query` 的入参和钩子来对。`AppGroup`、`PluginApp` 今天不展开。

过关标志：能说出 `@app.init` / `@app.query` / `@app.shutdown` 各在什么时候被调用；能说出客户端看到的是 `data: {json}\n\n`，元组里的 `last` 不会单独变成一种帧；能说出托管进程进的仍是 `app.run()`，venv、记账、探活、回收不在这个函数里。

---

## 今天在链路里的位置

```text
LocalSubprocessDeployer                         （Day 8）
  python -m <package_name> --host 0.0.0.0 --port <port> [--irpath ...]
  环境变量 RUNTIME_USERDATA
        │
        ▼
 模块 __main__ 调用 app.run()                   解析上述 CLI，uvicorn 拉起 self.app
        │
        ├─ FastAPI startup  →  @app.init        用户在这里给 app.agent 赋值
        ├─ GET  /health
        ├─ POST /query      →  @app.query       yield (msg, last)，框架写成 SSE
        ├─ POST /reset_conversation
        └─ FastAPI shutdown →  @app.shutdown
```

低码的 `-m` 是 `openjiuwen_runtime.examples.lowcode_agent`，并带 `--irpath`。高码的 `-m` 是 CLI 解析出的 `openjiuwen_runtime.<包名>`。两种进程里接 HTTP 的类都是 `AgentApp`。

---

## 1. `BaseApp`：一个 FastAPI、两个生命周期钩子、一个 `run()`

`BaseApp.__init__` 建一个 `FastAPI`，标题用 `app_name`。装饰器不执行函数，只把函数对象存下来。后写的同名装饰器覆盖前一个，每个钩子只留最后一次注册。

| 装饰器 | 存在哪 | 谁调用 |
| --- | --- | --- |
| `@app.init` | `self._init_hook` | FastAPI `startup` 事件里 `await` |
| `@app.shutdown` | `self._shutdown_hook` | FastAPI `shutdown` 事件里 `await` |

两个钩子都按协程来 `await`。`startup` 跑完，uvicorn 才对外接受连接。`init` 里加载模型、读 IR 的时间，算在 Day 7 那次 `/health` 等待里（最长 600 秒）。`init` 抛异常时进程起不来，deployer 那 2 秒后的 `poll()` 会看到退出码。

同时注册的基础路由只有 `GET /health`，响应三字段：`status`、`app`、`version`。

`run()` 是本地和托管共用的入口：

1. `_parse_cli_args()` 读 `--host`（默认 `0.0.0.0`）、`--port` / `-p`（默认 `8090`）、`--userdata` / `-u`、`--irpath` / `-i`。`--irpath` 指向的文件必须已经存在，否则进程在进 uvicorn 之前就退出。
2. 函数参数 `host` / `port` 不是 `None` 时用函数参数。注释和 docstring 写的是「命令行优先」，代码是函数实参优先。模板和示例都写无参 `app.run()`，所以托管命令行上的 `--port` 进得去。若改成 `app.run(port=8090)`，deployer 传入的端口会被丢掉，Manager 记的 URL 和进程实际监听对不上。
3. `_setup_runtime_env` 把 `userdata` 写成环境变量 `RUNTIME_USERDATA`，把 `file`（来自 `--irpath`）写成 `RUNTIME_IR_PATH`，然后从 `kwargs` 里弹出，避免传进 `uvicorn.run`。deployer 把 userdata 放进子进程环境变量，不放进命令行；低码读 IR 走 `RUNTIME_IR_PATH`。

---

## 2. `AgentApp`：一个实例服务所有对话

类文档上的三句话就是实例模型：

- 一个 `AgentApp` 持有一个 Agent 实例，放在 `app.agent`。
- 这一个实例处理所有对话。
- 会话隔离用请求里的 `conversation_id`，由 Agent 自己实现。框架不保存历史消息。

`AgentApp` 在基类路由之外再挂三条，并再注册一次 `/health`：

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| `POST` | `/query` | 调 `@app.query`，响应 `text/event-stream` |
| `POST` | `/reset_conversation` | `app.agent` 有 `clear_session` 就 `await` 它，然后返回 `{"status":"ok",...}` |
| `GET` | `/agent_detail` | 调 `@app.agent_detail`。没注册这个钩子时返回 501 |
| `GET` | `/health` | 见下一小节 |

`reset_conversation` 不读 `user_id`。Agent 没有 `clear_session`，或者 `app.agent` 还是 `None`，接口仍然返回 ok。`QueryRequest.user_id` / `space_id` 只来自 POST body，默认 `anonymous` / `default`。管理面的 `X-User-ID`、`X-Space-ID` 停在 Day 6 的 Server，不会注入到这个对话进程。

### `/health` 注册了两次

`BaseApp` 先注册三字段的 `/health`。`AgentApp._register_agent_routes` 末尾再注册一个带 `agent_loaded: self.agent is not None` 的 `/health`。这段代码找到先注册的路由，把端点存进局部变量 `original_endpoint`，之后没有替换、也没有删掉它。

Starlette 按注册顺序匹配，先注册的路由处理请求。因此当前实现里，客户端打到的是 `BaseApp` 那一版，响应里没有 `agent_loaded`。`docs/zh/4. Agent接入.md` 的示例带了 `agent_loaded`，和这条注册顺序对不上。`/docs` 里可以看到两个 `GET /health`。

---

## 3. `@app.query`：三参数进去，SSE 只带消息体

装饰器同样只保存函数。`POST /query` 里的实际调用是：

```189:189:service/openjiuwen_runtime/service/app/agent_app.py
                        gen = self._query_hook(processed_messages, query_request, cancel_event)
```

三个位置参数：

| 参数 | 是什么 |
| --- | --- |
| `processed_messages` | `QueryRequest.messages`。中间件 `before_query` 可以替换这份列表 |
| `query_request` | 整个 `QueryRequest`。多轮用 `request.conversation_id` |
| `cancel_event` | 本次请求新建的 `asyncio.Event()`。客户端断开，或生成器结束时，框架 `set()` |

`QueryRequest` 的字段：`messages`（当前这一轮的消息列表，模型注释写明不是完整历史）、`conversation_id`（必填）、`user_id`、`space_id`、`stream`。`stream` 被模型接进来，端点不读它，响应固定是 SSE。

钩子要是异步生成器，逐次：

```python
yield msg, last
```

框架侧：

```192:213:service/openjiuwen_runtime/service/app/agent_app.py
                            async for msg, last in gen:
                                if await request.is_disconnected():
                                    logger.info(...)
                                    cancel_event.set()
                                    break
                                chunk_count += 1
                                processed_msg = msg
                                for mw in self._middlewares:
                                    ...
                                    processed_msg = await mw.before_response(...)
                                ...
                                yield f"data: {json.dumps(processed_msg)}\n\n"
```

线上一条消息是：

```text
data: {"type": "text", "content": "..."}\n\n
```

`last` 被解包之后，当前实现不再使用。流什么时候结束，看生成器什么时候结束（或客户端断开后 `break`）。`last=True` 是写钩子的人给「这是这一轮最后一条」留的标记；低码和 CLI 模板都在最后一条上标 `True`，中间的增量标 `False`。解析 SSE 的客户端只看到 `msg` 的 JSON。

成功路径的 `json.dumps` 没有 `ensure_ascii=False`，中文会变成 `\uXXXX`。失败路径那一条用了 `ensure_ascii=False`。

一次 `/query` 的顺序：

1. 按注册顺序跑每个中间件的 `before_query`。中间件自己抛异常只打日志，请求继续。
2. 调用 query 钩子，逐条 `yield`。每条再过 `before_response`，再写成 SSE。
3. 生成器正常结束，跑 `after_query`。
4. 钩子或序列化抛异常：跑 `on_error`，再补一条 SSE，HTTP 流已经开始，状态码仍是 200：

```text
data: {"type": "error", "error": "..."}\n\n
```

5. 没注册 `@app.query` 时，`generate()` 什么都不 yield，客户端拿到空的 SSE 流。

客户端断开时，框架在**下一条**消息到来时才发现，然后 `cancel_event.set()` 并停止往外写。钩子里如果还在等模型，要自己看这个事件。CLI 的 react / workflow 模板和低码 runner 都写成第三个参数 `cancel_event=None`，循环里 `is_set()` 就 `break`。`finally` 里也会 `set()`，所以正常结束时事件同样是已设置。

类文档和 `simple_agent_app.py` 把钩子写成两个参数 `(msgs, request)`。调用点固定传三个。两个参数的函数一进 `/query` 就是 `TypeError`，再被收成上面那条 `type=error` 的 SSE。能对上调用点的写法是模板和低码那一版：

```python
async def query(msgs, request, cancel_event=None):
    ...
    yield {"type": "text_delta", "content": delta}, False
    yield {"type": "result", "content": full_text}, True
```

---

## 4. `simple_agent_app.py` 对到这条约定上

这个文件是回声 Agent，用来看装饰器怎么串，不代表托管后的进程。

| 片段 | 对上哪条约定 |
| --- | --- |
| `app = AgentApp(...)` | 一个进程一个应用 |
| `@app.init` 里 `app.agent = MockAgent()` | 框架不创建 Agent，用户在 startup 里挂上 |
| `@app.query` 把 `request.conversation_id` 传给 `agent.stream` | 多轮键是 conversation_id |
| `yield msg, last` | 和框架的 `async for msg, last` 对齐 |
| `MockAgent.stream` 只 yield 一次，`last` 恒为 `True` | 单条回复 |
| `sessions[conversation_id]` | 会话状态放在这一个实例里，按 id 分开 |
| `clear_session` | `/reset_conversation` 会调到它 |
| `if __name__ == "__main__": app.run()` | 和模板相同，也是 `python -m` 时会走进去的入口 |

`query(msgs, request)` 少了第三个参数。按上一节的调用点，这条示例进程若真的收到 `POST /query`，回声逻辑不会执行，响应是一条错误 SSE。Day 12 抄模板时用三参数那一版。

`MockAgent` 只回显最后一条 `role=user` 的 `content`，不读历史列表里的其它消息。这和 `QueryRequest.messages`「当前消息、不是全量历史」的注释一致：历史要 Agent 自己按 `conversation_id` 留。

---

## 5. `app.run()` 本地自测和 Runtime 托管

两边进的是同一个函数。模板末尾、示例末尾、被 `python -m` 拉起之后，都是无参 `app.run()`，再由它解析 `--host` / `--port` / `--irpath`。

托管多出来的部分都在这个函数外面，Day 7 和 Day 8 已经写过：

| | 自己执行 `app.run()` | Runtime 拉起的同一个 `app.run()` |
| --- | --- | --- |
| 解释器 | 当前环境 | `{DEPLOY_DIR}/{deployment_id}/.venv` 里的 Python |
| 谁启动 | 当前终端 | deployer `Popen`，stdout/stderr 进 `logs/agent.log` |
| 端口 | 默认 8090，或你传的 `--port` | deployer 写入的 `--port`，缺省时它自己找空端口 |
| 登记 | 没有 deployment 记录 | 主表 `url` / `status`，子表 `pid` / `venv_path` |
| 就绪 | 自己看日志、自己 curl `/health` | Manager 探 `{url}/health`，最长 600 秒 |
| 停 | 终端打断，uvicorn 会走 `shutdown`，`@app.shutdown` 会跑 | Day 8：按 pid `kill -9`，不发 `SIGTERM`。`@app.shutdown` 依赖进程能处理退出信号，这条回收路径上钩子不会跑 |
| 磁盘 | 无部署目录 | `.venv` 在 delete 时删掉；`logs/`、低码的 `ir.json` 还在 |

所以本地把 `/query` 跑通，只证明钩子和 SSE 约定成立。venv 隔离、部署记录、探活失败改 `failed`、delete 回收，都要走到 deploy 之后才看得到。学习计划里的那条坑就是这件事。

---

## 和前后几天的关系

- Day 5 手测的 `/health`、`/query`、`/reset_conversation` 就是 `AgentApp` 这几条路由。当时看到的 SSE 行，是本节 `data: {json.dumps(msg)}`。
- Day 6 的租户头不到这个进程。对话侧若要用户标识，读 body 里的 `user_id`，默认是 `anonymous`。
- Day 8 的启动命令在 `app.run()` 被解析。`--irpath` 变成 `RUNTIME_IR_PATH`；userdata 由 deployer 放进环境变量。低码 runner 的 `@app.init` 读的就是这两个值。
- Day 10 抽读低码 runner 时，沿用同一套装饰器：`init` 里按 IR 建 Agent，`query` 里把引擎 chunk 收成事件再 `yield event, last`。
- Day 12～14 写自己的 Agent 时，钩子签名用三参数；最后一条 `last=True`。交给 Runtime 之后，对比的是本节这张表，而不是再改 `AgentApp`。
