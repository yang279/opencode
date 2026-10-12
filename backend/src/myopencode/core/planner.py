"""任务规划器：把用户任务拆解为有序、带依赖的步骤列表（Plan-and-Execute 的 Plan 段）。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from ..config.schema import PlanningConfig
from ..llm.base import LLMProvider
from ..llm.retry import resilient_stream
from .session import Message

_logger = logging.getLogger("myopencode.planner")


@dataclass
class PlanStep:
    id: str
    title: str
    description: str
    depends_on: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "depends_on": list(self.depends_on),
        }


class Planner:
    def __init__(
        self,
        provider: LLMProvider,
        config: PlanningConfig,
        llm_config: Any = None,
        fallbacks: Optional[List[LLMProvider]] = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self._llm_config = llm_config
        self._fallbacks = fallbacks or []

    async def plan(self, user_content: str, context: str = "") -> List[PlanStep]:
        """产出步骤列表；LLM 失败时回退为单步。"""
        steps = await self._llm_plan(user_content, context)
        if not steps:
            steps = [PlanStep(id="step-1", title="执行任务", description=user_content)]
        return steps[: self.config.max_steps]

    async def _llm_plan(self, user_content: str, context: str) -> List[PlanStep]:
        system = (
            "你是任务规划器。把用户任务拆解为可执行的步骤列表，返回严格 JSON：\n"
            '{"steps": [{"title": "步骤名", "description": "具体要做什么", "depends_on": ["依赖步骤下标(0开始),无依赖则空数组]"]}]}\n'
            "规则：步骤要具体、可原子执行；能并行的步骤 depends_on 置空；只输出 JSON，不要解释。"
        )
        user = "任务：{}\n{}".format(user_content, context)
        messages = [Message(role="system", content=system), Message(role="user", content=user)]
        parts: List[str] = []
        if self._llm_config is not None:
            providers = [self.provider, *self._fallbacks]
            async for ev in resilient_stream(providers, messages, [], self._llm_config):
                if ev.kind == "text" and ev.delta:
                    parts.append(ev.delta)
        else:
            async for ev in self.provider.stream(messages, []):
                if ev.kind == "text" and ev.delta:
                    parts.append(ev.delta)
        raw = "".join(parts).strip()
        data = _extract_json(raw)
        if not data:
            return []
        return _parse_steps(data)


def _extract_json(raw: str) -> Optional[dict]:
    """容错解析 JSON：剥离 markdown 代码围栏。"""
    text = raw.strip()
    if text.startswith("```"):
        # 去掉 ```json ... ```
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试截取首尾大括号
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def _parse_steps(data: dict) -> List[PlanStep]:
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list):
        return []
    steps: List[PlanStep] = []
    for i, s in enumerate(raw_steps):
        if not isinstance(s, dict):
            continue
        deps = s.get("depends_on") or []
        if not isinstance(deps, list):
            deps = []
        dep_ids: List[str] = []
        for d in deps:
            # 下标形式 → 转成 step-id
            if isinstance(d, int):
                dep_ids.append("step-{}".format(d + 1))
            elif isinstance(d, str):
                dep_ids.append(d)
        steps.append(
            PlanStep(
                id="step-{}".format(i + 1),
                title=str(s.get("title", "步骤{}".format(i + 1))),
                description=str(s.get("description", "")),
                depends_on=dep_ids,
            )
        )
    return steps


def topological_batches(steps: List[PlanStep]) -> List[List[PlanStep]]:
    """按依赖关系分层，返回可顺序执行的批次列表（批内可并行）。"""
    remaining = {s.id: s for s in steps}
    batches: List[List[PlanStep]] = []
    completed: set = set()
    while remaining:
        ready = [
            s for s in remaining.values() if all(d in completed for d in s.depends_on)
        ]
        if not ready:
            # 依赖缺失/成环：取剩余第一个，避免死锁
            ready = [next(iter(remaining.values()))]
        batches.append(ready)
        for s in ready:
            completed.add(s.id)
            remaining.pop(s.id, None)
    return batches