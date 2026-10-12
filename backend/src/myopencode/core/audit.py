"""审计日志：append-only JSONL，记录谁/何时/做了什么/审批决定/改动文件。

独立于普通日志，用于合规追溯；写入前统一脱敏。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from ..security import crypto
from . import tracing
from .observability import redact


class AuditLogger:
    def __init__(self, path: Optional[str], enabled: bool = True) -> None:
        self.path = os.path.expanduser(path) if path else None
        self.enabled = enabled and bool(self.path)

    def record(self, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        tc = tracing.current()
        line: dict = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": event,
        }
        for k in ("trace_id", "session_id", "span_id"):
            if tc.get(k):
                line[k] = tc[k]
        line.update(fields)
        line = redact(line)
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(crypto.encrypt_str(json.dumps(line, ensure_ascii=False, default=str)) + "\n")
        except OSError:  # pragma: no cover - 审计失败不应影响主流程
            pass