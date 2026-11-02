# coding: utf-8
"""OrgModelClient：第 2 层协议适配（路径 + 鉴权注入 + 401 重试）。

故意不继承 BaseModelClient：本 demo 聚焦三件事的落层层，
正式接入时再挂 registry，业务侧仍只拿 Model（第 3 层不变）。

对齐先例：
- OpenAIAccountModelClient._invoke_once：先 resolve，401/403 再 force_refresh
- AscendAffinity / CustomHeaders：api_key 留空，去掉 Authorization
"""

from __future__ import annotations

from typing import Any, Optional, Union

import httpx

from openjiuwen.core.foundation.llm.schema.config import (
    LLMAuthMode,
    ModelClientConfig,
    ModelRequestConfig,
)
from openjiuwen.core.foundation.llm.schema.message import AssistantMessage, BaseMessage, UsageMetadata
from openjiuwen.core.foundation.llm.model_clients.openai_model_client import (
    _normalize_openai_base_url,
    _should_omit_authorization,
)

from .mock_gateway import COMPLETIONS_PATH, ORG_TOKEN_HEADER
from .org_auth import OrgAuthManager

_AUTH_RETRY_STATUS_CODES = {401, 403}


class OrgGatewayError(Exception):
    """假网关 / 组织网关 HTTP 错误。"""

    def __init__(self, message: str, *, status_code: int, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class OrgModelClient:
    """组织网关 ModelClient（学习版）。

    职责：
    1. 用 api_base + completions_path 显式拼 URL（解决 /chat/completions/v2）
    2. auth_mode=CustomHeaders，api_key 留空，避免 Bearer
    3. 每次请求前从 OrgAuthManager 取 token，写入自定义头；401 有限次强制刷新重试
    """

    def __init__(
        self,
        model_config: ModelRequestConfig,
        model_client_config: ModelClientConfig,
        *,
        auth_manager: OrgAuthManager,
        completions_path: str = COMPLETIONS_PATH,
        token_header: str = ORG_TOKEN_HEADER,
        http_client: Optional[httpx.AsyncClient] = None,
        auth_retry_limit: int = 1,
    ) -> None:
        self.model_config = model_config
        self.model_client_config = model_client_config
        self.auth_manager = auth_manager
        self.completions_path = completions_path.strip().strip("/")
        self.token_header = token_header
        self._http = http_client
        self.auth_retry_limit = auth_retry_limit
        # 审计：课里打印「拼了什么 URL / 带了什么头」
        self.last_url: str = ""
        self.last_headers: dict[str, str] = {}
        self.invoke_attempts: int = 0

        self._validate_config()

    def _validate_config(self) -> None:
        cfg = self.model_client_config
        if not cfg.api_base:
            raise ValueError("OrgModelClient 需要 api_base（到前缀为止，不含 chat/completions/v2）")
        auth_mode = cfg.auth_mode
        if auth_mode not in (LLMAuthMode.CustomHeaders, LLMAuthMode.CustomHeaders.value):
            raise ValueError(
                f"组织网关应使用 auth_mode=CustomHeaders，当前={auth_mode!r}"
            )
        if str(cfg.api_key or "").strip():
            raise ValueError("CustomHeaders 模式下 api_key 应留空，避免拼出 Authorization: Bearer")
        if not _should_omit_authorization(cfg):
            raise ValueError("配置未满足 omit Authorization 条件，请检查 auth_mode / api_key")

    def completions_url(self) -> str:
        """显式拼装：{api_base}/{completions_path}。

        不要把完整 path 塞进 api_base 再交给默认 /chat/completions 拼装。
        """
        base = str(self.model_client_config.api_base or "").strip().rstrip("/")
        return f"{base}/{self.completions_path}"

    @staticmethod
    def wrong_urls_if_only_api_base(api_base_candidates: dict[str, str]) -> dict[str, str]:
        """对照课：若只改 api_base、仍走默认拼法，会得到哪些错误 URL。"""
        result = {}
        for label, api_base in api_base_candidates.items():
            # 复用框架现有拼装，展示「只改 api_base 对不上」
            normalized = _normalize_openai_base_url(api_base)
            result[label] = f"{normalized}/chat/completions"
        return result

    async def invoke(
        self,
        messages: Union[str, list[BaseMessage], list[dict]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AssistantMessage:
        """非流式调用：取 token → POST → 必要时 force_refresh 再打一次。"""
        body = self._build_body(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return await self._invoke_once(body=body)

    async def _invoke_once(self, *, body: dict[str, Any]) -> AssistantMessage:
        """先 resolve；鉴权失败再 force_refresh 重试（次数受 auth_retry_limit 限制）。"""
        token = await self.auth_manager.resolve_token(force_refresh=False)
        try:
            return await self._post(body=body, token=token)
        except OrgGatewayError as exc:
            if exc.status_code not in _AUTH_RETRY_STATUS_CODES:
                raise
            if self.auth_retry_limit < 1:
                raise
            refreshed = await self.auth_manager.resolve_token(force_refresh=True)
            return await self._post(body=body, token=refreshed)

    async def _post(self, *, body: dict[str, Any], token: str) -> AssistantMessage:
        if self._http is None:
            raise RuntimeError("OrgModelClient 需要注入 httpx.AsyncClient（demo 用 ASGITransport）")

        url = self.completions_url()
        headers = self._build_headers(token=token)
        self.last_url = url
        self.last_headers = dict(headers)
        self.invoke_attempts += 1

        response = await self._http.post(url, json=body, headers=headers)
        payload: Any
        try:
            payload = response.json()
        except Exception:
            payload = response.text

        if response.status_code >= 400:
            message = ""
            if isinstance(payload, dict):
                err = payload.get("error") or {}
                if isinstance(err, dict):
                    message = str(err.get("message") or "")
            raise OrgGatewayError(
                message or f"gateway HTTP {response.status_code}",
                status_code=response.status_code,
                payload=payload,
            )

        return self._parse_assistant(payload)

    def _build_headers(self, *, token: str) -> dict[str, str]:
        """静态 custom_headers + 本次动态 token；绝不写 Authorization。"""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        static = self.model_client_config.custom_headers or {}
        for key, value in static.items():
            if str(key).lower() == "authorization":
                # 禁止把 Bearer 塞进静态头
                continue
            headers[str(key)] = str(value)
        headers[self.token_header] = token
        return headers

    def _build_body(
        self,
        messages: Union[str, list[BaseMessage], list[dict]],
        *,
        model: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> dict[str, Any]:
        normalized = self._normalize_messages(messages)
        body: dict[str, Any] = {
            "model": model or self.model_config.model_name,
            "messages": normalized,
        }
        if temperature is not None:
            body["temperature"] = temperature
        elif self.model_config.temperature is not None:
            body["temperature"] = self.model_config.temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        return body

    @staticmethod
    def _normalize_messages(
        messages: Union[str, list[BaseMessage], list[dict]],
    ) -> list[dict[str, Any]]:
        if isinstance(messages, str):
            return [{"role": "user", "content": messages}]
        out: list[dict[str, Any]] = []
        for item in messages:
            if isinstance(item, BaseMessage):
                out.append({"role": item.role, "content": item.content})
            elif isinstance(item, dict):
                out.append(
                    {
                        "role": item.get("role", "user"),
                        "content": item.get("content", ""),
                    }
                )
            else:
                raise TypeError(f"不支持的 message 类型: {type(item)}")
        return out

    @staticmethod
    def _parse_assistant(payload: Any) -> AssistantMessage:
        if not isinstance(payload, dict):
            return AssistantMessage(content=str(payload))
        choices = payload.get("choices") or []
        content = ""
        finish_reason = "stop"
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            content = str(message.get("content") or "")
            finish_reason = str(choices[0].get("finish_reason") or "stop")
        usage_raw = payload.get("usage") or {}
        usage = None
        if isinstance(usage_raw, dict):
            usage = UsageMetadata(
                model_name=str(payload.get("model") or ""),
                input_tokens=int(usage_raw.get("prompt_tokens") or 0),
                output_tokens=int(usage_raw.get("completion_tokens") or 0),
                total_tokens=int(usage_raw.get("total_tokens") or 0),
            )
        return AssistantMessage(
            content=content,
            finish_reason=finish_reason,
            usage_metadata=usage,
        )


def build_org_client_config(
    *,
    api_base: str,
    static_headers: Optional[dict[str, str]] = None,
) -> ModelClientConfig:
    """组织网关推荐配置：CustomHeaders + 空 api_key + 静态头（不含动态 token）。

    client_provider 暂用 OpenAI：本 demo 不走 create_model_client，
    只借用 ModelClientConfig 的校验与 auth_mode 字段；正式接入再挂组织 provider。
    """
    return ModelClientConfig(
        client_provider="OpenAI",
        api_base=api_base,
        api_key="",
        auth_mode=LLMAuthMode.CustomHeaders,
        custom_headers=static_headers or {"X-Org-Tenant": "demo-tenant"},
        verify_ssl=False,
        timeout=30.0,
    )
