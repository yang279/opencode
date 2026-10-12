from myopencode.memory.short_term import estimate_tokens, resolve_context_window


def test_estimate_tokens_cjk_vs_ascii():
    assert estimate_tokens("") == 0
    assert estimate_tokens("你好世界") == 4  # 4 个中文字 = 4 token
    assert estimate_tokens("hello") == 1  # 5 ascii -> 5//4 = 1
    assert estimate_tokens("hello world") == 2  # 11 ascii -> 11//4 = 2
    assert estimate_tokens("ab世界") == 2  # cjk=2 + other=2 -> 2//4 = 0


def test_estimate_tokens_not_underestimating_cjk():
    # 13 个中文字：旧算法 len//4 会低估；新算法应精确为 13
    assert estimate_tokens("这是一个很长的中文句子测试") == 13


def test_resolve_context_window_known():
    assert resolve_context_window("deepseek-v4-pro") == int(128000 * 0.8)
    assert resolve_context_window("claude-3-5-sonnet-latest") == int(200000 * 0.8)
    assert resolve_context_window("llama3") == int(8192 * 0.8)


def test_resolve_context_window_unknown():
    assert resolve_context_window(None) is None
    assert resolve_context_window("some-unknown-model") is None