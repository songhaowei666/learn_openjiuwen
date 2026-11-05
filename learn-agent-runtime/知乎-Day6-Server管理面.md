# Day 6：Server 管理面——租户头怎么进来，隔离做到哪一步

Day 4 把管理面 5 个接口的契约走通了。  
Day 6 只回答一件事：**这些接口口口声声「仅当前租户」，代码到底有没有拦住别人。**

精读两处：

- `server/openjiuwen_runtime/server/main.py`
- `server/openjiuwen_runtime/server/middleware/tenant.py`

过关标志：能不看源码说出 `X-User-ID` / `X-Space-ID` 从哪读、写到哪、默认缺头会不会 401；以及 **list 什么时候过滤、get/delete 有没有校验归属**。

---

## 今天在链路里的位置

```text
请求（可带 X-User-ID / X-Space-ID）
        │
        ▼
 TenantContextMiddleware          ← 只读头，写入 request.state
        │  默认不强制
        ▼
 main.py 路由
   deploy ──► 把 user_id / space_id 写进部署记录
   list   ──► 有值才当过滤条件
   get / delete ──► 取出了租户，查询却只用 deployment_id
        │
        ▼
 DeploymentManager（Day 7 再精读部署过程）
```

口诀：**头是标签，不是门锁。** 部署时贴上 `user_id` / `space_id`；列表在你自己带头时才会按标签筛；知道 `deployment_id` 就能查、能删，不看标签。

---

## 1. 头是怎么注入的

中间件是 `TenantContextMiddleware`，在 `main.py` 里这样挂上，覆盖全部 HTTP 路由（包括 `/health`）：

```79:79:server/openjiuwen_runtime/server/main.py
app.add_middleware(TenantContextMiddleware, require_tenant=False)
```

`dispatch` 做三件事，没有第四件：

1. 从请求头取 `X-User-ID`、`X-Space-ID`（代码里又写了一遍全小写；Starlette 的 `Headers.get` 本身不区分大小写，两次查找是同一件事）。
2. `require_tenant=True` 时，两个头缺一就直接 `401`，body 为 `Missing tenant context: X-User-ID and X-Space-ID headers are required`。缺头的请求到不了路由。
3. 把读到的值（没有就是 `None`）写到 `request.state.user_id`、`request.state.space_id`，然后 `call_next`。

路由侧统一用 `get_tenant_context(request)` 再读出来，返回 `(user_id, space_id)`。读不到属性时也是 `None`，不会抛错。

文件头注释写「从 HTTP Header 或 JWT Token 中提取」。**实现里没有解析 `Authorization`，也没有解 JWT。** 现在唯一入口就是这两个头。注释和 `__init__` 文档还写 `require_tenant`「默认 True」；函数签名的默认值是 `False`。以签名和 `main.py` 的调用为准。

也没有从环境变量读这个开关。要强制租户，得改 `add_middleware` 那一行（或以后做成配置）。`.env` 改不了。

---

## 2. 默认强制租户吗

**不强制。**

注册时写死 `require_tenant=False`，旁边注释是「临时禁用租户验证，测试用」。于是：

| 请求 | 现在的结果 |
|---|---|
| 不带两个头 | 继续进路由，`user_id`、`space_id` 都是 `None` |
| 只带其中一个 | 同样放行，缺的那个是 `None` |
| 两个都带 | 放行，原样放进 `request.state` |
| `GET /health` | 中间件照样跑，但处理函数不读租户，永远 `{"status":"healthy"}` |

空字符串当成没带：`require_tenant=True` 时过不了 `if not user_id`；列表过滤时 `if params.user_id` 也不会把它放进条件。

当前进程里，不带租户头调用 deploy / list / get / delete，都不会因为「没租户」而 401。

---

## 3. 四个接口各自怎么用这两个值

### deploy：会落库，当标签

`POST /api/v1/agents/deploy` 取出上下文，放进 `DeployAgentParams.user_id` / `space_id`。`DeploymentManager._deploy` 用它们填 `DeploymentCreate`，写入 `deployment` 表。两列都可空（`string`，长度 64），并各有一个普通索引。

不带头部署时，这两列就是 `NULL`。响应体只回 `deployment_id`、`type`、`name`、`status`、`url`，**不回** `user_id` / `space_id`。标签在库里，调用方从 HTTP 响应上看不到。

### list：带头才过滤，不带头就是全量

`GET /api/v1/agents` 的文档字符串写「仅返回当前租户的部署」。过滤发生在 `DeploymentManager.list_deployments`：

```239:242:management/openjiuwen_runtime/management/manager.py
        if params.user_id:
            filters[DeploymentFields.USER_ID] = params.user_id
        if params.space_id:
            filters[DeploymentFields.SPACE_ID] = params.space_id
```

这是**可选 AND**，不是「必须按租户」：

| 请求头 | 实际查询 |
|---|---|
| 两个都有 | `deployment_type=agent`，并且 `user_id` 与 `space_id` 都相等 |
| 只有 `X-Space-ID` | 该 space 下全部 agent（不限 user） |
| 只有 `X-User-ID` | 该 user 的全部 agent（不限 space） |
| 都不带 | 只有类型（以及可选的 `status`），**所有租户的 agent 都在列表里** |

`NULL` 列不会匹配某个具体 id。所以「带头的租户」看不到「没带头部署出来的记录」；「不带头的人」反而看得到所有人的。

列表项同样不返回 `user_id` / `space_id`，只有 `deployment_id`、`name`、`status`、`url`、`port`。

### get：不校验归属

`GET /api/v1/agents/{deployment_id}` 也取了 `user_id, space_id`，随后没有使用。调用是：

```297:299:server/openjiuwen_runtime/server/main.py
        deployment = await manager.get_deployment(
            deployment_id
        )
```

`get_deployment` 的条件只有 `deployment_id`。记录上的 `user_id` / `space_id` 既不参与查询，也不和请求头比较。找到就返回详情（同样不含租户字段）；找不到才 404。

知道 UUID，任意调用方都能读到别人的 `url`、端口、状态。

### delete：不校验归属

`DELETE /api/v1/agents/{deployment_id}` 同样取出租户后丢掉。`delete_deployment(deployment_id)` 按 id 停进程、删策略侧记录、再删 `deployment` 表。成功与否只看这条 id 在不在，不看它属于谁。

知道 UUID，就可以删掉另一个 `space_id` 的部署。

---

## 4. 直接回答今天的两道题

**list 按租户过滤了吗？**

过滤函数写了，但是条件触发。两个头都在时，按 user + space 过滤；只带一个时只滤那一列；都不带时不过滤租户。默认（测试用法、不带头）等于列出全部 agent 部署。

**get / delete 真正校验归属了吗？**

没有。路由注释和函数文档写了「仅能访问 / 仅能删除当前租户的部署」，处理函数拿到租户上下文后没有拿去比对。Manager 的 get/delete 签名里也没有 `user_id` / `space_id` 参数。归属校验目前是注释，不是行为。

对照：

| 能力 | 现状 |
|---|---|
| 从头注入 `request.state` | 有 |
| 缺头 401 | 代码支持，**默认关闭** |
| JWT / Token → 租户 | 注释有，**代码没有** |
| 部署时把租户写入记录 | 有，可空 |
| 响应里带回租户 | 没有 |
| list 强制按 `space_id` | 没有；不带头则全量 |
| get / delete 比对归属 | 没有 |
| 用配置打开强制租户 | 没有，写死在 `add_middleware` |

这和计划里的避坑一致：「以为多租户已完备——仅有标签与列表过滤，鉴权需自补。」Day 17 要补的就是：强制头或 Token、get/delete 归属校验、列表无头不得看全量。

---

## 5. 读 `main.py` 时顺手钉住的结构

租户之外，这个文件今天需要能复述的骨架（部署策略细节留给 Day 7）：

| 块 | 做什么 |
|---|---|
| 模块导入时 | 按 `RUNTIME_DB_TYPE` 建 sqlite / mysql / gaussdb handler，再 `DeploymentManager(db_handler)`。类型不支持直接抛 `ValueError`，进程起不来 |
| `lifespan` | 启动 `manager.initialize()`，退出 `manager.shutdown()` |
| `prepare_subprocess_deployment` | 仅 `subprocess`：分配或校验端口；`MODE=product` 不找本地 whl；否则固定找 `lowcode_agent_runner-0.1.0-py3-none-any.whl` |
| `get_deploy_type` | 全局 `DEPLOY_TYPE` 为 docker / k8s 时忽略请求里的 `mode`；否则用请求的 `mode`（默认 `subprocess`） |
| 五个路由 | `/health`、`POST /api/v1/agents/deploy`、`GET /api/v1/agents`、`GET/DELETE /api/v1/agents/{deployment_id}` |

`deploy` 在调 Manager 之前就生成 `deployment_id`，把上传的 JSON 写到 `{deploy_path}/{deployment_id}/ir.json`，再把 `ir_path`、`whl_path`、`port`、`deployment_id`、可选 `userdata` 放进 `extras`。失败统一包成 500，detail 以 `Deployment failed` 开头。

---

## 和前后几天的关系

- Day 4 的结论「列表按租户过滤」要收窄成：**只有请求自己带了租户头才过滤。** 当时手测若没带头，看到的就是全表。
- Day 7 读 `manager.py` 时，部署主链按 `deploy_agent` → `_deploy` → strategy 走；租户只是 `DeploymentCreate` 上的两列，不参与拉起进程。
- Day 17 的改造点已经能点名：`main.py` 第 79 行的开关、`list_agents` 在头为空时的查询、`get_agent` / `delete_agent` 里被丢掉的 `user_id` / `space_id`。Manager 要加归属参数还是在路由里先 `get` 再比对，到那天再定；今天先确认缺口在 server 这一层已经存在。
