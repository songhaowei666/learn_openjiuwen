# Pregel 与检查点学习 Demo

对照 `spec/断点续传与Pregel图模型.md` 的可运行 CLI。不接模型，用工作流顶层 API 演示：

1. 并行分支 + `wait_for_all` 汇合
2. `session.interact` 中断与 `InteractiveInput` 续跑，并打印 `GraphState` 摘要
3. 异常后节点重入，对比有无业务幂等守卫
4. 互斥分支误用 AND 汇合 → 假完成；`BranchRouter` OR 组可放行

## 运行

依赖使用示例根目录共用 `.venv`：

```bash
cd learn_note/example
source .venv/bin/activate
cd pregel_checkpoint
python -m backend.main          # 跑完全部课程
python -m backend.main parallel
python -m backend.main interrupt
python -m backend.main reenter
python -m backend.main idempotent
python -m backend.main barrier
python -m backend.main interrupt --interactive   # 人机课手输回复
```

检查点落在 `pregel_checkpoint/workspace/checkpointer`（shelve 文件）。
