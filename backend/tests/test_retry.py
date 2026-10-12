import asyncio

from myopencode.config.schema import LLMConfig
from myopencode.core.session import Message
from myopencode.llm.base import LLMEvent
from myopencode.llm.retry import is_retryable, resilient_stream


class RateLimitError(Exception):
    status_code = 429


class RetryProv:
    def __init__(self, name, fail_before=1):
        self.name = name
        self.fail_before = fail_before
        self.calls = 0

    async def stream(self, messages, tools):
        self.calls += 1
        if self.calls <= self.fail_before:
            raise RateLimitError("limited")
        yield LLMEvent(kind="text", delta="ok[" + self.name + "]")


class MidStream:
    async def stream(self, messages, tools):
        yield LLMEvent(kind="text", delta="partial")
        raise RateLimitError("mid")


class Hang:
    async def stream(self, messages, tools):
        await asyncio.sleep(10)
        yield LLMEvent(kind="text", delta="x")


async def _collect(providers, cfg):
    out = []
    async for ev in resilient_stream(providers, [Message(role="user", content="x")], [], cfg):
        out.append(ev.delta)
    return "".join(out)


def _cfg(**kw):
    defaults = dict(timeout_seconds=1.0, max_retries=2, backoff_base=0.02, backoff_max=0.05, fallback_providers=[])
    defaults.update(kw)
    return LLMConfig(**defaults)


def test_is_retryable():
    assert is_retryable(RateLimitError())
    assert is_retryable(asyncio.TimeoutError())
    assert not is_retryable(ValueError("x"))


def test_retry_then_succeed():
    p = RetryProv("a", fail_before=1)
    assert asyncio.run(_collect([p], _cfg())) == "ok[a]"
    assert p.calls == 2


def test_fallback_after_exhaust():
    m = RetryProv("main", fail_before=99)
    f = RetryProv("fallback", fail_before=0)
    r = asyncio.run(_collect([m, f], _cfg(max_retries=1)))
    assert r == "ok[fallback]"
    assert m.calls == 2  # 1 try + 1 retry


def test_mid_stream_no_retry():
    try:
        asyncio.run(_collect([MidStream()], _cfg()))
        assert False, "should raise"
    except RateLimitError:
        pass


def test_timeout_raises():
    try:
        asyncio.run(_collect([Hang()], _cfg(timeout_seconds=0.1, max_retries=0)))
        assert False, "should raise"
    except asyncio.TimeoutError:
        pass