"""记忆数据模型：语义记忆（稳定事实）与场景记忆（episode）。"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict


def _now() -> float:
    return time.time()


def _uuid() -> str:
    return uuid.uuid4().hex


@dataclass
class SemanticMemory:
    """语义记忆：关于用户偏好、项目约定等跨会话的稳定事实。"""

    content: str
    category: str = "general"
    importance: int = 3
    id: str = field(default_factory=_uuid)
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    last_accessed: float = field(default_factory=_now)
    times_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "importance": self.importance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed": self.last_accessed,
            "times_used": self.times_used,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SemanticMemory":
        return cls(
            id=str(d.get("id", "")),
            content=str(d.get("content", "")),
            category=str(d.get("category", "general")),
            importance=int(d.get("importance", 3)),
            created_at=float(d.get("created_at", _now())),
            updated_at=float(d.get("updated_at", _now())),
            last_accessed=float(d.get("last_accessed", _now())),
            times_used=int(d.get("times_used", 0)),
        )


@dataclass
class EpisodicMemory:
    """场景记忆：一次会话的摘要记录（做了什么、结论、结果）。"""

    session_id: str
    title: str
    summary: str
    start_ts: float = field(default_factory=_now)
    end_ts: float = field(default_factory=_now)
    message_count: int = 0
    id: str = field(default_factory=_uuid)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "title": self.title,
            "summary": self.summary,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "message_count": self.message_count,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EpisodicMemory":
        return cls(
            id=str(d.get("id", "")),
            session_id=str(d.get("session_id", "")),
            title=str(d.get("title", "")),
            summary=str(d.get("summary", "")),
            start_ts=float(d.get("start_ts", _now())),
            end_ts=float(d.get("end_ts", _now())),
            message_count=int(d.get("message_count", 0)),
        )