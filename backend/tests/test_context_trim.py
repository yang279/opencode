import asyncio

from myopencode.config.schema import MemoryConfig
from myopencode.core.session import Message, Session
from myopencode.memory.manager import MemoryManager
from myopencode.memory.short_term import ShortTermMemory


class _FakeSummarizer:
    def __init__(self):
        self.calls = 0

    async def summarize_conversation(self, messages, prior_summary=""):
        self.calls += 1
        return (prior_summary + "\n[折叠 {} 条]".format(len(messages))).strip()


def test_compact_folds_over_window():
    cfg = MemoryConfig(enabled=False, context_window_tokens=40, keep_recent_tokens=20)
    st = ShortTermMemory(_FakeSummarizer(), cfg)
    msgs = [
        Message(role="user", content="a" * 80),
        Message(role="assistant", content="b" * 80),
        Message(role="user", content="c" * 40),
    ]
    summary, kept = asyncio.run(st.compact(msgs, "", model=None))
    assert len(kept) < len(msgs)
    assert summary != ""


def test_build_context_trims_session():
    cfg = MemoryConfig(enabled=False, context_window_tokens=40, keep_recent_tokens=20)
    fake = _FakeSummarizer()
    st = ShortTermMemory(fake, cfg)
    mgr = MemoryManager(cfg, None, fake, st)
    session = Session(session_id="s", title="t")
    session.messages = [
        Message(role="user", content="a" * 80),
        Message(role="assistant", content="b" * 80),
        Message(role="user", content="c" * 40),
    ]
    asyncio.run(mgr.build_context(session, "", "", model=None))
    assert len(session.messages) < 3
    assert session.summary != ""
    assert session.summary_compressed_count > 0