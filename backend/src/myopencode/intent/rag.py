"""RAG 识别（预留）：判断是否需要检索。当前恒 False。"""
from __future__ import annotations

from .base import RecognitionContext
from .schema import Intent


class RagRecognizer:
    """占位实现：未来接入向量库后，这里判断是否需要检索并把结果注入上下文。"""

    async def recognize(self, ctx: RecognitionContext, current: Intent) -> Intent:
        current.needs_rag = False
        return current