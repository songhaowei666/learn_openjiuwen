# openJiuwen Agent Runtime 到底是什么？先把边界画清楚

最近在啃 openJiuwen 的 **Agent Runtime** 仓库。入门第一天最容易踩的坑不是装环境，而是把几个名字搞混：Studio、Core、Runtime、WorkSwarm、AgentOS……看起来都跟 Agent 有关，职责却完全不是一回事。

这篇只讲一件事：**本仓是什么、不是什么，以及它在生态里站哪一层。**

---

## 一句话定位

**Agent Runtime = Agent 的部署与生命周期托管平台，不是 Agent 框架本身。**

换句话说：

- 它负责：把已经开发好的 Agent **部署上去、跑起来、查状态、删掉、做健康检查**；
- 它不负责：当推理引擎、当编排 IDE、当办公协作入口。

如果你脑子里还在问「Agent 怎么思考、怎么编排工具」，那问题多半该去找 **Core / Studio**，而不是 Runtime。

---

## Runtime 主要解决什么问题

按官方定位，它盯住的是「从开发态到生产态」这一段：

1. **统一部署**：不同类型的 Agent，用同一套管理接口部署并对外服务；
2. **多租户隔离**：用 `user_id` / `space_id` 这类上下文，区分不同用户与空间的运行实例；
3. **多种部署方式**：默认 `subprocess`（子进程），也预留 `docker`、`k8s`；
4. **生命周期管理**：部署、列表、详情、删除、健康检查。

管理面常见接口大致是：

- `POST /api/v1/agents/deploy`
- `GET /api/v1/agents`
- `GET /api/v1/agents/{deployment_id}`
- `DELETE /api/v1/agents/{deployment_id}`
- `GET /health`

部署成功后，真正对话走的是 Agent 实例自己的口子，比如 `/query`、`/health`、`/reset_conversation`。

---

## 生态里这几个产品分别干什么

把边界写成一张对照表，比背概念快：

| 产品 | 它是什么 | 和 Runtime 的关系 |
|------|----------|-------------------|
| **agent-studio** | 低码编排平台：搭流程、产 Agent | 配置 Runtime 地址后，可一键发布 / 下架 / 在线验证 |
| **agent-core** | Agent SDK / 引擎 | 提供 Agent 的底层运行与能力实现；Runtime 托管的是「跑起来的实例」 |
| **WorkSwarm** | 办公协作入口 | **另一套产品**；与本仓的关系是复用 `foundation`，不是 Runtime 本体 |
| **agentos-enterprise** | 企业整包交付方案 | 能力全、包袱重；**二次开发别一上来就改它** |
| **agent-runtime（本仓）** | 部署与生命周期托管 | 把 Agent 从「写好了」接到「线上可调」 |

记住三个易错点：

1. **Runtime ≠ WorkSwarm**：共享基础库，产品目标不同；
2. **Runtime ≠ Agent 框架**：框架/引擎在 Core；编排在 Studio；
3. **二次开发优先改 Runtime，不优先 fork AgentOS**。

---

## 二次开发该改哪、不该改哪

如果你的目标是「多项目组 Agent 托管与管理」，建议默认姿态是：

**Runtime 做托管底座；治理层（权限、审批、审计、项目组目录等）自己长。**

改动优先级可以粗暴记：

- **优先区**：`server`（管理面 API / 租户中间件）、`management`（部署编排）、`service`（Agent 服务抽象）、后续还有 `cli`
- **少动区**：`foundation`（DB、venv、端口、部署目录等基础能力）——被 WorkSwarm 等外部产品复用，乱动容易牵一发动全身
- **先别碰**：`agentos-enterprise` 整包——太重，不能马上上手

一句话：**轻底座 + 自研治理**，比「把企业整包拆开改」现实得多。

---

## 自测：你今天有没有搞清楚

闭卷答这几题，答不上来就再读一遍本文：

1. 用一句话说：本仓是什么、不是什么？
2. Studio / Core / WorkSwarm / AgentOS 各自干什么？和 Runtime 什么关系？
3. 对错判断：
   - 二次开发应优先从 AgentOS 改起？（应为错）
   - WorkSwarm 和 Runtime 是同一产品？（应为错）
   - Runtime 负责把 Agent 带到可在线调用的生产态？（应为对）
   - Agent 的推理/编排应主要写在 Runtime 里？（应为错）
4. 做多项目组改造时，为什么先动 Runtime、少动 `foundation`？

标准答案可以压成三句：

1. **本仓 = 部署与生命周期托管，不是 Agent 框架；**
2. **Studio 编排发布 / Core 引擎 / Swarm 协作入口（只吃 foundation）/ AgentOS 企业整包（先别碰）；**
3. **二次开发改托管面，少动共享底座。**

---

## 写在最后

入门 Agent Runtime，第一天真正该交付的不是一段可跑代码，而是一张**生态边界图**。边界画清了，后面读目录、起服务、跟部署链路，才不会把「引擎、编排、托管、协作、企业整包」揉成一团。

下一篇计划写：**顶层目录地图——`server` / `management` / `service` / `foundation` 各自一句话职责。**

（基于 openJiuwen Agent Runtime 公开文档与仓库学习笔记整理，仅作技术理解分享。）
