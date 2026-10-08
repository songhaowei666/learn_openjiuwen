# 断点续传不必先啃 Pregel：用三课看并行汇合、人机续跑与幂等

> 建议标题：`openJiuwen | Pregel与检查点 | 断点续传不必先啃 Pregel：并行汇合、人机续跑与幂等`
>
> 本文记录我在 openJiuwen agent-core 里做的一个小 Demo：`pregel_checkpoint`。不接模型，用工作流顶层 API 跑几张静态图。重点不是「合同审查 / 扣款」这些玩具场景，而是：**并行怎么汇合**，**互斥分支误用 wait_for_all 会怎样**，**问人时检查点留什么**，以及**崩溃恢复后为什么会扣两次钱**。

## 目录

- [一、先说问题：会话式 Agent 丢了状态怎么办](#一先说问题会话式-agent-丢了状态怎么办)
- [二、整体架构](#二整体架构)
- [三、课 1：并行汇合，不必先懂超步](#三课-1并行汇合不必先懂超步)
- [四、课 4：只走一条分支时，wait_for_all 会假完成](#四课-4只走一条分支时wait_for_all-会假完成)
- [五、课 2：人机中断，检查点里能看见 pending](#五课-2人机中断检查点里能看见-pending)
- [六、课 3：至少一次重入，幂等要自己做](#六课-3至少一次重入幂等要自己做)
- [七、踩坑：节点内状态会回滚，外部副作用不会](#七踩坑节点内状态会回滚外部副作用不会)
- [八、开发者要不要懂 Pregel](#八开发者要不要懂-pregel)
- [九、这个 Demo 故意没做什么](#九这个-demo-故意没做什么)
- [十、总结](#十总结)

---

## 一、先说问题：会话式 Agent 丢了状态怎么办

做带流程的 Agent，常见两条路：

- **会话式**：连续性寄在对话上下文里。中断后果是会话丢失或失真，重跑接近全量。
- **检查点式**：状态外置到存储，每次关键流转写入。恢复从最近快照回退，重跑接近「当前卡住的那一步」。

openJiuwen 工作流走后者。对外你用的是 `Workflow`、`wait_for_all`、`session.interact`、`InteractiveInput`；对内引擎是 Pregel 风格的超步图。多数业务只需要前者；只有排障或改恢复语义时，才值得下钻后者。

本 Demo 故意做成 CLI 多课，把「产品语义」先跑出来，再在必要时对照检查点里的 `pending_nodes`。

---

## 二、整体架构

没有前端，没有模型。一条命令按序跑三张图，Checkpointer 用 shelve 落在 `workspace/`。

```
CLI (python -m backend.main)
   │
   ▼
lessons.py                 三课：并行 / 人机 / 副作用
   ├─ workflows.py         三张静态 Workflow
   ├─ components.py        自定义节点（打标签、问人、写账本）
   └─ setup.py             PersistenceCheckpointer(shelve)
          │
          ▼
   workspace/checkpointer*     图状态 + 工作流状态
   workspace/charge_*.json     课 3 外部扣款账本
```

项目结构：

```
pregel_checkpoint/
  backend/
    main.py            # CLI 入口
    lessons.py         # 三课编排与断言
    workflows.py       # 构图
    components.py      # 节点
    setup.py           # 检查点初始化、GraphState 摘要
  workspace/           # shelve 与账本
  doc/                 # 本文
  README.md            # 怎么跑
```

三课各自独立 `session_id`，互不干扰。课 2、课 3 会在中断或异常后读一次 `graph_store().get(session_id, workflow_id)`，把 `pending_nodes`、`step`、`node_version` 打印出来，方便把「产品现象」和「图状态」对上号。

---

## 三、课 1：并行汇合，不必先懂超步

图很简单：

```
start ──► left  ──► merge(wait_for_all) ──► end
      └─► right ─┘
```

`start` 往左右各连一条边，左右是两个打标签的节点，`merge` 声明 `wait_for_all=True`。跑起来你会看到 left / right 都能执行，merge 要等两边都到齐才输出 `left:... | right:...`。

构图时关键只有两处：

```python
flow.add_workflow_comp(
    "merge",
    MergeNode(),
    wait_for_all=True,
    inputs_schema={
        "left_text": "${left.text}",
        "right_text": "${right.text}",
    },
)
flow.add_connection("start", "left")
flow.add_connection("start", "right")
flow.add_connection("left", "merge")
flow.add_connection("right", "merge")
```

业务开发到这里可以停住：多出边就是并行，汇合点加 `wait_for_all`。下一节专门演示「只走一条分支却仍按 AND 等两侧」会怎样。

正常跑完后，图检查点会被清掉。课 1 末尾打印的 `graph_state.exists == False`，就是在验证「完成走清理，不是错误」。

---

## 四、课 4：只走一条分支时，wait_for_all 会假完成

课 1 是「两侧都会跑」。若业务其实是**互斥分支**（只走 left 或只走 right），却仍给 merge 挂上 `wait_for_all=True`，并静默地要求 left AND right，就会踩坑。

### 错误构图

```
start ──► left ──► merge(wait_for_all) ──► end
          right ─┘   （right 从未从 start 连出，永远不会激活）
```

跑起来日志只有 `start`、`left`，**没有** `merge` / `end`。更隐蔽的是：状态仍是 `COMPLETED`，`result` 却是 `None`。

原因在 Pregel 超步循环：没有就绪节点且消息缓冲为空时，引擎认为图跑完了。Barrier 只收到 left，还在等 right，merge 一直不就绪——于是整张图「空转结束」，而不是一直挂起等超时。

### 正确构图

互斥出口用 `BranchRouter` 做条件边。`add_conditional_connection` 会把多个目标登记为互斥集合，编译期把 merge 的屏障收成 OR 组：`(left | right) -> merge`。

```
start ─条件─► left | right ──► merge(wait_for_all) ──► end
```

只传 `path=left` 时，merge 能跑，结果类似 `merged: left:合同审查`，`right_text` 为 `None`。

CLI：`python -m backend.main barrier`（详见 README）。这是少数「业务 API 用错了，要对一下 Barrier / CNF」的场景。

---

## 五、课 2：人机中断，检查点里能看见 pending

图：

```
start ──► ask ──► end
```

`ask` 里不接提问器组件，直接调会话 API：

```python
answer = await session.interact(f"请确认或修改草稿（当前：{draft}）")
```

第一次 `invoke` 返回：

- `state == INPUT_REQUIRED`
- `result` 里带 `__interaction__`，`payload.id` 是组件 id（这里是 `ask`）

此时去读检查点，典型摘要是：

```text
pending_nodes: ['ask']
step: 2
node_version: {'__start__': 1, 'start': 1, 'ask': 1}
exists: True
```

含义用产品语言说：**流程停在 ask，引擎记得下次要先重入这个节点**；用 Pregel 语言说：`pending_node` 里挂着待恢复节点，恢复时优先调度它们。

续跑必须两件事同时满足：

1. **同一个 `session_id`**，否则是新会话，检查点对不上；
2. 输入改成 `InteractiveInput`，并按中断返回的 `payload.id` 写入回复：

```python
user_input = InteractiveInput()
user_input.update(payload.id, {"text": reply})
await flow.invoke(user_input, create_workflow_session(session_id=session_id))
```

续跑完成后检查点再次被清理。中断保存、正常结束清理——这是 Checkpointer 生命周期里最值得记住的一对相反路径。日常编排用提问器组件也是同一条路，只是提问器内部帮你调了 `interact`。

---

## 六、课 3：至少一次重入，幂等要自己做

图：

```
start ──► charge ──► end
```

`charge` 先往 `workspace/charge_<session_id>.json` 写一笔「扣款」，再故意抛错，模拟「支付 API 已成功、进程随后挂掉」。

第一次失败后，检查点里能看到：

```text
pending_nodes: ['charge']
```

用空的 `InteractiveInput()` 触发恢复（异常恢复也走交互输入这条入口，与单元测试一致）。引擎会**再次进入 charge**：

| 模式 | 恢复后外部账本 count | 结果 |
| --- | --- | --- |
| 无幂等守卫 | 2 | 真实世界里等于扣了两次 |
| 有幂等守卫 | 1，且 `skipped: true` | 重入时读到 `done`，跳过真实扣款 |

守卫逻辑很朴素：

```python
if self._idempotent and done:
    return {"charged": True, "count": count, "skipped": True}

# 先写外部账本，再决定是否「崩溃」
path.write_text(...)
if not crashed:
    raise RuntimeError("模拟扣款后进程崩溃...")
```

框架保证的是「状态可恢复」和「失败节点会再跑」；**不保证外部副作用恰好一次**。幂等是业务责任。

---

## 七、踩坑：节点内状态会回滚，外部副作用不会

课 3 最初想用 `session.update_global_state` 记扣款次数。结果是：同一次 `invoke` 里先改状态再抛错，恢复后次数像没改过一样。

原因在超步边界：成功的超步结束会 `commit`；节点在执行中失败时，本超步未提交的 session 更新可能被丢掉。而真实的支付、写文件、发消息，**不会**跟着 Pregel 一起回滚。

所以 Demo 改成外部 JSON 账本：

- 用来证明「至少一次」有多危险；
- 也用来证明「幂等标记」应该落在不会随失败超步蒸发的地方（外部存储、或成功提交后的业务状态）。

这是本 Demo 里最值得带走的坑。

---

## 八、开发者要不要懂 Pregel

对照本 Demo 的用法：

| 你在做什么 | 要不要啃 Pregel |
| --- | --- |
| 编排并行 / 汇合 / 条件边 | 通常否；互斥分支误用 AND 汇合时见课 4 |
| 开 Checkpointer、人机续跑 | 否，顶层 API 即可 |
| 给副作用做幂等 | 否，只需接受「会重入」这一结论 |
| 排障：汇合不触发、续传后分支没了、循环计数错乱 | 要，看 barrier / pending / channel |
| 自研恢复策略、直接读写 `GraphState` | 要 |

一句话：**多数业务开发者不必先懂 Pregel；要把断点续传用稳，至少要懂「会重入」和「外部副作用要幂等」。**

更深的源码地图（`PregelLoop`、Channel、命名空间拆分）写在同目录的 spec：`spec/断点续传与Pregel图模型.md`。

---

## 九、这个 Demo 故意没做什么

- 不接大模型，不问真实合同；
- 不做前端进度树；人机回复在自动模式下写死，也可 `--interactive` 手输；
- 不改引擎，不做运行时动态加节点；条款数量不定一类需求，应走循环 + 分支，或组件内子工作流；
- 不实现自定义 `BaseKVStore`；只演示内置 persistence + shelve；
- 不把 `GraphInterrupt` 暴露给业务代码；课 2 停在 `interact` / `InteractiveInput`。

---

## 十、总结

openJiuwen 把检查点式工作流的能力摊在顶层 API 上：并行用多出边，汇合用 `wait_for_all`，问人用 `interact`，续跑用同一 `session_id` 的 `InteractiveInput`。Checkpointer 在中断和异常时保存，在正常结束时清理。

真正要自己补上的，通常不是 Pregel 论文，而是两件事：

1. 认清恢复语义是**至少一次**，失败 / 中断节点会重入；
2. 把外部副作用设计成幂等，并且不要假设「节点里刚写入的 session 状态」在抛错后一定还在。

跑通三课之后，若线上出现「汇合永远等不到」或「续传行为对不上文档」，再带着 `pending_nodes` 和 barrier 去读引擎源码，会比一上来啃超步模型高效得多。
