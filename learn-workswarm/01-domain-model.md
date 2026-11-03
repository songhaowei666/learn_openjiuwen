# §1 领域模型学习笔记

对应清单：`design-canvas-extract-checklist.md` §1。  
验收：能不靠 UI 手写一张合法 graph JSON，并说清 graph / run / 项目绑定 / 用户手改四件事。

精读入口（够地基，不必啃完后半 layout 修复）：

- `jiuwenswarm/common/schema/designer_graph.py`（约前 500 行 + TypedDict）
- `jiuwenswarm/channels/web/frontend/src/features/designer/executionGraphTypes.ts`
- `gateway/common/work_mode.py`
- `jiuwenswarm/channels/web/frontend/src/features/designer/designerCanvasNodes.ts`（`UserCanvasEdit`）
- 契约钉死测试：`tests/unit_tests/design/test_designer_execution_graph_contract.py`

---

## 1.1 执行图契约 `designer-execution-graph.v1`

### 核心二分：`type` vs `pipeline`

| 字段 | 含义 | 合法值 |
|---|---|---|
| `node.type` | 画布模态（用户看见的种类） | `text` / `table` / `image` / `video` / `audio` |
| `config.pipeline` | 内部生成配方（谁来跑、跑什么） | `brief` / `character` / `scene` / `storyboard` / `clip` / `compose` / `music` / `speech` |
| `config.role` | 与模态同字符串（MiniMax 风格），**不是** pipeline | 同 `type` |

常见对照（`PIPELINE_TO_TYPE`）：

| pipeline | 默认 type |
|---|---|
| brief | text |
| character / scene | image |
| storyboard | table |
| clip / compose | video |
| music / speech | audio |

要点：

- 叙事角色（Character / Scene / Clip）写在 **pipeline / 文件名 / Plan**，不写进 `node.type`。
- 画布标题倾向模态名（Image / Video / …）；带语义后缀的 label（如 `Character 1: Alice`）应保留。
- 旧图可用 `n_character_*` 等 id 推断 pipeline（`infer_pipeline_from_id`）。
- 无 pipeline 的纯 text 节点，compiler 会拒绝（没有可委派成员）。

### 顶层结构

```text
DesignerExecutionGraph
  schema_version   = "designer-execution-graph.v1"
  graph_id         如 graph_<16hex>
  project_id       真实 Design 项目，不能虚空默认
  title / description?
  source?          "prompt" | "manual"
  nodes[] / edges[]
  metadata?        含 user_canvas_edits、媒体设置等
  created_at / updated_at?   ms
```

### 节点 / 边 / layout

**节点 `DesignerGraphNode`**

| 字段 | 说明 |
|---|---|
| `id` | 稳定节点 id |
| `type` | 模态 |
| `label` | 画布标题 |
| `config` | pipeline / prompt / generate / upload / edit / materials / … |
| `layout` | `{x,y,width?,height?}`，前端拖拽后写回 domain |
| `output_ref?` | 图上可挂一份产物引用；跑图真相仍以 run 的 node_states 为准 |

**常用 config 键**：`role` `pipeline` `prompt` `inputs` `delegate` `agent_template` `collaborate` `generate` `upload` `edit` `interaction_mode` `materials`

**边 `DesignerGraphEdge`**：`id` / `source` / `target` / `kind`（目前几乎只有 `data`）/ `label?`

**默认 agent 模板**（pipeline → AgentGroup 成员名，裸名、不要 `group/member`）：

| pipeline | template |
|---|---|
| brief | brief |
| character | character |
| scene | scene |
| storyboard | storyboard |
| clip | clip |
| compose | compose |

### 最小合法样例（brief → character）

```json
{
  "schema_version": "designer-execution-graph.v1",
  "graph_id": "graph_deadbeefcafebabe",
  "project_id": "proj_demo",
  "title": "学习样例",
  "source": "manual",
  "nodes": [
    {
      "id": "n_brief",
      "type": "text",
      "label": "Text",
      "config": {
        "pipeline": "brief",
        "prompt": "一个科幻短片：宇航员发现废弃空间站"
      },
      "layout": { "x": 0, "y": 0, "width": 240, "height": 120 }
    },
    {
      "id": "n_character_1",
      "type": "image",
      "label": "Character 1: Astronaut",
      "config": {
        "pipeline": "character",
        "prompt": "穿橙色宇航服的女宇航员，半身像"
      },
      "layout": { "x": 320, "y": 0, "width": 240, "height": 180 }
    }
  ],
  "edges": [
    {
      "id": "e_brief_character_1",
      "source": "n_brief",
      "target": "n_character_1",
      "kind": "data"
    }
  ],
  "metadata": {}
}
```

### 不变量

1. `schema_version` 必须精确等于 `designer-execution-graph.v1`。
2. `type` 只表达模态；叙事职责看 `config.pipeline`。
3. 前后端字面量由契约测试钉死，改一边必须改另一边。
4. Python 侧权威归一化入口：`normalize_execution_graph`。

---

## 1.2 运行态契约 `designer-execution-run.v1`

与 graph **分文件存储**：`graphs/{graph_id}.json` vs `runs/{run_id}.json`。

### 顶层

```text
DesignerExecutionRun
  schema_version   = "designer-execution-run.v1"
  run_id / graph_id / project_id
  status           draft|running|paused|completed|failed|cancelled
  node_states      { [node_id]: DesignerNodeState }
  current_node_ids 当前在跑的节点
  metadata?
    trigger_source?   "canvas" | "leader"
    scope_node_ids?   限定本轮驱动的节点集合
    target_node_id?   单节点生成目标
  error? / warning? / warnings?
```

### `DesignerNodeState`

| 字段 | 说明 |
|---|---|
| `status` | pending / running / completed / failed / cancelled |
| `output_ref` / `output_refs` | 产物 URI（预览看这里） |
| `error` / `blocked_by` | 失败与阻塞上游 |
| `activity` / `activity_tail` / `activity_log` | 过程展示 |
| `history` | 历史快照（有上限） |
| `version` | 内容迭代版本；单节点/级联重跑 +1，避免 WAL 缓存复用旧结果 |

### 虚拟 Leader 节点

- id：`__leader__`
- **只出现在** `run.node_states`，**从不**画到 canvas 的 `nodes[]`
- 用于 Leader 异步工具活动（thinking / tool_call / stage）

### 不变量

1. Graph 描述「要跑什么」；Run 描述「跑到哪了、产出是什么」。
2. `trigger_source=leader` 的触发与 Leader 生命周期绑定；canvas 触发独立。
3. 对话轮次 ≠ 执行触发：接受触发后应尽快返回，媒体生成在后台跑。

---

## 1.3 一项目一会话一画布

入口：`gateway/common/work_mode.py`。

| 概念 | 事实 |
|---|---|
| `work_mode` | `work` / `code` / `design` |
| 与 Agent `mode` | **正交**；design 不进 work/code 的执行 profile / mode_matrix |
| `EXECUTION_WORK_MODES` | 只有 `{work, code}` |
| 虚拟默认项目 | `default`（work）、`default_code`（code） |
| design 项目 | **无**虚拟默认；必须绑真实 Design project |

绑定链：

```text
session (work_mode=design)
  → project_id（真实项目）
    → graph_id（该会话画布）
```

摘出产品时：Design 工作区不要复用 work/code 的默认项目逻辑，也不要塞进普通 team 的 mode_matrix。

---

## 1.4 用户手改事实：`user_canvas_edits`

### 结构

挂在 `graph.metadata`：

```ts
type UserCanvasEdit = {
  op: 'add' | 'remove' | 'connect' | 'disconnect' | 'replace';
  node_id: string;
  peer_id?: string;   // 连线对端
  label?: string;
  role?: string;
  type?: string;
  at: number;         // ms
};
```

写入：`appendUserCanvasEdit`（前端 `designerCanvasNodes.ts`）

- 追加到 `metadata.user_canvas_edits`
- 同时打标 `user_topology_edit: true`
- 只保留最近约 **40** 条

### 语义与 Agent 规则

| op | 含义 |
|---|---|
| add | 用户新增节点 |
| remove | 用户删除节点 |
| connect | 用户连边（`peer_id` 为对端） |
| disconnect | 用户断边 |
| replace | 用户替换节点/内容相关手改 |

硬规则（`agents/swarm/assembly.py` Leader prompt）：

> `user_canvas_edits` 是已发生的事实——**不要**恢复被删除的节点或被断开的边。

节点 Worker 上下文也会注入同一份 edits（`node_agent.py` / `node_tools.py`），建图与执行两侧都当事实读。

### 不变量

1. 手改日志是领域事实，不是 UI 装饰。
2. Agent 可在其上继续创作，但不得「好心撤销」用户拓扑。
3. 摘出产品时：乐观本地编辑 → save 上传 → 服务端权威回推，这条链路要保留。

---

## 自测清单

- [ ] 口头区分 `type` 与 `pipeline`，并举 character / storyboard 两例
- [ ] 手写一张含 2 节点 1 边的 graph JSON（字段齐全）
- [ ] 说出 run 相对 graph 多了哪些字段，以及 `__leader__` 为何不在画布上
- [ ] 解释为何 design 不能用 `default` 项目
- [ ] 用户删了一条边后，Leader 看到 edits 应如何行为

动手项目（仓库根目录，使用 `.vscode` 的 deepstudy 解释器）：

```bash
PY=/Users/song/anaconda3/envs/deepstudy/bin/python
$PY learn-workswarm/projects/01-execution-graph/exercise.py
$PY learn-workswarm/projects/02-execution-run/exercise.py
$PY learn-workswarm/projects/03-work-mode-binding/exercise.py --cases
$PY learn-workswarm/projects/04-user-canvas-edits/exercise.py
```

说明见 [`projects/README.md`](./projects/README.md)。

下一步：`design-canvas-extract-checklist.md` §2 存储与权威源。
