# coding: utf-8
"""本地假组织网关：只认 {prefix}/chat/completions/v2 + 自定义鉴权头。

用 Starlette + httpx ASGITransport，不占真实端口，方便 CLI 三课验收。
"""

from __future__ import annotations

import json
from typing import Optional, Set

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route


# 演示约定：组织不走 Bearer，而是自定义头（真实头名待对接时确认）
ORG_TOKEN_HEADER = "X-Org-Access-Token"
# 网关前缀：业务侧 api_base 应设为到此前缀为止，不含 chat/completions/v2
ORG_API_PREFIX = "/org/llm"
COMPLETIONS_PATH = "chat/completions/v2"
FULL_COMPLETIONS_PATH = f"{ORG_API_PREFIX}/{COMPLETIONS_PATH}"


class MockOrgGatewayState:
    """网关侧持有的「当前合法 token」集合，以及请求审计。"""

    def __init__(self) -> None:
        self.valid_tokens: Set[str] = set()
        self.requests: list[dict] = []
        # 若设为 True：见到 Authorization 头直接 400（演示禁止 Bearer）
        self.reject_authorization = True

    def accept_token(self, token: str) -> None:
        self.valid_tokens.add(token)

    def revoke_all(self) -> None:
        self.valid_tokens.clear()


def create_mock_app(state: Optional[MockOrgGatewayState] = None) -> Starlette:
    """构造假网关 ASGI 应用。"""
    gw = state or MockOrgGatewayState()

    async def chat_completions(request: Request) -> Response:
        raw_headers = {k.decode().lower(): v.decode() for k, v in request.scope["headers"]}
        path = request.url.path
        body_bytes = await request.body()
        try:
            body = json.loads(body_bytes.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {"_raw": body_bytes.decode("utf-8", errors="replace")}

        record = {
            "path": path,
            "method": request.method,
            "headers": dict(raw_headers),
            "body": body,
        }
        gw.requests.append(record)

        # 路径必须严格是 .../chat/completions/v2
        if path.rstrip("/") != FULL_COMPLETIONS_PATH:
            return JSONResponse(
                {"error": {"message": f"path not found: {path}", "type": "not_found"}},
                status_code=404,
            )

        if gw.reject_authorization and "authorization" in raw_headers:
            return JSONResponse(
                {
                    "error": {
                        "message": "Authorization header is not allowed; use X-Org-Access-Token",
                        "type": "auth_style_error",
                    }
                },
                status_code=400,
            )

        token = raw_headers.get(ORG_TOKEN_HEADER.lower(), "")
        if not token or token not in gw.valid_tokens:
            return JSONResponse(
                {"error": {"message": "invalid or expired org token", "type": "auth_error"}},
                status_code=401,
            )

        # 协议体按 OpenAI chat/completions 风格回一段固定内容
        model = body.get("model") or "org-demo-model"
        user_text = ""
        messages = body.get("messages") or []
        if messages:
            last = messages[-1]
            if isinstance(last, dict):
                user_text = str(last.get("content") or "")
        content = f"[org-v2] echo: {user_text}" if user_text else "[org-v2] ok"

        return JSONResponse(
            {
                "id": "chatcmpl-org-demo",
                "object": "chat.completion",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )

    async def catch_all(request: Request) -> Response:
        gw.requests.append(
            {
                "path": request.url.path,
                "method": request.method,
                "headers": {k.decode().lower(): v.decode() for k, v in request.scope["headers"]},
                "body": None,
            }
        )
        return JSONResponse(
            {"error": {"message": f"path not found: {request.url.path}", "type": "not_found"}},
            status_code=404,
        )

    app = Starlette(
        routes=[
            Route(FULL_COMPLETIONS_PATH, chat_completions, methods=["POST"]),
            Route("/{path:path}", catch_all, methods=["GET", "POST", "PUT", "DELETE", "PATCH"]),
        ]
    )
    # 挂到 app.state，方便测试侧读取
    app.state.gateway = gw
    return app
