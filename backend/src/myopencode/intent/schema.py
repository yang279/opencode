"""意图识别数据模型与常量。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# ── 语义分类体系 ─────────────────────────────────────────────
CATEGORY_CODE_EDIT = "code_edit"
CATEGORY_CODE_READ = "code_read"
CATEGORY_EXPLORE = "explore"
CATEGORY_EXECUTE = "execute"
CATEGORY_QUESTION = "question"
CATEGORY_PLAN = "plan"
CATEGORY_CHAT = "chat"
CATEGORY_COMPOSE = "compose"
CATEGORY_UNKNOWN = "unknown"

# 供 LLM 分类使用的合法类别（不含 unknown，unknown 是内部兜底）
INTENT_CATEGORIES = [
    CATEGORY_CODE_EDIT,
    CATEGORY_CODE_READ,
    CATEGORY_EXPLORE,
    CATEGORY_EXECUTE,
    CATEGORY_QUESTION,
    CATEGORY_PLAN,
    CATEGORY_COMPOSE,
    CATEGORY_CHAT,
]

# ── 工具分组（与 tools 的 category 对齐）──────────────────────
GROUP_READ = "read"
GROUP_WRITE = "write"
GROUP_EXECUTE = "execute"
GROUP_SKILL = "skill"
GROUP_MEMORY = "memory"
GROUP_MCP = "mcp"
GROUP_INTERRUPT = "interrupt"
GROUP_PLAN = "plan"
GROUP_RAG = "rag"

# 破坏性工具组（安全 gating 时，仅 code_edit / execute 类意图才允许）
DESTRUCTIVE_GROUPS = [GROUP_WRITE, GROUP_EXECUTE, GROUP_MCP]

# 常开组：无论什么意图都保留（含 plan/delegate 等编排工具 + rag_search 检索）
ALWAYS_GROUPS = [GROUP_SKILL, GROUP_MEMORY, GROUP_INTERRUPT, GROUP_PLAN, GROUP_RAG]

# 意图 → 允许的工具组（skill/memory 由 ToolRecognizer 额外追加）
INTENT_TO_TOOL_GROUPS: Dict[str, List[str]] = {
    CATEGORY_CODE_EDIT: [GROUP_READ, GROUP_WRITE, GROUP_EXECUTE, GROUP_MCP],
    CATEGORY_CODE_READ: [GROUP_READ],
    CATEGORY_EXPLORE: [GROUP_READ],
    CATEGORY_EXECUTE: [GROUP_READ, GROUP_EXECUTE, GROUP_MCP],
    CATEGORY_QUESTION: [],
    CATEGORY_PLAN: [GROUP_READ],
    CATEGORY_COMPOSE: [GROUP_READ, GROUP_WRITE],
    CATEGORY_CHAT: [],
    CATEGORY_UNKNOWN: [],
}


@dataclass
class Intent:
    """一次识别的结果。"""

    category: str = CATEGORY_UNKNOWN
    confidence: float = 0.0
    tool_names: Optional[List[str]] = None  # None = 全部工具
    needs_rag: bool = False
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "tool_names": self.tool_names,
            "needs_rag": self.needs_rag,
            "reasoning": self.reasoning,
        }