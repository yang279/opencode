"""resume 最小 checkpoint：中断残留工具轮回退测试。"""
from myopencode.core.agent import _repair_interrupted
from myopencode.core.session import Message, Session


def _session(messages):
    s = Session(session_id="s1", title="t")
    s.messages = messages
    return s


def test_repair_dangling_tool_call():
    s = _session(
        [
            Message(role="user", content="hi"),
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
                ],
            ),
        ]
    )
    assert _repair_interrupted(s) is True
    assert len(s.messages) == 1
    assert s.messages[-1].role == "user"


def test_repair_complete_round_noop():
    s = _session(
        [
            Message(role="user", content="hi"),
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
                ],
            ),
            Message(role="tool", content="result", tool_call_id="c1", name="read_file"),
        ]
    )
    assert _repair_interrupted(s) is False
    assert len(s.messages) == 3


def test_repair_partial_tool_results():
    s = _session(
        [
            Message(role="user", content="hi"),
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    {"id": "c1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                    {"id": "c2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
                ],
            ),
            Message(role="tool", content="r1", tool_call_id="c1", name="a"),
        ]
    )
    assert _repair_interrupted(s) is True
    assert len(s.messages) == 1


def test_repair_pure_text_noop():
    s = _session(
        [
            Message(role="user", content="hi"),
            Message(role="assistant", content="answer"),
        ]
    )
    assert _repair_interrupted(s) is False
    assert len(s.messages) == 2