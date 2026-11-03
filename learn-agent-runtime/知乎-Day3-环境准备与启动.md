# Day 3：把 Runtime 跑起来——.env 六件套与 /health

Day 1 讲边界，Day 2 认目录。  
Day 3 只干一件更「手感」的事：**配好 `server/.env`，把管理面服务拉起来，用 `GET /health` 确认它活着。**

这天过关的标志不是把文档背下来，而是你能闭着眼睛说出：**改哪几个键、用哪种启动路径、成功时该看到什么。**

---

## 先对齐：今天启动的是哪一层？

启动的是 **`server/` 管理面**（Agent Runtime Manager），不是某个具体 Agent 对话进程。

```text
你 curl /health
      │
      ▼
 server/  ← 今天要起来的东西（默认 :8186）
      │
      ▼（Day 4 才会真正走）
 management → applications（部署后的 Agent 实例）
```

所以今天成功的最小闭环是：

**进程起来 → 监听 8186 → `{"status":"healthy"}`**

---

## 常见误解：server / management / service 都要起 HTTP 吗？

**不要。** 三者角色不同，只有「真正跑起来的进程」才会各自带 HTTP。

| 目录 | 是不是独立常驻 HTTP | 实际角色 |
|---|---|---|
| **server** | 是（Day 3 起的这个） | 管理面：部署 / 列表 / 删除 / `/health`，默认 `:8186` |
| **management** | 否 | **库**：被 server 调用，负责选策略、拉起 / 停掉实例 |
| **service** | 本身不是常驻服务 | **Agent 侧壳子**：被 applications 使用；每个**已部署的 Agent 进程**再开自己的 HTTP（`/query`、`/health`…） |

口诀：

**平时只先起 `server` 这一台管理面；`management` 装在它里面当部署引擎；真正对话时，每个 Agent 实例才再起一个（或多个）HTTP 口。**

---

## Agent 实例到底谁来启动？

**控制权在 `management`，入口命令来自 `server`。**

```text
Studio / curl
    │  POST /api/v1/agents/deploy
    ▼
server          ← 收请求、存 IR、分配端口，调用 manager
    │  manager.deploy_agent(...)
    ▼
management      ← 真正「决定怎么起、动手起」
    │  按 DEPLOY_TYPE / mode 选 Deployer
    ├── LocalSubprocessDeployer  → 本机子进程
    ├── DockerDeployer           → 容器
    └── K8sDeployer              → Pod
    ▼
applications + service   ← 被拉起的 Agent 进程（自己再开 /query 等）
```

分工：

- **谁下命令**：客户端 / Studio 调管理面 API  
- **谁转发**：`server`（不自己直接 `Popen` 业务 Agent）  
- **谁控制启停**：`management` 的 `DeploymentManager` + 对应 Deployer  
- **谁被启动**：`applications` 里的具体 Agent（套着 `service` 壳）

---

## 只能本机起 Agent 吗？可以远程吗？

**可以远程，但不靠 `subprocess` 跨机器 SSH 起进程。** 分两层看：

### Agent 落在哪台机器

| `DEPLOY_TYPE` | Agent 跑哪 | 算不算远程 |
|---|---|---|
| `subprocess` | **和 runtime-server 同一台机** 的子进程 | 只能本机 |
| `docker` | Docker 引擎所在宿主机（默认同机；实现支持 `-H` 指远程 Docker） | 可到远程 Docker 主机 |
| `k8s` | **集群节点** 上的 Pod | 天然分布式 / 远程 |

本地学习默认 `subprocess`，所以会感觉「只能本机起」。要把 Agent 跑到别的机器 / 集群，改用 **docker / k8s**。

### 调用可以远程

`server` 若监听 `0.0.0.0:8186`，**另一台电脑**可以 curl / Studio 调 deploy。  
但若仍是 `subprocess`，Agent 进程还是起在 **server 那台机器**上——只是「下命令的人」可以在远程。

再压一句：**控制面可以远程访问；Agent 落点由部署策略决定——本机进程 / Docker 主机 / K8s 集群。**

---

## 文档怎么读（别平均用力）

### `docs/zh/1. 快速开始.md`

抓三条就够：

1. 环境：`python>=3.11.4`、`uv`、git、bash  
2. 先有 `.env`，再安装 / 启动  
3. 启动命令本质是：`python -m openjiuwen_runtime.server.main`，默认端口 **8186**

文档后半段是 Studio 联调发布，那是后续章节；Day 3 可以先不跟。

### `docs/zh/2. 配置说明.md`

当作 **`.env` 字典**。今天必懂六项（学习计划勾选的那些），其余（镜像、K8s、UV_EXTRA_ARGS）知道「存在」即可。

---

## 实操：复制 `.env`

```bash
cd server
cp .env.example .env
```

`.env` 已在 `.gitignore` 里，不会进仓库——改本地配置放心。

**本地学习建议值（本机已按此配）：**

| 键 | 建议 | 为什么 |
|---|---|---|
| `RUNTIME_DB_TYPE` | `sqlite` | 免装 MySQL，部署记录落本地库文件 |
| `IP` | `127.0.0.1` | 本机回环；必填，缺了 Settings 会校验失败 |
| `PORT` | `8186` | 管理面默认端口 |
| `DEPLOY_DIR` | `deploys` | 相对路径会解析到仓库根下并自动创建 |
| `DEPLOY_TYPE` | `subprocess` | 本地默认：子进程拉 Agent，不依赖 Docker/K8s |
| `MODE` | `dev` | 源码学习态：依赖/whl 走本地开发路径 |

示例里默认常是 `RUNTIME_DB_TYPE=mysql` + `MODE=dev`。  
本地第一天没必要硬上 MySQL——**先 sqlite 跑通 /health**，再换 mysql 验证连接配置。

---

## 六件套：各自管什么

### 1. `RUNTIME_DB_TYPE`

Runtime **管理面自己的库**（部署记录等），不是大模型向量库。

- `sqlite`：本地文件，上手最快  
- `mysql` / `gaussdb` / `opengauss`：要配 HOST/PORT/USER/PASSWORD/NAME，库需**事先建好**

源码里选择逻辑很直接（`server/.../main.py`）：按类型实例化对应 Handler。

### 2. `IP`

宿主机对外地址，Agent 实例回调 / 客户端拼地址时会用到。  
本机填 `127.0.0.1`；真机部署填可达 IP。配置校验：**有 `.env` 时必填。**

### 3. `PORT`

管理面监听端口，默认 `8186`。  
注意：文档里的 `HOST`（默认 `0.0.0.0`）是「绑在哪张网卡」；`IP` 是「对外宣告的地址」——别混。

### 4. `DEPLOY_DIR`

部署过程落盘目录（配置、临时文件等）。  
相对路径 → 拼到**仓库根**；不存在会自动 `mkdir`。

### 5. `DEPLOY_TYPE`

收到部署请求时，**怎么拉起 Agent**（真正动手的是 management 里对应 Deployer）：

- `subprocess`：本机子进程（本地默认，Agent 与 server 同机）  
- `docker` / `k8s`：强制容器 / 集群策略，且通常要配 `LOWCODE_IMAGE`（可把 Agent 落到远程主机 / 集群节点）

今天只启动管理面，**还不会真正 deploy**；但这个键决定你后面 Day 4 一按部署会走哪条路。

### 6. `MODE`（仅 `DEPLOY_TYPE=subprocess` 时有意义）

- `dev`：本地源码 / 本地 dist whl  
- `product`：按已安装包 / PyPI 环境跑

口诀：**本仓源码调试 → `dev`；装完包上线 → `product`。**

---

## 怎么启动（文档 vs 仓库现状）

README 写的是：

```bash
bash scripts/run-server.sh
```

当前仓库里 **没有** `scripts/run-server.sh`，对应能力主要在：

| 路径 | 特点 |
|---|---|
| `scripts/deploy_dev_server.sh` | 偏完整开发启动：读 `.env`、编 whl、`uv sync`、再 `python -m ...` |
| `scripts/run-server.ps1` | Windows 版同类逻辑 |
| `server/deploy.sh` | 更轻：venv + 装 foundation/management，但端口会在 8100–8299 自选 |
| 手工 | `uv sync` → `uv pip install -e ../foundation -e ../management` → `python -m openjiuwen_runtime.server.main` |

Day 3 目标是 **/health**，手工轻量路径足够：

```bash
cd server
uv venv && source .venv/bin/activate
uv sync
uv pip install -e ../foundation -e ../management
set -a; source .env; set +a
python -m openjiuwen_runtime.server.main
```

入口末尾就是用 Settings 里的 `HOST`/`PORT` 起 uvicorn。

---

## 验证：`GET /health`

服务起来后：

```bash
curl -s http://127.0.0.1:8186/health
```

期望：

```json
{"status":"healthy"}
```

对应实现极简：

```84:87:server/openjiuwen_runtime/server/main.py
@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}
```

注意：这是 **管理面存活探针**，不代表已经成功部署过任何 Agent；Agent 自己的 `/health` 是实例端口上的另一回事（Day 4+）。

也可打开：`http://127.0.0.1:8186/docs` 看 Swagger。

---

## server 管理面 HTTP 一览

实现都在 `server/openjiuwen_runtime/server/main.py`，当前共 **5 个接口**：

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/health` | 管理面健康检查 → `{"status":"healthy"}` |
| `POST` | `/api/v1/agents/deploy` | 上传 IR，部署 Agent |
| `GET` | `/api/v1/agents` | 部署列表（可用 query `status` 过滤） |
| `GET` | `/api/v1/agents/{deployment_id}` | 单个部署详情 |
| `DELETE` | `/api/v1/agents/{deployment_id}` | 删除 / 下架部署 |

### `POST /api/v1/agents/deploy` 要点

- **Body**：`multipart` 上传 IR 文件字段 `file`
- **Query**：
  - `name`（必填）
  - `mode`（默认 `subprocess`）
  - `port`（可选，不填则自动分配）
  - `userdata`（可选）
- **成功**：HTTP 201，大致含 `deployment_id`、`type`、`name`、`status`、`url`

### 边界提醒

- 上表是 **管理面**（生命周期）接口。
- 对话相关的 `/query`、实例 `/health`、`/reset_conversation` 在**部署后的 Agent 进程**上（`service` + `applications`），不在 `server`。

Day 3 只要求会打 `/health`；其余四个是 Day 4 手测主战场。

---

## 和前两天怎么串起来

- Day 1：Runtime = 部署与生命周期托管 → 今天启动的正是托管入口  
- Day 2：`server` 是管理面 REST → `/health` 就挂在这层  
- Day 3：环境与进程真的起来了 → 明天才能放心手测 deploy API

---

## 自测：今天有没有搞清楚

闭卷答：

1. 本地学习为什么优先 `sqlite` + `subprocess` + `MODE=dev`？  
2. `IP` 和 `HOST`、`PORT` 分别管什么？  
3. `DEPLOY_TYPE` 和 `MODE` 的生效关系是什么？  
4. `GET /health` 成功说明了什么、**不能**说明什么？  
5. README 的 `run-server.sh` 缺失时，你还有哪两条启动退路？  
6. `server` / `management` / `service` 谁常驻 HTTP？Agent 实例由谁真正拉起？  
7. 想把 Agent 跑到别的机器，该改 `DEPLOY_TYPE` 还是只远程 curl 一下就行？

压成几句标准答案：

1. **六件套决定「用什么库、对外地址、监听口、落盘目录、怎么部署、依赖从哪来」；**  
2. **今天起来的是 server 管理面；management 是库；service 是 Agent 进程壳；**  
3. **实例启停由 management 的 Deployer 控制；subprocess 同机，远程落点靠 docker/k8s；**  
4. **`/health` 只证明管理面活着，部署通不通是 Day 4。**

---

## 今日清单（对照学习计划）

- [x] 阅读快速开始 + 配置说明  
- [x] 复制并理解六件套（本地改为 sqlite）  
- [x] 启动 Runtime（默认 8186）  
- [x] `GET /health` 成功 → `{"status":"healthy"}`  

本机实操记录：`RUNTIME_DB_TYPE=sqlite`，日志可见 `Using database: sqlite`，Uvicorn 监听 `0.0.0.0:8186`。
