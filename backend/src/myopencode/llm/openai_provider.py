"""OpenAI Provider（含 OpenAI 兼容协议，如国产大模型 / vLLM / LiteLLM）。"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator, List, Optional

from ..core import metrics
from ..core import tracing
from ..core.session import Message
from .base import LLMEvent, ToolSchema
from .usage import record_usage


class OpenAIProvider:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.model = model or "gpt-4o"
        self._api_key = api_key
        self._base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "openai 未安装，请 `pip install openai` 后使用该 provider"
                ) from exc
            kwargs: dict = {}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def stream(
        self,
        messages: List[Message],
        tools: List[ToolSchema],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra_body: Optional[dict] = None,
    ) -> AsyncIterator[LLMEvent]:
        start = time.perf_counter()
        metrics.incr("llm_call_total", model=self.model)
        with tracing.span("llm.stream", model=self.model):
            sampling: dict = {}
            if temperature is not None:
                sampling["temperature"] = temperature
            if max_tokens is not None:
                sampling["max_tokens"] = max_tokens
            if extra_body:
                sampling["extra_body"] = extra_body
            stream = await self._get_client().chat.completions.create(
                model=self.model,
                messages=[m.to_openai_dict() for m in messages],
                tools=[t.to_openai_dict() for t in tools] or None,
                stream=True,
                stream_options={"include_usage": True},
                **sampling,
            )
            accumulated: dict = {}
            usage = None
            async for chunk in stream:
                if chunk.usage is not None:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield LLMEvent(kind="text", delta=delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        acc = accumulated.setdefault(
                            tc.index, {"id": None, "name": "", "arguments": ""}
                        )
                        if tc.id:
                            acc["id"] = tc.id
                        if tc.function and tc.function.name:
                            acc["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            acc["arguments"] += tc.function.arguments
        metrics.observe_histogram("llm_call_seconds", time.perf_counter() - start, model=self.model)
        if usage is not None:
            record_usage(
                self.model,
                int(getattr(usage, "prompt_tokens", 0) or 0),
                int(getattr(usage, "completion_tokens", 0) or 0),
            )
        for acc in accumulated.values():
            if acc["name"]:
                args = acc["arguments"] or "{}"
                try:
                    json.loads(args)
                except json.JSONDecodeError:
                    args = "{}"
                yield LLMEvent(
                    kind="tool_call",
                    tool_name=acc["name"],
                    tool_id=acc["id"],
                    tool_arguments=args,
                )