"""评测运行器：用真实 LLM 跑黄金集，产出 pass rate。

用法：
    python -m myopencode.evals.run_evals [--config PATH] [--cases PATH]

依赖已配置的 provider（config.json），会真实调用工具，请在可写目录运行。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict, List

from ..config.loader import load_config
from ..core.agent import Agent
from ..core.session import Session
from ..llm.registry import create_provider
from ..tools.registry import ToolRegistry
from .judge import EvalCase, judge


def load_cases(path: str) -> List[EvalCase]:
    cases = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            d = json.loads(line)
            cases.append(
                EvalCase(
                    id=d["id"],
                    prompt=d["prompt"],
                    expect_tools=d.get("expect_tools", []),
                    expect_ask_user=d.get("expect_ask_user", False),
                    expect_category=d.get("expect_category"),
                )
            )
    return cases


async def _run_case(agent: Agent, case: EvalCase) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    original = agent.emit

    async def collect(ev: Dict[str, Any]) -> None:
        events.append(ev)

    agent.emit = collect
    session = Session(session_id=case.id, title=case.id)
    try:
        await agent.run(session, case.prompt)
    finally:
        agent.emit = original
    return events


async def _run_all(agent: Agent, cases: List[EvalCase]) -> List[Dict[str, Any]]:
    results = []
    for case in cases:
        events = await _run_case(agent, case)
        results.append(judge(case, events))
    return results


def _main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="myopencode evals runner")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--cases", default=None, help="黄金集 JSONL 路径")
    args = parser.parse_args(argv)

    cases_path = args.cases or os.path.join(os.path.dirname(__file__), "cases.jsonl")
    config = load_config(args.config)
    config.sandbox.enabled = False  # 评测只读，避免容器探测副作用

    provider = create_provider(config)
    agent = Agent(config=config, provider=provider, tools=ToolRegistry())

    results = asyncio.run(_run_all(agent, load_cases(cases_path)))
    passed = sum(1 for r in results if r["passed"])
    summary = {
        "total": len(results),
        "passed": passed,
        "pass_rate": (passed / len(results)) if results else 0.0,
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))