"""识别器接口与上下文。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from ..config.schema import IntentConfig
from ..core.session import Session
from .schema import Intent


@dataclass
class RecognitionContext:
    """一次识别的输入上下文。"""

    session: Session
    user_message: str
    tools_meta: List[Dict[str, Any]] = field(default_factory=list)  # [{name, description, category}]
    config: Optional[IntentConfig] = None


class Recognizer(Protocol):
    """识别器接口：原地修改并返回 Intent，便于管道串联。"""

    async def recognize(self, ctx: RecognitionContext, current: Intent) -> Intent:
        ...  # pragma: no cover