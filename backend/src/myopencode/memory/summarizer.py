"""基于 LLM 的摘要与事实抽取，供记忆模块复用。"""
from __future__ import annotations

import asyncio
from typing import List

from ..core import tracing
from ..core.session import Message
from ..llm.base import LLMProvider

# 摘要/知识抽取 LLM 调用超时（秒），避免记忆固化无限挂起
_SUMMARY_TIMEOUT = 60.0


class Summarizer:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def _complete(self, system: str, user: str) -> str:
        messages = [Message(role="system", content=system), Message(role="user", content=user)]
        parts: List[str] = []
        with tracing.span("memory.summarize"):
            async def _drain() -> None:
                async for ev in self.provider.stream(messages, []):
                    if ev.kind == "text" and ev.delta:
                        parts.append(ev.delta)

            try:
                await asyncio.wait_for(_drain(), timeout=_SUMMARY_TIMEOUT)
            except asyncio.TimeoutError:
                pass
        return "".join(parts).strip()

    def _transcript(self, messages: List[Message], tool_trunc: int = 500) -> str:
        lines = []
        for m in messages:
            if m.role == "system":
                continue
            content = (m.content or "").strip()
            if m.role == "tool":
                content = content[:tool_trunc]
            if not content:
                continue
            lines.append("[{}] {}".format(m.role, content))
        return "\n".join(lines)

    async def summarize_conversation(
        self, messages: List[Message], prior_summary: str = ""
    ) -> str:
        """滚动压缩：合并既有摘要 + 被折叠消息，产出新摘要。"""
        transcript = self._transcript(messages)
        if not transcript:
            return prior_summary
        system = (
            "你是对话摘要助手。用简洁的中文总结一段历史对话，保留关键上下文、任务目标、"
            "已做修改、结论与未完成事项。只输出摘要本身，不要解释。"
        )
        user = transcript
        if prior_summary:
            user = "已有摘要：\n{}\n\n新的对话摘录：\n{}".format(prior_summary, transcript)
        result = await self._complete(system, user)
        return result or prior_summary

    async def summarize_session(self, messages: List[Message]) -> str:
        """会话结束：把整段会话总结成 episode 摘要。"""
        transcript = self._transcript(messages)
        if not transcript:
            return ""
        system = (
            "你是会话摘要助手。请用中文总结这段会话：做了什么、得出什么结论、产出了什么、"
            "还有哪些未完成事项。输出一段简洁摘要。"
        )
        return await self._complete(system, transcript)

    async def extract_facts(self, text: str) -> List[str]:
        """从文本抽取稳定事实（语义记忆）。"""
        if not text:
            return []
        system = (
            "你是事实抽取助手。从给定文本中抽取值得长期记住的、关于用户偏好、项目约定、"
            "环境信息、重要结论的稳定事实。每条是一个简短句子。如果没有值得记的事实，"
            "输出空。每行一条，不要编号，不要其他解释。"
        )
        result = await self._complete(system, text)
        return [line.strip(" -·\t") for line in result.splitlines() if line.strip(" -·\t")]