# Day 7：DeploymentManager——一次部署怎么记账、怎么选策略

Day 6 停在路由把 `DeployAgentParams` 交给 Manager。  
Day 7 只回答一件事：**`deploy_agent` 之后，记录写到哪、策略怎么选、deployer 什么时候被叫到。**

按函数把 `manager.py` 的分支和失败后库里剩什么读完，看 `知乎-Day7-manager.py精读.md`。

精读：

- `management/openjiuwen_runtime/management/manager.py`
- `management/openjiuwen_runtime/management/models/deployment_params.py`
- `management/openjiuwen_runtime/management/models/enums.py`
- `management/openjiuwen_runtime/management/models/schemas.py`

策略基类只跟到「它调用 deployer」这一跳。venv、启动命令、日志目录留给 Day 8。

过关标志：能不看源码画出 `deploy_agent` → `_deploy` → strategy → deployer，并说出主表 `deployment` 和模式子表各记什么。

---

## 今天在链路里的位置

```text
POST /api/v1/agents/deploy          （Day 6：已生成 deployment_id、写好 ir.json）
        │
        ▼
 deploy_agent(DeployAgentParams)    补上 package_name，收成统一参数
 deploy_plugin / deploy_image       另外两条入口，HTTP 管理面现在没挂
        │
        ▼
 _deploy
   1. 主表 deployment 插入一行，状态 pending
   2. 按 mode 取出 strategy，写模式子表
   3. strategy.deploy
        │
        ▼
 BaseDeploymentStrategy.deploy
   再读两张表 → 组 DeployContext → deployer.deploy(ctx)
   成功：主表改 running，并回写 url
        │
        ▼
 _wait_until_deployment_ready       running 且 /health 返回 2xx 才算完成
        │
        ▼
 重新读主表，返回 DeploymentInfo
```

口诀：**Manager 记账、选策略、等就绪；拉进程的是 deployer。**

三种模式在 Manager 里只是一张表：

| `DeployMode` | Strategy | 默认 Deployer | 子表 |
|---|---|---|---|
| `subprocess` | `SubprocessStrategy` | `LocalSubprocessDeployer` | `process` |
| `docker` | `DockerStrategy` | `DockerDeployer` | `docker` |
| `k8s` | `K8sStrategy`（依赖导入成功才注册） | `K8sDeployer` | `k8s` |

K8s 的导入包在一层 `try/except` 里。导入失败时字典里没有 `k8s`，日志打一条 warning；之后谁来 `get_strategy(DeployMode.K8S)`，直接 `RuntimeError`。Manager 不读 `DEPLOY_TYPE`，模式完全由调用方传入。HTTP 那边的 `get_deploy_type` 已经在进 Manager 之前定好了。

---

## 1. 参数、枚举、主表

这四个文件把「调用方怎么说」和「库里怎么存」分开。

### 调用参数：四个 dataclass

`deployment_params.py` 全是 `@dataclass`，给 Manager 的公开方法用：

| 类型 | 必填 | 默认 | 多出来的字段 |
|---|---|---|---|
| `DeployAgentParams` | `name`、`version` | `mode=subprocess` | `extras` |
| `DeployPluginParams` | 同上 | `mode=subprocess` | `url`、`extras` |
| `DeployImageParams` | `image`、`name`、`version`、`mode` | `mode` 无默认 | `extras` |
| `ListDeploymentsParams` | 无 | `limit=100`，`offset=0` | 类型、状态、`user_id`、`space_id` 都可空 |

策略自己要的字段（`ir_path`、`whl_path`、`port`、`deployment_id`）一律放进 `extras`，不进这几个 dataclass 的具名参数。

进 `_deploy` 之前，三条部署入口再收成内部的 `_DeployExecutionParams`：类型、名字、版本、模式、租户、`extras`。

### 三个枚举

`enums.py` 都是 `str, Enum`，落库就是这些字符串：

| 枚举 | 值 |
|---|---|
| `DeploymentType` | `agent` / `plugin` / `image` |
| `DeployMode` | `subprocess` / `docker` / `k8s` |
| `DeploymentStatus` | `pending` / `running` / `stopped` / `failed` / `running_not_ready` |

`running_not_ready` 在 Manager 的写入路径里不会出现。它只由 K8s deployer 的 `get_status` 返回。下面的就绪等待只认 `running`。

### 主表：`deployment`

`schemas.py` 给出表名、字段名和两个 Pydantic 模型。`manager.py` 用同一套字段名拼出 `DEPLOYMENT_TABLE_DEF`：

| 字段 | 约束 | 谁来填 |
|---|---|---|
| `id` | 自增主键 | 数据库 |
| `deployment_id` | string(64)，唯一、非空 | 调用方放进 `extras`，没有则 Manager 自己生成 UUID |
| `version` / `deployment_type` / `name` | 非空 | 入口参数 |
| `deployment_status` | 非空 | `_deploy` 先写 `pending`；strategy 再改成 `running` 或 `failed` |
| `url` | 可空，最长 512 | 插入时取 `extras["url"]`；Agent 这条路径当时没有，成功后由 strategy 回写 |
| `user_id` / `space_id` | 可空，string(64)，各有普通索引 | 原样写入，不参与拉起 |
| `created_at` / `updated_at` | 非空 | `_deploy` 用 `datetime.utcnow()` |
| `data` | JSON，可空 | 只取 `extras["data"]` |

`DeploymentCreate` 是插入前的形状，没有 `id`、状态、时间。`DeploymentInfo` 是读出来的形状，带 `id` 和状态；`Config.from_attributes = True`，ORM 对象和 dict 都能 `model_validate`。

`user_id`、`space_id` 在 `DeploymentInfo` 里有，HTTP 响应仍不返回它们。这和 Day 6 对得上：标签在库里。

---

## 2. 三条入口收成一条 `_deploy`

```149:171:management/openjiuwen_runtime/management/manager.py
    async def deploy_agent(self, params: DeployAgentParams) -> DeploymentInfo:
        """部署Agent"""
        ...
        extras = dict(params.extras)
        extras["package_name"] = params.name
        return await self._deploy(
            _DeployExecutionParams(
                deployment_type=DeploymentType.AGENT,
                ...
            )
        )
```

三条入口的差别只有类型和往 `extras` 里塞的那一个键：

| 方法 | `deployment_type` | 额外写入 `extras` | 提前拒绝 |
|---|---|---|---|
| `deploy_agent` | `agent` | `package_name = params.name` | 无 |
| `deploy_plugin` | `plugin` | `url = params.url` | 无 |
| `deploy_image` | `image` | `image = params.image` | `mode == subprocess` 时 `NotImplementedError`，进不了 `_deploy` |

当前 `main.py` 只调用 `deploy_agent`。`version` 写死 `"1.0.0"`，`deployment_id` 在路由里已经生成，放进 `extras`。Plugin、Image 是 Manager 上的方法，管理面这 5 个路由没有对应入口。

`deploy_agent` 会复制一份 `extras` 再写 `package_name`，调用方原来的 dict 不被改。`_deploy` 里还会 `pop` 掉 `deployment_id`，所以这个键不会再流进子表的 `**kwargs`。

Server 实际送进来的 `extras` 是：

| 键 | 去向 |
|---|---|
| `deployment_id` | 被 `_deploy` 取走，作为主键业务号 |
| `ir_path` / `whl_path` / `port` | 留给 `strategy.create_record`，subprocess 写进 `process` 表 |
| `data` | 主表 `deployment.data`，同时也在 `**kwargs` 里交给子表 |
| `package_name` | `deploy_agent` 补上，等于查询参数里的 `name`，进 `process.package_name` |

有 `ir_path` 时，真正 `python -m` 的模块名在 deployer 里会被换成低码 runner。那一行在 `LocalSubprocessDeployer.deploy`，Day 8 再读。今天只要记住：主表的 `name` 和子表的 `package_name` 都是这个查询参数，启动模块名不一定等于它。

---

## 3. `_deploy` 逐步做什么

```423:482:management/openjiuwen_runtime/management/manager.py
    async def _deploy(self, params: _DeployExecutionParams) -> DeploymentInfo:
        extras = dict(params.extras)
        deployment_id = extras.pop("deployment_id", None) or self._generate_deployment_id()
        ...
        await self.db_handler.create(DEPLOYMENT_TABLE_NAME, deployment_data)
        strategy = self.get_strategy(params.mode)
        try:
            await strategy.create_record(...)
            deploy_result = await strategy.deploy(deployment_id, self.db_handler)
            ...
            await self._wait_until_deployment_ready(deployment_id)
        except Exception as e:
            ...
            await self.db_handler.update(..., FAILED)
            raise
        deployment_record = await self.db_handler.get(...)
        return DeploymentInfo.model_validate(deployment_record)
```

按发生顺序：

1. **定 `deployment_id`。** `extras` 里有就用，没有才 `uuid4`。HTTP 低码部署走的是前一种，所以响应里的 id 和路由一开始生成的是同一个。
2. **插主表，状态 `pending`。** `url` 来自 `extras.get("url")`。Agent 部署这时还没有 URL，列是空的。`data` 只取 `extras["data"]`：Server 在带了 `userdata` 时放的是 `{"userdata": "..."}`，否则是 `None`。`ir_path` 不会进主表。
3. **按 `mode` 取 strategy，写子表。** `create_record(db, deployment_id, version, **extras)`。subprocess 的 `_build_record_data` 会把 `host`（默认 `localhost`）、`port`、`whl_path`、`ir_path`、`package_name`、`data` 写进 `process`。此时还没有 `pid`、`venv_path`。
4. **`strategy.deploy`。** 返回的 `DeployResult.success` 为假，就 `raise RuntimeError(message)`。subprocess 失败时 message 已经以 `Deployment failed` 开头，Server 的 500 不会再套一层前缀。
5. **等就绪。** 见下一节。超时、探活失败、中途变成 `failed`，都算异常。
6. **异常只改主表状态。** `except` 把 `deployment_status` 更新成 `failed`，然后原样抛出。这里不调用 `stop`。deployer 已经把进程拉起来、strategy 也已经写成 `running` 之后，如果卡在探活，主表会变成 `failed`，进程还在。
7. **成功则重读主表。** 返回的 `DeploymentInfo.status` / `url` 是 strategy 写回去的值，一般是 `running` 加上 `http://{IP}:{port}/`。

`initialize` 在进程启动时做三件事：连接数据库、按 `DEPLOYMENT_TABLE_DEF` 建主表、对每个已注册 strategy 建子表。`shutdown` 只 `disconnect`，不停 Agent、不删行。

---

## 4. strategy 到 deployer

`BaseDeploymentStrategy.deploy` 是三种模式共用的那一跳（subprocess 在外面又包了一层）：

```153:207:management/openjiuwen_runtime/management/deployments/base/strategy.py
    async def deploy(self, deployment_id: str, db_handler: DBHandler) -> DeployResult:
        record = await self.get_record(...)          # 模式子表
        deployment = await db_handler.get(...)       # 主表
        # 再次写成 pending
        ctx = self._build_deploy_context(record, deployment)
        result = await self._deployer.deploy(ctx)
        # 成功：主表 running，有 url 就写 url
        # 失败：主表 failed
        return result
```

subprocess 的覆盖只多做一件事：`super().deploy` 成功后，把 `DeployResult.pid` 和 `venv_path` 更新回 `process` 表。Docker、K8s 用基类实现，没有这一步。

`Deployer` 是抽象类，三个方法：

| 方法 | 入参 | 谁来组参数 |
|---|---|---|
| `deploy` | `DeployContext` | strategy 的 `_build_deploy_context` |
| `stop` | `deployment_id` + `**kwargs` | strategy 的 `_get_stop_kwargs`（subprocess 取出 `pid`、`venv_path`） |
| `get_status` | 同上 | strategy 的 `_get_status_kwargs`（subprocess 只取 `pid`） |

`DeployContext` 拆成两截：`common`（`deployment_id`、`host`、`port`、`url`）和模式自己的 `params`。subprocess 的 `params` 是 `SubprocessParams`：`whl_path`、`ir_path`、`package_name`、`venv_path`、`userdata`。`userdata` 从子表 `data` 字典里拿，也就是 Server 放进 `extras["data"]` 的那个对象。

`DeployResult` 固定带回：`success`、`deployment_id`、`message`、`url`、`pid`、`venv_path`。后两个只有本地进程用；strategy 成功分支只用 `success` 和 `url` 改主表。

这一跳到此为止。`LocalSubprocessDeployer.deploy` 里面的建 venv、装 whl、`Popen`，是 Day 8 的正文。

---

## 5. 就绪：`running` 之后还要探活

strategy 返回成功时，主表已经是 `running`，URL 也写上了。`_deploy` 仍要再等 `_wait_until_deployment_ready`：

- 超时 600 秒，轮询间隔 20 秒。第一次检查立刻发生，健康的实例不用干等 20 秒。
- 记录消失：`RuntimeError`，文案是 `not found while waiting for readiness`。
- 状态变成 `failed`：立刻失败。
- 状态是 `running` 且 `url` 为空：直接通过。
- 状态是 `running` 且有 `url`：对 `{url}/health` 发 GET，2 秒超时，状态码 2xx 才通过。
- 其它状态（包括 `running_not_ready`、`pending`、`stopped`）继续等，直到超时。

探活的主机替换规则在 `_health_url_with_loopback_host`：URL 的主机已经是 `127.0.0.1`、`localhost`、`::1` 时不做替换；否则再用 `127.0.0.1` 加原来的端口试一次 `/health`。注释写的是配置 IP 被本机访问策略拦住时的兜底。subprocess 写回的 URL 用的是 `settings.IP`，所以本机若配的不是环回地址，会走这一次兜底。

超时异常文案是 `not ready within 600s (last_status=...)`。它和探活期间的任何异常一样，回到 `_deploy` 的 `except`，主表被改成 `failed`，异常继续抛给 Server，变成 500。进程不会在这一步被停掉。

---

## 6. 停、删、查模式

删除不接收租户，只接收 `deployment_id`。模式可以不传，不传就 `_detect_deploy_mode`：按 strategy 字典的顺序，对每张子表 `get_record`，谁先有行就用谁的模式。三张子表都没有，模式是 `None`。

`delete_deployment` 的顺序：

1. `stop_deployment`。模式未知则直接返回 `False`，删除仍继续。
2. 模式已知时，`strategy.stop` → `deployer.stop`。成功才把主表改成 `stopped`；失败只打日志，**删除不会因此停下来**。
3. `strategy.delete_record`，删模式子表那一行。
4. 删主表。返回值是主表这一下删没删掉。子表删失败、进程停失败，只要主表行没了，HTTP 仍视为成功。

`stop` 本身不删行、不删 venv 与否，要看具体 deployer。subprocess 的 `stop` 签名注释写了「停止并清理虚拟环境」，实现留到 Day 8 对一下注释和代码。

列表和详情 Manager 侧没有新规则：`list_deployments` 把非空的类型、状态、`user_id`、`space_id` 做成 AND 过滤；`get_deployment` 只按 `deployment_id`。Day 6 的结论不用改。

有一个和响应字段有关的事实，读主表时能钉住。`GET /api/v1/agents` 和详情里的 `port` 取的是 **主表** `data.port`。当前 `POST /deploy` 放进主表 `data` 的只有 `userdata`（或整列为空），端口在 `process.port`。所以这条 HTTP 响应里的 `port`，在现有低码部署路径上是空的。能用的地址是主表 `url`，那是 deployer 成功之后回写的。

---

## 和前后几天的关系

- Day 6 的部署在 `manager.deploy_agent` 处交给今天。租户两列在 `DeploymentCreate` 里原样落库，不进入 `DeployContext`，也不参与选策略。
- Day 4 记录的返回字段 `deployment_id`、`url`、`status`，分别来自：路由预先生成的 id、strategy 把 `DeployResult.url` 写回主表、就绪通过后重读到的 `running`。中途失败则整次 500，主表留下一行 `failed`。
- Day 8 从 `SubprocessStrategy` 和 `LocalSubprocessDeployer.deploy` 往下读：子表字段怎么变成 `DeployContext`，venv 目录、whl、`python -m` 和 `stop` 是否回收目录。
- Day 17 若要做归属校验，get/delete 的签名今天仍然只有 `deployment_id`。比对要加在路由里先读再比，或给 Manager 补上 `user_id` / `space_id` 参数。部署主链不用为这件事改 strategy。
