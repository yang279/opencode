from types import SimpleNamespace

from myopencode.config.schema import ReflexionConfig
from myopencode.core.reflexion import ReflexionController


class _DummyProvider:
    def __init__(self, replies):
        self.replies = list(replies)

    async def stream(self, messages, tools, **kwargs):
        from myopencode.llm.base import LLMEvent

        for r in self.replies:
            yield LLMEvent(kind="text", delta=r)


def _state(cancelled=False, rejected=False):
    return SimpleNamespace(cancelled=cancelled, rejected=rejected)


def test_allow_retry_budget_aware():
    cfg = ReflexionConfig(enabled=True, max_attempts=3, budget_aware=True)
    budget = SimpleNamespace(status=lambda: {"over": False})
    ctl = ReflexionController(cfg, _DummyProvider([]), budget=budget)
    assert ctl.allow_retry(1) is True
    assert ctl.allow_retry(2) is True
    assert ctl.allow_retry(3) is False  # 达到 max_attempts

    over = SimpleNamespace(status=lambda: {"over": True})
    ctl2 = ReflexionController(cfg, _DummyProvider([]), budget=over)
    assert ctl2.allow_retry(1) is False


def test_judge_error_free():
    import asyncio

    cfg = ReflexionConfig(enabled=True, verifier="error_free")
    ctl = ReflexionController(cfg, _DummyProvider([]))

    v = asyncio.run(ctl.judge(_state(), errored=False, category="compose", sandbox=None, verify_command=None))
    assert v.success is True

    v = asyncio.run(ctl.judge(_state(), errored=True, category="compose", sandbox=None, verify_command=None))
    assert v.success is False

    v = asyncio.run(ctl.judge(_state(cancelled=True), errored=False, category=None, sandbox=None, verify_command=None))
    assert v.success is False


def test_judge_none_never_retries():
    import asyncio

    cfg = ReflexionConfig(enabled=True, verifier="none")
    ctl = ReflexionController(cfg, _DummyProvider([]))
    v = asyncio.run(ctl.judge(_state(), errored=True, category=None, sandbox=None, verify_command=None))
    assert v.success is True


def test_critique_uses_llm():
    import asyncio

    from myopencode.core.session import Message, Session

    prov = _DummyProvider(["反思：上一轮跑偏了，应当先规划。"])
    cfg = ReflexionConfig(enabled=True, use_critique=True)
    ctl = ReflexionController(cfg, prov)
    s = Session(session_id="s1", title="t")
    s.append(Message(role="user", content="写小说"))
    s.append(Message(role="assistant", content="直接开写"))
    out = asyncio.run(ctl.critique(s))
    assert "反思" in out