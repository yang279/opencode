"""BM25 词汇检索（自研纯 Python）：CJK 单字 + 英文/数字词分词。

与语义向量路互补：语义抓同义，BM25 抓专有名词/编号等精确匹配。
"""
from __future__ import annotations

import math
import re
from typing import List, Tuple

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")


def tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs: List[List[str]] = []
        self._len: List[int] = []
        self._avgdl: float = 0.0
        self._df: dict = {}
        self._idf: dict = {}

    @property
    def size(self) -> int:
        return len(self._docs)

    def build(self, docs: List[str]) -> None:
        self._docs = [tokenize(d) for d in docs]
        self._len = [len(t) for t in self._docs]
        n = len(self._docs)
        self._avgdl = (sum(self._len) / n) if n else 0.0
        self._df = {}
        for toks in self._docs:
            for term in set(toks):
                self._df[term] = self._df.get(term, 0) + 1
        self._idf = {
            term: math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            for term, df in self._df.items()
        }

    def search(self, query: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """返回 [(doc_idx, score)]，按分数降序。"""
        if not self._docs:
            return []
        q = tokenize(query)
        if not q:
            return []
        scores: List[float] = [0.0] * len(self._docs)
        for term in set(q):
            idf = self._idf.get(term)
            if not idf:
                continue
            for i, toks in enumerate(self._docs):
                tf = toks.count(term)
                if tf == 0:
                    continue
                dl = self._len[i] or 1
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1))
                scores[i] += idf * (tf * (self.k1 + 1)) / denom
        ranked = sorted(
            ((i, s) for i, s in enumerate(scores) if s > 0),
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked[:top_k]
