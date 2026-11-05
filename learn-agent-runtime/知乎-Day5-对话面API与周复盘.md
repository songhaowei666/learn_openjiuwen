# Day 5：对话面 API——对已部署 Agent 说话

Day 4 走的是 **管理面**（`:8186`）：部署、列表、详情、删除。  
Day 5 只盯 **对话面**：Agent 自己那个端口上的 `/health`、`/query`、`/reset_conversation`。

文档是 `docs/zh/4. Agent接入.md`。它列了三种接入：**API（可用）**、**CLI（待开放）**、**WebUI（待开放）**。今天只把 API 这条打穿。

过关标志：你能不看文档说出「该打哪个端口、请求体必填什么、响应为什么是 SSE」，并知道文档表格里的 `/{prefix}` 和 curl 示例里的根路径分别对应哪一种进程。

---

## 今天在链路里的位置

```text
你
 ├─ 管理 ──► server :8186     GET /health、/api/v1/agents/...
 │
 └─ 对话 ──► Agent 实例       GET /health
              （day4_echo      POST /query                 ← 今天
               :8090）         POST /reset_conversation
```

对话 **不经 server 转发**。管理面返回的 `url` 就是对话面地址。Day 4 高码实例是：

| 项 | 值 |
|---|---|
| 工程 | `learn-agent-runtime/day4-echo` |
| `deployment_id` | `889236ca-3155-475b-9a6a-7a292e93cf91` |
| `url` | `http://127.0.0.1:8090/` |
| 壳子 | `service` 的 `AgentApp`（`day4_echo_runner.py`） |

口诀：**8186 管生死，8090 管说话。**

---

## 文档在说两种壳，不要混成一种 URL

`4. Agent接入.md` 的表格和 curl 示例对的不是同一种进程。

| 壳 | 代码 | 路径长什么样 | 文档落在哪 |
|---|---|---|---|
| **单个 AgentApp** | `service/.../agent_app.py` | 根路径：`/health`、`/query`、`/reset_conversation` | 文中 curl（`:8090/query`） |
| **AppGroup** | `service/.../app_group.py` | 组：`/`、`/health`；应用：`/{prefix}/health`、`/{prefix}/query`、`/{prefix}/reset_conversation` | 文首那张端点表 |

`day4_echo` 是单个 `AgentApp`，所以打根路径。对它请求 `/day4_echo/query` 会 404。

AppGroup 示例在 `service/examples/multi_agent_group.py`：多个 Agent 挂到同一端口，用前缀分开，例如 `/customer/query`。今天不展开，知道「前缀是组挂载出来的」即可。

单应用 OpenAPI 上实际只有这 4 条业务路由（本机 `GET :8090/openapi.json`）：

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/health` | 这个 Agent 进程是否活着 |
| `POST` | `/query` | 发消息，**SSE 流** |
| `POST` | `/reset_conversation` | 按 `conversation_id` 清会话 |
| `GET` | `/agent_detail` | 文档表没写；未实现钩子时 **501** |

框架自带：`GET /docs`、`GET /openapi.json`。单应用没有组信息，`GET /` 是 **404**。

---

## 1. `GET /health`

这是 **Agent 实例** 的探活，和管理面 `GET :8186/health` 不是同一个 JSON。

```bash
curl -s http://127.0.0.1:8090/health
```

本机 `day4_echo` 实测：

```json
{"status":"healthy","app":"day4_echo","version":"0.1.0"}
```

字段从 `AgentApp(app_name=..., version=...)` 来。

文档示例里还有 `"agent_loaded": true`。源码里 `AgentApp` 确实又注册了一个带 `agent_loaded` 的 `/health`（`self.agent is not None`），但 `BaseApp` 在更早的时候已经注册了不带该字段的 `/health`。Starlette 按注册顺序匹配，**先注册的那条生效**。所以现网看到的是三字段版本，不是文档里的四字段版本。`day4_echo` 的 `@app.init` 也没有给 `app.agent` 赋值，即便走到增强版，`agent_loaded` 也会是 `false`。

---

## 2. `POST /query`

契约在 `service/openjiuwen_runtime/service/models/request.py` 的 `QueryRequest`。

| 字段 | 是否必填 | 含义 |
|---|---|---|
| `conversation_id` | **必填** | 会话键。多轮记忆靠它，框架不替你存历史 |
| `messages` | 可缺省，默认 `[]` | 当前这轮消息，不是完整历史。文档说遵循 AG-UI：`role` + `content` |
| `user_id` | 可缺省，默认 `anonymous` | 业务自己用；框架不据此鉴权 |
| `space_id` | 可缺省，默认 `default` | 同上 |
| `stream` | 可缺省，默认 `true` | 模型上有这个字段，**路由不读它**，一律走 SSE |

缺 `conversation_id`：

```bash
curl -s -X POST http://127.0.0.1:8090/query \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"hi"}]}'
```

实测 **422**，`loc` 为 `body.conversation_id`，`msg` 为 `Field required`。

正常请求（`-N` 让 curl 不要缓冲 SSE）：

```bash
curl -sN -X POST http://127.0.0.1:8090/query \
  -H 'Content-Type: application/json' \
  -d '{
    "messages": [{"role": "user", "content": "你好，Day5 对话面"}],
    "conversation_id": "day5-conv-001",
    "user_id": "song"
  }'
```

本机实测响应头：

```text
HTTP/1.1 200 OK
content-type: text/event-stream; charset=utf-8
cache-control: no-cache, no-transform
x-accel-buffering: no
```

正文（`json.dumps` 默认把中文转成 `\uXXXX`，解析后就是原文）：

```text
data: {"type": "text_delta", "content": "收到：你好，Day5 对话面"}

data: {"type": "result", "content": "收到：你好，Day5 对话面"}
```

### 响应长什么样，由 Agent 自己定

框架只保证一件事：把 `@app.query` 里 `yield` 出来的 **消息对象** 包成 SSE：

```text
data: <json>\n\n
```

`day4_echo` 约定了两种 `type`：`text_delta`（增量）、`result`（收尾）。文档里的 Python 示例在找 `text` / `tool_call`，那是另一个 Agent 的约定，不是框架枚举。接到新 Agent 先看它的 `@app.query`，再写解析。

钩子签名是 `yield (msg, last)`。`last` 表示这一条是不是最后一块，**框架收了但没有写进 SSE**，客户端只能靠消息里的 `type` 判断结束。`day4_echo` 里 `text_delta` 的 `last=False`，`result` 的 `last=True`。

服务端路径（`agent_app.py` 的 `query_endpoint`）：

1. 校验 body → `QueryRequest`
2. 中间件 `before_query`（改 messages）
3. 调 `@app.query(messages, request, cancel_event)`
4. 每块再走 `before_response`，然后 `yield data: ...`
5. 客户端断开就 `cancel_event.set()` 并停
6. 正常结束走 `after_query`；钩子抛错则在 **同一条 SSE** 里追加 `{"type":"error","error":"..."}`，HTTP 仍是 200（流已经开了）

同一 `conversation_id` 再发一轮，本机仍只回显当前这句（`收到：第二轮，还记得我吗`）。`day4_echo` 没有把历史放进 `app.agent`，所以 **id 相同 ≠ 它记得你**。记忆是业务在 `conversation_id` 上自己做的，框架只把这个字符串递进钩子。

---

## 3. `POST /reset_conversation`

```bash
curl -s -X POST http://127.0.0.1:8090/reset_conversation \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"day5-conv-001"}'
```

本机实测 **200**：

```json
{"status":"ok","message":"Conversation day5-conv-001 reset"}
```

缺 `conversation_id` 同样 **422**。`user_id` 在模型里是可选字段，端点没有拿它做鉴权。

源码实际做的事：

```text
若 self.agent 存在，且有 clear_session(conversation_id)
    则 await clear_session(...)
然后一律返回 status=ok
```

`day4_echo` 的 `init` 没有设置 `app.agent`，所以这次 reset **返回成功，但没有清掉任何状态**。`service/examples/simple_agent_app.py` 才是文档设想的样子：`init` 里 `app.agent = MockAgent()`，`MockAgent.clear_session` 删掉该 `conversation_id` 的会话。

记一句：**HTTP 200 只说明端点被打到了；会话有没有被清，取决于这个 Agent 有没有实现 `clear_session`。**

顺带：`GET /agent_detail` 本机是 **501**，`detail` 为 `agent_detail hook not implemented`。Day 5 的三个必测接口不含它。

---

## 和文档示例的三处差别（读文档时对着看）

| 文档 | 本机 `day4_echo` |
|---|---|
| `/health` 含 `agent_loaded` | 只有 `status` / `app` / `version`（先注册的路由生效） |
| 查询结果示例是 `type=text` | 本 Agent 是 `text_delta` + `result` |
| reset 文案看起来像真的清了上下文 | 本 Agent 没有 `app.agent`，只回了 ok |

CLI 接入、WebUI 接入在文档里都是「待开放」。对外说话，现在就是 HTTP。

---

## 第 1 周复盘

### 我能向同事怎么解释这个项目？

用三句话：

1. **本仓是 Agent 的部署和生命周期托管平台，不是 Agent 框架。** 思考和编排在 Core / Studio；这里负责拉起进程、给 URL、查状态、删掉。
2. **两个口，别打错。** `:8186` 是管理面（deploy / list / get / delete / 自己的 `/health`）。部署成功后的 `url`（本机 `:8090`）才是对话面（`/health`、`/query`、`/reset_conversation`）。对话不经过 8186。
3. **两条发布路。** 低码：`POST /api/v1/agents/deploy` 吃 IR，dev 模式还要本地 `lowcode_agent_runner` 的 whl。高码：`openjiuwen agent deploy <工程目录>`，吃你自己的 Agent whl，再装 `service` / `foundation`。CLI 和 server 必须在同一工作目录起，才会写到同一份 `deployments.db`，管理面才能 list 到高码实例。

生态边界也可以顺口带上：Studio 编排、Core 是引擎、WorkSwarm 只复用 `foundation`、AgentOS 整包太重，二次开发先改 Runtime。

### 卡点是什么？

| 卡点 | 现在的事实 |
|---|---|
| 低码 REST 部署没跑完 | `MODE=dev` 缺 `dist/lowcode_agent_runner-0.1.0-py3-none-any.whl`，契约（422/404）已经验证过 |
| 高码没有 HTTP 发布 | 文档写明待开放；现路是 CLI |
| 管理面控制偏薄 | 没有 stop / start / restart 路由；删除是有的 |
| 多租户还不是鉴权 | 有 `user_id` / `space_id` 标签和列表过滤，`require_tenant=False`；get/delete 的归属校验要自己补 |
| 没有业务 workspace | 隔离粒度是 `deployment_id` 目录，不是项目组工作区 |
| 对话记忆不在框架里 | `conversation_id` 只是请求字段；`day4_echo` 不记历史，reset 也可以是空操作 |
| 共库容易看空列表 | CLI 在仓库根、server 在 `server/` 启动，会各写一份 `deployments.db` |

### 下周优先补哪块？

第 2 周主题是「请求从 API 到进程拉起」。优先顺着这条读，不要先铺治理：

1. **Day 6–8：部署链路。** `server/main.py` → `TenantContextMiddleware` → `management/.../manager.py` → `subprocess/strategy.py` + `deployer.py` → `foundation` 的 venv。目标是能口述：一次 deploy 如何变成 `{DEPLOY_DIR}/{deployment_id}/.venv`，以及租户头现在注入了什么、没拦住什么。
2. **Day 9：把今天的对话面嵌回钩子约定。** 精读 `base_app.py` / `agent_app.py`，对照 `simple_agent_app.py`：`@app.init` 里要不要挂 `app.agent`、`@app.query` 为什么 `yield (msg, last)`、`clear_session` 什么时候真的被调用。
3. **低码 whl 可以后补。** 高码实例已经能 query；低码 runner 是第 2 周 Day 10 抽样，不挡「说清链路」。

**第 1 周验收：** 管理面能起；高码 Agent 已部署并可 query；低码完整 deploy 的前置（runner whl）已经能说清。对话面三个接口本机都打过。

---

## 自检

- [ ] 能指出 8186 和 8090 各承担什么
- [ ] 能解释文档表格的 `/{prefix}` 和 curl 根路径分别对应 AppGroup / 单 AgentApp
- [ ] 能默写 `/query` 的必填字段，以及响应是 SSE `data: {...}`
- [ ] 知道 `type` 由业务 Agent 定义，`last` 不会出现在 SSE 里
- [ ] 知道 `reset_conversation` 返回 ok 不等于会话一定被清空
- [ ] 能用三句话向同事讲清本仓，并说出下周先读部署链路
