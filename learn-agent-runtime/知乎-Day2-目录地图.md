# openJiuwen Agent Runtime 目录地图：先认路，再改代码

Day 1 把边界画清楚了：本仓是 **Agent 部署与生命周期托管平台**，不是 Agent 框架。  
Day 2 只做一件更落地的事：**把仓库顶层目录当成一张地图，写清每个目录一句话职责，并标出「该改 / 少改」。**

入门第二常见坑不是读不懂代码，而是上来就改错层——改了 `foundation` 牵一发动全身，或者在 `applications` 里硬塞本该放在 `management` 的逻辑。

---

## 先记一张调用链

把目录关系压成一条链路，后面再对号入座：

```text
客户端 / Studio / CLI
        │
        ▼
   server/          ← 管理面 REST（部署、查列表、删实例、健康检查）
        │
        ▼
 management/        ← 选策略并真正拉起 / 停掉实例
        │
        ├── subprocess / docker / k8s
        ▼
 applications/      ← 具体 Agent 进程（低码、工作流、A2A…）
        │
        ▼
   service/         ← Agent 侧统一壳子：/query、/health、/reset_conversation
        │
        ▼
 foundation/        ← DB / 配置 / 日志 / 端口等底座（被上面多层复用）
```

再压成一句口诀：

**Server 管「管什么」；Management 管「怎么部署」；Service + Applications 管「对话怎么跑」；Foundation 是大家共用的底座。**

补充三个容易混的点（Day 3 还会再练手感）：

1. **不是每个目录都起一个 HTTP**：常驻管理面只有 `server`；`management` 是库；`service` 随每个已部署 Agent 进程一起露出口子。  
2. **谁真正拉起 Agent**：`server` 收 `POST /api/v1/agents/deploy`，`management` 里的 Deployer（subprocess / docker / k8s）动手启停。  
3. **本机 vs 远程**：`subprocess` 只能和 server 同机；要远程落点用 `docker` / `k8s`。远程 curl 管理面 ≠ Agent 跑到你电脑上。

---



## 九个顶层目录：各写一句话


| 目录              | 一句话职责                                                                                                    |
| --------------- | -------------------------------------------------------------------------------------------------------- |
| `server/`       | FastAPI **管理面入口**：租户中间件 + `/api/v1/agents/`* 部署/查询/删除 + `/health`                                        |
| `management/`   | **部署与会话编排核心**：`DeploymentManager` + subprocess/docker/k8s Deployer，负责实例启停与状态                             |
| `service/`      | Agent 进程的 **统一服务抽象**（`BaseApp` / `AgentApp`），规定对话面 API，不关心具体业务 Agent                                     |
| `foundation/`   | **跨模块底座**：DB（sqlite/mysql/gaussdb）、配置、日志、messaging、security 等共用能力                                        |
| `applications/` | **具体 Agent 实现**（如 `lowcode_agent`、`workflow_agent`、`ir_execution_service`、`a2a_service`），由 Management 拉起 |
| `cli/`          | 命令行入口 `openjiuwen`，复用 management 能力做运维/管理（能力仍在补齐）                                                        |
| `scripts/`      | 启动 / 构建 / 发布脚本（如 `run-server.sh`、`deploy_dev_server.sh`、`build-cli.sh`）                                  |
| `docker/`       | 镜像构建文件（`Dockerfile.server`、`Dockerfile.lowercode`）                                                       |
| `docs/`         | 中英文文档（快速开始、配置、部署、接入、安全）                                                                                  |


包名对照（扫 `pyproject.toml` 时不容易晕）：


| 目录           | 包名                              | 主要依赖                        |
| ------------ | ------------------------------- | --------------------------- |
| `server`     | `agent-runtime-server`          | `foundation` + `management` |
| `management` | `openjiuwen-runtime-management` | `foundation`                |
| `service`    | `openjiuwen-runtime-service`    | `foundation`                |
| `foundation` | `openjiuwen-runtime-foundation` | 最底层                         |
| `cli`        | `agent-runtime-cli`             | `foundation` + `management` |


---



## 每个优先目录里，先看哪个文件

不必深读实现，Day 2 只要「认路口」：

1. `server/`
  - 入口：`server/openjiuwen_runtime/server/main.py`  
  - 一眼能看到管理面路由：`POST /api/v1/agents/deploy`、`GET /api/v1/agents`、详情、删除、`GET /health`  
  - 旁边还有租户中间件 `middleware/tenant.py`
2. `management/`
  - 入口：`management/.../manager.py`（`DeploymentManager`）  
  - 策略目录：`deployments/subprocess|docker|k8s/`  
  - 另有 `session/`：部署起来之后的会话与服务访问编排
3. `service/`
  - 入口：`service/.../app/base_app.py`  
  - 这里定的是 Agent 进程对外契约，不是「某个业务 Agent 的业务逻辑」
4. `foundation/`
  - 扫目录即可：`db/`、`config/`、`log/`、`messaging/`、`security/`  
  - Day 2 目标是知道「底座长什么样」，不是改它
5. `applications/`
  - 把子项目当成「被托管的具体 Agent」：低码、工作流、IR 执行、A2A 等  
  - 你二次开发「新 Agent 类型」时才会重点进来

其余三个辅助目录：`cli/` 是命令行面；`scripts/` / `docker/` 是怎么起服务、怎么打镜像；`docs/` 是官方说明，Day 3 起服务会直接用到。

---



## 二次开发：优先区 vs 少改区

- 结合 Day 1 的「轻底座 + 自研治理」，目录级优先级可以这样记：

### 优先区（二次开发主战场）

- `server`：加/改管理 API、请求模型、租户规则、对接外部系统  
- `management`：加部署策略、改生命周期、会话路由与实例编排  
- `service`：扩展对话面能力、调整 Agent 基类契约  
- `cli`：补命令、把运维动作脚本化



### 按需区

- `applications`：接新 Agent 类型，或改某种已有 Agent 行为时再动  
- `scripts` **/** `docker` **/** `docs`：交付与文档配套，跟随主改动一起更新



### 尽量少改区

- `foundation`：被 server / management / service / cli，以及 WorkSwarm 等外部产品复用  
乱动 DB、日志、配置抽象，很容易「本仓能跑、别人挂了」或「一处修、处处炸」

一句话：**改托管面，少动共享底座；具体 Agent 逻辑进** `applications`**，别往** `foundation` **塞业务。**

---



## 用两个场景检验你有没有认路

**场景 A：想加一个「按项目组列出 Agent」的管理接口**  
→ 先动 `server`（路由与请求模型），再视情况落到 `management`（查询/过滤逻辑）。  
一般 **不要** 为了这件事去改 `foundation`。

**场景 B：想支持一种新的部署方式（比如特殊容器运行时）**  
→ 主战场在 `management/deployments/`，对外若需暴露参数再改 `server`。  
对话协议本身通常仍走 `service`，与部署策略解耦。

**场景 C：想做一个自己的高码 Agent**  
→ 实现落在 `applications`（或独立工程），并遵循 `service` 的 `AgentApp` 契约；部署仍走 `server` → `management`。

如果这三个场景你都能立刻指出「第一刀砍哪一层」，Day 2 就算过关。

---



## 自测：你今天有没有搞清楚

闭卷答这几题：

1. 用口诀说清：`server` / `management` / `service` / `foundation` / `applications` 各管什么？
2. 九个顶层目录里，哪些是二次开发优先区？哪个是尽量少改区？为什么少改？
3. 对错判断：
  - 对话 `/query` 主要实现在 `server`？（应为错，在 Agent 进程侧，经 `service` 抽象）  
  - 部署策略（subprocess/docker/k8s）主逻辑在 `management`？（应为对）  
  - 多项目组治理接口应优先改 `foundation`？（应为错）  
  - `cli` 与 `server` 都可能调用 `management`？（应为对）
4. 若要「加管理 API」和「加一种新 Agent」，分别优先进哪个目录？

标准答案可以压成三句：

1. **Server 管管理面，Management 管部署编排，Service 管 Agent 服务契约，Applications 是具体 Agent，Foundation 是共享底座；**
2. **优先改 server / management / service / cli，少改 foundation；**
3. **加管理能力走 server（+management），加 Agent 实现走 applications（守 service 契约）。**

---



## 写在最后

Day 2 真正该交付的不是背目录名，而是一张**可指导改代码的地图**：知道请求从哪进、实例在哪起、对话在哪跑、底座为什么少动。

下一篇计划写：**环境准备与启动——读配置、起 Runtime、验证** `GET /health`**。**

（基于 openJiuwen Agent Runtime 公开文档与仓库学习笔记整理，仅作技术理解分享。）