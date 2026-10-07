# learn_openjiuwen

跟随 openJiuwen 学习 Agent 的可运行 demo。每个子目录是一个示例，`doc/` 里是对应的知乎文章和标题。

| 目录 | 内容 |
| --- | --- |
| `wsdw_multi_workflow` | 一个 Agent 挂多条业务流，中途追问、断点续跑 |
| `swarmflow_a2ui` | 工作流跑到一半要问人，进度树和表单分两条流 |

Python 虚拟环境、前端依赖和 `.env` 都在本目录，两个示例共用。

```bash
uv venv --python 3.11 .venv
uv pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
cp .env.example .env   # 填写 WSDW_API_KEY 等
npm install
source .venv/bin/activate
```

各示例的启动命令见对应目录下的 README。
