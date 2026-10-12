"""delegate 子代理预算与轮次上限测试。"""
import asyncio
import json

from myopencode.config.loader import parse_config_dict
from myopencode.config.schema import default_config
from myopencode.core.agent import Agent
from myopencode.core.session import Message, Session
from myopencode.llm import usage as usage_mod
from myopencode.tools.registry import ToolRegistry

from fakes import FakeLLMProvider, tool_call


def test_planning_defaults():
    cfg = default_config()
    assert cfg.subagent.budget_usd is None
    assert cfg.subagent.max_rounds == 0
    assert cfg.subagent.require_approval is False


def test_delegate_budget_parsing():
    cfg = parse_config_dict(
        {"subagent": {"budget_usd": 1.5, "max_rounds": 4, "allow_write": False}}
    )
    assert cfg.subagent.budget_usd == 1.5
    assert cfg.subagent.max_rounds == 4
    assert cfg.subagent.allow_write is False


def test_permissions_default_deny_parsing():
    assert parse_config_dict({}).permissions.default_deny_commands is True
    assert (
        parse_config_dict({"permissions": {"default_deny_commands": False}})
        .permissions.default_deny_commands
        is False
    )


def test_loop_respects_max_rounds(tmp_path):
    events = []

    async def emit(ev):
        events.append(ev)

    provider = FakeLLMProvider([[tool_call("list_dir", json.dumps({"path": "."}))]])
    cfg = default_config()
    cfg.working_dir = str(tmp_path)
    cfg.sandbox.enabled = False
    agent = Agent(config=cfg, provider=provider, tools=ToolRegistry(), emit=emit)
    session = Session(session_id="s1", title="t")
    session.append(Message(role="user", content="列目录"))
    state = agent._build_state(session)

    asyncio.run(agent._loop(state, final=False, session=session, max_rounds=3))

    assert provider.calls == 3


def test_delegate_cost_counter():
    token = usage_mod.begin_delegate_cost()
    usage_mod._accumulate_delegate_cost(1.0)
    usage_mod._accumulate_delegate_cost(2.5)
    assert usage_mod.end_delegate_cost(token) == 3.5
    assert usage_mod.delegate_cost_active() is False