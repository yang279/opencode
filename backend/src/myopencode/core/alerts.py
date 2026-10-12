"""预算告警 webhook 通知（fire-and-forget，失败不影响主流程）。"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

_logger = logging.getLogger("myopencode.alerts")


async def send_alert(url: Optional[str], event: str, payload: Dict[str, Any]) -> None:
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json={"event": event, **payload})
    except Exception as exc:  # pragma: no cover - 通知失败静默
        _logger.warning("alert webhook failed: %s", exc)