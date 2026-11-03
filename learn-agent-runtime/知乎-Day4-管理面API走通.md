# Day 4：管理面全部接口——探活、部署、列表、详情、删除

Day 3 把 `server` 拉起来了，`GET /health` 过关。  
Day 4 只盯管理面这一层：**把 `server/main.py` 里挂出的全部 HTTP 接口走通。**

这天过关标志：你能不看文档，说出管理面**一共有哪些路由**、每个要什么参数、成功返回什么字段；并知道 **`deployment_id` / `url` / `status` 分别从哪来。**

---

## 今天在链路里的位置

```text
curl / Studio
      │
      ▼
 server/main.py     ← 今天读的全部路由（仅此文件显式注册）
      │  health / deploy / list / get / delete
      ▼
 management/        ← Day 4 只「调用到」，不深入 Deployer
      ▼
 Agent 实例 HTTP    ← Day 5 再聊 /query
```

文档 `docs/zh/3. Agent部署.md` 讲的是 **怎么用不同部署模式把低码 Agent 拉起来**（进程 / docker / k8s）；真正绑定请求格式的是 `server/openjiuwen_runtime/server/main.py`。

---

## 管理面全部接口一览（契约）

源码里 `@app.get/post/delete` **一共 5 个业务路由**（无 stop/start/restart，无高码 deploy REST）：

| # | 方法 | 路径 | 作用 | 成功大致形态 |
|---|---|---|---|---|
| 0 | `GET` | `/health` | 管理面自身探活 | `{"status":"healthy"}` |
| 1 | `POST` | `/api/v1/agents/deploy` | 上传 IR，部署**低码** Agent | `201` + `deployment_id` / `url` / `status`… |
| 2 | `GET` | `/api/v1/agents` | 列表（可按 status 过滤） | `{ "deployments": [ ... ] }` |
| 3 | `GET` | `/api/v1/agents/{deployment_id}` | 详情 | 单条部署信息 |
| 4 | `DELETE` | `/api/v1/agents/{deployment_id}` | 删除/下线 | `{ "message": "..." }` |

FastAPI 框架自带（非业务手写，但可用来看契约）：

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc |
| `GET` | `/openapi.json` | OpenAPI JSON |

**没有的接口（容易误以为有）**：`POST .../stop`、`.../start`、`.../restart`；高码 `deploy` HTTP；对话 `/query` 代理（对话打 Agent 自己的端口）。

租户：中间件 `TenantContextMiddleware` 当前 `require_tenant=False`（测试用），路由里仍会取 `user_id` / `space_id`，列表按租户过滤。

---

## 0. `GET /health`

管理面进程是否活着（**不是**某个 Agent 实例的健康检查）。

```bash
curl -s http://127.0.0.1:8186/health
# {"status":"healthy"}
```

Agent 实例探活应打其 `url`，例如 `GET http://127.0.0.1:8090/health`。

---

## 1. `POST /api/v1/agents/deploy`

### 请求

- **Query**
  - `name`（必填）：部署名称（=包名）
  - `mode`（可选，默认 `subprocess`）：部署器类型
  - `port`（可选）：不填则自动分配
  - `userdata`（可选）：用户自定义数据
- **Body**：`multipart/form-data`，字段名 `file`，内容为低码 Agent 的 **IR JSON**

文档示例（docker）：

```bash
curl -X POST \
  "http://127.0.0.1:8186/api/v1/agents/deploy?name=demo&mode=docker" \
  -F "file=@/path/to/ir.json"
```

本机当前 `.env`：`DEPLOY_TYPE=subprocess`，`MODE=dev`，端口 `8186`。subprocess 手测可写成：

```bash
curl -X POST \
  "http://127.0.0.1:8186/api/v1/agents/deploy?name=day4-demo&mode=subprocess" \
  -F "file=@applications/ir_execution_service/ir_execution_service/test/llm_test.json"
```

### 服务端流程（读路由时抓住这条链）

1. 取租户上下文 → 生成 `deployment_id = uuid4()`
2. 把上传文件落到 `DEPLOY_DIR/{deployment_id}/ir.json`
3. `get_deploy_type(mode)`：若全局 `DEPLOY_TYPE` 是 `docker`/`k8s`，**强制覆盖**请求里的 `mode`；只有 `subprocess` 才尊重请求 `mode`
4. subprocess 时 `prepare_subprocess_deployment`：分配/校验端口；`MODE=dev` 还要求本地存在 `dist/lowcode_agent_runner-0.1.0-py3-none-any.whl`
5. 调 `manager.deploy_agent(...)`，成功后过滤内部字段返回

### 成功返回（重点记这三个）

```json
{
  "deployment_id": "<uuid>",
  "type": "agent",
  "name": "day4-demo",
  "status": "running",
  "url": "http://127.0.0.1:<port>/"
}
```

| 字段 | 含义 | 从哪来 |
|---|---|---|
| `deployment_id` | 部署唯一 ID，后续 GET/DELETE 都用它 | 路由里 `uuid.uuid4()`，再塞进 `extras` |
| `url` | Agent 实例对外访问地址 | Deployer 生成；subprocess 形如 `http://{IP}:{port}/` |
| `status` | 部署状态枚举值 | `DeploymentStatus`：`pending` / `running` / `stopped` / `failed` / `running_not_ready` |

HTTP 状态码：成功是 **`201 Created`**（不是 200）。

---

## 2. `GET /api/v1/agents`

可选 query：`status`（别名过滤）。

单条列表项返回：

```json
{
  "deployment_id": "...",
  "name": "...",
  "status": "running",
  "url": "http://...",
  "port": 8123
}
```

外层包一层：`{ "deployments": [ ... ] }`。

---

## 3. `GET /api/v1/agents/{deployment_id}`

在列表字段基础上多了 `type`、`created_at`、`updated_at`。  
不存在 → **`404`**，`detail` 形如 `Deployment xxx not found`。

---

## 4. `DELETE /api/v1/agents/{deployment_id}`

成功：

```json
{ "message": "Deployment <id> deleted" }
```

不存在同样 **`404`**。真正停进程/删容器的动作在 `management.delete_deployment` 里完成。

---

## `mode` vs `DEPLOY_TYPE`（容易混）

| 来源 | 作用 |
|---|---|
| 请求 query `mode` | 单次部署希望用哪种 Deployer |
| `.env` 的 `DEPLOY_TYPE` | 全局策略：`docker`/`k8s` 时**无视**请求 mode，强制该模式；`subprocess` 时才听请求 |

再叠加：`MODE=dev|product` 只在 subprocess 下影响依赖从哪来——dev 用本地 whl，product 走 PyPI。

文档里「进程部署的 runtime-server 启动容器化低码 Agent」= 管理面自己是进程，但某次 deploy 用 `mode=docker`（且 `DEPLOY_TYPE` 允许）。

---

## 手测记录（本机 8186）

前提：`server` 已起，`GET /health` → `{"status":"healthy"}`。仓库里有 IR 样例：

`applications/ir_execution_service/ir_execution_service/test/llm_test.json`

| 操作 | 结果 |
|---|---|
| `GET /api/v1/agents` | `200` → `{"deployments":[]}`（当前无部署） |
| `GET .../not-a-real-id` | `404` → `Deployment not-a-real-id not found` |
| `DELETE .../not-a-real-id` | `404` 同上 |
| `POST .../deploy?name=demo` 不带 file | `422` → body.file required |
| `POST .../deploy` 只带 file 不带 name | `422` → query.name required |
| `POST` 带 IR + name（MODE=dev） | `500` → **缺少** `dist/lowcode_agent_runner-0.1.0-py3-none-any.whl` |

结论（对齐学习计划「有 IR 则低码；没有则先看接口契约」）：

- **接口契约已走通**：参数校验、404、列表空集都符合代码预期。
- **完整低码 REST 部署**仍缺 `lowcode_agent_runner` whl；本仓高码路径不必等它。

也可打开交互文档核对：`http://127.0.0.1:8186/docs`（OpenAPI）。

---

## 加餐：高码 empty Agent 已拉起（`day4-echo`）

文档写「高码 HTTP 发布待开放」。当前主路是 **CLI → Manager → 自研 WHL**，不走 `POST /api/v1/agents/deploy`。

工程目录：`learn-agent-runtime/day4-echo`（empty 模板，回显用户消息）。

```bash
# 1) 本仓 CLI（不要用 anaconda 里那个同名 openjiuwen）
cd server && source .venv/bin/activate
uv pip install -e ../cli -e ../foundation -e ../management

# 2) MODE=dev 需要 dist 里先有底座 whl
cd ..
uv build foundation --out-dir dist
uv build service --out-dir dist

# 3) 创建 + 部署
openjiuwen new agent day4-echo --template empty --output-dir ./learn-agent-runtime
set -a; source server/.env; set +a
export DIST_DIR=$PWD/dist
openjiuwen agent deploy ./learn-agent-runtime/day4-echo --port 8090
```

本机结果：

| 项 | 值 |
|---|---|
| `deployment_id` | `889236ca-3155-475b-9a6a-7a292e93cf91` |
| `url` | `http://127.0.0.1:8090/` |
| `status` | `running` |

```bash
curl -s http://127.0.0.1:8090/health
# {"status":"healthy","app":"day4_echo","version":"0.1.0"}

curl -s -N -X POST http://127.0.0.1:8090/query \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"你好，Day4 高码"}],"conversation_id":"day4-demo-1"}'
# data: {"type":"text_delta","content":"收到：你好，Day4 高码"}
# data: {"type":"result","content":"收到：你好，Day4 高码"}
```

口诀：**低码 REST 吃 IR + lowcode runner；高码 CLI 吃你自己的 Agent whl + service/foundation 底座。**

回收：`openjiuwen agent delete 889236ca-3155-475b-9a6a-7a292e93cf91`

---

## 端口别搞混

| 端口 | 是谁 | 干什么 |
|---|---|---|
| **8186** | Runtime `server` 管理面 | `/health`、`/api/v1/agents/...` |
| **8090** | 业务 Agent 实例（如 `day4_echo`） | `/health`、`/query`、`/reset_conversation` |

```text
你 ──管理──► server :8186
你 ──对话──► agent  :8090   ← 不经 server 转发
```

`/query` 请求体字段是 **`messages`**（不是 `msgs`）。

---

## 共库：server 才能「查到」高码部署

CLI 与 server 都写相对路径 `deployments.db`，**跟当前工作目录绑定**。

| 在哪启动 / 执行 | 用哪份库 |
|---|---|
| `server/` 目录 | `server/deployments.db` |
| **仓库根目录** | 根目录 `deployments.db` ← CLI 部署 `day4_echo` 在这 |

所以：在 `server/` 里 `openjiuwen agent list` 会空；server 若也从 `server/` 起，`GET :8186/api/v1/agents` 也看不到高码实例。

**正确姿势：仓库根启动 server + 仓库根跑 CLI。**

```bash
cd /Users/song/Documents/vscode/agent-runtime
source server/.venv/bin/activate
set -a; source server/.env; set +a
python -m openjiuwen_runtime.server.main
```

共库后：

```bash
curl -s http://127.0.0.1:8186/api/v1/agents
curl -s http://127.0.0.1:8186/api/v1/agents/889236ca-3155-475b-9a6a-7a292e93cf91
```

就能看到高码 Agent 的 `deployment_id` / `url` / `status`。

---

## server 能怎么「控制」高码 Agent？

对外 REST **只有**：list / get / delete（外加低码 deploy）。  
**没有** HTTP 级的 stop / start / restart；`management` 里虽有 `stop_deployment`，server 没挂路由。

| 动作 | 怎么做 |
|---|---|
| 查列表/详情 | `GET /api/v1/agents`、`GET /api/v1/agents/{id}` |
| 下线删除 | `DELETE /api/v1/agents/{id}`（停进程 + 清记录） |
| 高码发布 | **CLI** `openjiuwen agent deploy <工程目录>` |
| 对话 | 打 Agent 的 `url`，如 `POST :8090/query` |

控制面偏薄是首版边界（偏 Studio 低码发布/下架），也是后续二次开发常见缺口。

---

## 高码 Agent 日常部署（备忘）

```bash
cd /Users/song/Documents/vscode/agent-runtime
source server/.venv/bin/activate          # 本仓 CLI，别用 anaconda 同名命令
set -a; source server/.env; set +a
export DIST_DIR=$PWD/dist

# 改业务：编辑 day4_echo_runner.py 的 @app.query
# 再部署（可先 delete 旧 id）
openjiuwen agent deploy ./learn-agent-runtime/day4-echo --port 8090
openjiuwen agent list
```

---

## 一句话带走

**8186 管生命周期，8090 聊业务；高码用 CLI 部署，server 共库后才能 list/get/delete。**  
控制力目前偏弱（无 stop/start HTTP），这是产品现状，不是操作失误。

---

## 自检

- [ ] 能默写管理面全部 5 个业务路由（含 `/health`）  
- [ ] 知道 `/docs` / `/openapi.json` 是框架自带  
- [ ] 知道 deploy 成功返回的三个关键字段含义  
- [ ] 分得清请求 `mode`、`DEPLOY_TYPE`、`MODE`  
- [ ] 本机至少验证过 list + 假 id 的 404  
- [ ] 能说清低码 REST vs 高码 CLI 两条部署路  
- [ ] 分得清 8186 / 8090，以及为何要在仓库根共库  



