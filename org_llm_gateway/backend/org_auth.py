# coding: utf-8
"""OrgAuthManager：动态 token 的缓存、过期判断与强制刷新。

对齐 openjiuwen 先例 OpenAIAccountAuthManager：
只对外暴露 resolve_token(force_refresh=False)，
内部处理 skew、缓存、并发刷新；不把刷新逻辑塞进 Model。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Optional


# 演示用：过期前提前刷新的秒数（真实接入可按组织策略调整）
DEFAULT_REFRESH_SKEW_SECONDS = 1


@dataclass(frozen=True, slots=True)
class OrgToken:
    """一次签发的组织凭证。"""

    value: str
    expires_at: float
    issued_at: float

    def is_expiring(self, *, now: float, skew_seconds: int = DEFAULT_REFRESH_SKEW_SECONDS) -> bool:
        """是否已过期或进入提前刷新窗口。"""
        return self.expires_at <= now + skew_seconds


class OrgAuthManager:
    """组织动态 token 管理器（学习版）。

    真实环境里 _fetch_token 会打组织 IAM / OAuth；
    本 demo 用内存计数器模拟签发，方便验收「缓存命中」与「401 强制刷新」。
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = 30.0,
        refresh_skew_seconds: int = DEFAULT_REFRESH_SKEW_SECONDS,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.refresh_skew_seconds = refresh_skew_seconds
        self._now = now or time.time
        self._token: Optional[OrgToken] = None
        self._lock = asyncio.Lock()
        self.refresh_count = 0
        self.fetch_count = 0

    async def resolve_token(self, force_refresh: bool = False) -> str:
        """取当前可用 token；force_refresh=True 时跳过缓存强制重签。"""
        async with self._lock:
            now = self._now()
            if (
                not force_refresh
                and self._token is not None
                and not self._token.is_expiring(now=now, skew_seconds=self.refresh_skew_seconds)
            ):
                return self._token.value

            token = await self._fetch_token(now=now)
            self._token = token
            if force_refresh:
                self.refresh_count += 1
            return token.value

    def peek_token(self) -> Optional[OrgToken]:
        """调试用：看当前缓存，不触发刷新。"""
        return self._token

    def mark_expired(self) -> None:
        """演示用：把缓存 token 标成已过期，逼出下一次刷新路径。"""
        if self._token is None:
            return
        self._token = OrgToken(
            value=self._token.value,
            expires_at=self._now() - 1,
            issued_at=self._token.issued_at,
        )

    async def _fetch_token(self, *, now: float) -> OrgToken:
        """模拟向组织鉴权服务要一张新 token。"""
        self.fetch_count += 1
        # 真实接入：POST IAM，解析 access_token / expires_in
        value = f"org-token-{self.fetch_count}"
        return OrgToken(
            value=value,
            expires_at=now + self.ttl_seconds,
            issued_at=now,
        )
