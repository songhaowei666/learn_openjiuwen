# AgentSession 的 pre_run 与 checkpoint：ModelContext 才是模型的消息视野

> 建议标题：`openJiuwen | AgentSession与Context | pre_run、checkpoint 与 ModelContext 消息视野`
>
> 本文整理自对 openJiuwen agent-core 源码的阅读：围绕 `AgentSession.pre_run`、Checkpointer 恢复、以及 `ModelContext` / `ContextWindow` 的关系，并延展到 Team / Workflow / Node 等会话类型。对应 Demo：`react_structured_session`。重点不是怎么跑命令，而是多轮会话时**状态从哪来、消息存在哪、模型到底看见什么**，以及各类 Session 各自管哪一层。

## 目录

- [一、先说问题：同 conversation_id 再跑一轮，历史从哪来](#一先说问题同-conversation_id-再跑一轮历史从哪来)
- [二、pre_run：正式执行前的会话初始化钩子](#二pre_run正式执行前的会话初始化钩子)
- [三、checkpoint 恢复的不是「message 列表」，是整份 session state](#三checkpoint-恢复的不是message-列表是整份-session-state)
- [四、链路：state → ModelContext → ContextWindow → LLM](#四链路state--modelcontext--contextwindow--llm)
- [五、全量历史会话消息维护吗](#五全量历史会话消息维护吗)
- [六、ModelContext 维护的是模型的消息视野](#六modelcontext-维护的是模型的消息视野)
- [七、会话家族：AgentTeam / Agent / Workflow / Node](#七会话家族agentteam--agent--workflow--node)
- [八、踩坑与注意事项](#八踩坑与注意事项)
- [九、总结](#九总结)

---



## 一、先说问题：同 conversation_id 再跑一轮，历史从哪来

做 ReAct 多轮时，常见直觉是：

1. 上一轮的 user / assistant / tool message 全存进 session；
2. 下一轮 `pre_run` 从 checkpoint 把「历史所有 message」灌回来；
3. ReActAgent 从 session 直接读这些 message 接着聊。

源码里的路径更接近：**checkpoint 恢复整份 session state → ContextEngine 把其中的** `context` **装成 ModelContext → 真正喂模型的是 ContextWindow**。  
历史对话在 state 里，但挂在 `state["context"]`，不是 session 顶层的一串裸 message；Agent 执行时用的也是 `ModelContext`，不是 `session.get_messages()`。

---



## 二、pre_run：正式执行前的会话初始化钩子

`AgentSession.pre_run` 与 `post_run` 成对出现，负责把 session 从「刚创建」变成「可跑」。核心三步：

1. **幂等**：`_pre_run_done` 已为真则直接返回，避免重复触发事件或重复恢复。
2. **广播** `SessionEvents.AGENT_SESSION_CREATED`：把 `session_id`、`card`、`session` 交给 Runner / SessionController 等订阅方（例如挂到 chain_session 的 data_container）。
3. **Checkpointer**：`pre_agent_execute(inner, inputs)`——按 session 恢复上次快照，并把本轮 `inputs` 写入 state（如 `INTERACTIVE_INPUT`）。

Runner 的 `_prepare_agent` 会在真正跑 Agent 之前调用它。可记成：

> 跑 Agent 之前：通知外界 session 已建好 → 从 checkpoint 恢复历史状态 → 注入本轮 inputs。

对应 Demo 里「同 `conversation_id` 两轮 session_id 一致」：身份靠 conversation / session_id 对齐；能否续上对话，还取决于上一轮是否把 context 写回 state 并 `commit`。

---



## 三、checkpoint 恢复的不是「message 列表」，是整份 session state

以内存 Checkpointer 为例：`AgentStorage.recover` 取出 blob，反序列化后 `session.state().set_state(state)`。  
`_get_state_to_save` 用的是 `session.state().get_state(...)`——**整份 KV 快照**。

常见会一起回来的内容包括：


| 内容                    | 作用                                     |
| --------------------- | -------------------------------------- |
| `context`             | 对话 messages、窗口位置、token / processor 状态等 |
| `data_context` 等业务 KV | 工具读写的业务状态（Demo 里的 session 工具）          |
| HITL / interrupt 相关   | 断点续跑                                   |
| 本轮 `inputs`           | `pre_agent_execute` 里再写入               |


历史对话确实在 checkpoint 里，但路径是 `state["context"]`，不是「顶层全量 message 数组」。

落盘时机：上一轮结束附近会 `context_engine.save_contexts(session)`，把 ModelContext 的 `save_state()` 写回 `session.update_state({"context": states})`，再 `session.commit()` / `post_run` 交给 checkpointer。

---



## 四、链路：state → ModelContext → ContextWindow → LLM

```
上一轮结束
  → save_contexts(session)     # ModelContext → session.state["context"]
  → commit / post_run          # checkpointer 持久化整份 state

下一轮开始
  → pre_run → recover          # 整份 state 回到 session
  → ReActAgent._init_context
  → context_engine.create_context(session)
  → _load_state_from_session   # session.get_state("context") → context.load_state
  → ReAct 循环用 ModelContext
  → get_context_window()       # 本轮实际喂给 LLM 的窗口
```

`ReActAgent._inner_invoke` 里大致是：`context = await self._init_context(session)`，再挂到 callback context。之后 `add_messages`、`get_context_window` 都走这个 context。

因此更准确的说法是：

> checkpoint 恢复整份 session state；其中的 `context` 带着历史 messages（及上下文元数据）。ReActAgent 通过 ContextEngine 装成 `ModelContext`，再基于 context 继续跑——而不是每轮直接扫 session 上的 message 列表。

---



## 五、全量历史会话消息维护吗

**默认不是「永久、不可变的全量聊天档案」。** 维护的是当前 ModelContext 里那份可演进的上下文，再经 checkpoint 落盘。

默认配置（`ReActAgentConfig`）里常见：

- `max_context_message_num=None` → buffer **没有硬上限**，会一直往里加；
- 同进程、同 session、且未开压缩时，**看起来像在维护全量历史**。

但一旦下列机制生效，就不是「历史上每一条原文」了：


| 机制                                                        | 效果                     |
| --------------------------------------------------------- | ---------------------- |
| `max_context_message_num`                                 | 超限后裁旧消息                |
| context processors（压缩 / compact）                          | 旧消息被摘要替换，原文可能没了        |
| offload                                                   | 大段内容挪到内存 / 文件，上下文里只留句柄 |
| `default_window_message_num` / `default_window_round_num` | 发给模型的窗口可能只取最近 N 条 / 轮  |


另外：框架这条链路**没有**单独再建一套「永不删改的全量会话库」。若要严格审计，需要在 session 外自存聊天记录。

---



## 六、ModelContext 维护的是模型的消息视野

可以这么理解，再拆一层：

```
ModelContext（工作上下文 / 消息视野）
    │  get_context_window()
    │  + processors / window 配置 / reload
    ▼
ContextWindow（本轮实际喂给 LLM 的 messages）
```

- **ModelContext**：当前会话给模型用的工作集——消息 buffer，以及窗口、压缩、offload 相关状态。
- **ContextWindow**：从 ModelContext 派生、本轮真正发出去的那份；可以更短、更压缩，不等于 buffer 全文。

所以：

- 说「模型的消息视野」——对，它管的就是给模型用的那套对话上下文；
- 「视野」有两层：buffer 里存的，和某次调用真正发出去的。

业务 KV（如 `data_context`）仍在 session state 上，由工具通过 `session.get_state` / `update_state` 或 `get_current_session()` 读写，和「模型看见的 messages」是两条线，不要混成一个概念。

### 为何还要 context_id：一个 session 可以挂多个 ModelContext

| ID | 管什么 |
| --- | --- |
| `session_id` | 会话 / Checkpointer / 业务 KV 的身份 |
| `context_id` | 该会话里的哪一块消息视野（主对话、旁路任务、某条 workflow） |

本质：**不同 key 区分不同的 ModelContext**。

- 进程内池子 key：`{session_id}_{context_id}`
- 落盘到 `session.state["context"]`：再用 `context_id` 当分桶 key

简单 ReAct 默认只用 `default_context_id`；需要并行 / 嵌套对话线时再建第二个 context。

Demo：`python -m backend.main multi_context`（`react_structured_session/backend/multi_context.py`）。同一 `session_id` 下创建 `main` 与 `side_task`，分别写入周会 / 天气消息，验收互不污染；`save_contexts` 后 `session.state["context"]` 含两个 key。

---

## 七、会话家族：AgentTeam / Agent / Workflow / Node

前文主体是 **AgentSession**（API：`create_agent_session` / `openjiuwen.core.session.agent.Session`，内部 `_inner` 为 `AgentSession`）。  
它是「单 Agent 对话」的容器；ModelContext 挂在它的 `state["context"]` 里。框架里还有几类 Session，职责不同，不要都当成「存聊天记录的地方」。

### 三层视角（先钉住 Agent 这条线）

```text
AgentSession（会话容器：session_id、state KV、pre_run/post_run、checkpointer）
    │  state["context"]     ← save_contexts / load_state
    │  state["data_context"] 等业务 KV
    ▼
ModelContext（按 context_id 分桶的消息工作集）× N
    │  get_context_window()
    ▼
ContextWindow（本轮真正喂 LLM 的切片）
```

- **AgentSession**：谁在跑、状态往哪存、怎么恢复——**身份 + 整包 state**。
- **ModelContext**：模型对话账本——**内容**；一个 AgentSession 里可以多个。
- **ContextWindow**：这一次调用看见什么——**瞬时视图**。

### 全家对照

| 类型 | 常见挂法 | 管什么 |
| --- | --- | --- |
| **AgentTeam Session**（`create_agent_team_session`，内部 `AgentTeamSession`） | 团队运行的**根** | 多智能体一轮任务、团队级 state / checkpointer（`pre_agent_team_execute`） |
| **AgentSession** | Team 可 `create_agent_session` 生出；或独立创建 | 单成员对话、业务 KV、`state["context"]` / ModelContext |
| **WorkflowSession** | 常由 `agent_session.create_workflow_session()` 挂在 Agent 下；也可独立创建 | 整张工作流图 / Pregel；**不是**对话 message buffer |
| **NodeSession** | 挂在 **WorkflowSession** 上（按 `node_id`） | 图上**单个节点**的 IO / 局部状态；checkpointer 委托给 parent |

方向要注意：

- Agent → Workflow：`AgentSession` **生出** `WorkflowSession`（`parent=agent._inner`，常共用 `session_id`）。`wsdw_multi_workflow` 即此路径。
- Team → Agent：**TeamSession 生出** 各成员 `AgentSession`（共享输出流等），不是「某个 AgentSession 下面挂 Team」。
- Workflow → Node：跑组件时 `NodeSession(workflow_session, node_id)`；嵌套子图还有 `SubWorkflowSession`。

合在一起（AgentTeams 跑任务且成员再调工作流时）：

```text
AgentTeam Session
  └── AgentSession（成员）
        ├── ModelContext × N（state["context"] 分桶）
        └── WorkflowSession（可选）
              └── NodeSession（每节点）
```

### 易混点

- **说「session 存消息」不精确**：消息在 ModelContext，挂在 AgentSession 的 state 里。
- **NodeSession ≠ ModelContext**：前者是工作流节点作用域，后者是 Agent 对话分桶。
- **WorkflowSession 不强制挂 Agent**：Runner 也可 `session=None` 或只传字符串 id，单独跑图。
- 群聊 Demo（如 `swarmchat_room`）更多是房间 / 广播绑定；经典 Leader–Teammate 任务运行时，顶层才是 AgentTeam Session。

---

## 八、踩坑与注意事项

1. **只建同 id 的 session 不够**：要能续对话，上一轮必须 `save_contexts` 再 `commit`；否则 checkpoint 里没有完整 `context`。
2. **`update_state` 写业务数据**：宜在 `pre_run`（restore）之后写，避免被恢复的旧 state 盖掉（Demo 的 session 工具说明里也强调过）。
3. **无参工具读 session**：继承 `Tool` 要用 `invoke(self, inputs, **kwargs)` 取 `session`；`@tool` 函数内用 `get_current_session()`，不要把 `session` 写进函数签名。
4. **不要把 session state 当成审计级全量聊天库**：默认链路保证的是「可续跑的工作上下文」，不是「永久全量原文」。官方 Checkpointer（含 SQLite）仍是 **KV 快照**，不是按消息行拆的结构化聊天表；要审计库需旁路双写。
5. **分清会话类型**：续聊看 AgentSession + ModelContext；跑图看 WorkflowSession + NodeSession；多智能体任务看 AgentTeam Session。

---

## 九、总结

- `pre_run`：幂等初始化 + 会话创建事件 + checkpointer 恢复与注入 inputs。
- checkpoint：恢复**整份 session state**；对话历史在 `state["context"]`。
- ReActAgent：经 ContextEngine 得到 `ModelContext`，再 `get_context_window` 喂模型。
- 默认可不限条数堆消息，但截断 / 压缩 / offload / 窗口配置会改写「全量」含义。
- **ModelContext ≈ 模型的消息视野（工作集）；ContextWindow ≈ 本轮实际可见切片。**
- **session_id 定会话，context_id 定视野分桶**；同 AgentSession 可挂多个 ModelContext（本质是不同 key）。
- **会话家族**：Team 包住多个 Agent；Agent 可生出 Workflow；Workflow 下再挂 Node——各管一层，不要混成「一个 session」。

怎么跑 Demo、如何验收结构化输出 / 同 conversation_id / 多 ModelContext，见 `react_structured_session/README.md` 与仓库 `spec/ReActAgent结构化输出与Runner会话.md`。