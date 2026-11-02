# 组织网关不是改 api_base：用三课看 v2 路径、非 Bearer 与动态 token

> 建议标题：`openJiuwen | 组织LLM网关 | 组织网关不是改 api_base：v2 路径、非 Bearer 与动态 token`
>
> 本文记录我在 openJiuwen 学习仓库里做的一个小 Demo：`org_llm_gateway`。不接真实组织 IAM，也不接真实大模型，用本地假网关把三件事跑清楚：**路径为什么不能只改 `api_base`**，**鉴权为什么不是 Bearer**，以及**会过期的 token 该落在哪一层**。对照的是 openjiuwen 的三级模型，不是「再包一层 SDK」。

## 目录

- [一、先说问题：组织网关常常「差一点」](#一先说问题组织网关常常差一点)
- [二、先记住三级，再谈改哪一层](#二先记住三级再谈改哪一层)
- [三、课 1：路径是 chat/completions/v2](#三课-1路径是-chatcompletionsv2)
- [四、课 2：鉴权不带 Bearer](#四课-2鉴权不带-bearer)
- [五、课 3：动态 token 不要进 Model](#五课-3动态-token-不要进-model)
- [六、踩坑与禁止项](#六踩坑与禁止项)
- [七、这个 Demo 故意没做什么](#七这个-demo-故意没做什么)
- [八、总结](#八总结)

---

## 一、先说问题：组织网关常常「差一点」

企业内部 LLM 网关，协议体往往还是 OpenAI 的 chat/completions JSON，甚至 SSE 也差不多。真正让人对着配置改半天的，通常是这三处「差一点」：

1. 路径不是 `{base}/v1` 再拼 `/chat/completions`，而是硬编码成 `{prefix}/chat/completions/v2`；
2. 鉴权头不是 `Authorization: Bearer <key>`，而是某个组织自定义头；
3. Token 会过期，要按请求取、缓存、失败再刷——不能写死在 `.env` 里，也不能让每个业务调用自己塞 header。

如果这三件事改错层，你会看到两种典型后果：

- 改 `Model` 或业务代码：到处传 `custom_headers`，会话、Agent、工作流每个入口都得改一遍；
- 只拧 `api_base`：URL 永远差一截，`/v2` 跑到 `/chat/completions` 前面，或者 path 被拼了两次。

Demo 的目标很窄：**把问题钉在正确的层上**，用假网关验收行为，真实头名和前缀留给对接清单。

---

## 二、先记住三级，再谈改哪一层

openjiuwen 把模型调用大致拆成三层：

```text
1. AsyncOpenAI / httpx     # 真正发 HTTP、拼 URL、带 header、流式解析
2. ModelClient             # 协议适配、鉴权策略、连接池、请求/响应归一化
3. Model                   # 业务统一入口 invoke/stream，不感知网关细节
```

调用链是：`Model` → `create_model_client` → 具体 `*ModelClient` → transport。

| 问题 | 落层层 | 不要落在哪 |
| --- | --- | --- |
| `chat/completions/v2` | ModelClient（URL 拼装） | 不要靠「完整 path 塞进 api_base」糊弄 SDK |
| 非 Bearer | ModelClientConfig + ModelClient | 不要在业务侧每次手写 Authorization |
| 动态 token | AuthManager + ModelClient | 不要进 Model，不要进静态 custom_headers |

协议仍兼容 OpenAI JSON 时，**尽量不新造第 3 层 API**。优先做一个组织 `ModelClient`，外挂 `AuthManager`；业务继续拿 `Model`。

本 Demo 里的 `OrgModelClient` 是学习版：为了可读，没有挂进社区 registry，CLI 直接打这一层。正式接入时再注册 provider，业务代码仍应只看见 `Model`。

---

## 三、课 1：路径是 chat/completions/v2

组织真实路径是：

```text
{prefix}/chat/completions/v2
```

框架默认拼法是：

```text
{api_base}/chat/completions
```

`_normalize_openai_base_url` 只会剥「以 `/chat/completions` 结尾」的 URL，对 `/chat/completions/v2` 无效。于是只改 `api_base` 会出现：

| 你设的 api_base | 实际请求 |
| --- | --- |
| `https://gw/.../prefix` | `.../prefix/chat/completions`（缺 `/v2`） |
| `https://gw/.../prefix/v2` | `.../prefix/v2/chat/completions`（顺序错） |
| `https://gw/.../prefix/chat/completions/v2` | `.../v2/chat/completions` 再被拼一次（重复） |

解法在第 2 层显式拼：

```text
api_base = https://gw.example.com/<prefix>   # 不含 chat/completions/v2
completions_path = chat/completions/v2
→ POST {api_base}/{completions_path}
```

Demo 假网关只认 `/org/llm/chat/completions/v2`。用默认 `_chat_completions_url(prefix)` 实打是 404；`OrgModelClient.completions_url()` 打中后回一段 echo。body 仍按 OpenAI chat/completions JSON，解析逻辑可以继续复用；必要时像亲和网关那样走 httpx 直 POST，而不是默认 `chat.completions.create` 的路径假设。

---

## 四、课 2：鉴权不带 Bearer

默认 `auth_mode=ApiKey` 会让 SDK / Client 带上 Bearer。组织网关若禁止 `Authorization`，这条路直接废。

框架已有能力：

- `LLMAuthMode.CustomHeaders` / `NoneAuth`
- `_should_omit_authorization`：CustomHeaders 且 `api_key` 为空时，剥掉 Authorization
- 先例：`AscendAffinity` 使用 `auth_mode=CustomHeaders`

推荐配置形态：

```text
auth_mode = CustomHeaders
api_key   = ""                          # 留空，避免拼 Bearer
custom_headers = { 静态头... }          # 只放不变的头
```

Demo 假网关见到 `Authorization` 直接 400；`OrgModelClient` 发出的请求头里只有 `X-Org-Access-Token`（演示名）和静态租户头，没有 Bearer。真实对接时替换头名，并确认是否还要时间戳、签名、租户 ID。

动态凭证不要写死在静态 `custom_headers`——那是下一课。

---

## 五、课 3：动态 token 不要进 Model

Token 会过期。正确拆法是两块，**都不要进 Model**：

| 组件 | 层级 | 职责 |
| --- | --- | --- |
| `OrgAuthManager` | extensions / org 适配包 | 取 token、缓存、过期、刷新、加锁；对外 `resolve_token(force_refresh=False)` |
| 注入与 401 重试 | 第 2 层 ModelClient | 每次 invoke/stream 前取 token → 写入本次请求头；401/403 则 force_refresh 再打一次 |
| `Model` | 第 3 层 | 不管 token |
| 静态 api_key / custom_headers | 配置 | 只放不变的东西 |

这和社区已有先例同构：`OpenAIAccountAuthManager` + `OpenAIAccountModelClient._invoke_once`（先 resolve，失败 force_refresh）。区别只是：OpenAI Account 最终仍是 Bearer；组织网关把同一张票写进自定义头。

课里验收三条行为：

1. 缓存命中：连续两次 invoke，`fetch_count` 不增加；
2. 网关吊销旧票：第一次 401，Client 强制刷新后第二次成功，`refresh_count + 1`；
3. 静态头里的同名 token 会被当次动态值覆盖——真正的「写死过期 token」反模式，在只靠静态头、不走 Manager 时，会稳定 401。

建议行为可以收成三句：

1. Manager 只暴露 `resolve_token`；内部处理 skew、缓存、并发刷新。
2. ModelClient 发请求前取 token，写入组织要求的 header；鉴权失败有限次刷新重试。
3. Model 保持 `invoke` / `stream`，业务无感。

---

## 六、踩坑与禁止项

**路径**

- 不要把完整 `.../chat/completions/v2` 塞进 `api_base` 再交给默认拼装。
- `_normalize_openai_base_url` 不认识 `/chat/completions/v2` 后缀，别指望它帮你剥干净。

**鉴权**

- `CustomHeaders` 但 `api_key` 非空时，omit 逻辑可能仍保留 Authorization 路径——组织场景请留空。
- 静态 `custom_headers` 里也不要手写 `Authorization`。

**动态 token**

- 禁止业务侧每次 `model.invoke(..., custom_headers={token})`。
- 禁止把会过期的 token 写进静态 `custom_headers`。
- 禁止改共享 `AsyncOpenAI` 全局 `api_key` 做刷新（易串租户，且你们不用 Bearer）。
- 禁止把刷新逻辑塞进 `Model`。

**分层心态**

协议兼容时，优先 org `ModelClient` + AuthManager；协议不兼容再独立 transport，仍然保持 `Model` 入口不变。

---

## 七、这个 Demo 故意没做什么

- 不改 agent-core，不向社区包注册正式 `OrgLLM` provider。
- 不接真实 IAM / 真实模型；流式是否标准 SSE、错误体是否 OpenAI 风格，列在对接清单里。
- 鉴权头名用 `X-Org-Access-Token` 占位，真实名称以组织文档为准。
- 无 Agent、无工作流、无前端——只把第 2 层行为跑明白。

---

## 八、总结

组织网关接入，不是「再找一个能填的配置项」，而是三件事各自归层：

1. **路径** → ModelClient 显式 `completions_path`；
2. **非 Bearer** → `CustomHeaders` + 空 `api_key`；
3. **动态 token** → AuthManager 管刷新，ModelClient 管注入与 401 重试，Model 不动。

把层找对，续聊和排障才有坐标：URL 404 先看拼装，400/鉴权风格看 header 策略，401 间歇失败看 Manager 与重试，而不是在业务代码里到处补 header。
