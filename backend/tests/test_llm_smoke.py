"""真实 LLM 冒烟测试：默认跳过，需显式提供 API key 环境变量。"""
import os

import pytest

pytestmark = pytest.mark.llm

_NEEDS = os.environ.get("MYOPENCODE_TEST_API_KEY")


@pytest.mark.skipif(not _NEEDS, reason="需设置 MYOPENCODE_TEST_API_KEY 才运行")
def test_real_llm_streams_text():
    import asyncio

    from myopencode.config.schema import default_config
    from myopencode.core.session import Message
    from myopencode.llm.registry import create_provider

    cfg = default_config()
    cfg.providers["openai"].api_key = _NEEDS
    cfg.providers["openai"].model = os.environ.get("MYOPENCODE_TEST_MODEL", "gpt-4o-mini")
    cfg.providers["openai"].base_url = os.environ.get("MYOPENCODE_TEST_BASE_URL") or None

    async def _run():
        provider = create_provider(cfg)
        parts = []
        async for ev in provider.stream([Message(role="user", content="只回复 ok")], []):
            if ev.kind == "text":
                parts.append(ev.delta)
        assert "".join(parts).strip() != ""

    asyncio.run(_run())