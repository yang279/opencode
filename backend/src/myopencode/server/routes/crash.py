"""崩溃上报：前端捕获的未捕获异常写入本地 crash.log。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ...core.observability import redact

router = APIRouter()

_CRASH_LOG = os.path.join(
    os.path.expanduser("~"), ".config", "myopencode", "logs", "crash.log"
)


class CrashReport(BaseModel):
    message: str
    stack: Optional[str] = None
    source: Optional[str] = None


@router.post("/crash")
async def report_crash(report: CrashReport) -> dict:
    line = redact(
        {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "source": report.source or "frontend",
            "message": report.message,
            "stack": report.stack,
        }
    )
    try:
        os.makedirs(os.path.dirname(_CRASH_LOG), exist_ok=True)
        with open(_CRASH_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:  # pragma: no cover - 崩溃上报失败不应再抛
        pass
    return {"ok": True}