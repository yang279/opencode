"""进程内指标：计数器 + 直方图（含分桶），供 /metrics 输出（Prometheus 文本格式）。"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Dict, List, Tuple

# 延迟直方图分桶上限（秒），超出落入最后一桶（+Inf）
_LATENCY_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]


def _key(name: str, labels: Dict[str, str]) -> str:
    if not labels:
        return name
    return name + "{" + ",".join(f'{k}="{v}"' for k, v in sorted(labels.items())) + "}"


def _bucket_label(tail: str, bound: str) -> str:
    if not tail:
        return '{le="%s"}' % bound
    inner = tail[1:-1]
    return "{" + inner + ',le="%s"}' % bound


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = defaultdict(int)
        # name{labels} -> (count, sum)
        self._histograms: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        # name{labels} -> per-bucket 计数（长度 = len(_LATENCY_BUCKETS) + 1）
        self._buckets: Dict[str, List[int]] = defaultdict(lambda: [0] * (len(_LATENCY_BUCKETS) + 1))

    def incr(self, name: str, value: int = 1, **labels: str) -> None:
        key = _key(name, labels)
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, value: float, **labels: str) -> None:
        key = _key(name, labels)
        with self._lock:
            count, total = self._histograms[key]
            self._histograms[key] = (count + 1, total + value)

    def observe_histogram(self, name: str, value: float, **labels: str) -> None:
        key = _key(name, labels)
        with self._lock:
            count, total = self._histograms[key]
            self._histograms[key] = (count + 1, total + value)
            b = self._buckets[key]
            for i, ub in enumerate(_LATENCY_BUCKETS):
                if value <= ub:
                    b[i] += 1
                    break
            else:
                b[-1] += 1

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "histograms": {
                    k: {"count": c, "sum": s} for k, (c, s) in self._histograms.items()
                },
                "buckets": {
                    k: {"bounds": list(_LATENCY_BUCKETS), "counts": list(v)}
                    for k, v in self._buckets.items()
                },
            }


_default: "Metrics | None" = None


def set_default(m: Metrics) -> None:
    global _default
    _default = m


def incr(name: str, value: int = 1, **labels: str) -> None:
    if _default is not None:
        _default.incr(name, value, **labels)


def observe(name: str, value: float, **labels: str) -> None:
    if _default is not None:
        _default.observe(name, value, **labels)


def observe_histogram(name: str, value: float, **labels: str) -> None:
    if _default is not None:
        _default.observe_histogram(name, value, **labels)


def render_prometheus(m: Metrics) -> str:
    snap = m.snapshot()
    lines: List[str] = []
    for key, value in snap["counters"].items():
        base = key.split("{", 1)[0]
        lines.append(f"# TYPE {base} counter")
        lines.append(f"{key} {value}")
    for key, hist in snap["histograms"].items():
        base = key.split("{", 1)[0]
        tail = key[len(base):]
        bdata = snap["buckets"].get(key)
        if bdata is not None:
            lines.append(f"# TYPE {base} histogram")
            counts = bdata["counts"]
            bounds = bdata["bounds"]
            cum = 0
            for i, ub in enumerate(bounds):
                cum += counts[i]
                lines.append(f"{base}_bucket{_bucket_label(tail, str(ub))} {cum}")
            cum += counts[-1]
            lines.append(f'{base}_bucket{_bucket_label(tail, "+Inf")} {cum}')
            lines.append(f"{base}_sum{tail} {hist['sum']}")
            lines.append(f"{base}_count{tail} {hist['count']}")
        else:
            lines.append(f"# TYPE {base}_sum counter")
            lines.append(f"{base}_sum{tail} {hist['sum']}")
            lines.append(f"# TYPE {base}_count counter")
            lines.append(f"{base}_count{tail} {hist['count']}")
    return "\n".join(lines) + ("\n" if lines else "")
