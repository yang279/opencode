"""向量化：OpenAI 兼容 embeddings 接口（复用主 provider 连接）。

产出 float 列表（长度 = 模型维度，text-embedding-3-large 为 3072）。
"""
from __future__ import annotations

from typing import List, Optional

_BATCH = 2048  # OpenAI embeddings 单次上限


class Embedder:
    def __init__(
        self,
        model: str = "text-embedding-3-large",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            kwargs: dict = {"timeout": self._timeout}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """批量向量化，返回与输入等长的向量列表。"""
        if not texts:
            return []
        client = self._get_client()
        out: List[List[float]] = []
        for i in range(0, len(texts), _BATCH):
            batch = texts[i : i + _BATCH]
            resp = await client.embeddings.create(model=self.model, input=batch)
            for d in resp.data:
                out.append(list(d.embedding))
        return out
