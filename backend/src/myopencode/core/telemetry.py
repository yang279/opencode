"""轻量遥测导出：把 span 缓冲 + 指标快照按周期 POST 到远程端点。

- 由 `observability.otlp_endpoint` 开启，默认关闭。
- 采用简单 JSON 负载（非 OTLP protobuf），便于对接自建采集器/网关做二次转换。
- 后台守护线程、尽力而为：网络/序列化失败不影响主流程。
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from typing import Any, Dict, Optional, Set

from . import metrics as metrics_mod
from . import tracing


class TelemetryExporter:
    def __init__(self, endpoint: str, interval: float = 15.0) -> None:
        self.endpoint = endpoint
        self.interval = interval
        self._sent_spans: Set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _payload(self) -> Dict[str, Any]:
        spans = tracing.snapshot_spans(limit=200)
        fresh = []
        with self._lock:
            for s in spans:
                if s["span_id"] in self._sent_spans:
                    continue
                self._sent_spans.add(s["span_id"])
                fresh.append(s)
            if len(self._sent_spans) > 5000:
                # 防止集合无限膨胀
                self._sent_spans = {s["span_id"] for s in spans}
        metrics = metrics_mod._default
        return {
            "app": "myopencode",
            "ts": time.time(),
            "spans": fresh,
            "metrics": metrics.snapshot() if metrics is not None else {},
        }

    def _post(self) -> None:
        data = json.dumps(self._payload(), ensure_ascii=False, default=str).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)  # noqa: S310
        except Exception:  # pragma: no cover
            pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.interval)
            if self._stop.is_set():
                break
            self._post()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="telemetry")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None