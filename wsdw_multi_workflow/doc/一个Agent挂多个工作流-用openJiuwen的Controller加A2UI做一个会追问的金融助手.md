# 一个 Agent 挂多个工作流：用 openJiuwen 的 Controller + A2UI 做一个会追问的金融助手

> 本文记录我把 openJiuwen agent-core 里的一个多工作流示例，改造成「Python 后端 + React 前端」小项目 wsdw_multi_workflow 的过程。重点不在三个玩具金融流程，而在两件事：**Agent 如何在多条业务流之间路由并在中途停下来问人**，以及**如何把这种"停下来问人"渲染成真正的表单，而不是一句干巴巴的文本**。

---

## 一、先说问题：业务型 Agent 难在哪

做过业务型 Agent 的同学大概都遇到过这种需求：

- 入口只有一个对话框，用户可能说「我要转账」「帮我买点理财」「查下余额」；
- 每条业务都是一条固定流程（工作流），流程里某一步缺信息，要**停下来问用户**；
- 用户答完，要**从断点继续**，而不是从头再来；
- 更麻烦的是，用户可能先说理财、没答完又说转账——**多个流程同时挂起**。

如果每个业务做一个独立 Agent，入口和状态就散了；如果全塞给一个大 ReAct Agent 自由发挥，流程又不可控。

openJiuwen 给的解法是 `ControllerAgent`：**用一层"任务控制面"管生命周期，业务步骤交给 Workflow 执行**。

---



## 二、整体架构

先上一张全景图：

```
浏览器 (React + @a2ui/react)
   │  POST /api/chat  {query, conversation_id}
   ▼
FastAPI  ──SSE──►  A2UI 消息流（createSurface / updateComponents / updateDataModel）
   │
   ▼
ControllerAgent
   ├─ EventHandler      用户输入 → 意图（新建任务 / 恢复任务）
   ├─ TaskManager       任务状态机（可持久化）
   ├─ TaskScheduler     捞出可执行任务
   └─ TaskExecutor      选工作流 → 执行 → 中断或完成
          │
          ▼
   Workflow: start → Questioner(追问) → end
     · 转账服务（问金额）
     · 理财服务（问产品）
     · 余额查询（问账号）
```

项目结构：

```
wsdw_multi_workflow/
  api/                    # Python 后端
    server.py             # FastAPI + SSE，输出 A2UI
    a2ui_messages.py      # Controller 输出 → A2UI 消息
    agent_factory.py      # 装配 Agent / 模型 / 工作流
    handlers/             # Event → Intent → Task
    executors/            # 选流、执行、中断恢复
    workflows/            # 三个金融工作流
  web/                    # React + A2UI 前端
```

---



## 三、Controller 在建模什么

这是我读源码时最大的收获：**Controller 建模的不是业务，而是"任务控制面"**。几个核心概念一句话讲清：


| 概念                   | 含义                         |
| -------------------- | -------------------------- |
| Event                | 外界发生了什么：用户输入、任务完成、任务需要交互   |
| Intent               | 对这件事该怎么动任务：新建、恢复、不明        |
| Task                 | 可调度、可持久化的工作单元，带状态机         |
| EventHandler         | Event → Intent → 改 Task 状态 |
| Scheduler / Executor | 任务可跑时执行，执行结果再变成 Event      |


任务状态机：

```
submitted → working → completed / failed / paused / canceled
                 ↘ input-required（等人）→ 用户补充 → submitted → 继续
```

整条链路可以记成一句话：

**Event →（Handler 经 Intent）→ Task → Scheduler → Executor → 新的 Event**

顺带一提，openJiuwen 的 DeepAgent 外循环（`TaskLoopController`）就是继承这套 Controller 做的，所以理解了这个 demo，再看 DeepAgent 的外循环会非常顺。

---



## 四、两级意图：为什么要拆

这个项目里 LLM 做了两次判断，职责完全不同。

**第一级：任务层（EventHandler）**

LLM 看到"当前会话里未完成的任务列表 + 用户这句话"，通过 function call 三选一：

- `create_task`：开新任务
- `resume_task(task_id)`：继续某个在等人的任务
- `unknown_task`：没听懂，澄清

这一层**不关心**是转账还是理财，只关心任务生命周期。

**第二级：能力层（WorkflowTaskExecutor）**

新任务还没绑定工作流时，Executor 把注册过的工作流描述拼成分类列表，让 LLM 只输出 `{"result": int}`：

```python
tool_list = [tool.description for tool in self._ability_manager.list()]
category_list = "分类0：意图不明\n" + "\n".join(
    f"分类{i+1}：{c}" for i, c in enumerate(tool_list)
)
```

选中后把 `workflow_id` 写进 `task.extensions`，**之后恢复这个任务时不再重新猜业务**。

拆开的好处很直接：恢复路径是确定性的，只有新任务才需要"猜"。

---



## 五、工作流要注册两次，别漏

这是我第一次读代码时困惑的地方：

```python
# 可执行资源：Runner.run_workflow(id) 靠它拿到实例
Runner.resource_mgr.add_workflow(transfer_workflow.card, lambda: transfer_workflow)

# 能力目录：二级意图分类靠它列出候选
agent.ability_manager.add(transfer_workflow.card)
```

可以理解为：`ability_manager` 是**菜单**，`resource_mgr` 是**厨房**。

- 只进菜单：LLM 能选中，但运行时找不到实例；
- 只进厨房：能跑，但分类列表是空的，LLM 选不了。

---



## 六、核心：中断与恢复

每个工作流中间都有一个 `QuestionerComponent`，缺字段时工作流会挂起。Executor 拿到结果后分两种情况：

```python
if isinstance(exec_result.result, list):
    # 工作流在交互节点停下
    task.input_required_fields = {"id": result.payload.id, "value": result.payload.value}
    task.status = TaskStatus.INPUT_REQUIRED
    # 对外输出 TASK_INTERACTION（提问内容）
else:
    # 工作流跑完，对外输出 TASK_COMPLETION
```

用户答完后，Handler 把新输入追加进 `task.inputs`，状态改回 `SUBMITTED`。Executor 再次执行时发现任务已有 `workflow_id` 和 `input_required_fields`，于是走恢复分支：

```python
interactive_input = InteractiveInput()
interactive_input.update(component_id, user_response)
exec_result = await Runner.run_workflow(workflow_id, inputs=interactive_input, session=workflow_session)
```

**中断契约很简单：停下时记住"卡在哪个组件"，恢复时按同一个组件 id 把答案填回去。**

Executor 入口只认两种合法状态，其余一律报错，不做静默兜底：


| workflow_id | input_required_fields | 行为                     |
| ----------- | --------------------- | ---------------------- |
| 无           | -                     | 新任务：选流 + 首次执行          |
| 有           | 有                     | 恢复：InteractiveInput 续跑 |
| 有           | 无                     | 状态异常，直接报错              |


---



## 七、相对原示例我改了什么

原示例是框架自带的教学代码，读的时候发现两处值得改：

**1. 任务列表没有按会话隔离**

原代码里意图识别取上下文时按 `session_id`，取任务时却是全量：

```python
tasks = await self._task_manager.get_task()   # 全量
```

`TaskManager` 挂在 Controller 上，不是每个会话一份。多会话并行时，A 会话的意图 Prompt 里会混进 B 会话的挂起任务。改成：

```python
tasks = await self._task_manager.get_task(
    TaskFilter(session_id=session.get_session_id())
)
```

**2. 恢复一个"不在等人"的任务时静默改状态**

原逻辑里，如果 LLM 选了 `resume_task`，但任务其实不在 `INPUT_REQUIRED`，会直接把状态改回 `INPUT_REQUIRED`，用户这轮输入就丢了。我改成显式拒绝并报错，问题暴露在明处。

---



## 八、把"停下来问人"变成真正的表单：接入 A2UI

命令行版本里，工作流中断时用户只能看到一行字：「请您提供转账金额相关的信息」。放到 Web 上，我希望它是一张**带输入框和提交按钮的卡片**。

这里用了 [A2UI](https://a2ui.org/)（Agent to UI）协议。它的思路是：Agent 不输出 HTML，也不输出可执行代码，而是输出**声明式的 JSON 组件描述**，前端用自己白名单里的组件来渲染。核心就三类消息：

- `createSurface`：开一块 UI 区域
- `updateComponents`：描述组件树
- `updateDataModel`：填数据（组件通过 path 绑定）



### 后端：Controller 输出事件 → A2UI 消息

映射规则只有几行：

```python
if kind == "TASK_INTERACTION":
    return build_form_surface(surface_id, text)     # 追问 → 表单
if kind == "TASK_FAILED":
    return build_error_surface(surface_id, text)    # 失败 → 错误卡片
if kind == "TASK_COMPLETION":
    return build_info_surface(surface_id, "办理完成", text)
```

追问表单是一个 Card，里面有标题、提问、TextField、提交按钮。按钮的 action 把输入框的值带回前端：

```python
{
    "id": "submit",
    "component": "Button",
    "child": "submit-label",
    "variant": "primary",
    "action": {
        "event": {
            "name": "submit_answer",
            "context": {"answer": {"path": "/answer"}},
        }
    },
}
```

FastAPI 这边就是一个 SSE 接口，逐块把 Controller 输出转成 A2UI 消息推给前端；同一会话加了一把 `asyncio.Lock`，避免并发请求把同一个会话的任务状态搅乱。

### 前端：交给 A2UI 渲染器

前端用官方的 `@a2ui/react`，核心是一个 `MessageProcessor`：

```tsx
const processor = new MessageProcessor([basicCatalog], (action) => {
  const query = queryFromAction(action);   // submit_answer 取 answer
  if (query) sendRef.current?.(query);
});
```

收到 SSE 里的消息就 `processor.processMessages(messages)`，页面上每个 Surface 用 `<A2uiSurface />` 渲染。首页的"转账 / 理财 / 余额"三张入口卡片也是用 A2UI 消息描述的，点击按钮等价于发送「我要转账」。

这样一轮交互在界面上是：

1. 用户点「开始转账」；
2. 后端建任务、选中转账流、跑到 Questioner 停下；
3. 前端出现一张「需要补充信息」表单卡片；
4. 用户填 100、点提交；
5. 后端恢复工作流，前端出现「办理完成：转账服务完成: 100」。

---



## 九、坦白说：还没解决的问题

这个项目能跑通主流程，但离"生产可用"还差几步，列出来给想借鉴的同学避坑：

**1. 表单提交仍然靠 LLM 判断恢复哪个任务**

目前表单提交后，前端只是把答案当普通文本发回去，后端仍由一级意图 LLM 决定 `resume` 哪个任务。只有一个任务在等人时问题不大；**多个任务同时 input-required 时，用户答一句「100」，LLM 可能恢复错任务**。更稳的做法是：追问表单里带上 `task_id`，提交时直接走确定性恢复，LLM 只做兜底。

**2. 缺一个"待办面板"**

多个任务挂起时，用户根本不知道系统里还有几件事没办完。理想的界面应该有一块常驻的待办区：业务名、在等什么字段、继续 / 取消按钮。

**3. 二级选流的边界情况**

当 LLM 返回 `result=0`（意图不明）或越界时，选流函数没有给出明确结果，需要补上显式处理。

**4. 框架还在 Beta**

openJiuwen 目前是 0.1.x，接口仍在演进，依赖最好锁版本。

---



## 十、总结

回头看，这个项目真正值得带走的是一套骨架：

**Controller 管任务**：Event → Intent → Task → Scheduler → Executor，状态写在 Task 上而不是散落在对话里；

- **Executor 管选流与执行**：新任务才猜业务，恢复任务靠 `workflow_id` 确定性续跑；
- **Workflow 管业务步骤**：追问节点天然支持中断与 `InteractiveInput` 恢复；
- **A2UI 管呈现**：把 `TASK_INTERACTION` 渲染成表单，把"机器人在猜我说什么"变成"我在填一张表"。

如果你也在做「一个入口、多条业务流水线、中间要问人」的 Agent，可以直接拿这套结构替换成自己的业务工作流。

---

**参考**

- openJiuwen agent-core：`examples/workflow_agent/multi_workflow_agent_demo`
- A2UI 协议：[https://a2ui.org/](https://a2ui.org/)
- 本文项目代码：[https://github.com/songhaowei666/wsdw_multi_workflow](https://github.com/songhaowei666/wsdw_multi_workflow)

*示例改造自 openJiuwen agent-core，遵循 Apache-2.0 协议。*