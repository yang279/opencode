"""记忆编排：组装上下文（system 段 + 裁剪 messages）与会话结束固化。"""
from __future__ import annotations

from typing import List, Optional, Tuple

from ..config.schema import MemoryConfig
from ..core import tracing
from ..core.session import Message, Session
from .short_term import ShortTermMemory
from .store import MemoryStore
from .summarizer import Summarizer


class MemoryManager:
    def __init__(
        self,
        config: MemoryConfig,
        store: MemoryStore,
        summarizer: Summarizer,
        short_term: ShortTermMemory,
    ) -> None:
        self.config = config
        self.store = store
        self.summarizer = summarizer
        self.short_term = short_term

    async def build_context(
        self,
        session: Session,
        system_prompt: str,
        skills_section: str,
        model: Optional[str] = None,
    ) -> Tuple[str, List[Message]]:
        """返回 (完整 system_prompt 文本, 发送给 LLM 的 messages)。"""
        with tracing.span("memory.build_context"):
            summary, messages = await self.short_term.compact(
                session.messages, session.summary or "", model=model
            )
        folded = len(session.messages) - len(messages)
        if folded > 0:
            session.summary = summary
            session.summary_compressed_count += folded
            # 真正裁剪：移除已折叠消息，防止每轮重复摘要 + 持久化膨胀
            session.messages = messages

        parts: List[str] = []
        if system_prompt:
            parts.append(system_prompt)
        if skills_section:
            parts.append(skills_section)
        memory_section = self._memory_section(session) if self.config.enabled else ""
        if memory_section:
            parts.append(memory_section)
        if session.summary:
            parts.append("## 会话摘要\n" + session.summary)
        return "\n\n".join(parts) if parts else "", messages

    def _memory_section(self, session: Session) -> str:
        query = ""
        for m in reversed(session.messages):
            if m.role == "user":
                query = m.content or ""
                break

        sections: List[str] = []
        if self.config.semantic_enabled:
            facts = self.store.search_facts(query, limit=20)
            if facts:
                lines = ["## 长期记忆（语义）"]
                lines.extend("- {}".format(f.content) for f in facts)
                sections.append("\n".join(lines))

        if self.config.episodic_enabled:
            episodes = [
                e
                for e in self.store.search_episodes(query, limit=5)
                if e.session_id != session.session_id
            ]
            if episodes:
                lines = ["## 场景记忆（历史会话）"]
                lines.extend(
                    "- {}: {}".format(e.title, e.summary[:200]) for e in episodes
                )
                sections.append("\n".join(lines))

        return "\n\n".join(sections)

    async def finalize_session(self, session: Session) -> None:
        """会话结束：固化 episode 摘要，可选自动抽取语义记忆。不抛错影响主流程。"""
        if not self.config.enabled or not session.messages:
            return
        try:
            with tracing.span("memory.finalize"):
                summary = await self.summarizer.summarize_session(session.messages)
            if summary and self.config.episodic_enabled:
                title = (session.title or "未命名会话")[:50]
                self.store.add_episode(
                    session.session_id, title, summary, len(session.messages)
                )
            if summary and self.config.semantic_enabled and self.config.auto_extract:
                for fact in (await self.summarizer.extract_facts(summary))[:20]:
                    try:
                        self.store.add_fact(fact)
                    except ValueError:
                        continue
        except Exception:
            pass