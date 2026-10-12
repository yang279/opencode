"""语义识别：规则关键词优先，未命中用识别模型兜底（混合）。"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..config.schema import IntentConfig
from ..core.session import Message
from ..llm.base import LLMProvider
from .base import RecognitionContext
from .schema import (
    CATEGORY_CHAT,
    CATEGORY_CODE_EDIT,
    CATEGORY_CODE_READ,
    CATEGORY_COMPOSE,
    CATEGORY_EXECUTE,
    CATEGORY_EXPLORE,
    CATEGORY_PLAN,
    INTENT_CATEGORIES,
    Intent,
)

# 小模型分类的最低置信度：低于则判 unknown（全量工具，不误导剪枝）
_MIN_CONFIDENCE = 0.5

# 规则表：类别 -> 关键词（小写子串匹配）。
# 原则：只放「无歧义的技术/创作信号」；模糊动词（修改/添加/优化/写一个…）一律交给
# 小模型，避免宽规则误伤。命中顺序即优先级。
_RULES: List[Tuple[str, List[str]]] = [
    (
        CATEGORY_EXECUTE,
        [
            "npm run", "npm install", "npm test", "npx ", "pip install", "cargo build",
            "cargo test", "cargo ", "pytest", "poetry ", "mvn ", "gradle", "make ",
            "docker ", "kubectl", "git commit", "git push", "git clone",
            "运行测试", "跑测试", "跑一下测试", "构建", "编译", "部署", "安装依赖",
        ],
    ),
    (
        CATEGORY_PLAN,
        [
            "怎么做", "该怎么", "方案", "架构", "重构方案", "设计文档",
            "技术选型", "roadmap", "architecture",
        ],
    ),
    (
        CATEGORY_CODE_EDIT,
        [
            "refactor", "rename", "bugfix", "fix bug",
            "重命名", "重构", "修 bug", "修bug", "修复 bug",
            "改代码", "修改代码", "新增函数", "新增类", "新增接口",
            "写函数", "写个函数", "写个类", "实现这个功能", "实现功能",
        ],
    ),
    (
        CATEGORY_CODE_READ,
        [
            "解释", "explain", "what does", "how does", "understand",
            "这个函数", "这个类", "什么意思", "原理", "含义", "做什么",
        ],
    ),
    (
        CATEGORY_EXPLORE,
        [
            "grep", "locate", "搜索", "查找", "定位", "在哪里", "哪里有", "有哪些文件",
        ],
    ),
    (
        CATEGORY_COMPOSE,
        [
            "翻译", "润色", "扩写", "续写",
            "写一篇", "写篇", "写首诗", "写小说", "写文章", "写作文", "写文案",
            "写邮件", "写周报", "写报告", "写故事", "写剧本",
            "小说", "文案", "故事", "作文",
        ],
    ),
]

_LLM_SYSTEM = (
    "你是意图分类器。把用户消息分为以下之一，只输出 JSON，不要任何解释：\n"
    "- code_edit: 修改/新增/重构/删除代码或配置\n"
    "- code_read: 阅读/解释/理解代码\n"
    "- explore: 在代码库里搜索/查找/定位文件或符号\n"
    "- execute: 运行命令、构建、测试、部署、装依赖\n"
    "- question: 纯概念/知识问答（与代码库无关）\n"
    "- plan: 规划、架构设计、方案、只分析不修改\n"
    "- compose: 内容创作/写作（文章、小说、文案、翻译、润色等非代码文本）\n"
    "- chat: 纯粹闲聊寒暄\n\n"
    "关键区分：\n"
    "1. 写文章/写小说/写故事/写文案/翻译/润色 → compose；写函数/写代码/写脚本/实现功能 → code_edit\n"
    "2. 修改代码/改 bug → code_edit；修改文章/改文案 → compose\n"
    "3. 解释代码 → code_read；解释概念（如\"什么是闭包\"）→ question\n"
    "4. 架构/方案/设计文档/重构方案 → plan\n"
    "5. chat 仅用于真正无任务的闲聊，不要当兜底\n\n"
    "示例：\n"
    "「写一篇科幻小说」→ {\"category\":\"compose\",\"confidence\":0.99}\n"
    "「写一个排序函数」→ {\"category\":\"code_edit\",\"confidence\":0.99}\n"
    "「修改一下登录接口」→ {\"category\":\"code_edit\",\"confidence\":0.95}\n"
    "「润色这段文案」→ {\"category\":\"compose\",\"confidence\":0.95}\n"
    "「解释这个函数做什么」→ {\"category\":\"code_read\",\"confidence\":0.95}\n"
    "「npm run build 为什么报错」→ {\"category\":\"execute\",\"confidence\":0.9}\n"
    "「什么是依赖注入」→ {\"category\":\"question\",\"confidence\":0.95}\n"
    "「帮我设计一个高可用架构方案」→ {\"category\":\"plan\",\"confidence\":0.95}\n"
    "「今天天气怎么样」→ {\"category\":\"chat\",\"confidence\":0.9}\n"
    "「在项目里搜索日志相关代码」→ {\"category\":\"explore\",\"confidence\":0.95}\n\n"
    "只输出：{\"category\":\"...\",\"confidence\":0.0}"
)


class SemanticRecognizer:
    def __init__(self, config: IntentConfig, provider: LLMProvider) -> None:
        self.config = config
        self.provider = provider

    async def recognize(self, ctx: RecognitionContext, current: Intent) -> Intent:
        text = (ctx.user_message or "").strip()
        if not text:
            current.category = CATEGORY_CHAT
            current.confidence = 0.9
            current.reasoning = "空消息"
            return current

        category = self._match_rules(text)
        if category is not None:
            current.category = category
            current.confidence = 0.7
            current.reasoning = "规则命中"
            return current

        result = None
        try:
            result = await asyncio.wait_for(
                self._llm_classify(text), timeout=self.config.timeout
            )
        except Exception:
            result = None
        if result is not None:
            if result[1] >= _MIN_CONFIDENCE:
                current.category = result[0]
                current.confidence = result[1]
                current.reasoning = "小模型分类"
            # 低置信度：保持 unknown（全量工具），不误导剪枝
        return current

    def _match_rules(self, text: str) -> Optional[str]:
        low = text.lower()
        for category, keywords in _RULES:
            if any(k in low for k in keywords):
                return category
        return None

    async def _llm_classify(self, text: str) -> Optional[Tuple[str, float]]:
        msgs = [
            Message(role="system", content=_LLM_SYSTEM),
            Message(role="user", content=text),
        ]
        extra_body = {"enable_thinking": False} if self.config.disable_thinking else None
        parts: List[str] = []
        async for ev in self.provider.stream(
            msgs,
            [],
            temperature=self.config.temperature,
            max_tokens=max(self.config.max_tokens, 64),
            extra_body=extra_body,
        ):
            if ev.kind == "text" and ev.delta:
                parts.append(ev.delta)
        return self._parse_json("".join(parts).strip())

    def _parse_json(self, raw: str) -> Optional[Tuple[str, float]]:
        data: Optional[Dict[str, Any]] = None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError:
                    data = None
        if isinstance(data, dict):
            cat = str(data.get("category", "")).strip()
            if cat in INTENT_CATEGORIES:
                try:
                    conf = float(data.get("confidence", 0.0))
                except (TypeError, ValueError):
                    conf = 0.0
                return cat, max(0.0, min(1.0, conf))
        # 兜底：JSON 解析失败时，从原始文本里按类别名抽取（保守给中等置信度）
        low = raw.lower()
        for cat in INTENT_CATEGORIES:
            if cat in low:
                return cat, 0.5
        return None