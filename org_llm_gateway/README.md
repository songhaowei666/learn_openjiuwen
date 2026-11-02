# 组织 LLM 网关接入（chat/completions/v2）

对照 `spec/组织LLM接口v2与动态token接入.md` 的 CLI demo。不接真实组织网关、不接真实模型，用本地假网关演示：

1. 路径必须是 `{prefix}/chat/completions/v2`，只改 `api_base` 对不上
2. 鉴权不是 Bearer：`auth_mode=CustomHeaders` 且 `api_key` 留空
3. 动态 token：`OrgAuthManager` 管刷新，`OrgModelClient` 管注入与 401 重试；`Model` 不动

## 运行

依赖使用仓库根目录共用 `.venv`：

```bash
# 仓库根目录
source .venv/bin/activate
cd org_llm_gateway
python -m backend.main          # 跑完全部课程
python -m backend.main path     # 仅路径课
python -m backend.main auth     # 仅鉴权课
python -m backend.main token    # 仅动态 token 课
python -m backend.main static   # 附加：静态头写死 token
```

### 预期

- `path`：打印三种错误 `api_base` 拼装结果；错误 URL 实打 404；`OrgModelClient` 正确 path 返回 echo 内容
- `auth`：带 `Authorization: Bearer` → 400；Client 请求头无 Authorization，有 `X-Org-Access-Token`
- `token`：缓存命中不重复 fetch；吊销后 401 → force_refresh → 成功，`refresh_count+1` 且 attempts 多 2 次
