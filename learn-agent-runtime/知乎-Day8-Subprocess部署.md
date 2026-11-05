# Day 8：Subprocess 部署——一个 deployment_id 一套目录、一个进程

Day 7 停在 `strategy.deploy` 把 `DeployContext` 交给 deployer。  
Day 8 只回答默认路径上的下一跳：**虚拟环境建在哪、进程用什么命令拉起、停的时候磁盘上还剩什么。**

精读：

- `management/openjiuwen_runtime/management/deployments/subprocess/strategy.py`
- `management/openjiuwen_runtime/management/deployments/subprocess/deployer.py`
- `foundation/openjiuwen_runtime/foundation/venv_manager.py`

`models.py` 只作为子表字段表来对。Docker / K8s 今天不展开。

过关标志：能不看源码说出隔离键、目录形状、以及这条路径上没有业务级 workspace；并能指出 `stop` 删掉的是 `.venv`，`logs/` 和 `ir.json` 还在。

---

## 今天在链路里的位置

```text
Manager._deploy                         （Day 7：主表 pending，process 子表已有一行）
        │
        ▼
 SubprocessStrategy.deploy
   super().deploy
     读 process + deployment
     组 DeployContext[SubprocessParams]
     LocalSubprocessDeployer.deploy(ctx)
        │
        ├─ VirtualEnvironmentManager.create_venv(deployment_id)
        │     {DEPLOY_DIR}/{deployment_id}/.venv
        ├─ 按 MODE 用 uv pip 装包
        ├─ Popen:  {venv}/bin/python -m <模块> --host 0.0.0.0 --port <port>
        └─ stdout/stderr → {deployment_id}/logs/agent.log
        │
        ▼
 成功则回写 process.pid、process.venv_path
 基类把主表改成 running，并写入 url
        │
        ▼
 Manager 再探 {url}/health               （仍是 Day 7 的等待，不在 deployer 里）
```

口诀：**一个 `deployment_id`，一套目录，一个进程。** 业务名字只进主表 `name` 和子表 `package_name`，不参与目录名。

本仓库 `DEPLOY_DIR=deploys`（相对路径会拼到项目根）。磁盘上已经能对上这个形状：

```text
deploys/
├── 1288556c-0769-4379-81b6-87b4e702b95b/
│   └── ir.json                          HTTP 低码先落文件；进程没起来时目录可以只有它
└── 889236ca-3155-475b-9a6a-7a292e93cf91/
    ├── .venv/                           uv venv，解释器在 .venv/bin/python
    └── logs/agent.log                   子进程 stdout + stderr
```

---

## 1. `SubprocessStrategy`：子表字段，以及比基类多的一步

策略自己几乎不碰进程。它做三件事：声明 `process` 表、把记录收成 `DeployContext`、成功后把 pid 和 venv 路径写回子表。

`_build_record_data` 在拉起之前就插入一行。当时还没有 pid 和 venv：

| 列 | 这时的值 |
|---|---|
| `deployment_id` / `version` | 来自 Manager |
| `host` | `kwargs` 里没有就写 `"localhost"`。HTTP 和 CLI 都不传 host，所以是这个默认值 |
| `port` | HTTP 在进 Manager 之前已经分配，这里有数；CLI 不传 `--port` 时这一列是空的 |
| `url` / `pid` / `venv_path` | 空。前两个等 deployer 成功，url 写在主表，pid 和 venv 由本类补回子表 |
| `whl_path` / `ir_path` / `package_name` | 从 `extras` 来 |
| `data` | Server 带了 `userdata` 时是 `{"userdata": "..."}`，否则空 |

`package_name` 在 `deploy_agent` 里被设成 `params.name`。HTTP 的 `name` 是查询参数里的部署名；CLI 的 `name` 是 `openjiuwen_runtime.<包名>` 这种模块路径。它先被记进子表。真正 `python -m` 用不用它，要等 deployer 看有没有 `ir_path`。

`_build_deploy_context` 把这一行拆开：

- `common`：`deployment_id`、`host`、`port`、`url`
- `params`：`SubprocessParams`，含 `whl_path`、`ir_path`、`package_name`、`venv_path`、`userdata`
- `userdata` 从子表 `data["userdata"]` 再取一次

`deploy` 的覆盖只有成功之后那一下更新：

```72:88:management/openjiuwen_runtime/management/deployments/subprocess/strategy.py
    async def deploy(self, deployment_id: str, db_handler) -> Any:
        """部署并更新 pid 和 venv_path 到子表"""
        result = await super().deploy(deployment_id, db_handler)

        # 部署成功后，更新子表记录的 pid 和 venv_path
        if result.success and (result.pid is not None or result.venv_path):
            update_data = {}
            if result.pid is not None:
                update_data["pid"] = result.pid
            if result.venv_path:
                update_data["venv_path"] = result.venv_path

            await db_handler.update(
                self._table_def.table_name,
                {"deployment_id": deployment_id},
                update_data,
            )
```

基类在 `super().deploy` 里已经把主表改成 `running` 并写上 `url`。子表的 `port` 不会在这里被改。CLI 没指定端口时，deployer 自己挑的端口只出现在主表 `url` 里，`process.port` 仍是空的。

失败时 `success` 为假，这段更新不执行。`process.pid`、`process.venv_path` 保持空，即使磁盘上 `.venv` 已经建出来了。

`_get_stop_kwargs` 取出 `pid` 和 `venv_path`。`_get_status_kwargs` 只取 `pid`。

---

## 2. `LocalSubprocessDeployer.deploy`：建环境、装包、拉进程

构造函数记下 `default_host=127.0.0.1`、`default_port_start=8000`，再持有一个 `VirtualEnvironmentManager` 和字典 `self._processes`。后面两个默认值，以及 `_get_venv_python_path` / `_get_venv_pip_path`，本文件没有任何调用。真正的解释器路径走 `venv_manager.get_python_executable`。`self._processes` 也没有任何写入，见第 5 节。

`deploy` 按这个顺序走。任一步抛异常，都被收成 `DeployResult(success=False, message="Deployment failed: ...")`，目录不会在这个 `except` 里回滚。

1. **决定启动模块。** 有 `ir_path` 时，模块名写死为 `openjiuwen_runtime.examples.lowcode_agent`。子表里那个 `package_name`（HTTP 上就是查询参数 `name`）不参与 `-m`。没有 `ir_path` 时，用 `SubprocessParams.package_name`。CLI 高码走这条：`-m openjiuwen_runtime.<包名>`。模块名最后仍为空，直接 `RuntimeError`。

2. **建 venv。** `create_venv(deployment_id)`。目录公式在下一节。

3. **按 `settings.MODE` 装包。** 两条分支装的东西不同：

```144:159:management/openjiuwen_runtime/management/deployments/subprocess/deployer.py
            if settings.MODE == "dev":
                # 安装基础运行时 WHL（studio/foundation/management/service）
                base_whl_files = sorted(settings.dist_path.glob("openjiuwen_*.whl"))
                for whl_file in base_whl_files:
                    self.venv_manager.pip_install(deployment_id, str(whl_file))
                    ...
                if whl_path and Path(whl_path).exists():
                    self.venv_manager.pip_install(deployment_id, str(whl_path))
                    ...
                else:
                    raise RuntimeError(f"Agent WHL not found: {whl_path}")
            else:
                # 从 PyPI仓库安装 lowcode-agent-runner
                self.venv_manager.pip_install(deployment_id, "lowcode-agent-runner")
```

| `MODE` | 装进这个 venv 的内容 | WHL 从哪来 |
|---|---|---|
| `dev`（`.env.example` 的值） | `DIST_DIR` 下全部 `openjiuwen_*.whl`，再加本次的 agent WHL。文件不存在就失败 | HTTP 低码指向 `dist/lowcode_agent_runner-0.1.0-py3-none-any.whl`；CLI 指向刚 `uv build` 出来的那个 WHL |
| `product`（配置默认值） | 只装 PyPI 上的名字 `lowcode-agent-runner` | Server 在 product 下把 `whl_path` 收成空路径，这条分支也不读本地 WHL |

`pip_install` 失败时返回 `False`，这里没有看返回值。装包失败仍会继续 `Popen`。进程随即退出的话，要到下面第 6 步才变成部署失败，原因在 `agent.log` 里。

4. **定端口，拼命令。** `ctx.port` 有值就用它。HTTP 的 `prepare_subprocess_deployment` 已经分配或校验过端口，所以 deployer 不会再挑。端口为空（CLI 不传 `--port`）时，本机 `bind(("", 0))` 拿一个临时端口。监听地址写死 `0.0.0.0`，不用子表里的 `host`，也不用 `settings.HOST`。

```171:179:management/openjiuwen_runtime/management/deployments/subprocess/deployer.py
            cmd = [
                str(python_executable),
                "-m",
                package_name,
                "--host", "0.0.0.0",
                "--port", str(port)
            ]
            if ir_path:
                cmd.extend(["--irpath", ir_path])
```

低码因此多一个 `--irpath {DEPLOY_DIR}/{deployment_id}/ir.json`。这个 json 是 Server 在调用 Manager 之前写的，deployer 只把它当成参数传进去。

5. **环境变量和日志。** 复制当前环境，设 `VIRTUAL_ENV` 为 venv 根目录。有 `userdata` 时写入 `RUNTIME_USERDATA`，日志里打的是打码后的值，命令行参数里不出现它。日志目录是 venv 的**上一级**：

```text
{DEPLOY_DIR}/{deployment_id}/logs/agent.log
```

文件以追加方式打开，stdout 和 stderr 都指向它。成功返回后这个文件对象留在父进程里，没有 `close`。

Windows 会加 `CREATE_NEW_PROCESS_GROUP`。其他系统就是一次普通 `Popen`，没有 `start_new_session`。

6. **等 2 秒再看进程还在不在。** `process.poll()` 已经有返回码，就读日志全文，抛 `Process exited: ...`。还活着就当启动成功。这一步只证明进程没立刻退出。`/health` 仍由 Manager 在外面探，最长 600 秒。

成功时 URL 是 `http://{settings.IP}:{port}/`。用的是 Runtime 配置里的 `IP`，和进程实际绑定的 `0.0.0.0`、子表里的 `localhost` 是三个不同的值。`DeployResult` 带回 `pid` 和 `venv_path`，供上一节写回 `process` 表。

---

## 3. `VirtualEnvironmentManager`：路径只认 deployment_id

```36:46:foundation/openjiuwen_runtime/foundation/venv_manager.py
    def get_venv_path(deployment_id: str) -> Path:
        """
        根据部署ID获取虚拟环境路径
        ...
        """
        return settings.deploy_path / deployment_id / ".venv"
```

`settings.deploy_path` 来自 `DEPLOY_DIR`。相对路径在配置校验里拼成项目根下的绝对路径，并 `mkdir`。`.env.example` 写 `DEPLOY_DIR=deploys`，所以本机就是仓库根下的 `deploys/<deployment_id>/.venv`。

`create_venv`：

- 目录已经在，直接返回，不重建。同一次 `deployment_id` 再走进来，会把包装进旧环境。
- 否则调用 `uv venv <path>`。PATH 里没有 `uv`，`_resolve_uv_executable` 抛 `RuntimeError: uv executable not found in PATH`，部署失败。
- 创建后再确认 `bin/python`（Windows 是 `Scripts/python.exe`）存在。没有 pip 时再跑 `ensurepip`。

`pip_install` 的命令是：

```text
uv pip install <包或 whl 路径> --python <该 venv 的 python>  <UV_EXTRA_ARGS>
```

`UV_EXTRA_ARGS` 按 shell 分词拼到命令末尾。`.env.example` 里是镜像源和 `--native-tls` 一类参数。安装时把 `UV_HTTP_TIMEOUT`、`UV_REQUEST_TIMEOUT` 设成 600，并发下载设成 1。stderr 里命中 timeout / failed to fetch 一类关键字才重试，最多 3 次，间隔 5 秒。其它错误立刻返回 `False`。

`delete_venv(deployment_id)` 会 `rmtree` 上面那个 `.venv`。`LocalSubprocessDeployer.stop` 不调用它，自己按库里的 `venv_path` 字符串删目录。两条路径在「库里的路径等于 `get_venv_path`」时删的是同一处；库里的 `venv_path` 为空时，`delete_venv` 也不会被补上一刀。

---

## 4. 今天要钉死的三件事

### 隔离粒度是 deployment_id

目录、venv、日志、低码的 `ir.json`，键都是这一次部署的 id。

- HTTP：`main.py` 先 `uuid4()`，再建 `{deploy_path}/{deployment_id}/`，把上传文件写成 `ir.json`，再把这个 id 放进 `extras`。
- CLI：`extras` 里不带 `deployment_id`，Manager 自己再生成一个 UUID，venv 仍用这个新 id。

同名 Agent 部署两次，得到两个 id、两套目录、两个端口。主表 `name` 可以相同，唯一约束在 `deployment_id` 上。`user_id` / `space_id` 留在主表，不进 `DeployContext`，deployer 也不读它们。

### 目录就是 `{DEPLOY_DIR}/{deployment_id}/.venv` 加上同级 `logs/`

一次走完的低码部署，这个 id 目录里是：

```text
{DEPLOY_DIR}/{deployment_id}/
├── ir.json          Server 在进 Manager 之前写入；CLI 高码没有这一步
├── .venv/           uv 创建，Python 在 bin/python
└── logs/agent.log   子进程的 stdout 和 stderr，追加写
```

`logs/` 是 `.venv` 的兄弟目录，在 venv 外面。停服务时如果只删 `.venv`，日志还在。上面 `deploys/` 里那两个 uuid 目录，分别对上「只有 ir.json」和「`.venv` + `logs/agent.log`」这两种中间状态。

### 这条路径上没有业务级 workspace

subprocess 这三个文件里，文件系统范围就是「一次部署一个目录」。没有按项目组、空间、业务 Agent 名再套一层工作区，也没有 workspace 表或 workspace 路径配置。

其它包里出现的 `workspace_id`（例如 a2a 把请求参数往下传）是调用参数，不参与这里的建目录和起进程。业务上要的项目组工作区，要在 Runtime 外面自己建；本路径提供的隔离单位就是 `deployment_id`。

---

## 5. 停和查：杀的是 pid，删的是 `.venv`

`stop` 的注释写「停止部署并清理虚拟环境」。对照实现：

1. 若 `deployment_id` 在 `self._processes` 里，先 `terminate`，10 秒后再 `kill`。`deploy()` 用的是 `subprocess.Popen`，并且没有把句柄放进这个字典。当前拉起的进程走不到这一支。
2. 否则拿到子表里的 `pid`，直接 `kill -9`（Windows 是 `taskkill /F`）。没有先发 `SIGTERM`。pid 已经不存在时，这里打一条 warning，函数仍继续，最后仍返回成功。
3. `venv_path` 非空且目录还在，就 `shutil.rmtree` 这个路径。删的是 `.venv`。`logs/`、`ir.json`、以及 `{deployment_id}/` 目录本身都留着。

`delete_deployment` 先 `stop` 再删数据库行，不再扫这个目录。所以删掉一条部署之后，磁盘上通常还剩：

```text
{DEPLOY_DIR}/{deployment_id}/logs/agent.log
{DEPLOY_DIR}/{deployment_id}/ir.json     # 低码才有
```

部署中途失败时更彻底：异常发生前 venv 可能已经建好，但子表 `venv_path` 仍是空的。之后的 `stop` 拿不到路径，`.venv` 也会留下。Manager 在探活失败时同样不调用 `stop`（Day 7），那种情况下进程还在，`.venv` 也在。

`get_status` 同样先看 `self._processes`（当前为空），再对 pid 做 `kill -0`。活着返回 `RUNNING`，否则 `STOPPED`；没有 pid 则 `PENDING`。管理面的列表和详情走 `manager.get_deployment_status`，只读主表那一列，不会调用这个方法。进程退出之后，主表可以继续显示 `running`，直到某次真正执行 `strategy.get_status`（主链现在没有这一步），或者删除时用 pid 去杀。

---

## 和前后几天的关系

- Day 7 的 `deploy_agent` → `_deploy` → `strategy.deploy` 在 `LocalSubprocessDeployer.deploy` 接上。主表 `url`、状态 `running` 仍由基类回写；subprocess 多写的是 `process.pid` 和 `process.venv_path`。探活超时后主表改 `failed`、进程仍在，今天对得上：deployer 返回成功之后就不再看这个进程。
- Day 6 的租户两列停在主表。建目录、装包、起进程都不读 `user_id` / `space_id`。
- Day 9 要读的 `@app.query` 跑在今天拉起的那个进程里。低码的 `-m` 固定是 `openjiuwen_runtime.examples.lowcode_agent`，并带上 `--irpath`；高码的 `-m` 才是 CLI 解析出的 `openjiuwen_runtime.<包名>`。
- Day 14 观察 `{DEPLOY_DIR}/{deployment_id}/` 时，用今天这张目录图：`.venv` 是环境，`logs/agent.log` 是这个进程的输出，`ir.json` 只在 HTTP 低码出现。`delete` 之后先看日志目录还在不在，再看进程 pid 是否还在。
- 学习计划里的 workspace 缺口，到今天可以写成一句：托管单位是部署目录，业务工作区要自建。多项目组若要按空间隔离文件，现有 subprocess 路径没有这个钩子，目录名只有 `deployment_id`。
