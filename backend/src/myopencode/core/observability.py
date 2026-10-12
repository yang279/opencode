"""结构化日志：JSON formatter + 初始化 + 脱敏。

所有业务日志走 stderr + 文件，绝不碰 stdout（stdout 保留给 Rust 壳层的握手行）。
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from . import tracing

# 日志 record 中由 logging 自带的属性，不当作业务字段输出
_STD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message",
}

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(client[_-]?secret|private[_-]?key)\s*[:=]\s*[^\s,}\"']+"),
]
_KEY_VALUE_RE = re.compile(
    r"(?i)(api[-_]?key|authorization|secret|token|password)\s*[:=]\s*[\"']?([^\"'\s,}]+)"
)
_SENSITIVE_KEYS = {
    "api_key", "apikey", "authorization", "token", "secret",
    "password", "access_token", "api-token", "auth",
}


def redact(value: Any) -> Any:
    """递归脱敏：密钥值、Bearer、敏感键名一律替换为 ***。"""
    if isinstance(value, dict):
        out: Dict[Any, Any] = {}
        for k, v in value.items():
            if str(k).lower().replace("-", "_") in _SENSITIVE_KEYS:
                out[k] = "***"
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        s = value
        for pat in _SECRET_PATTERNS:
            s = pat.sub("***", s)
        s = _KEY_VALUE_RE.sub(lambda m: m.group(1) + "=***", s)
        return s
    return value


class JsonFormatter(logging.Formatter):
    """单行 JSON 日志，自动注入 trace/span/session 上下文。"""

    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
        }
        tc = tracing.current()
        for k, v in tc.items():
            if v:
                data[k] = v
        data["event"] = record.getMessage()
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        for key, val in record.__dict__.items():
            if key in _STD_ATTRS or key.startswith("_"):
                continue
            data[key] = val
        return json.dumps(redact(data), ensure_ascii=False, default=str)


def setup_logging(config: Any) -> None:
    """根据 observability 配置初始化根 logger（幂等）。"""
    root = logging.getLogger()
    root.setLevel(str(getattr(config, "log_level", "info")).upper())
    if getattr(root, "_myopencode_configured", False):
        return
    root._myopencode_configured = True  # type: ignore[attr-defined]

    fmt = JsonFormatter()

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    root.addHandler(stderr_handler)

    log_file = getattr(config, "log_file", None)
    if log_file:
        path = os.path.expanduser(log_file)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            path, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # 压住 uvicorn/httpx/asyncio 噪声
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)