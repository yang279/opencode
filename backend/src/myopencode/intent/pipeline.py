"""意图识别管道：语义 → 工具 → RAG（预留），按顺序串联。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..config.schema import AppConfig, IntentConfig
from ..core.session import Session
from ..llm.base import LLMProvider
from .base import RecognitionContext, Recognizer
from .rag import RagRecognizer
from .schema import CATEGORY_UNKNOWN, Intent
from .semantic import SemanticRecognizer
from .tool_select import ToolRecognizer


def build_intent_pipeline(
    config: AppConfig, recognition_provider: LLMProvider
) -> "IntentPipeline":
    """根据配置组装完整识别管道（供启动时与 PUT /config 热更新时复用）。"""
    return IntentPipeline(
        config.intent,
        [
            SemanticRecognizer(config.intent, recognition_provider),
            ToolRecognizer(config.intent),
            RagRecognizer(),
        ],
    )


class IntentPipeline:
    def __init__(
        self,
        config: IntentConfig,
        recognizers: Optional[List[Recognizer]] = None,
    ) -> None:
        self.config = config
        self._recognizers: List[Recognizer] = list(recognizers or [])

    async def recognize(
        self, session: Session, user_message: str, tools_meta: List[Dict[str, Any]]
    ) -> Intent:
        """执行识别管道，返回最终 Intent。任何一步异常都退化为「全工具 + 未知意图」。"""
        if not self.config.enabled:
            return Intent(category=CATEGORY_UNKNOWN, tool_names=None)

        intent = Intent()
        ctx = RecognitionContext(
            session=session,
            user_message=user_message,
            tools_meta=tools_meta,
            config=self.config,
        )
        for recognizer in self._recognizers:
            try:
                intent = await recognizer.recognize(ctx, intent)
            except Exception:
                # 单步失败不中断，最终由 tool_names=None 兜底
                continue
        return intent