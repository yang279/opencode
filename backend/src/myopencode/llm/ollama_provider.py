"""Ollama Provider：通过 OpenAI 兼容 HTTP 接口访问本地模型。"""
from __future__ import annotations

from typing import Optional

from .openai_provider import OpenAIProvider


class OllamaProvider(OpenAIProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        base_url = base_url or "http://localhost:11434/v1"
        super().__init__(api_key="ollama", base_url=base_url, model=model or "llama3")