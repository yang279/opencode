"""短期记忆：上下文 token 预算与惰性滚动压缩。"""
from __future__ import annotations

from typing import List, Tuple

from ..config.schema import MemoryConfig
from ..core.session import Message
from .summarizer import Summarizer


def estimate_tokens(text: str) -> int:
    """粗略 token 估算（无外部依赖）。"""
    return max(1, len(text or "") // 4)


class ShortTermMemory:
    def __init__(self, summarizer: Summarizer, config: MemoryConfig) -> None:
        self.summarizer = summarizer
        self.config = config

    def total_tokens(self, messages: List[Message]) -> int:
        return sum(estimate_tokens(m.content) for m in messages)

    async def compact(
        self, messages: List[Message], prior_summary: str
    ) -> Tuple[str, List[Message]]:
        """惰性压缩：超过上下文预算时折叠最旧消息，返回 (新摘要, 保留消息)。"""
        window = self.config.context_window_tokens
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