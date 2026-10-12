"""Agent 主循环集成测试：用假 LLM 验证整链事件顺序与结果回填。"""
import asyncio
import json

from myopencode.config.schema import default_config
from myopencode.core.agent import Agent
from myopencode.core.session import Session
from myopencode.tools.registry import ToolRegistry

from fakes import FakeLLMProvider, text, tool_call


def _make_agent(provider, events, tmp_path):
    cfg = default_config()
    cfg.working_dir = str(tmp_path)
    cfg.sandbox.enabled = False

    async def emit(ev):
        events.append(ev)

    return cfg, Agent(config=cfg, provider=provider, tools=ToolRegistry(), emit=emit)


def _kinds(events):
    return [e["type"] for e in events]


def test_plain_text_reply(tmp_path):
    events = []
    provider = FakeLLMProvider([[text("你好")]])
    _, agent = _make_agent(provider, events, tmp_path)
    session = Session(session_id="s1", title="t")

    asyncio.run(agent.run(session, "打个招呼"))

    kinds = _kinds(events)
    assert "assistant_text" in kinds
    assert kinds[-1] == "done"
    assert session.messages[-1].role == "assistant"
    assert session.messages[-1].content == "你好"


def test_tool_call_loop(tmp_path):
    events = []
    provider = FakeLLMProvider(
        [
            [tool_call("list_dir", json.dumps({"path": "."}))],
            [text("列完了")],
        ]
    )
    _, agent = _make_agent(provider, events, tmp_path)
    session = Session(session_id="s1", title="t")

    asyncio.run(agent.run(session, "列出目录"))

    kinds = _kinds(events)
    assert "tool_call_start" in kinds
    assert "tool_call_end" in kinds
    assert kinds[-1] == "done"
    assert "tool" in [m.role for m in session.messages]
    assert session.messages[-1].role == "assistant"
    assert session.messages[-1].content == "列完了"


def test_ask_user_blocking(tmp_path):
    events = []
    provider = FakeLLMProvider(
        [
            [
                tool_call(
                    "ask_user",
                    json.dumps({"question": "选哪个", "options": [{"label": "A"}, {"label": "B"}]}),
                )
            ],
            [text("你选了答案")],
        ]
    )
    _, agent = _make_agent(provider, events, tmp_path)
    session = Session(session_id="s1", title="t")

    async def driver():
        task = asyncio.create_task(agent.run(session, "帮我问个问题"))
        answered = False
        while not task.done():
            for ev in events:
                if ev["type"] == "ask_user" and not answered:
                    fut = session.pending_questions[ev["id"]].future
                    if not fut.done():
                        fut.set_result("A")
                        answered = True
            await asyncio.sleep(0.001)
        await task

    asyncio.run(driver())

    kinds = _kinds(events)
    assert "ask_user" in kinds
    assert any(m.role == "tool" and m.content == "A" for m in session.messages)
    assert kinds[-1] == "done"
    assert session.messages[-1].content == "你选了答案"