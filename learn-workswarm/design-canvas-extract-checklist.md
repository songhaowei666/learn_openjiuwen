# Design 画布能力摘出：知识点清单

目标：把 Design 画布 + Agent 操控这套能力，从 JiuwenSwarm 里摘成相对独立的产品/模块。按序补齐即可。

---

## 0. 先定边界（半天想清楚）

决定要摘的是哪一层，后面清单深度差很多：

| 摘法 | 带走什么 | 难度 |
|---|---|---|
| A. 只摘画布 UI + 图存取 | 前端画布 + graph schema + 读写 RPC | 低 |
| B. 画布 + 自动建图 + 跑图 | A + Director 链 + RunCoordinator + handlers | 中 |
| C. 完整「对话操控画布」 | B + Leader 工具/rails + team.design 装配 | 高 |
| D. 含媒体生成闭环 | C + 图/视频模型 + 锁体系 + 参考图 | 很高 |

建议：先按 **B → C** 学，D 单独当第二阶段。

---

## 1. 领域模型（必补，地基）

1. **执行图契约 `designer-execution-graph.v1`**
   - `type`（模态：text/table/image/video/audio）vs `config.pipeline`（brief/character/scene/...）
   - 节点 / 边 / layout / metadata
   - 入口：`jiuwenswarm/common/schema/designer_graph.py`
   - 前端镜像：`jiuwenswarm/channels/web/frontend/src/features/designer/executionGraphTypes.ts`

2. **运行态契约 `designer-execution-run.v1`**
   - `node_states`、产出 `output_ref`、history、trigger source

3. **一项目一会话一画布**
   - `work_mode=design` 不进 work/code 的 mode_matrix
   - 无虚拟默认项目；真实 Design project 绑定
   - 入口：`gateway/common/work_mode.py`

4. **用户手改事实：`user_canvas_edits`**
   - op：`add` / `remove` / `connect` / `disconnect` / `replace`
   - Agent 必须当事实，不能「帮用户恢复」

---

## 2. 存储与权威源

5. **GraphStore 文件布局**
   - `graphs/{graph_id}.json`、run 落盘
   - `DesignerGraphStore` / `reload_graph_inplace`
   - 入口：`jiuwenswarm/server/runtime/designer/graph_store.py`

6. **谁是权威**
   - 服务端 store 为准；前端是投影
   - Agent patch / 用户拖拽 / 跑图 都写回同一份 graph

7. **产物目录与 URI**
   - 节点产出文件怎么落盘、如何变成可预览 URI

---

## 3. 前后端协议（摘出时的「对外 API」）

8. **Designer RPC 面**（`designer_adapter`）
   - `designer.workspace.*`
   - `designer.graph.get/list/save/patch`
   - `designer.run.start/get/pause/cancel`
   - `designer.media.capabilities`
   - 入口：`jiuwenswarm/server/runtime/gateway_adapter/designer_adapter.py`

9. **实时推送事件**
   - `designer.graph.updated`
   - `designer.run.updated` / `designer.node.updated`
   - `designer.leader.activity`

10. **会话绑定**
    - session ↔ project ↔ graph_id
    - `DesignTeamBridge.bind_round` 把本轮绑到图上
    - 入口：`jiuwenswarm/server/runtime/design/team_bridge.py`

---

## 4. 前端画布（若要独立 UI）

11. **React Flow（`@xyflow/react`）基础**
    - 自定义节点、Handle、边、viewport

12. **双图适配**
    - Domain graph ↔ ReactFlow graph（`designerGraphAdapter`）
    - layout 持久化回 domain

13. **Zustand 状态机**
    - `designerStore` / `designerRunStore` / chat store
    - 本地编辑乐观更新 vs 服务端事件覆盖

14. **用户编辑记账**
    - `appendUserCanvasEdit` 何时写、如何随 save 上传
    - 入口：`features/designer/designerCanvasNodes.ts`

15. **运行控制 UI**
    - 全量跑 / 单节点 / cascade 与后端语义对齐

前端根目录：`jiuwenswarm/channels/web/frontend/src/features/designer/`

---

## 5. Agent 操控面（C 方案核心）

16. **Leader 三工具分工**
    - `designer_graph_autorun`：整图建图
    - `designer_graph_patch` / `designer_story_edit`：小改 / 故事事实
    - `swarmflow`：触发执行（异步 accept-and-trigger）

17. **感知路径**
    - `designer_graph_get` 读 store
    - 节点上下文包注入（含上游产出 + edits）
    - `read_upstream` / `read_node_context`

18. **Rail 架构**
    - `DesignerAuthoringRail` / `DesignerExecutionRail` / `DesignerSurfaceSanitizerRail`
    - keep-list 裁剪工具表面（为何不能直接复用普通 team）
    - 入口：`jiuwenswarm/agents/harness/design/rails/`

19. **Prompt 硬规则**
    - `_DESIGN_LEADER_SYSTEM_PROMPT`（`agents/swarm/assembly.py`）
    - report-only 轮次：`report_pending` 防跑完立刻再改

20. **AgentGroup 包**
    - `jiuwenswarm/resources/agent/workspace/plugins/agent_groups/designer/`
    - leader + brief/character/scene/storyboard/clip/compose 成员清单与 persona

---

## 6. 建图流水线（Director）

21. **`run_director_chain` 阶段**
    - 分析 → brief → 审核 → 分镜 → 审核 → 执行图 → 校验
    - 入口：`jiuwenswarm/server/runtime/design/director_chain.py`

22. **导演契约 / Plan A**
    - `pipeline/director_contract.py`、脚本分析 `script_analysis.py`

23. **Reference-led 建图**
    - 用户上传参考图如何进角色/场景绑定
    - 入口：`pipeline/reference_led.py`

24. **技能与风格包**
    - `jiuwenswarm/server/runtime/designer/skills/`（scenario/agent/style）

---

## 7. 执行引擎（跑画布）

25. **RunCoordinator / StoreNodeSpawner**
    - 单图锁、防重入、conversation round vs trigger 边界
    - 入口：`jiuwenswarm/server/runtime/design/context.py`、`run_coordinator.py`

26. **拓扑执行语义**
    - 未产出节点、单节点覆盖、cascade 下游闭包
    - 上游失败 / 跳过策略

27. **Node Handler 体系**
    - `handlers/`：text / image / video / audio / compose / clip
    - 与 AgentGroup 成员工具的对应关系

28. **节点 Worker 契约**
    - `shot_ticket: design:{graph}:{run}:{node}`
    - `read → generate → submit` 三步工具模式
    - 入口：`resources/.../designer/tools/node_tools.py`

---

## 8. 媒体与一致性（D 方案，可后补）

29. **图/视频模型调用封装**
    - `call_image_model` / `call_video_model` / 超时与失败语义

30. **锁体系（这是复杂度大头）**
    - character / cast-prop / clothing / axis / continuity / clip staging
    - 为什么 patch 故事事实要走 `designer_story_edit` 而不是只改 prompt

31. **音频与合成**
    - `ffmpeg_compose` / `mix_audio` / speech-tts

32. **模型能力探测**
    - `designer.media.capabilities`、分辨率/时长限制

---

## 9. 平台耦合（摘出时要「切断或替换」）

33. **`team.design` 模式装配**
    - `mode_matrix` 的 `NEW_TEAM_DESIGN`
    - swarm assembly / capability providers

34. **Gateway ↔ AgentServer 事件通道**
    - 普通 chat.send 与 designer.* 并存时怎么路由

35. **Project / Session / work_mode**
    - design 与 work/code 分桶；cron 禁用等约束

36. **openjiuwen agent_teams / DeepAgentRail**
    - 工具卡、PromptSection、AbilityManager
    - 若独立产品，要决定是否仍依赖这套 harness

---

## 10. 建议学习顺序（按周）

| 周 | 补什么 | 验收标准 |
|---|---|---|
| 1 | §1 + §2 + §3 | 能手动画一张 graph JSON，RPC 读写、前端渲染 |
| 2 | §4 | 拖拽改图 → 落库 → 刷新不丢；edits 有日志 |
| 3 | §7（先无 Agent） | 点运行按钮能按拓扑跑通 text 节点 |
| 4 | §6 | 给一句创意需求，能生成带 brief/分镜的图 |
| 5 | §5 | 对话里 autorun / patch / swarmflow 闭环 |
| 6+ | §8 + §9 | 图视频生成 + 从宿主剥离依赖 |

---

## 11. 精读文件入口（少而硬）

1. `gateway/common/work_mode.py` — design 与执行模式正交
2. `jiuwenswarm/common/schema/designer_graph.py` — 契约
3. `jiuwenswarm/server/runtime/gateway_adapter/designer_adapter.py` — 对外 RPC
4. `jiuwenswarm/server/runtime/design/team_bridge.py` — 绑定 + 推送
5. `jiuwenswarm/agents/harness/design/rails/designer_authoring_rail.py` — 建图工具
6. `jiuwenswarm/agents/harness/design/rails/designer_execution_rail.py` — 跑图工具
7. `jiuwenswarm/agents/swarm/providers/designer_tools.py` — get/patch 表面
8. `jiuwenswarm/server/runtime/design/director_chain.py` — 建图链入口
9. `jiuwenswarm/server/runtime/designer/node_agent.py` — 工具实现 + 节点上下文
10. `jiuwenswarm/channels/web/frontend/src/features/designer/components/DesignerCanvas.tsx` — 画布

---

## 12. 你真正要「会」的能力（非文件）

- 图编辑的 CRDT 不是重点；重点是 **单权威 store + 事件投影**
- Agent 不是「操作 UI」，是 **操作领域图的工具面**
- **对话轮次**与**执行触发**必须拆开（否则 RPC 被媒体生成卡死）
- 叙事角色 ≠ 节点 type；拆不清后面全是 patch 幻觉
- 一致性锁是产品护城河，也是最难独立维护的部分——可先不做 D

---

## 附录：Agent 感知与操控速记

### 角色分层

| 角色 | 职责 |
|---|---|
| Leader（主编） | 跟用户对话；建图、小改、触发跑图 |
| Node Worker | 每个画布节点跑一次；生成该节点产物 |

### 感知

- `designer_graph_get` → 读 store 权威图
- `user_canvas_edits` → 用户手改日志当事实
- 节点上下文包 / `read_upstream` → 上游产出与锁

### 操控

```text
全新需求  → designer_graph_autorun → save → push graph.updated → 通常 swarmflow
小改拓扑  → designer_graph_patch   → save → push graph.updated
故事事实  → designer_story_edit    → 再 patch prompt → cascade 重跑
跑图      → swarmflow() / (node_id) / (node_id, cascade=true)
```

### 推回画布的事件

- `designer.graph.updated`
- `designer.leader.activity`
- `designer.run.updated` / `designer.node.updated`
