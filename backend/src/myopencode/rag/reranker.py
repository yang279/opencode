"""LLM 重排：复用现有 provider 对候选 chunk 按相关性排序。

解析失败时回退原始融合顺序，保证检索不因模型输出异常而中断。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ..core.session import Message

_SYSTEM = (
    "你是检索排序器。根据用户查询，把候选片段按相关性从高到低排序。"
    "只输出一个 JSON 数组，包含片段编号（从 0 开始），例如 [2, 0, 1]。不要解释。"
)


class Reranker:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def rerank(self, query: str, chunks: List[Dict[str, Any]]) -> List[int]:
        """返回按相关性降序的 chunk 下标列表。"""
        n = len(chunks)
        if n <= 1:
            return list(range(n))
        prompt = _build_prompt(query, chunks)
        msgs = [
            Message(role="system", content=_SYSTEM),
            Message(role="user", content=prompt),
        ]
        parts: List[str] = []
        try:
            async for ev in self.provider.stream(
                msgs, [], temperature=0.0, max_tokens=256
            ):
                if ev.kind == "text" and ev.delta:
                    parts.append(ev.delta)
        except Exception:
            return list(range(n))
        return _parse_order("".join(parts), n)


def _build_prompt(query: str, chunks: List[Dict[str, Any]]) -> str:
    lines = ["查询：{}".format(query or ""), "", "候选片段："]
    for i, c in enumerate(chunks):
        text = (c.get("text") or "").strip()
        head = (c.get("heading") or c.get("source") or "").strip()
        prefix = "({})".format(head) if head else ""
        lines.append("[{}] {}\n{}".format(i, prefix, text[:600]))
    lines.append("")
    lines.append("请输出按相关性排序的片段编号 JSON 数组：")
    return "\n".join(lines)


def _parse_order(raw: str, n: int) -> List[int]:
    idx = _extract_ints(raw, n)
    if not idx:
        return list(range(n))
    order: List[int] = []
    seen = set()
    for i in idx:
        if i not in seen:
            seen.add(i)
            order.append(i)
    for i in range(n):
        if i not in seen:
            order.append(i)
    return order[:n]


def _extract_ints(raw: str, n: int) -> List[int]:
    m = re.search(r"\[[^\]]*\]", raw or "")
    cand = m.group(0) if m else (raw or "")
    out: List[int] = []
    for s in re.findall(r"\d+", cand):
        v = int(s)
        if 0 <= v < n:
            out.append(v)
    return out
