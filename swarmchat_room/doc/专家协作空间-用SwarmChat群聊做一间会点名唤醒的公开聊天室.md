# 专家协作空间：用 SwarmChat 群聊做一间会点名唤醒的公开聊天室

> 建议标题：`openJiuwen | SwarmChat | 专家协作空间：公开归档、按需唤醒、专家当众回复`
>
> 本文记录我在 openJiuwen agent-core 里做的一个小 Demo：`swarmchat_room`。页面是一间公开聊天室：人说的话全部进历史；只有勾选的专家会被叫醒，根据群聊摘录用真实模型当众回复。重点不是「预算 10 万两周上线」这个玩具场景，而是三件事：**公开消息怎么归档**，**点名如何决定谁开口**，以及**后开口的专家如何看见先开口专家的公开回复**。

---

## 一、先说问题：多人专家协作难在哪

做过「一群专家围着一个需求讨论」的同学，大概都撞过这几堵墙：

- 约束要先说完。预算、工期、范围往往是人先摆到桌上，这时还不该叫醒任何模型；
- 需要研究意见时，只该叫醒研究；需要法务意见时，只该叫醒法务；
- 法务开口时，必须看得到研究已经说过的公开结论，否则两个人各说各话；
- 研究不该因为法务发了一句公开回复，就被再次叫醒。

如果把整段群史塞进每个专家的上下文，成本和噪声都会涨。如果专家回复再去 @ 别人，房间里会出现互相叫醒的连环炮。

openJiuwen 的 SwarmChat 给的解法很克制：**公开房间里每句话都归档；唤醒是另一条闸门，只看 `mentions`。** 本 Demo 不拉起完整的 `TeamAgent`，只走到群聊这一层：`TeamBackend` 负责归档和发言身份，摘录交给模型，回复再写回同一间房。

---

## 二、整体架构

传输很简单：一条 HTTP 归档，页面再拉历史。没有 SSE，也没有 A2UI。

```
浏览器 (React)
   │  GET  /api/roster      勾选框名册
   │  GET  /api/history     history.jsonl 解析结果
   │  POST /api/messages    {body, mentions, client_message_id}
   ▼
FastAPI
   └─ Room
         ├─ TeamBackend.append_group_message   用户发言归档
         ├─ context_for                        给被点名专家做摘录
         ├─ SharedModel                        根目录 .env 里的真实模型
         └─ GroupSendMessageTool               专家公开回复（mentions=[]）
                │
                ▼
         内存库广播行 + workspace/.../history.jsonl
```

项目结构：

```
swarmchat_room/
  backend/
    main.py                 # /api/health、/roster、/history、/messages
    room.py                 # 建房、归档、摘录、模型回复、专家发言
  frontend/
    src/App.tsx             # 消息列表、勾选、播放脚本、摘录旁注
  workspace/                # 群聊历史投影目录（gitignore）
  doc/                      # 本文
```

一次点击在界面上是这样的：

1. 输入「预算 10 万，两周上线。」，两个专家都不勾选。消息进历史，没有专家气泡，旁边也没有摘录；
2. 勾选研究，发送「请评估技术可行性」。研究拿到摘录，用模型公开回复；
3. 只勾选法务，发送「请看法务风险」。法务摘录里能看到研究那句公开回复；研究保持沉默；
4. 点名不存在的人，接口返回 400，历史不增加；
5. 用同一个 `client_message_id` 重发同一句话，返回 `duplicate=true`，研究不会再出现第二条回复。

---

## 三、SwarmChat 在建模什么

读源码时，最值得抓住的是这四个概念：

| 概念 | 含义 |
| --- | --- |
| 公开广播 | 消息进团队会话的广播表，并投影到 `history.jsonl` |
| `mentions` | 显式成员名列表。为空只归档；非空才生成 `notified_members` |
| `context_for` | 按该成员广播水位到触发消息，取最近几条摘录，并附上历史文件路径 |
| `GroupSendMessageTool` | 作者绑定当前 `backend.member_name`，不接受调用方伪造 `sender` |

整条链路可以记成一句话：

**用户发言 → 归档并投影 → 按 mentions 叫醒 → 摘录进模型 → 专家公开回复（不再点名他人）**

注意：本 Demo 故意不跑完整的 `GroupMessageHandler`，因此不推进 `read_at`。两位专家第一次被 @ 时水位都是 0，摘录窗口是 `(0, 触发时间]` 内最新几条，并带上本次触发消息。正因为不推进水位，法务第二次开口前仍能从 0 扫到研究已经公开的那句回复；又因为法务那条消息的 `mentions` 只有 `legal`，研究不会再次开口。

---

## 四、建房：一间进程内的房间

进程启动时只建一次房。数据库用内存 SQLite，事件总线用 `InProcessMessager()`，没有订阅消费者；广播发布失败只记日志，不回滚已写入的消息。

名册很短：主持人 `leader`，研究 `research`，法务 `legal`。页面勾选框只暴露后两位。`TeamBackend` 默认身份是主持人：

```python
self.backend = TeamBackend("room", "leader", True, self.db, self.messager)
```

群聊历史不写到 `~/.openjiuwen`，而是落到 demo 自己的目录。做法是给 `TeamAgentSpec` 配本地 workspace，并在绑会话前清掉旧登记，避免仍指向上一次的默认路径：

```python
WORKSPACE_DIR = Path(__file__).resolve().parents[1] / "workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
await asyncio.to_thread(GroupConversationLog.delete_registered, "room", "discussion-1")

self.backend.group_chat_spec = TeamAgentSpec(
    agents={"leader": DeepAgentSpec()},
    team_name="room",
    leader=LeaderSpec(member_name="leader"),
    workspace=TeamWorkspaceConfig(
        enabled=True,
        root_path=str(WORKSPACE_DIR),
        version_control=False,
    ),
)
self.backend.bind_group_session("discussion-1")
```

页底显示的 `context_path`，就是这份 `history.jsonl` 的绝对路径。

---

## 五、归档与唤醒：同一条入口，两道闸门

用户发送走 `POST /api/messages`。整段处理包在 `set_session_id("discussion-1")` 里。`post_message` 内部还会再 set/reset 一次，外层令牌负责在退出后把会话恢复回来，这样后面的 `get_message` 和 `context_for` 仍打在同一张动态表上。

第一步永远是归档：

```python
result = await self.backend.append_group_message(
    "user",
    body,
    client_message_id=client_message_id,
    mentions=mentions,
    attachments=(),
)
```

这里有两道闸门：

1. **成员校验**。`mentions` 里出现未知名字，`post_message` 抛 `ValueError`，整次请求不落库，接口返回 `invalid_group_chat`；
2. **幂等**。相同 `client_message_id` 配上相同正文和 mentions，返回 `duplicate=true`，Demo 直接结束，不再叫模型、不再二次回复。

`mentions` 为空时，`notified_members` 为空。消息进了历史，房间里没有人被叫醒。这就是「先把约束说完」那一步。

---

## 六、摘录、模型、公开发言

被点名的专家不会拿到整份 `history.jsonl` 文本，而是拿到 `context_for` 渲染好的一段中文通知：时间范围、触发消息 id、历史文件路径，以及最近几条 JSON 摘录。Demo 把这段摘录直接喂给模型：

```python
trigger = await self.backend.db.message.get_message(result.message.message_id)
excerpt = await context_for(self.backend, member_name, trigger)
content = await self._reply_text(member_name, excerpt)
```

`context_for` 要读数据库行上的 `meta`，所以这里必须传消息表行，不能传已经投影过的 `ConversationMessage`。

模型配置复用示例根目录的 `common.SharedModel`，从 `.env` 读 `API_BASE`、`API_KEY`、`MODEL_NAME`、`MODEL_PROVIDER`。研究和法务各有一句系统提示，约束角色和篇幅；用户消息就是摘录原文。

发言时临时切换身份。`GroupSendMessageTool` 不接受调用方指定 `sender`，作者就是当时的 `backend.member_name`：

```python
self.backend.member_name = member_name
try:
    output = await GroupSendMessageTool(self.backend, make_translator("cn")).invoke({
        "content": content,
        "client_message_id": f"reply-{client_message_id}-{member_name}",
    })
finally:
    self.backend.member_name = "leader"
```

专家回复的 `mentions` 固定为空。这句话会进公开历史，供后来的人看见，但不会把刚发过言的专家再叫醒。一次请求勾选多人时，按 `notified_members` 顺序逐个摘录、逐个回复。

---

## 七、前端只要把三件事画清楚

前端是精简 React，端口 `5175`，`/api` 代理到 `8002`。进入页面先拉名册和历史。

页面上刻意突出三件事：

1. **只归档**：不勾选专家时，只有用户气泡；
2. **点名唤醒**：勾选谁，谁出现模型回复；用户消息旁边贴上本次 `excerpts`；
3. **后到的人看得见**：法务那次摘录里含有研究的公开回复；研究没有第二条气泡。

「播放脚本」和手工输入走同一个接口。脚本用固定的 `client_message_id`，用来演示未知成员失败和重复发送。摘录面板挂在当次响应上，刷新后历史气泡还在，摘录旁注会消失——它是调试视图，不是第二份持久存储。真正的持久投影是页底那条 `history.jsonl`。

---

## 八、这个 Demo 故意没做什么

它能把 SwarmChat 的主路径跑通，但有几处边界写在这里，避免把示例当成完整团队运行时。

**1. 没有拉起 TeamAgent**

没有 Leader 模型调度，没有任务看板，没有成员进程拉起。`TeamBackend` 只充当群聊记账员和发言身份。

**2. 没有推进 read_at**

同一专家被第二次 @ 时，摘录仍从 0 取最近几条。接上真实 `GroupMessageHandler` 之后，水位会前移，窗口语义会变。

**3. 专家不会互相叫醒**

Demo 在工具调用时把 `mentions` 留空。如果把别的专家写进回复的 mentions，公开房间会重新进入唤醒逻辑。

**4. 模型状态与内存库同进程**

房间数据库在内存里，进程重启后广播表清空；`history.jsonl` 仍留在 `swarmchat_room/workspace/`。页面会重新读到文件里的旧气泡，但内存库与文件不是同一份真相源，演示时重启后端等于重新开一局内存账本。

---

## 九、怎么跑

依赖装在示例根目录 `learn_note/example`：共用 `.venv`、`node_modules` 和 `.env`。

```bash
cd learn_note/example
cp .env.example .env   # 填写 API_KEY 等
source .venv/bin/activate
```

仓库根目录启动后端：

```bash
uv run uvicorn --app-dir learn_note/example/swarmchat_room backend.main:app --host 127.0.0.1 --port 8002
```

另开终端：

```bash
cd learn_note/example
npm run dev:swarmchat
```

浏览器打开 http://127.0.0.1:5175 。点「播放脚本」，或自己勾选专家发送。

---

## 十、总结

这条链路可以收成四句话：

- **公开房间管历史**：每句话进广播表，并投影到 `history.jsonl`；
- **mentions 管唤醒**：不勾选只归档，勾选谁谁开口；
- **摘录管上下文**：专家先看最近几条和文件路径，再决定怎么当众说；
- **绑定身份管发言**：工具作者是当时的成员名，专家回复不再点名他人。

多人专家协作里，难的不是「再加一个模型」，而是把「全员可见」和「按需开口」拆开。SwarmChat 把这两件事做成同一间房里的两道闸门之后，后面的专家可以站在前面的公开结论上继续说话，又不会把整个房间重新吵起来。

---

**参考**

- 群聊归档与摘录：`openjiuwen/agent_teams/group_chat/handler.py`
- 专家公开发言工具：`openjiuwen/agent_teams/group_chat/tools.py`
- 历史文件投影：`openjiuwen/agent_teams/group_chat/conversation.py`
- 本文项目代码：[https://github.com/songhaowei666/learn_openjiuwen/tree/main/swarmchat_room](https://github.com/songhaowei666/learn_openjiuwen/tree/main/swarmchat_room)

*示例基于 openJiuwen agent-core，遵循 Apache-2.0 协议。*
