"""LLM Provider 接口定义与数据类型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol

from ..core.session import Message


@dataclass
class ToolSchema:
    """传给 LLM 的工具描述（OpenAI function-calling 风格）。"""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_openai_dict(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class LLMEvent:
    """stream() 产出的流式事件。"""

    kind: str  # "text" | "tool_call"
    delta: Optional[str] = None
    tool_name: Optional[str] = None
    tool_id: Optional[str] = None
    tool_arguments: Optional[str] = None  # 部分 JSON 字符串，按需累积


class LLMProvider(Protocol):
    """LLM Provider 统一接口。"""

    def stream(
        self,
        messages: List[Message],
        tools: List[ToolSchema],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[LLMEvent]:
        """流式产出文本增量或工具调用。

        temperature/max_tokens/extra_body 为可选的采样/免思考控制，默认 None
        表示沿用 provider 自身默认值（主循环不传，识别分类传小值）。
        """
        ...  # pragma: no cover