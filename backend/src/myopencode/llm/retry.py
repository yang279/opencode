"""LLM 调用韧性：超时 / 指数退避重试 / provider 降级链。

策略：只在「首 token 产生之前」失败才重试或切换 provider，避免流中途重试
造成重复 delta；流中途失败直接上抛，由 agent 兜底。timeout_seconds 解释为
「单 chunk 空闲超时」，既防挂死又允许长生成。
"""
from __future__ import annotations

import asyncio
import random
from typing import AsyncIterator, Awaitable, Callable, List, Optional

from ..core.session import Message
from .base import LLMEvent, LLMProvider, ToolSchema

# 视为可重试的 HTTP 状态码
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
# 异常类名包含这些子串视为可重试（openai/anthropic SDK 异常）
_RETRYABLE_NAME_SUBSTR = (
    "RateLimit",
    "APIConnection",
    "APITimeout",
    "InternalServerError",
    "ServiceUnavailable",
)


def is_retryable(exc: BaseException) -> bool:
    """判断异常是否值得重试（连接/限流/超时/服务端 5xx）。"""
    if isinstance(exc, asyncio.TimeoutError):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and status in _RETRYABLE_STATUS:
        return True
    name = type(exc).__name__
    return any(s in name for s in _RETRYABLE_NAME_SUBSTR)


def _backoff(cfg, attempt: int) -> float:
    base = cfg.backoff_base * (2 ** (attempt - 1))
    return min(base, cfg.backoff_max) + random.uniform(0.0, 0.3)


async def resilient_stream(
    providers: List[LLMProvider],
    messages: List[Message],
    tools: List[ToolSchema],
    cfg,
    max_tokens: int | None = None,
    on_degraded: Optional[Callable[[str], Awaitable[None]]] = None,
) -> AsyncIterator[LLMEvent]:
    """依次尝试 providers（主 → 备用链），带超时与重试的流式封装。"""
    last_exc: BaseException | None = None
    for idx, provider in enumerate(providers):
        if idx > 0 and on_degraded is not None:
            await on_degraded("主 LLM 失败，已降级到备用 provider #{}".format(idx))
        attempt = 0
        while attempt <= cfg.max_retries:
            kwargs: dict = {}
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            agen = provider.stream(messages, tools, **kwargs)
            first = True
            try:
                while True:
                    ev = await asyncio.wait_for(
                        agen.__anext__(), timeout=cfg.timeout_seconds
                    )
                    first = False
                    yield ev
            except StopAsyncIteration:
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                if not first:
                    # 已出首 token，中途失败不重试（避免重复 delta）
                    raise
                if not is_retryable(exc):
                    last_exc = exc
                    break
                last_exc = exc
                if attempt >= cfg.max_retries:
                    break
                attempt += 1
                await asyncio.sleep(_backoff(cfg, attempt))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("无可用 provider")
