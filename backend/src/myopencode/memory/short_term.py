"""短期记忆：上下文 token 预算与惰性滚动压缩。"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..config.schema import MemoryConfig
from ..core.session import Message
from .summarizer import Summarizer

# 中文/全角字符（token 密度远高于 ASCII，需单独计数）
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：CJK 按 1 字 1 token，其余按 4 字符 1 token。"""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return max(1, cjk + other // 4)


# 常见模型上下文窗口（token）。匹配到则按 80% 保留余量触发压缩。
_MODEL_CONTEXT_WINDOWS = {
    "deepseek": 128000,
    "gpt-4o": 128000,
    "gpt-4": 8192,
    "gpt-3.5": 16384,
    "claude": 200000,
    "llama3": 8192,
    "qwen": 32768,
}
_CONTEXT_RESERVE_RATIO = 0.8


def resolve_context_window(model: Optional[str]) -> Optional[int]:
    """按模型名子串推断上下文窗口（保留 20% 余量）；未命中返回 None。"""
    if not model:
        return None
    m = model.lower()
    for key, window in _MODEL_CONTEXT_WINDOWS.items():
        if key in m:
            return int(window * _CONTEXT_RESERVE_RATIO)
    return None


class ShortTermMemory:
    def __init__(self, summarizer: Summarizer, config: MemoryConfig) -> None:
        self.summarizer = summarizer
        self.config = config

    def total_tokens(self, messages: List[Message]) -> int:
        return sum(estimate_tokens(m.content) for m in messages)

    async def compact(
        self,
        messages: List[Message],
        prior_summary: str,
        model: Optional[str] = None,
    ) -> Tuple[str, List[Message]]:
        """惰性压缩：超过上下文预算时折叠最旧消息，返回 (新摘要, 保留消息)。"""
        window = resolve_context_window(model) or self.config.context_window_tokens
        keep = max(0, min(self.config.keep_recent_tokens, window))

        if self.total_tokens(messages) <= window:
            return prior_summary, list(messages)

        kept: List[Message] = []
        acc = 0
        for m in reversed(messages):
            t = estimate_tokens(m.content)
            if acc + t > keep and kept:
                break
            kept.append(m)
            acc += t
        kept.reverse()

        fold = messages[: len(messages) - len(kept)]
        if not fold:
            return prior_summary, kept

        new_summary = await self.summarizer.summarize_conversation(fold, prior_summary)
        return new_summary, kept