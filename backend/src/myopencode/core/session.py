"""会话状态：保存对话历史与待审批项。"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    # 用户消息附带的原始附件（Claude 式文档块）：{name, media_type, data_b64}
    attachments: List[Dict[str, str]] = field(default_factory=list)

    def _attachment_text(self, att: Dict[str, str]) -> str:
        """解码 text/* 附件为 UTF-8 文本（解码失败返回空串）。"""
        try:
            return base64.b64decode(att.get("data_b64", "")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return ""

    def content_parts(self, provider_kind: str) -> Any:
        """返回发送给 LLM 的 content：无附件为纯字符串，有附件为 multipart 列表。

        - text/*：解码为带文件名头的 text 块（所有 provider 通用）
        - image/*、application/pdf：仅 anthropic 支持，映射为 image/document 块
        - 其他类型：跳过（前端已按 provider 能力拦截，此处防御）
        """
        if not self.attachments:
            return self.content

        parts: List[Dict[str, Any]] = []
        if self.content:
            parts.append({"type": "text", "text": self.content})
        for att in self.attachments:
            media = (att.get("media_type") or "").lower()
            data = att.get("data_b64", "")
            name = att.get("name", "附件")
            if media.startswith("text/"):
                text = self._attachment_text(att)
                parts.append({"type": "text", "text": "### {}\n{}".format(name, text)})
            elif media.startswith("image/"):
                if provider_kind == "anthropic":
                    parts.append(
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media, "data": data},
                        }
                    )
                elif provider_kind == "openai":
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:{};base64,{}".format(media, data)},
                        }
                    )
            elif provider_kind == "anthropic" and media == "application/pdf":
                parts.append(
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": media, "data": data},
                    }
                )
            # 其余类型（含非 anthropic 的 image/pdf）前端已拦截，这里忽略
        return parts if parts else self.content

    def to_openai_dict(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"role": self.role, "content": self.content_parts("openai")}
        if self.tool_calls is not None:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            msg["name"] = self.name
        return msg

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls is not None:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            d["name"] = self.name
        if self.attachments:
            d["attachments"] = self.attachments
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Message":
        return cls(
            role=d.get("role", "user"),
            content=d.get("content", ""),
            tool_calls=d.get("tool_calls"),
            tool_call_id=d.get("tool_call_id"),
            name=d.get("name"),
            attachments=d.get("attachments") or [],
        )


@dataclass
class ApprovalItem:
    approval_id: str
    tool: str
    args: Dict[str, Any]
    message: str
    future: Any  # asyncio.Future，用于 await 用户决策


@dataclass
class QuestionItem:
    question_id: str
    question: str
    future: Any  # asyncio.Future，用于 await 用户文字回答
    options: List[Dict[str, Any]] = field(default_factory=list)
    multi: bool = False


@dataclass
class SafetyItem:
    safety_id: str
    reasons: Any
    severity: str
    future: Any  # asyncio.Future，用于 await 用户 continue/abort


@dataclass
class Session:
    session_id: str
    title: str = ""
    messages: List[Message] = field(default_factory=list)
    pending_approvals: Dict[str, ApprovalItem] = field(default_factory=dict)
    pending_questions: Dict[str, QuestionItem] = field(default_factory=dict)
    pending_safety: Dict[str, SafetyItem] = field(default_factory=dict)
    summary: str = ""
    summary_compressed_count: int = 0
    execution_state: Optional[Dict[str, Any]] = None
    tokens_in: int = 0
    tokens_out: int = 0

    def append(self, message: Message) -> None:
        self.messages.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.session_id,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "summary": self.summary,
            "summary_compressed_count": self.summary_compressed_count,
            "execution_state": self.execution_state,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Session":
        return cls(
            session_id=d.get("id", ""),
            title=d.get("title", ""),
            messages=[Message.from_dict(m) for m in d.get("messages", [])],
            summary=d.get("summary", ""),
            summary_compressed_count=int(d.get("summary_compressed_count", 0)),
            execution_state=d.get("execution_state"),
            tokens_in=int(d.get("tokens_in", 0) or 0),
            tokens_out=int(d.get("tokens_out", 0) or 0),
        )