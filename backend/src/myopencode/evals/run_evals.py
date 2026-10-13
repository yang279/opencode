"""评测运行器：用真实 LLM 跑黄金集，产出 pass rate。

用法：
    python -m myopencode.evals.run_evals [--config PATH] [--cases PATH] [--tag security]

- 默认跑 `cases.jsonl`（常规黄金集）
- `--tag security` 只跑打上 `security` 标签的红队集（`cases_security.jsonl`）
- 依赖已配置的 provider（config.json），会真实调用工具，请在可写目录运行
- 为确定性起见：禁用沙箱（避免容器探测副作用）；安全护栏强制开启且关闭 LLM 精排，
  仅用规则层判定（provider=None），这样红队判定可离线、可复现
- 交互事件自动回复：approval→reject / safety→block / ask_user→空串（可按 case 覆盖）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

from ..config.loader import load_config
from ..core.agent import Agent
from ..core.session import Session
from ..llm.registry import create_provider
from ..security.safety import SafetyGate
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
                    forbidden_tools=d.get("forbidden_tools", []),
                    expect_safety_event=d.get("expect_safety_event", False),
                    expect_content_flag=d.get("expect_content_flag", False),
                    expect_reject=d.get("expect_reject", False),
                    tags=d.get("tags", []),
                    approval_reply=d.get("approval_reply", "reject"),
                    safety_reply=d.get("safety_reply", "block"),
                    ask_user_reply=d.get("ask_user_reply", ""),
                )
            )
    return cases


def _resolve(container: Dict[str, Any], key: Optional[str], decision: str) -> None:
    if not key:
        return
    item = container.get(key)
    if item is not None and not item.future.done():
        item.future.set_result(decision)


async def _run_case(agent: Agent, case: EvalCase) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    session = Session(session_id=case.id, title=case.id)
    original = agent.emit

    async def collect(ev: Dict[str, Any]) -> None:
        events.append(ev)
        t = ev.get("type")
        sid = ev.get("id")
        if t == "approval_request":
            _resolve(session.pending_approvals, sid, case.approval_reply)
        elif t == "safety":
            _resolve(session.pending_safety, sid, case.safety_reply)
        elif t == "ask_user":
            _resolve(session.pending_questions, sid, case.ask_user_reply)

    agent.emit = collect
    try:
        await agent.run(session, case.prompt)
    finally:
        agent.emit = original
    return events


async def _run_all(agent: Agent, cases: List[EvalCase]) -> List[Dict[str, Any]]:
    results = []
    for case in cases:
        events = await _run_case(agent, case)
        res = judge(case, events)
        res["tags"] = case.tags
        results.append(res)
    return results


def _group_by_tag(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in results:
        for tag in r.get("tags") or ["untagged"]:
            bucket = out.setdefault(tag, {"total": 0, "passed": 0})
            bucket["total"] += 1
            if r["passed"]:
                bucket["passed"] += 1
    for tag, bucket in out.items():
        bucket["pass_rate"] = bucket["passed"] / bucket["total"] if bucket["total"] else 0.0
    return out


def _main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="myopencode evals runner")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--cases", default=None, help="黄金集 JSONL 路径")
    parser.add_argument("--tag", default=None, help="只跑带指定 tag 的 case（如 security）")
    args = parser.parse_args(argv)

    cases_path = args.cases or os.path.join(os.path.dirname(__file__), "cases.jsonl")
    config = load_config(args.config)
    config.sandbox.enabled = False  # 评测只读，避免容器探测副作用
    config.safety.enabled = True  # 安全评测强制开启护栏
    config.safety.llm_confirm = False  # 关闭 LLM 精排，红队判定确定性/可离线

    provider = create_provider(config)
    agent = Agent(config=config, provider=provider, tools=ToolRegistry())
    # 确定性安全护栏（provider=None → 仅规则层，不触发 LLM 二次精排）
    agent.set_safety(SafetyGate(config.safety, None))

    cases = load_cases(cases_path)
    if args.tag:
        cases = [c for c in cases if args.tag in c.tags]
    if not cases:
        print("no cases to run")
        return 1

    results = asyncio.run(_run_all(agent, cases))
    passed = sum(1 for r in results if r["passed"])
    summary = {
        "total": len(results),
        "passed": passed,
        "pass_rate": (passed / len(results)) if results else 0.0,
        "by_tag": _group_by_tag(results),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
