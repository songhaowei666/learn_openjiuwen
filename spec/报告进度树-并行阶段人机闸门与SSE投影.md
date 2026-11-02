# 报告进度树：用 openJiuwen Workflow 做并行调研、人机闸门与进度投影

对应 demo：尚未落地（建议目录 `workflow_report_tree`）。  
引擎语义对照：`pregel_checkpoint` / `spec/断点续传与Pregel图模型.md`。  
Web 人机与 A2UI 交互形态可参考：`wsdw_multi_workflow`（追问表单），**不使用 SwarmFlow**。

本文定义「报告进度树」业务：一张 **Workflow 静态图** 跑并行调研与多段人机闸门；前端用 SSE 投影进度树，表单走独立通道。重点是：**图怎么构图**，**并行 / 中断 / 续跑在 Workflow 层是什么语义**，以及**进度与表单为什么分两条流**。

## 1. 业务是什么

用户提交一个调研主题，工作流按固定拓扑推进：

1. **调研**：`arch` 与 `capability` 同超步并行，树上同时亮起两个调研节点。
2. **汇合**：`merge(wait_for_all)` 等两路都完成后，进入审批。
3. **审批**：`session.interact` 人机闸门——通过走撰写支路；驳回走结束支路，不再问风格、不写报告。
4. **撰写**：串行再问风格、关注点，然后 `write` 节点产出 `{title, body}`。

页面要实时看到：当前阶段（可用虚拟 phase 节点或按节点分组）、并行节点状态、卡在哪个组件等人。等人时节点下出现可点的 A2UI 表单。

同类业务：多源核验中途确认、多角色并行签后再汇总、长报告生成中的选题 / 补材料闸门。共性是「多支线推进 + 局部等人 + 最终汇合」。

## 2. 不在本设计内

- SwarmFlow（`phase` / `parallel` / `agent` / `human` / journal）。本设计只用 `openjiuwen.core.workflow.Workflow`。
- 真实模型（落地 demo 用确定性自定义组件即可；需要模型时再换成 LLM 组件）。
- ControllerAgent / 多工作流意图路由（那是 `wsdw_multi_workflow`）。
- 一次运行同时挂多个可提交表单（产品上同一时刻只暴露当前 interrupt 对应的表单；双 pending 时按队列或合并交互设计，见第 5 节）。
- 进程无 Checkpointer 的「假续跑」：本设计人机续跑依赖 **同 `session_id` + Checkpointer + `InteractiveInput`**。

## 3. 工作流拓扑

```text
                    ┌─► arch ──────┐
start ─► (fan-out) ─┤              ├─► merge(wait_for_all) ─► approve ─┬─► style ─► focus ─► write ─► end
                    └─► capability ─┘                                 │
                                                                     └─► rejected_end
```

| 节点 | 类型 | 行为 |
| --- | --- | --- |
| `start` | Start | 透传 `query`（主题） |
| `arch` / `capability` | WorkflowComponent | 并行调研，返回结构化 finding（demo 可写死） |
| `merge` | WorkflowComponent，`wait_for_all=True` | 合并两路 finding |
| `approve` | WorkflowComponent | `session.interact`；根据回复分支 |
| `style` / `focus` | WorkflowComponent | 串行人机：风格、关注点 |
| `write` | WorkflowComponent | 组装 `{title, body}` |
| `rejected_end` / `end` | End | 驳回结果或报告结果 |

构图要点：

- `start` 对 `arch`、`capability` **两条普通出边** → 同超步并行（底层 TriggerChannel）。
- `arch` / `capability` 进入 `merge` 时 **`wait_for_all=True`** → Barrier 汇合。
- 审批后用 `BranchRouter` / `add_conditional_connection`：`action == approve` 走撰写链，否则走 `rejected_end`。
- 人机节点统一 `await session.interact(...)`；外层看到 `INPUT_REQUIRED` / stream 中的 `INTERACTION` chunk。

示意（落地时写进 `backend/workflows.py`）：

```python
flow = Workflow(card=WorkflowCard(id="research_report", name="报告进度树"))
flow.set_start_comp("start", EchoStart(), inputs_schema={"query": "${query}"})
flow.add_workflow_comp("arch", ArchNode(), inputs_schema={"query": "${start.query}"})
flow.add_workflow_comp("capability", CapabilityNode(), inputs_schema={"query": "${start.query}"})
flow.add_workflow_comp(
    "merge",
    MergeFindings(),
    wait_for_all=True,
    inputs_schema={"arch": "${arch}", "capability": "${capability}"},
)
flow.add_workflow_comp("approve", ApproveNode(), inputs_schema={"findings": "${merge}"})
# style → focus → write → end；驳回支路 → rejected_end
flow.add_connection("start", "arch")
flow.add_connection("start", "capability")
flow.add_connection("arch", "merge")
flow.add_connection("capability", "merge")
flow.add_connection("merge", "approve")
# approve 条件边：approve → style；否则 → rejected_end
```

## 4. 架构：一条 SSE，两条逻辑通道

```text
浏览器
  POST /api/ask              → session_id / run_id，启动 Workflow.stream / invoke
  GET  /api/events/{id}      → SSE：progress | a2ui | done
  POST /api/reply            → InteractiveInput 续跑同 session_id
       │
FastAPI
  EventBridge                # 递增 id；Last-Event-ID 补发
  Workflow Runner            # Runner.run_workflow 或 flow.stream
  Progress Projector         # WorkflowEvents / 组件生命周期 → 扁平进度节点
  A2UI Bridge                # INTERACTION 载荷 → 表单；续跑成功后 deleteSurface
  Checkpointer                # InMemory 或 Persistence；保留中断时的图状态
       │
Workflow(research_report)    # 上节静态图
```

| 通道 | 事件 | 职责 |
| --- | --- | --- |
| 进度 | `progress` | 只读树增量：节点创建 / 状态覆盖 / detail |
| 表单 | `a2ui` | 创建 surface；该人机节点续跑完成后 `deleteSurface` |
| 结束 | `done` | `{ok, result}` 或 `{ok:false, error}` |

进度与表单不要挤在同一套「节点状态机」里：进度可覆盖；表单有创建和销毁；回复走独立 HTTP，服务端转成 `InteractiveInput` 再 `run_workflow(..., inputs=interactive, session=...)`。

与 `wsdw_multi_workflow` 的差异：那边是 Controller 选流 + 单节点追问；本设计是**单张多节点图**直接投影成进度树，并显式演示并行汇合。

## 5. 进度树怎么长

前端按 `parentId` 组树。投影建议绑定 Workflow 可观察事件（具体事件名以落地时 `WorkflowEvents` / tracer / stream chunk 为准）：

| 来源 | 树上表现 |
| --- | --- |
| 工作流开始 | 根 `workflow`，`running` |
| 组件开始执行 | 对应 `nodeId`（组件 id），`running`；父节点可为虚拟 phase 或根 |
| 并行 `arch` / `capability` 同时 active | 同层两个 `running` |
| `session.interact` 写出 `INTERACTION` | 该节点 `waiting_for_human`，并另发 `a2ui` |
| 组件正常结束 | 同节点 `completed`，可带 detail |
| 组件 / 工作流失败 | `failed` |
| 工作流完成 | 根 `completed`，`done.ok=true` |

虚拟 phase（可选）：投影器在进入 `arch|capability` 时挂 `phase:调研`，进入 `approve` 时挂 `phase:审批`，进入 `style` 时挂 `phase:撰写`。这是 UI 分组，不是 SwarmFlow 的 `phase()` API。

## 6. 人机闸门与并行语义（Workflow / Pregel）

同超步并行时，`GraphInterrupt` 与普通 `Exception` 行为不同（详见断点续传 spec）：

| 情况 | 期望产品行为 | Workflow / Pregel 要点 |
| --- | --- | --- |
| 调研两路自动跑，审批再问人 | 两路完成后 merge，再出现审批表单 | 并行在调研超步；HITL 在后续超步，本 demo 主路径 |
| 若并行支路内一路 HITL | 树上一路等待；兄弟默认**继续跑完**，不 cancel | `GraphInterrupt` 在 NodeTask 里转成返回值，不触发 FIRST_EXCEPTION 提前结束 |
| 两路同时 HITL | 两个 pending；续跑可能两次交互 | `pending_node` 可记两个；顶层 `__interrupt__` 可能只冒泡第一个 |
| 一路硬失败 | 展示失败；未完成兄弟可能被 cancel 并进 pending | 普通异常 → cancel 兄弟；恢复时 pending 一并重入 |
| 驳回即结束 | 条件边走 `rejected_end`，撰写节点不出现 | 业务分支，不是引擎自动剪枝 |

实务约束：

1. 并行支路避免不可幂等外部写；需要跳过重入时用业务状态守卫（引擎至少一次重入）。
2. 需要「问人时立刻停掉兄弟」时，改串行或显式取消，不要假设 HITL 会 cancel。
3. 双中断时交互层要对齐全部 `pending_node`，不要只做一张总问卷。
4. 中断是合法未完成态：Checkpointer `post_workflow_execute` 遇 `__interrupt__` **保存**图状态；正常结束才清理。

## 7. HTTP 与续跑契约（落地时）

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| POST | `/api/ask` | 体为 `question`；创建 `session_id`，启动工作流；返回 id |
| GET | `/api/events/{id}` | SSE；支持 `Last-Event-ID` |
| POST | `/api/reply` | 体含答复；构造 `InteractiveInput`，同 session 续跑；无等待则 409 |

首次输入普通 dict / 字符串；续跑必须是 `InteractiveInput`，并由 Checkpointer `pre_workflow_execute` 恢复业务状态。

## 8. 验收（产品视角）

1. 提交非空主题后，进度树出现并行的 `arch`、`capability`，二者完成后 `merge` 完成。
2. `approve` 变为等待输入并出现通过 / 驳回表单；未 reply 前不继续。
3. 驳回后 `done` 结果为 rejected 形态，树中不出现 `style` / `write`。
4. 通过后依次风格、关注点，`write` 完成；结果含 `title` / `body`。
5. 同 `session_id` 续跑不重跑已成功的调研支路（成功消息已在检查点侧处理）；刷新策略与 Checkpointer 实现一致（内存实现重启即失效需在 README 写明）。

## 9. 建议目录（落地时）

```text
workflow_report_tree/
  backend/
    main.py              # FastAPI：ask / events / reply
    workflows.py         # research_report 静态图
    components.py        # arch / capability / merge / approve / style / focus / write
    projector.py         # Workflow 事件 → progress
    a2ui_bridge.py       # INTERACTION → A2UI
    event_bridge.py
    setup.py             # Checkpointer
  frontend/              # 进度树 + A2UI（可参考 swarmflow_a2ui / wsdw 前端，但后端是 Workflow）
  doc/                   # 知乎文
  README.md
```

## 10. 和相邻 demo / spec 的边界

| demo / spec | 解决什么 | 和本设计的关系 |
| --- | --- | --- |
| 本 spec / `workflow_report_tree`（待落地） | Workflow 报告进度树 + SSE + A2UI | 本文 |
| `pregel_checkpoint` | CLI：并行汇合、HITL、异常重入与幂等 | 构图与中断语义的课表，无 Web 进度树 |
| `wsdw_multi_workflow` | Controller 挂多条短工作流 + A2UI 追问 | 交互可参考；拓扑不是并行调研树 |
| `swarmflow_a2ui` / `调研报告进度树-SwarmFlow与A2UI` | SwarmFlow 脚本进度树 | **对照样例，本设计不采用其引擎** |
| `方案分叉验收-fork与verify` | SwarmFlow fork / verify | 不在本范围 |
