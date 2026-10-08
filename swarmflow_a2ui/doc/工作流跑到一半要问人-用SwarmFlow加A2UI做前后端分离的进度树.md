# 工作流跑到一半要问人：用 SwarmFlow + A2UI 做一条前后端分离的进度树

> 本文记录我在 openJiuwen agent-core 里做的一个小 Demo：`swarmflow_a2ui`。用户在网页上提一个问题，后端跑一段预先写好的 SwarmFlow 脚本；页面上一边长出阶段和 Agent 的进度树，一边在人工节点上弹出真正的表单。重点不是「调研报告」这个玩具场景，而是两件事：**进度怎么增量推到前端**，以及**流程停下来问人时，怎么把提问变成可提交的界面**。

## 目录

1. [一、先说问题：TUI 里能问人，网页上怎么问](#一先说问题tui-里能问人网页上怎么问)
2. [二、整体架构](#二整体架构)
3. [三、脚本在声明什么](#三脚本在声明什么)
4. [四、同进程跑引擎，进度事件翻译成扁平节点](#四同进程跑引擎进度事件翻译成扁平节点)
5. [五、进度树：前端不存树](#五进度树前端不存树)
6. [六、human 节点：先占住 Future，再等用户](#六human-节点先占住-future再等用户)
7. [七、A2UI：三种问法，同一套消息顺序](#七a2ui三种问法同一套消息顺序)
8. [八、这个 Demo 故意没做什么](#八这个-demo-故意没做什么)
9. [九、总结](#九总结)

---

## 一、先说问题：TUI 里能问人，网页上怎么问

SwarmFlow 把多智能体协作写成一段普通 Python 脚本：`phase()` 划分阶段，`agent()` 跑一个执行节点，`parallel()` 把互不依赖的节点摊开，`human()` 在中间插入一次人工介入。命令行和 TUI 里，进度和提问都在同一个终端里滚动。

放到 Web 上，需求变了：

- 用户在前端输入问题，后端启动一段**事先写好**的脚本，而不是让模型现场编流程；
- 页面要实时看到跑到了哪个阶段、哪个 Agent，完成时带上 token 用量；
- 跑到 `human()` 时，不能只弹一行字，要给出审批、单选、文本框这种能点的界面；
- 用户提交之后，脚本从停下的地方继续，而不是整段重跑。

如果进度和表单挤在同一条消息流里，表单状态会被后面的进度事件冲掉；如果人工等待写进进度节点自己的状态机，节点一更新，等待中的回复就容易丢。所以这个 Demo 把两条流拆开：**进度只读、可覆盖；表单有创建和销毁，回复走单独的 HTTP。**

---

## 二、整体架构

传输上可以共用一条 SSE，逻辑上是两条通道。

```
浏览器 (React + Zustand + @a2ui/react)
   │  POST /api/ask     {question}
   │  GET  /api/events/{run_id}     SSE
   │       event: progress          进度树增量
   │       event: a2ui              表单创建 / 销毁
   │  POST /api/reply   {run_id, action, context}
   ▼
FastAPI
   ├─ EventBridge         带序号的事件日志，SSE 断线可按 Last-Event-ID 续传
   ├─ SwarmFlow Runner    同进程调用引擎 run_workflow
   │     └─ _Projector    引擎事件 → 扁平进度节点
   ├─ A2UI Bridge         human 的 prompt 标记 → A2UI JSON
   └─ HumanManager        asyncio.Future，挡住 human() 直到用户回复
          │
          ▼
   workflows/demo_workflow.py
     调研(parallel 两个 agent) → 审批(human) → 撰写(选择 + 补充 + agent)
```

项目结构：

```
swarmflow_a2ui/
  backend/
    main.py                 # /api/ask、/api/events、/api/reply
    swarmflow_runner.py     # 启动脚本、投影进度、挂上人工等待
    event_bridge.py         # 进程内事件日志
    a2ui_bridge.py          # human → A2UI
    human_manager.py        # 等待与唤醒
    workflows/demo_workflow.py
  frontend/
    src/stores/             # 进度表、A2UI 消息
    src/components/         # 进度树、表单、提问框
    src/api/                # ask / SSE / reply
  doc/                      # 本文
```

一次点击在界面上是这样的：

1. 用户输入「帮我调研 openJiuwen SwarmFlow 的架构设计」，点开始；
2. 进度树先出现「调研」，下面并行挂上「架构调研」「能力调研」，完成后标出 token；
3. 「审批」阶段停住，节点状态变成「等待输入」，下面展开通过 / 驳回和可选理由；
4. 通过之后再问报告风格（简报或详细报告），再问一句补充关注点；
5. 「撰写报告」完成，树收起，页面底部给出脚本的返回值。

驳回则直接结束，不再进入撰写。

---

## 三、脚本在声明什么

SwarmFlow 脚本就是一个带 `META` 和 `async def run(args)` 的 Python 模块。`META` 里写工作流名字、阶段计划和本次运行的 token 上限：

```python
META = {
    "name": "research-report",
    "description": "并行调研后经人工审批，再按选定风格生成报告",
    "phases": [
        {"title": "调研", "description": "并行收集架构与能力要点"},
        {"title": "审批", "description": "人工确认是否继续"},
        {"title": "撰写", "description": "按选定风格生成报告"},
    ],
    "workflow_token_limit": 2000,
}
```

调研阶段用 `parallel()` 同时拉起两个 `agent()`。`schema` 是一份 JSON Schema，用来规定这次调用必须返回结构化对象，而不是一段自由文本。`_FINDING` 要求结果里只有 `summary` 和 `points`：

```python
architecture, capability = await parallel([
    lambda: agent(
        f"请调研该主题的架构设计：{question}",
        label="架构调研",
        schema=_FINDING,
    ),
    lambda: agent(
        f"请调研该主题的核心能力：{question}",
        label="能力调研",
        schema=_FINDING,
    ),
])
```

引擎按 schema 校验返回值。通过之后，`agent()` 的结果就是 `dict`，后面的审批文案直接读 `summary`。

人工节点同样可以带 schema。审批要求 `{action, reason}`，选风格要求 `{style}`，补充关注点要求 `{focus}`。脚本只看这些字段决定要不要继续写报告：

```python
decision = await human(
    "[approval]\n调研结果已就绪，是否继续生成报告？\n"
    f"主题：{question}\n架构：{_summary(architecture)}\n能力：{_summary(capability)}",
    label="审批调研",
    schema=_APPROVAL,
)
if decision.get("action") != "approve":
    return {"status": "rejected", "reason": decision.get("reason", "")}
```

提示词第一行的 `[approval]`、`[choice:...]`、`[text]` 是这个 Demo 和 A2UI 桥约定的标记，引擎本身不解释它们。桥接层剥掉标记，剩下的正文才显示给用户。

脚本里还可以读 `budget.remaining()`。账本来自 `META["workflow_token_limit"]`，每个 agent / human 调用结束时由后端计入。Demo 里撰写之前会打一行「当前剩余预算」，进度树上能看到这个数字。

---

## 四、同进程跑引擎，进度事件翻译成扁平节点

`POST /api/ask` 生成 `run_id`，丢一个 `asyncio.Task` 去跑 `run_workflow(脚本路径, args=问题, progress_sink=...)`。FastAPI 和 SwarmFlow 引擎在同一个进程里，进度不走跨进程消息总线，直接进 `progress_sink`。

引擎抛出的是 `WorkflowProgressEvent`，种类包括工作流开始、阶段切换、Agent 开始 / 完成 / 失败、日志、工作流结束。前端要的是另一种形状：

```json
{
  "type": "progress",
  "nodeId": "phase:调研",
  "nodeType": "phase",
  "label": "调研",
  "status": "running",
  "parentId": "workflow",
  "tokens": null
}
```

`_Projector` 负责这场翻译，并且只保留前端画树需要的父子关系：

| 引擎事件 | 前端节点 | parentId |
| --- | --- | --- |
| WORKFLOW_STARTED | `workflow`，状态 running | 空 |
| PHASE | `phase:{标题}`，上一阶段标完成 | `workflow` |
| AGENT_STARTED | 引擎给出的 `agent_id`；human 的状态是 `waiting_for_human` | 当前阶段 |
| AGENT_COMPLETED | 同一 `nodeId` 改成 completed，带上 tokens | 当前阶段 |
| LOG | `log:{序号}` | 当前阶段 |
| WORKFLOW_COMPLETED | 当前阶段和 workflow 都标完成 | — |

并行的两个调研节点会先后（或交错）发出 `AGENT_STARTED`，但 `parentId` 都指向「调研」。前端不用理解 `parallel()`，只要认父节点 id。

同一节点会收到多次事件。开始是 `running`，结束是 `completed`，`nodeId` 不变。这就是后面前端用扁平表覆盖更新的原因。

---

## 五、进度树：前端不存树

前端 store 是一张 `nodeId → 节点` 的表。每条 `progress` 事件按 `nodeId` 覆盖旧记录；事件里没带的 `tokens`、`detail` 沿用上一次的值。SSE 重连时服务端按 `Last-Event-ID` 把错过的事件再推一遍，前端用事件 id 去重。

渲染时才派生树：

- `parentId == null` 的是根，这次只有 workflow；
- 其余节点挂到 `parentId` 等于自己 `nodeId` 的父节点下面，递归画出来。

所以页面上的层次是后端在事件里定好的：workflow → phase → log / agent / human。组件本身不维护一份会和事件打架的树形副本。

人工节点的表单不写进这张表的正文。`a2ui` 事件另外带 `nodeId` 和 `surfaceId`，store 只在对应节点上记一个 `surfaceId`。节点状态仍是 `waiting_for_human` 时，进度树在那一行下面渲染 A2UI Surface。节点完成后，后端再推一条 `deleteSurface`，前端把 `surfaceId` 清掉，表单消失，进度行留下完成状态和 token。

---

## 六、human 节点：先占住 Future，再等用户

`human()` 在引擎里会先发出 `AGENT_STARTED`（`node_type` 为 `human`），然后才进入 backend 的 `send_turn()` 并阻塞。用户有可能在页面上点得很快，回复请求比 `send_turn()` 更早到达。如果这时才创建 Future，回复会落空，后面再创建一个新的空 Future，流程就永远停住。

`HumanManager` 把「开始等」和「取走等待」拆开：

```python
def begin(self, run_id: str) -> asyncio.Future:
    """进度回调里调用。本轮还没被 backend 取走时，复用同一个 Future。"""
    ...

def wait(self, run_id: str) -> asyncio.Future:
    """send_turn 里调用。即使结果已经 set 过，也返回这一轮的 Future。"""
    ...
```

`progress_sink` 在发出 A2UI 之前同步调用 `begin()`。`send_turn()` 再 `await wait()`。回复若已经先到，`await` 会立刻拿到结果。

`POST /api/reply` 的正文是：

```json
{
  "run_id": "...",
  "action": "approve",
  "context": {"reason": ""}
}
```

`resolve()` 对当前 Future 做 `set_result`。backend 再按 schema 的 `required` 字段把 `action` / `context` 收成脚本要的 dict：审批要 `action` 和 `reason`，风格要 `style`（ChoicePicker 的值是字符串数组，取第一项），补充关注点要 `focus`。引擎拿这份结构和 schema 做校验，通过后 `human()` 返回，脚本继续。

一个 `run_id` 同时只挂一轮等待。这个 Demo 的三个人工节点是串行的，下一轮 `begin()` 会在上一轮被取走之后新建 Future。

---

## 七、A2UI：三种问法，同一套消息顺序

[A2UI](https://a2ui.org/) 让 Agent 输出声明式组件，而不是 HTML。前端只用自己白名单里的 basic catalog 来画。一段表单固定三步：

1. `createSurface`：打开一块 surface，`catalogId` 指向 v0.9 basic catalog；
2. `updateComponents`：组件树，必须有 `id: "root"`；
3. `updateDataModel`：把文案和输入框的初值写进数据模型，组件用 `path` 绑定。

标记和界面的对应关系：

| 提示词首行 | 界面 | 用户动作带回的字段 |
| --- | --- | --- |
| `[approval]` | 说明文字、驳回理由、通过 / 驳回 | `action=approve\|reject`，`context.reason` |
| `[choice:brief=简报\|detailed=详细报告]` | 单选 ChoicePicker + 确认 | `context.style`，值为 `["brief"]` 或 `["detailed"]` |
| `[text]` | 长文本框 + 提交 | `context.focus` |

按钮不把整个数据模型传回去，只在 `action.event.context` 里点名需要的 path。例如通过按钮：

```python
{
    "id": "approve",
    "component": "Button",
    "child": "approve-label",
    "variant": "primary",
    "action": {
        "event": {
            "name": "approve",
            "context": {"reason": {"path": "/reason"}},
        }
    },
}
```

前端用官方 `MessageProcessor` 吃这些消息。用户点按钮时，回调里拿到 `name` 和 `context`，连同当前 `run_id` 调用 `POST /api/reply`。进度树和表单是两个 store：进度事件进 `progressStore`，A2UI 消息进 `a2uiStore`，避免一次进度刷新把表单状态冲掉。

---

## 八、这个 Demo 故意没做什么

它能把主路径跑通，但有几处边界写在这里，避免把示例当成生产方案。

**1. Agent 节点没有调用真实模型**

脚本走的是 SwarmFlow 引擎的 `run_workflow`，`phase` / `parallel` / `human` / `budget` 都是引擎原语。`agent()` 的结果由同进程的 `InteractiveBackend` 按 `label` 生成固定结构，这样不配 API Key 也能点通页面。换成真实 worker，需要接团队侧的 `TeamWorkerBackend`，并准备模型与 human avatar 的规格。human 的等待方式也会从本进程的 Future，换成引擎那条 `submit_human_reply` 消息。

**2. 一个运行同时只等一个 human**

`HumanManager` 按 `run_id` 只保留一轮 Future。脚本如果在 `parallel()` 里同时问多个人，回复会串到同一轮上。串行的审批、选风格、补充关注点没有这个问题。

**3. 表单种类靠提示词标记，不靠 schema 自动生成**

schema 负责校验「回复长什么样」，标记负责决定「画哪一种控件」。新增一种交互要同时改脚本首行和 `a2ui_bridge`。这是为了让 Demo 的界面可复现，不是通用的 schema 到 UI 编译器。

**4. 运行状态在内存里**

`run_id`、事件日志、未完成的 Future 都在进程内。进程重启之后，页面上的旧 `run_id` 无法续上。SSE 的 `Last-Event-ID` 只能补同一次进程里错过的事件。

---

## 九、总结

这条链路可以收成四句话：

- **脚本管流程**：阶段、并行、人工、预算都写在 `demo_workflow.py` 里，Web 层不重新编排；
- **投影管进度**：引擎事件收成带 `nodeId` / `parentId` 的增量，前端用扁平表覆盖，渲染时再拼树；
- **Future 管等待**：human 一开始就把 Future 占住，用户回复只做 `set_result`，脚本从 `await human()` 后面继续；
- **A2UI 管呈现**：提问标记换成 `createSurface → updateComponents → updateDataModel`，按钮只回传用到的字段。

进度回答「跑到哪了」，表单回答「现在需要人做什么」。两条通道分开之后，后面的进度更新不会把正在填的表单清掉，人的回复也不会被写成下一条进度日志。

---

**参考**

- SwarmFlow 引擎进度事件：`openjiuwen/agent_teams/workflow/engine/progress.py`
- A2UI 协议：[https://a2ui.org/](https://a2ui.org/)
- 本文项目代码：[https://github.com/songhaowei666/learn_openjiuwen/tree/main/swarmflow_a2ui](https://github.com/songhaowei666/learn_openjiuwen/tree/main/swarmflow_a2ui)

*示例基于 openJiuwen agent-core，遵循 Apache-2.0 协议。*
