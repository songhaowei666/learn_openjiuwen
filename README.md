# learn_openjiuwen

跟随 openJiuwen 学习 Agent 的可运行 demo。每个子目录是一个示例，`doc/` 里是对应的知乎文章和标题。

| 目录 | 内容 |
| --- | --- |
| `wsdw_multi_workflow` | 一个 Agent 挂多条业务流，中途追问、断点续跑 |
| `swarmflow_a2ui` | 工作流跑到一半要问人，进度树和表单分两条流 |
| `swarmchat_room` | 专家协作空间，公开群聊、点名唤醒、真实模型回复 |
| `pregel_checkpoint` | Pregel 与检查点：并行汇合、屏障假完成、人机续跑、异常重入与幂等（CLI，无模型） |

Python 虚拟环境、前端依赖和 `.env` 都在本目录，各示例共用。前端依赖由根目录 `npm install` 装进 `node_modules`。

```bash
uv venv --python 3.11 .venv
uv pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
cp .env.example .env   # 填写 API_KEY 等，供 common.SharedModel 使用
npm install
source .venv/bin/activate
```

`wsdw_multi_workflow` 和 `swarmflow_a2ui` 的启动命令见各自目录下的 README。`swarmchat_room` 用根目录 `.env` 里的模型：在仓库根目录启动后端，再在本目录启动前端。

```bash
uv run uvicorn --app-dir learn_note/example/swarmchat_room backend.main:app --host 127.0.0.1 --port 8002
npm run dev:swarmchat
```

浏览器打开 http://127.0.0.1:5175 。

`pregel_checkpoint` 是 CLI，不接模型：

```bash
cd learn_note/example
source .venv/bin/activate
cd pregel_checkpoint
python -m backend.main
```

## 文档

| spec | demo | 知乎文 |
| --- | --- | --- |
| `spec/多工作流金融助手-Controller与A2UI.md` | `wsdw_multi_workflow` | `wsdw_multi_workflow/doc/` |
| `spec/调研报告进度树-SwarmFlow与A2UI.md` | `swarmflow_a2ui` | `swarmflow_a2ui/doc/` |
| `spec/专家协作空间-SwarmChat群聊.md` | `swarmchat_room` | `swarmchat_room/doc/专家协作空间-用SwarmChat群聊做一间会点名唤醒的公开聊天室.md` |
| `spec/方案分叉验收-fork与verify.md` | 尚未落地 | — |
| `spec/断点续传与Pregel图模型.md` | `pregel_checkpoint` | `pregel_checkpoint/doc/断点续传不必先啃Pregel-用三课看并行汇合人机续跑与幂等.md` |
