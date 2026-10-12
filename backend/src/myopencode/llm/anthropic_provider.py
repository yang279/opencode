"""Anthropic Provider（native tool use）。"""
from __future__ import annotations

import json
from typing import AsyncIterator, List, Optional

from ..core.session import Message
from .base import LLMEvent, ToolSchema
from .usage import record_usage


class AnthropicProvider:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.model = model or "claude-3-5-sonnet-latest"
        self._api_key = api_key
        self._base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "anthropic 未安装，请 `pip install anthropic` 后使用该 provider"
                ) from exc
            kwargs: dict = {}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncAnthropic(**kwargs)
        return self._client

    async def stream(
        self,
        messages: List[Message],
        tools: List[ToolSchema],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra_body: Optional[dict] = None,
    ) -> AsyncIterator[LLMEvent]:
        system = ""
        normalized = []
        for m in messages:
            if m.role == "system":
                system += m.content + "\n"
                continue
            entry: dict = {"role": m.role, "content": m.content}
            normalized.append(entry)

        sampling: dict = {}
        if temperature is not None:
            sampling["temperature"] = temperature
        stream = await self._get_client().messages.create(
            model=self.model,
            system=system or None,
            max_tokens=max_tokens or 4096,
            messages=normalized,
            tools=[t.to_openai_dict()["function"] for t in tools] or None,
            stream=True,
            **sampling,
        )

        tool_agg: dict = {}
        input_tokens = 0
        output_tokens = 0
        async for event in stream:
            if event.type == "message_start":
                m = getattr(event, "message", None)
                if m is not None and getattr(m, "usage", None) is not None:
                    input_tokens = int(getattr(m.usage, "input_tokens", 0) or 0)
            elif event.type == "message_delta":
                u = getattr(event, "usage", None)
                if u is not None:
                    output_tokens = int(getattr(u, "output_tokens", 0) or 0)
            elif event.type == "content_block_delta":
                d = event.delta
                if getattr(d, "type", None) == "text_delta":
                    yield LLMEvent(kind="text", delta=d.text)
                elif getattr(d, "type", None) == "input_json_delta":
                    agg = tool_agg.setdefault(
                        event.index, {"id": "", "name": "", "arguments": ""}
                    )
                    agg["arguments"] += d.partial_json
            elif event.type == "content_block_start":
                cb = event.content_block
                if getattr(cb, "type", None) == "tool_use":
                    tool_agg.setdefault(
                        event.index, {"id": "", "name": "", "arguments": ""}
                    )
                    tool_agg[event.index]["id"] = cb.id
                    tool_agg[event.index]["name"] = cb.name

        record_usage(self.model, input_tokens, output_tokens)

        for agg in tool_agg.values():
            if agg["name"]:
                args = agg["arguments"] or "{}"
                try:
                    json.loads(args)
                except json.JSONDecodeError:
                    args = "{}"
                yield LLMEvent(
                    kind="tool_call",
                    tool_name=agg["name"],
                    tool_id=agg["id"],
                    tool_arguments=args,
                )