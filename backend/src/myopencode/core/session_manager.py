"""会话管理器：多会话生命周期 + 落盘持久化。"""
from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Dict, List, Optional

from ..security import crypto
from .session import Session


class SessionManager:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or os.path.join(
            os.path.expanduser("~"), ".config", "myopencode", "sessions.json"
        )
        self.sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = fh.read()
            data = json.loads(crypto.decrypt_str(raw))
            for item in data if isinstance(data, list) else []:
                s = Session.from_dict(item)
                if s.session_id:
                    self.sessions[s.session_id] = s
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        """原子落盘：写临时文件 + os.replace，避免并发写竞争/半写文件。"""
        try:
            payload = json.dumps(
                [s.to_dict() for s in self.sessions.values()],
                ensure_ascii=False,
                indent=2,
            )
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with self._lock:
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(crypto.encrypt_str(payload))
                os.replace(tmp, self.path)
        except OSError:
            pass

    def create(self) -> Session:
        s = Session(session_id=uuid.uuid4().hex[:12], title="新对话")
        self.sessions[s.session_id] = s
        self.save()
        return s

    def get(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)

    def add_usage(self, session_id: str, input_tokens: int, output_tokens: int) -> None:
        """累加某会话的 token 用量（不落盘，落盘由 run 结束/shutdown 触发）。"""
        s = self.sessions.get(session_id)
        if s is None:
            return
        s.tokens_in += int(input_tokens or 0)
        s.tokens_out += int(output_tokens or 0)

    def delete(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.save()
            return True
        return False

    def list(self) -> List[dict]:
        return [
            {
                "id": s.session_id,
                "title": s.title or "新对话",
                "message_count": len(s.messages),
                "resumable": bool(s.execution_state and s.execution_state.get("active")),
                "tokens_in": s.tokens_in,
                "tokens_out": s.tokens_out,
            }
            for s in reversed(list(self.sessions.values()))
        ]

    def ensure_default(self) -> None:
        if not self.sessions:
            self.create()

    def resolve_approval(self, approval_id: str, decision: str) -> bool:
        for s in self.sessions.values():
            item = s.pending_approvals.get(approval_id)
            if item is not None and not item.future.done():
                item.future.set_result(decision)
                return True
        return False

    def resolve_question(self, question_id: str, answer: str) -> bool:
        for s in self.sessions.values():
            item = s.pending_questions.get(question_id)
            if item is not None and not item.future.done():
                item.future.set_result(answer)
                return True
        return False

    def resolve_safety(self, safety_id: str, decision: str) -> bool:
        for s in self.sessions.values():
            item = s.pending_safety.get(safety_id)
            if item is not None and not item.future.done():
                item.future.set_result(decision)
                return True
        return False