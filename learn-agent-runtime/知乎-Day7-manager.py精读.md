# Day 7 附录：`manager.py` 精读

配套总览是 `知乎-Day7-DeploymentManager.md`。那篇回答「链路怎么走」。  
这篇只对着 `management/openjiuwen_runtime/management/manager.py`（483 行）把每个函数的分支、返回值和失败后库里剩什么读完。

过关标志：给一个函数名，能说出它改哪张表、什么情况下返回 `False` / `None`、什么情况下把异常抛出去。

文件里的函数按这个顺序排：

| 行号 | 函数 | 谁会调用 |
|---|---|---|
| 83 | `__init__` | `server/main.py` 导入模块时 |
| 93 | `_create_default_strategies` | `__init__` 没传入 `strategies` 时 |
| 110 | `_generate_deployment_id` | `_deploy` 发现 `extras` 里没有可用 id |
| 115 | `_health_url_with_loopback_host` | 探活第一次失败之后 |
| 134 | `initialize` | FastAPI `lifespan` 启动 |
| 143 | `shutdown` | FastAPI `lifespan` 退出 |
| 149 / 173 / 197 | `deploy_agent` / `deploy_plugin` / `deploy_image` | HTTP 只用第一条 |
| 223 / 254 / 268 | `list_deployments` / `get_deployment` / `get_deployment_status` | 列表、详情；状态查询本文件内部也用 |
| 281 / 304 | `stop_deployment` / `delete_deployment` | HTTP 删除走第二条，它内部再调停 |
| 328 / 334 / 340 | `get_process_info` / `get_docker_info` / `get_k8s_info` | 本文件公开，当前 `main.py` 没调 |
| 346 / 354 | `get_strategy` / `_detect_deploy_mode` | 部署、停止、删除 |
| 365 / 387 | `_check_health_endpoint` / `_wait_until_deployment_ready` | 只有 `_deploy` |
| 423 | `_deploy` | 三条部署入口 |

strategy 和 deployer 的函数体不在这个文件里。这里出现 `strategy.deploy` 时，只说明本文件怎么调用、怎么处理返回值。

---

## 1. 文件头和主表定义（1–77 行）

`from __future__ import annotations` 让注解延迟求值，运行时没有别的行为。

内部参数 `_DeployExecutionParams` 的注释写「由 `deploy_agent` / `deploy_plugin` 组装」。`deploy_image` 也组装它。`extras` 用 `field(default_factory=dict)`，避免多个实例共享同一个字典。

`DEPLOYMENT_TABLE_DEF` 使用 `schemas.py` 里的表名 `deployment` 和 `DeploymentFields`，列和索引写在本文件：

```72:76:management/openjiuwen_runtime/management/manager.py
    indexes=[
        IndexDefinition([DeploymentFields.DEPLOYMENT_ID], unique=True),
        IndexDefinition([DeploymentFields.USER_ID], unique=False),
        IndexDefinition([DeploymentFields.SPACE_ID], unique=False),
    ],
```

`deployment_id` 上有两层唯一：列的 `unique=True`，再加上同名唯一索引。`user_id`、`space_id` 只有普通索引。类型、状态、名字都没有索引。

建表发生在 `initialize`，不发生在 import。import 这个模块只是把 `TableDefinition` 对象放在内存里。

---

## 2. 构造和生命周期

### `__init__`（83–90）

保存调用方给的 `DBHandler`。`strategies` 为 `None` 时调用 `_create_default_strategies()`。这里不连接数据库，也不建表。日志写的是 `DeploymentManager initialized`，和后面 `initialize()` 的 `initialized successfully` 是两句。

测试可以传入自己的 strategy 字典，替换默认三模式。

### `_create_default_strategies`（93–107）

字典按插入顺序固定为：

1. `DeployMode.SUBPROCESS` → `SubprocessStrategy()`
2. `DeployMode.DOCKER` → `DockerStrategy()`
3. 仅当 `K8sStrategy is not None` 时，再放入 `DeployMode.K8S`

`K8sStrategy` 在 `deployments/__init__.py` 里导入失败会被置成 `None`，异常对象留在 `K8S_IMPORT_ERROR`。失败时这里打 warning，进程继续起。后面 `_detect_deploy_mode` 按这个字典的顺序查子表，所以 subprocess 先于 docker，docker 先于 k8s。

### `initialize` / `shutdown`（134–147）

```134:147:management/openjiuwen_runtime/management/manager.py
    async def initialize(self) -> None:
        await self.db_handler.connect()
        await self.db_handler.init_table(DEPLOYMENT_TABLE_DEF)
        for strategy in self._strategies.values():
            await self.db_handler.init_table(strategy.get_table_definition())

    async def shutdown(self) -> None:
        await self.db_handler.disconnect()
```

`initialize` 先建主表，再按字典顺序建子表（默认是 `process`、`docker`，K8s 可用时还有 `k8s`）。`DBHandler.init_table` 的约定是表已存在则跳过创建。本函数不扫描已有 `running` 行，也不把进程重新挂回来。

`shutdown` 只断开数据库。不调用 `stop_deployment`，不删行，不碰 venv。进程退出后，子进程是否还活着，取决于操作系统对子进程的处理和 deployer 当时怎么 `Popen`，这个文件不负责。

---

## 3. 三条部署入口

三条都做同一件事：打日志、复制 `extras`、往副本里写一个键、装进 `_DeployExecutionParams`、`return await self._deploy(...)`。复制用 `dict(params.extras)`，调用方手里的字典不会被 `_deploy` 的 `pop` 改掉。

| 方法 | 写入 `extras` 的键 | 提前返回 |
|---|---|---|
| `deploy_agent` | `package_name = params.name`，覆盖调用方原来的同名键 | 无 |
| `deploy_plugin` | `url = params.url`，覆盖 `extras` 里已有的 `url` | 无。`url` 可以是 `None` |
| `deploy_image` | `image = params.image` | `mode == subprocess` 时先 `raise NotImplementedError`，日志还没打，`_deploy` 不会执行 |

`deploy_agent` 不检查 `mode` 是否真有对应 strategy，也不生成 `deployment_id`。这两件事都在 `_deploy`。

HTTP 的 `POST /api/v1/agents/deploy` 只调用 `deploy_agent`。Plugin 和 Image 是这个类的公开方法，`main.py` 没有路由。

---

## 4. `_deploy`：按行看

插入主表和取出 strategy 在 `try` 外面：

```451:453:management/openjiuwen_runtime/management/manager.py
        await self.db_handler.create(DEPLOYMENT_TABLE_NAME, deployment_data)

        strategy = self.get_strategy(params.mode)
```

`try` 从写子表开始，失败才把主表改成 `failed`：

```455:476:management/openjiuwen_runtime/management/manager.py
        try:
            await strategy.create_record(
                self.db_handler, deployment_id, params.version, **extras
            )
            deploy_result = await strategy.deploy(deployment_id, self.db_handler)
            if not deploy_result.success:
                raise RuntimeError(deploy_result.message or f"Deployment {deployment_id} failed")

            await self._wait_until_deployment_ready(deployment_id)
            logger.info(
                "Deployment completed: deployment_id=%s, name=%s",
                deployment_id,
                params.name,
            )
        except Exception as e:
            logger.error("Deployment failed: deployment_id=%s, error=%s", deployment_id, str(e))
            await self.db_handler.update(
                DEPLOYMENT_TABLE_NAME,
                {DeploymentFields.DEPLOYMENT_ID: deployment_id},
                {DeploymentFields.DEPLOYMENT_STATUS: DeploymentStatus.FAILED.value},
            )
            raise
```

### 定 id

再复制一次 `extras`（入口已经复制过）。然后：

```python
deployment_id = extras.pop("deployment_id", None) or self._generate_deployment_id()
```

`pop` 的默认值是 `None`。键不存在、值是 `None`、值是 `""`，都算假，于是自己 `uuid4()`。HTTP 放进来的是非空 UUID 字符串，会用路由生成的那个，并且这个键从 `extras` 里删掉，不会再传给 `create_record`。

`_generate_deployment_id` 就是 `str(uuid.uuid4())`，36 个字符，带连字符。列长度 64，放得下。

### 组插入字典

`DeploymentCreate` 只接这些字段：`deployment_id`、`version`、`deployment_type`、`name`、`url=extras.get("url")`、`user_id`、`space_id`、`data=extras.get("data")`。

`model_dump()` 之后，本函数再补三列，这三列不在 `DeploymentCreate` 里：

- `deployment_status = "pending"`
- `created_at = updated_at = datetime.utcnow()`

`utcnow()` 是不带时区的 UTC。两个时间戳是同一个对象，插入时相等。后面本文件把状态改成 `failed` 时只更新状态列，不改 `updated_at`。

`deployment_type` 在 `model_dump()` 的默认 python 模式里仍是枚举成员。`DeploymentType` 继承 `str`，成员的值就是 `"agent"` / `"plugin"` / `"image"`，写进 string 列。

此时 `extras` 里剩下的键（Agent 路径上是 `ir_path`、`whl_path`、`port`、`data`、`package_name`）不进主表，留给下面的 `**extras`。主表 `data` 列只来自 `extras["data"]` 这一个键。

### `try` 的边界

`db_handler.create` 和 `get_strategy` 都在 `try` **外面**。

| 失败点 | 主表 |
|---|---|
| `create` 抛错（表未初始化、唯一约束冲突） | 这一行没插进去；异常原样出去，不会写 `failed` |
| `get_strategy` 抛错（K8s 依赖没装上，或字典里没有这个 mode） | 行已经是 `pending`，停留在 `pending`，不会被改成 `failed` |
| `try` 里面任何 `Exception` | 把该行更新成 `failed`，再 `raise` 原异常 |

`try` 里面三步：

1. `strategy.create_record(db, deployment_id, version, **extras)`。子表写入失败会进 `except`。
2. `strategy.deploy(...)`。`success` 为假时，本函数自己 `raise RuntimeError`。message 用 `deploy_result.message`；message 为空才用 `Deployment {id} failed`。这个 `RuntimeError` 同样被下面的 `except Exception` 接住，所以主表仍会被改成 `failed`，然后把这个 `RuntimeError` 抛回去。
3. `_wait_until_deployment_ready`。超时或探活过程中的 `RuntimeError` 同样进 `except`。

`except` 接的是 `Exception`。`CancelledError`、`KeyboardInterrupt` 继承 `BaseException`，不会把行改成 `failed`。

`except` 里的 `update` 如果自己再抛错，调用方看到的是这次 `update` 的异常，原来的部署异常被换掉。`except` 里没有 `stop`。strategy 已经把进程拉起来之后若卡在探活，主表变成 `failed`，进程留在外面。

### 成功返回

`try` 正常结束才执行最后的 `get` + `model_validate`。这两行在 `try` 外面。`get` 得到 `None` 时，`model_validate(None)` 会抛校验错误，主表保持 strategy 写下的状态（通常已是 `running`），本函数不会再把它改成 `failed`。

这里直接把记录对象交给 `model_validate`，没有先判断 `to_dict`。`DeploymentInfo` 开了 `from_attributes`，SQLAlchemy 那条记录可以按属性读。`list` / `get` 的写法见第 5 节，三处并不相同。

---

## 5. 查询：三种读记录的写法

默认 SQL handler 造出来的行对象带 `to_dict()`。Redis handler 直接返回 `dict`。本文件为了同时接这两种返回值，写了三套做法。

### `list_deployments`（223–252）

过滤是「有值才放进 dict」：

```234:242:management/openjiuwen_runtime/management/manager.py
        filters = {}
        if params.deployment_type:
            filters[DeploymentFields.DEPLOYMENT_TYPE] = params.deployment_type.value
        if params.deployment_status:
            filters[DeploymentFields.DEPLOYMENT_STATUS] = params.deployment_status.value
        if params.user_id:
            filters[DeploymentFields.USER_ID] = params.user_id
        if params.space_id:
            filters[DeploymentFields.SPACE_ID] = params.space_id
```

空字符串进不了过滤。四个条件都空时，传给 `list_records` 的 `filters` 是 `None`，等于不带 WHERE。类型和状态放进去的是 `.value` 字符串，不是枚举对象。

`limit` / `offset` 原样下传。dataclass 的默认是 `100` 和 `0`，这个方法不再改。也没有 `order_by`，顺序由数据库默认决定。

每行都是 `DeploymentInfo.model_validate(r if hasattr(r, "to_dict") else r)`。这个三元表达式的两个分支都是 `r`，`hasattr` 的结果不影响传入对象。列表**不会**调用 `to_dict()`。返回 `list[DeploymentInfo]`，找不到时是空列表，不返回 `None`。

SQLAlchemy 行对象开了 `from_attributes`，直接校验能过。Redis handler 返回的本来就是 `dict`，同样能过。

### `get_deployment`（254–266）

条件只有 `deployment_id`。没有行就 `return None`。有行时和列表不同，这里真的调用了 `to_dict()`：

```264:266:management/openjiuwen_runtime/management/manager.py
        if hasattr(record, "to_dict"):
            return DeploymentInfo.model_validate(record.to_dict())
        return DeploymentInfo.model_validate(record)
```

### `get_deployment_status`（268–279）

同样按 `deployment_id` 取一行。没有行返回 `None`。有行时不用 `to_dict`，也不做 `model_validate`：

```277:279:management/openjiuwen_runtime/management/manager.py
        status = record.get(DeploymentFields.DEPLOYMENT_STATUS) \
            if isinstance(record, dict) else record.deployment_status
        return DeploymentStatus(status)
```

`dict` 走 `.get`，ORM 走属性。状态字符串对不上枚举时，`DeploymentStatus(status)` 抛 `ValueError`，本函数不接。

`_wait_until_deployment_ready` 不调用这个函数，它调用 `get_deployment` 拿整行，因为还要看 `url`。

---

## 6. 停和删

### `get_strategy`（346–352）

同步函数。`mode == k8s` 且 `K8S_IMPORT_ERROR is not None` 时：

```python
raise RuntimeError("K8s deployment is unavailable ...") from K8S_IMPORT_ERROR
```

其它情况是 `return self._strategies[mode]`。键不在字典里就是 `KeyError`。默认字典里 subprocess 和 docker 总是在；K8s 导入失败时，上面的 `RuntimeError` 会先于 `KeyError` 发生，因为判断写在下标前面。

### `_detect_deploy_mode`（354–363）

按 `_strategies` 的插入顺序，对每个 strategy 调用 `get_record`。第一行非空记录的 mode 立刻返回。主表不参与判断。三张子表都没有，返回 `None`。

两张子表意外都有同一 `deployment_id` 时，字典里更靠前的那个胜出，后面的行留着。默认顺序是 subprocess，然后 docker，然后 k8s。

### `stop_deployment`（281–302）

```286:302:management/openjiuwen_runtime/management/manager.py
        if mode is None:
            mode = await self._detect_deploy_mode(deployment_id)
            if mode is None:
                logger.warning("Cannot stop deployment, mode not found: ...")
                return False

        strategy = self.get_strategy(mode)
        result = await strategy.stop(deployment_id, self.db_handler)
        ...
        return result.success
```

- 调用方已经传入 `mode`：不再探测，即使这个 mode 和子表实际不符，也按传入的来。
- `mode` 是 `None` 且探测仍是 `None`：打 warning，返回 `False`。不抛异常。
- 探测到了，或调用方传入了：`strategy.stop`。返回值只有 `result.success`。日志里的失败不影响返回值。
- 本函数不删主表、不删子表。把主表改成 `stopped` 的代码在 `BaseDeploymentStrategy.stop` 里，且只在 `result.success` 时发生。

`get_strategy` 或 `strategy.stop` 若抛异常，本函数不接，调用方看到异常，返回值不会变成 `False`。subprocess 的 deployer 把停失败收成 `DeployResult(success=False)`，那种情况这里返回 `False`。

### `delete_deployment`（304–326）

```309:326:management/openjiuwen_runtime/management/manager.py
        if mode is None:
            mode = await self._detect_deploy_mode(deployment_id)

        await self.stop_deployment(deployment_id, mode)

        if mode:
            strategy = self.get_strategy(mode)
            await strategy.delete_record(self.db_handler, deployment_id)

        result = await self.db_handler.delete(
            DEPLOYMENT_TABLE_NAME,
            {DeploymentFields.DEPLOYMENT_ID: deployment_id}
        )
        return result
```

逐步：

1. 只有调用方没传 `mode` 才探测。探测结果可以仍是 `None`。
2. **无条件**调用 `stop_deployment`。探测结果是 `None` 时，这里把 `None` 再传进去，`stop_deployment` 会再探测一次。停返回 `False` 不会让删除停下来。停如果抛异常，后面的删子表、删主表都不会执行。
3. `mode` 为真才 `delete_record`。这个调用的返回值被丢掉。`mode is None` 时子表不动（本来也没查到）。
4. 删主表。SQL handler 的 `delete` 在 `rowcount > 0` 时返回 `True`。本函数把这个布尔值返回给 HTTP。主表没有这一行就是 `False`，路由把它当成 404。

因此：子表删失败、进程停失败（返回 `False`），只要主表行删掉了，调用方仍得到 `True`。反过来，主表根本没有这一行，但子表有、停也成功了，函数仍返回 `False`，子表行已经被第 3 步删掉。

---

## 7. 三个 `get_*_info`（328–344）

三个函数同一形状，只是 mode 和返回类型写死：

```328:332:management/openjiuwen_runtime/management/manager.py
    async def get_process_info(self, deployment_id: str) -> Optional[ProcessInfo]:
        strategy = self.get_strategy(DeployMode.SUBPROCESS)
        return await strategy.get_info(self.db_handler, deployment_id)
```

不探测模式。拿 docker 的 id 去调 `get_process_info`，子表没有行，`get_info` 返回 `None`，不会改去查 `docker` 表。`get_k8s_info` 在 K8s 没导入成功时，会在 `get_strategy` 处抛 `RuntimeError`。

当前 `main.py` 的详情接口用的是 `get_deployment`（主表），不走这三个函数。端口在 `process` 表上，所以 HTTP 详情读主表 `data.port` 读不到部署时传入的 `port`。

---

## 8. 探活和等待

### `_health_url_with_loopback_host`（115–132）

入参是部署记录上的 **base url**，还没拼 `/health`。步骤：

1. `urlparse(base_url.rstrip("/") + "/")`。
2. `hostname` 为空：返回 `None`。
3. 主机是 `127.0.0.1`、`localhost`、`::1`：返回 `None`。`urlparse` 会把主机名转成小写，`LOCALHOST` 也会命中。
4. 否则把主机换成 `127.0.0.1`，端口原样保留；没有端口就只用 `127.0.0.1`。query 和 fragment 被丢掉。路径保留到目录这一层（`path.rstrip("/")`）。
5. 返回 `urljoin(替换后的地址 + "/", "health")`。

例如 `http://10.0.0.5:9000/app` 得到 `http://127.0.0.1:9000/app/health`。Agent 写回的 url 是 `http://{IP}:{port}/`，路径是 `/`，结果就是 `http://127.0.0.1:{port}/health`。

### `_check_health_endpoint`（365–385）

先对原地址拼 health：`urljoin(base_url.rstrip("/") + "/", "health")`。`http://10.0.0.5:9000/` 得到 `http://10.0.0.5:9000/health`。

真正发请求的是同步的 `urllib.request.urlopen`，包在 `asyncio.to_thread` 里，避免堵住事件循环。超时默认 2 秒。状态码在 `[200, 300)` 才算成功。

`_try_once` 只捕获 `OSError`。`urllib.error.HTTPError` 继承 `URLError`，`URLError` 继承 `OSError`，所以 4xx / 5xx 变成 `False`，不会把部署打成异常。连不上、超时同样是 `False`。`OSError` 以外的异常会冒出去，最终被 `_deploy` 收成 `failed`。

第一次失败后才算兜底地址。兜底为 `None`，或和第一次的 URL 相同，就直接 `return False`。两次都失败才是 `False`。最坏大约两次 2 秒。

### `_wait_until_deployment_ready`（387–421）

默认超时 600 秒，间隔 20 秒。截止时间用事件循环的 `time()`，不是 `datetime`。

每一轮：

1. `get_deployment`。行没了：`RuntimeError("... not found while waiting for readiness")`。
2. 记下 `last_status = deployment.deployment_status.value`。
3. 状态是 `running`：
   - 有 `url`：探活成功就 `return`。探活失败不抛，落到第 5 步睡觉。
   - 没有 `url`：直接 `return`。空字符串也走「没有 url」这条，因为 `""` 为假。
4. 状态是 `failed`：`RuntimeError("... entered failed status")`。这一判断在 `running` 分支后面，同一次轮询不会两个都进。
5. 其它状态（`pending`、`stopped`、`running_not_ready`）以及「`running` 但探活失败」：`asyncio.sleep(20)` 后再看截止时间。

`while` 的条件在每轮开头检查。某一轮开头还没超时，里面却 `sleep` 了 20 秒，醒来才发现过了截止时间，于是抛：

```text
Deployment {id} not ready within 600s (last_status=...)
```

循环一次都没进过（例如超时传 0）时，`last_status` 仍是 `None`，文案里就是 `last_status=None`。

这个函数自己不改数据库。抛出去之后由 `_deploy` 的 `except` 把主表写成 `failed`。

---

## 9. 读这个文件时可以对上的结论

- 公开部署入口有三个，落库路径只有 `_deploy`。HTTP 只用 `deploy_agent`。
- 主表插入在 `try` 外，`get_strategy` 也在 `try` 外。K8s 策略不可用时，会留下一行永远停在 `pending` 的主表记录，异常直接到调用方。
- `try` 内失败会把主表改成 `failed` 并原样抛出，不停止已经拉起的进程。
- 删除把「停失败」当成可以继续：`stop` 返回 `False` 仍删行；`stop` 抛异常则整段删除中断。
- 模式探测只看子表，而且按 subprocess → docker → k8s 的顺序命中即停。
- 列表和详情的租户过滤不在这个文件里新增规则：`list_deployments` 对空的 `user_id` / `space_id` 不加条件，`get_deployment` / `delete_deployment` 的参数里没有租户。
