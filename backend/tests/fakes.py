"""集成测试用假 LLM provider：脚本化按轮次返回事件序列。"""
from __future__ import annotations

from typing import Any, AsyncIterator, List

from myopencode.core.session import Message
from myopencode.llm.base import LLMEvent


def text(delta: str) -> LLMEvent:
    return LLMEvent(kind="text", delta=delta)


def tool_call(name: str, arguments: str = "{}", tool_id: str | None = None) -> LLMEvent:
    return LLMEvent(kind="tool_call", tool_name=name, tool_arguments=arguments, tool_id=tool_id)


class FakeLLMProvider:
    """scripts 为每轮调用的 LLMEvent 列表；超出轮次则重复最后一个脚本。"""

    def __init__(self, scripts: List[List[LLMEvent]]) -> None:
        self.scripts = list(scripts)
        self.calls = 0

    def stream(
        self,
        messages: List[Message],
        tools: List[Any],
        temperature: Any = None,
        max_tokens: Any = None,
        extra_body: Any = None,
    ) -> AsyncIterator[LLMEvent]:
        idx = min(self.calls, len(self.scripts) - 1)
        self.calls += 1
        return _agen(self.scripts[idx])


async def _agen(events: List[LLMEvent]) -> AsyncIterator[LLMEvent]:
    for e in events:
        yield e