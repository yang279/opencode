"""内容审核：最终回答用识别模型二分类，命中标记或拦截。

默认关闭（SafetyConfig.content_filter_enabled=false），避免给正常回复引入额外延迟。
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from ..config.schema import SafetyConfig
from ..core.session import Message
from ..llm.base import LLMProvider

_SYSTEM = (
    "你是内容安全审核器。判断下面的文本是否包含有害、违法、仇恨歧视、"
    '色情或自我伤害内容。只输出 JSON：{"flag": true/false}，不要解释。'
)


class ContentFilter:
    def __init__(self, config: SafetyConfig, provider: Optional[LLMProvider] = None) -> None:
        self.config = config
        self.provider = provider

    @property
    def enabled(self) -> bool:
        return self.config.content_filter_enabled and self.provider is not None

    async def check(self, text: str) -> bool:
        """返回是否命中（True=需标记/拦截）。失败或超时一律放行。"""
        if not self.enabled:
            return False
        if not text.strip():
            return False
        try:
            return await asyncio.wait_for(
                self._classify(text), timeout=self.config.content_filter_timeout
            )
        except Exception:  # 审核失败不影响主流程，放行
            return False

    async def _classify(self, text: str) -> bool:
        msgs = [
            Message(role="system", content=_SYSTEM),
            Message(role="user", content=text[:4000]),
        ]
        parts: List[str] = []
        async for ev in self.provider.stream(
            msgs,
            [],
            temperature=0.0,
            max_tokens=16,
            extra_body={"enable_thinking": False},
        ):
            if ev.kind == "text" and ev.delta:
                parts.append(ev.delta)
        raw = "".join(parts).strip().lower()
        return "true" in raw