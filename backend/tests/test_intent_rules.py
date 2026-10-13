import asyncio

from myopencode.config.schema import IntentConfig
from myopencode.core.session import Session
from myopencode.intent.base import RecognitionContext
from myopencode.intent.schema import (
    CATEGORY_CODE_EDIT,
    CATEGORY_CODE_READ,
    CATEGORY_COMPOSE,
    CATEGORY_EXECUTE,
    CATEGORY_EXPLORE,
    CATEGORY_PLAN,
    CATEGORY_UNKNOWN,
    Intent,
)
from myopencode.intent.semantic import SemanticRecognizer
from myopencode.intent.tool_select import ToolRecognizer
from myopencode.intent.schema import CATEGORY_QUESTION, CATEGORY_CHAT
from myopencode.llm.base import LLMEvent


def test_match_rules_hit():
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("npm run build") == CATEGORY_EXECUTE
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("pip install requests") == CATEGORY_EXECUTE
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("帮我设计一个架构方案") == CATEGORY_PLAN
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("refactor 这个函数") == CATEGORY_CODE_EDIT
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("重命名这个变量") == CATEGORY_CODE_EDIT
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("解释这个函数") == CATEGORY_CODE_READ
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("grep 日志") == CATEGORY_EXPLORE
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("写一个故事") == CATEGORY_COMPOSE
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("翻译这段英文") == CATEGORY_COMPOSE
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("润色这段文案") == CATEGORY_COMPOSE


def test_match_rules_defer_ambiguous():
    # 模糊动词不落地规则，交给小模型
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("修改这篇文章") is None
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("优化这段代码") is None
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("添加一个功能") is None
    assert SemanticRecognizer(IntentConfig(), None)._match_rules("写一个排序函数") is None


class FakeProvider:
    def __init__(self, delta: str):
        self.delta = delta

    async def stream(self, messages, tools, temperature=None, max_tokens=None, extra_body=None):
        yield LLMEvent(kind="text", delta=self.delta)


async def _recognize(provider, text):
    rec = SemanticRecognizer(IntentConfig(), provider)
    ctx = RecognitionContext(session=Session(session_id="s"), user_message=text)
    return await rec.recognize(ctx, Intent())


def test_llm_classify_and_gate():
    # 规则不命中的歧义句，交给小模型
    intent = asyncio.run(_recognize(FakeProvider('{"category":"compose","confidence":0.99}'), "把这段文字再打磨一下"))
    assert intent.category == CATEGORY_COMPOSE
    assert intent.reasoning == "小模型分类"

    # 低置信度 → 保持 unknown（全量工具）
    intent = asyncio.run(_recognize(FakeProvider('{"category":"code_edit","confidence":0.2}'), "这段文字再打磨一下"))
    assert intent.category == CATEGORY_UNKNOWN


def test_parse_fallback_non_json():
    # 非 JSON 输出也能按类别名兜底抽取
    intent = asyncio.run(_recognize(FakeProvider("分类结果：code_edit"), "这段文字再打磨一下"))
    assert intent.category == CATEGORY_CODE_EDIT


def test_rag_search_tool_always_available():
    # rag_search 属于常开组，即使 question/chat 意图（工具组为空）也必须保留
    tools_meta = [
        {"name": "rag_search", "category": "rag", "description": ""},
        {"name": "read_file", "category": "read", "description": ""},
        {"name": "run_shell", "category": "execute", "description": ""},
    ]
    rec = ToolRecognizer(IntentConfig())
    ctx = RecognitionContext(session=Session(session_id="s"), user_message="x", tools_meta=tools_meta)

    for category in (CATEGORY_QUESTION, CATEGORY_CHAT, CATEGORY_CODE_READ):
        intent = asyncio.run(rec.recognize(ctx, Intent(category=category)))
        assert "rag_search" in intent.tool_names, "{} 意图下 rag_search 应常开".format(category)

    # question 意图下 read/execute 工具仍被剪枝，不会被误放行
    intent = asyncio.run(rec.recognize(ctx, Intent(category=CATEGORY_QUESTION)))
    assert "read_file" not in intent.tool_names
    assert "run_shell" not in intent.tool_names
