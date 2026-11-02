# coding: utf-8
"""三课：路径拼装 / 非 Bearer / 动态 token。

不接真实组织网关，用 mock ASGI + OrgAuthManager / OrgModelClient 验收。
"""

from __future__ import annotations

import httpx
from openjiuwen.core.foundation.llm.schema.config import ModelRequestConfig
from openjiuwen.core.foundation.llm.model_clients.openai_model_client import (
    _chat_completions_url,
    _normalize_openai_base_url,
    _should_omit_authorization,
)
from openjiuwen.core.foundation.llm.schema.config import LLMAuthMode, ModelClientConfig

from .mock_gateway import (
    COMPLETIONS_PATH,
    FULL_COMPLETIONS_PATH,
    ORG_API_PREFIX,
    ORG_TOKEN_HEADER,
    MockOrgGatewayState,
    create_mock_app,
)
from .org_auth import OrgAuthManager
from .org_model_client import OrgGatewayError, OrgModelClient, build_org_client_config


def _print_section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


async def _make_asgi_client(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    # base_url 只是 httpx 拼相对路径用；OrgModelClient 用绝对 path
    return httpx.AsyncClient(transport=transport, base_url="http://org-gw.test")


async def lesson_path() -> None:
    """课 1：只改 api_base 对不上 chat/completions/v2，必须显式 completions_path。"""
    _print_section("课 1：路径 chat/completions/v2")

    prefix = f"http://org-gw.test{ORG_API_PREFIX}"
    candidates = {
        "api_base=前缀": prefix,
        "api_base=前缀/v2": f"{prefix}/v2",
        "api_base=完整 path": f"{prefix}/{COMPLETIONS_PATH}",
    }

    print("框架默认拼装 _chat_completions_url(api_base)：")
    for label, api_base in candidates.items():
        wrong = _chat_completions_url(api_base)
        normalized = _normalize_openai_base_url(api_base)
        print(f"  [{label}]")
        print(f"    输入 api_base = {api_base}")
        print(f"    normalize     = {normalized}")
        print(f"    实际请求      = {wrong}")

    correct = f"{prefix}/{COMPLETIONS_PATH}"
    print()
    print(f"正确做法：api_base={prefix}")
    print(f"         completions_path={COMPLETIONS_PATH}")
    print(f"         → POST {correct}")
    print(f"期望 path（相对）: {FULL_COMPLETIONS_PATH}")

    # 真打假网关：错误 path → 404；显式 path → 200
    state = MockOrgGatewayState()
    app = create_mock_app(state)
    auth = OrgAuthManager(ttl_seconds=60)
    token = await auth.resolve_token()
    state.accept_token(token)

    async with await _make_asgi_client(app) as http:
        # 错误：默认拼出来的 /chat/completions
        wrong_url = _chat_completions_url(prefix)
        r_wrong = await http.post(
            wrong_url,
            json={"model": "demo", "messages": [{"role": "user", "content": "ping"}]},
            headers={ORG_TOKEN_HEADER: token},
        )
        print()
        print(f"错误 URL 实打: {wrong_url} → HTTP {r_wrong.status_code}")
        assert r_wrong.status_code == 404, r_wrong.text

        client = OrgModelClient(
            ModelRequestConfig(model="org-demo-model"),
            build_org_client_config(api_base=prefix),
            auth_manager=auth,
            http_client=http,
        )
        msg = await client.invoke("路径课你好")
        print(f"正确 URL 实打: {client.last_url} → content={msg.content!r}")
        assert FULL_COMPLETIONS_PATH in client.last_url
        assert "路径课你好" in (msg.content or "")

    print("课 1 通过")


async def lesson_auth() -> None:
    """课 2：非 Bearer；CustomHeaders + 空 api_key 才能 omit Authorization。"""
    _print_section("课 2：鉴权不带 Bearer")

    omit_cfg = ModelClientConfig(
        client_provider="OpenAI",
        api_base="http://example.test/org/llm",
        api_key="",
        auth_mode=LLMAuthMode.CustomHeaders,
        verify_ssl=False,
    )
    bearer_cfg = ModelClientConfig(
        client_provider="OpenAI",
        api_base="http://example.test/org/llm",
        api_key="secret",
        auth_mode=LLMAuthMode.ApiKey,
        verify_ssl=False,
    )
    print(f"CustomHeaders + 空 key → omit Authorization? {_should_omit_authorization(omit_cfg)}")
    print(f"ApiKey + secret      → omit Authorization? {_should_omit_authorization(bearer_cfg)}")
    assert _should_omit_authorization(omit_cfg) is True
    assert _should_omit_authorization(bearer_cfg) is False

    state = MockOrgGatewayState()
    state.reject_authorization = True
    app = create_mock_app(state)
    auth = OrgAuthManager(ttl_seconds=60)
    token = await auth.resolve_token()
    state.accept_token(token)
    prefix = f"http://org-gw.test{ORG_API_PREFIX}"

    async with await _make_asgi_client(app) as http:
        # 故意带 Bearer → 假网关 400
        bad = await http.post(
            f"{prefix}/{COMPLETIONS_PATH}",
            json={"model": "demo", "messages": [{"role": "user", "content": "x"}]},
            headers={
                "Authorization": f"Bearer {token}",
                ORG_TOKEN_HEADER: token,
            },
        )
        print(f"带 Authorization: Bearer → HTTP {bad.status_code}（期望 400）")
        assert bad.status_code == 400

        client = OrgModelClient(
            ModelRequestConfig(model="org-demo-model"),
            build_org_client_config(api_base=prefix),
            auth_manager=auth,
            http_client=http,
        )
        msg = await client.invoke("鉴权课你好")
        print(f"请求头 keys: {sorted(client.last_headers)}")
        assert "Authorization" not in client.last_headers
        assert client.last_headers.get(ORG_TOKEN_HEADER) == token
        assert "鉴权课你好" in (msg.content or "")

    print("课 2 通过")


async def lesson_token() -> None:
    """课 3：动态 token；缓存命中、过期刷新、401 强制刷新重试。"""
    _print_section("课 3：动态 token 与 401 重试")

    state = MockOrgGatewayState()
    app = create_mock_app(state)
    auth = OrgAuthManager(ttl_seconds=60)
    prefix = f"http://org-gw.test{ORG_API_PREFIX}"

    async with await _make_asgi_client(app) as http:
        client = OrgModelClient(
            ModelRequestConfig(model="org-demo-model"),
            build_org_client_config(api_base=prefix),
            auth_manager=auth,
            http_client=http,
        )

        # 1) 首次签发，网关登记合法 token
        t1 = await auth.resolve_token()
        state.accept_token(t1)
        print(f"首次 token={t1}, fetch_count={auth.fetch_count}")

        msg1 = await client.invoke("第一轮")
        print(f"第一轮 content={msg1.content!r}, attempts={client.invoke_attempts}")
        assert auth.fetch_count == 1
        assert "第一轮" in (msg1.content or "")

        # 2) 缓存命中：再调一次不应重新 fetch
        msg2 = await client.invoke("第二轮")
        print(f"第二轮 fetch_count={auth.fetch_count}（期望仍为 1）")
        assert auth.fetch_count == 1
        assert "第二轮" in (msg2.content or "")

        # 3) 模拟网关侧吊销旧 token → 401 → Client force_refresh → 成功
        state.revoke_all()
        # AuthManager 缓存仍是旧 token；刷新后拿到 org-token-2
        # 注意：刷新后必须让网关接受新 token。真实 IAM 刷新后网关自然认新票；
        # 这里在 Client 重试前，用「旁路」让假网关接受即将签发的下一张票。
        # 为保持课可验收，包一层：第一次 401 后 manager 会 force_refresh。

        original_fetch = auth._fetch_token

        async def _fetch_and_register(*, now: float):
            token = await original_fetch(now=now)
            state.accept_token(token.value)
            return token

        auth._fetch_token = _fetch_and_register  # type: ignore[method-assign]

        before_attempts = client.invoke_attempts
        before_refresh = auth.refresh_count
        msg3 = await client.invoke("吊销后重试")
        print(
            f"吊销后 content={msg3.content!r}, "
            f"attempts_delta={client.invoke_attempts - before_attempts}, "
            f"refresh_count={auth.refresh_count}"
        )
        assert auth.refresh_count == before_refresh + 1
        assert client.invoke_attempts - before_attempts == 2  # 一次 401 + 一次成功
        assert "吊销后重试" in (msg3.content or "")
        peeked = auth.peek_token()
        assert peeked is not None
        assert peeked.value.startswith("org-token-")
        assert peeked.value != t1

        # 4) 业务禁止：静态 custom_headers 写死过期 token（对照说明，不作为主路径）
        print()
        print("禁止项提醒：")
        print("  - 不要每次 model.invoke(..., custom_headers={token})")
        print("  - 不要把会过期的 token 写进静态 custom_headers")
        print("  - 不要改共享 AsyncOpenAI 全局 api_key 做刷新")
        print("  - Model（第 3 层）不管 token")

    print("课 3 通过")


async def lesson_wrong_static_token() -> None:
    """附加：把过期 token 写进静态头会怎样（应失败，且 AuthManager 帮不上忙）。"""
    _print_section("附加：静态头写死 token 会失败")

    state = MockOrgGatewayState()
    app = create_mock_app(state)
    prefix = f"http://org-gw.test{ORG_API_PREFIX}"

    async with await _make_asgi_client(app) as http:
        # 静态头里写一张网关不认的票
        cfg = build_org_client_config(
            api_base=prefix,
            static_headers={
                "X-Org-Tenant": "demo-tenant",
                ORG_TOKEN_HEADER: "stale-static-token",
            },
        )
        auth = OrgAuthManager(ttl_seconds=60)
        # 即便 AuthManager 能签新票，Client 的 _build_headers 会用动态 token 覆盖同名头；
        # 这里故意演示「只靠静态头、关掉动态注入」的反模式：直接 httpx 打。
        bad = await http.post(
            f"{prefix}/{COMPLETIONS_PATH}",
            json={"model": "demo", "messages": [{"role": "user", "content": "static"}]},
            headers={
                "Content-Type": "application/json",
                ORG_TOKEN_HEADER: "stale-static-token",
            },
        )
        print(f"静态过期 token → HTTP {bad.status_code}（期望 401）")
        assert bad.status_code == 401

        # 对照：OrgModelClient 动态注入可以成功
        good_token = await auth.resolve_token()
        state.accept_token(good_token)
        client = OrgModelClient(
            ModelRequestConfig(model="org-demo-model"),
            cfg,
            auth_manager=auth,
            http_client=http,
        )
        msg = await client.invoke("动态覆盖")
        # 动态头应覆盖静态同名 key
        assert client.last_headers[ORG_TOKEN_HEADER] == good_token
        assert client.last_headers[ORG_TOKEN_HEADER] != "stale-static-token"
        print(f"动态注入覆盖静态头 → content={msg.content!r}")

    print("附加课通过")


async def run_all() -> None:
    await lesson_path()
    await lesson_auth()
    await lesson_token()
    await lesson_wrong_static_token()
    print()
    print("全部课程通过")
