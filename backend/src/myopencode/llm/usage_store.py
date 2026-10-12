"""用量历史落库：JSONL 明细 + JSON 聚合，供成本统计与预算护栏查询。

- `records.jsonl`：append-only 明细，每行 {ts, model, session_id, input_tokens,
  output_tokens, cost}
- `totals.json`：按日/月/模型聚合，启动即加载，预算查询 O(1)

目录默认 `~/.config/myopencode/usage/`。线程安全，写入失败不影响主流程。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from ..security import crypto


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UsageStore:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.base = base_dir or os.path.join(
            os.path.expanduser("~"), ".config", "myopencode", "usage"
        )
        self._records_path = os.path.join(self.base, "records.jsonl")
        self._totals_path = os.path.join(self.base, "totals.json")
        self._lock = threading.Lock()
        # key: "day:2026-10-12" | "month:2026-10" | "model:gpt-4o:2026-10-12"
        self._totals: Dict[str, Dict[str, float]] = {}
        self._load()

    # ── 持久化基础 ──────────────────────────────────────────
    def _load(self) -> None:
        try:
            with open(self._totals_path, "r", encoding="utf-8") as fh:
                raw = fh.read()
            data = json.loads(crypto.decrypt_str(raw))
            if isinstance(data, dict):
                self._totals = data
        except (OSError, ValueError):
            self._totals = {}

    def _save_totals(self) -> None:
        try:
            os.makedirs(self.base, exist_ok=True)
            with open(self._totals_path, "w", encoding="utf-8") as fh:
                payload = json.dumps(self._totals, ensure_ascii=False, indent=2)
                fh.write(crypto.encrypt_str(payload))
        except OSError:  # pragma: no cover
            pass

    def _append_record(self, record: Dict[str, Any]) -> None:
        try:
            os.makedirs(self.base, exist_ok=True)
            line = json.dumps(record, ensure_ascii=False, default=str)
            with open(self._records_path, "a", encoding="utf-8") as fh:
                fh.write(crypto.encrypt_str(line) + "\n")
        except OSError:  # pragma: no cover
            pass

    # ── 写入 ────────────────────────────────────────────────
    def record(
        self,
        model: str,
        session_id: Optional[str],
        input_tokens: int,
        output_tokens: int,
        cost: float,
        ts: Optional[datetime] = None,
    ) -> None:
        now = ts or _utc_now()
        day = now.astimezone(timezone.utc).date().isoformat()
        month = day[:7]
        with self._lock:
            for key in ("day:{}".format(day), "month:{}".format(month)):
                t = self._totals.setdefault(
                    key, {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}
                )
                t["tokens_in"] = int(t.get("tokens_in", 0)) + input_tokens
                t["tokens_out"] = int(t.get("tokens_out", 0)) + output_tokens
                t["cost"] = float(t.get("cost", 0.0)) + cost

            mkey = "model:{}:{}".format(model, day)
            t = self._totals.setdefault(
                mkey, {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}
            )
            t["tokens_in"] = int(t.get("tokens_in", 0)) + input_tokens
            t["tokens_out"] = int(t.get("tokens_out", 0)) + output_tokens
            t["cost"] = float(t.get("cost", 0.0)) + cost

            self._append_record(
                {
                    "ts": now.astimezone(timezone.utc).isoformat(timespec="milliseconds"),
                    "model": model,
                    "session_id": session_id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                }
            )
            self._save_totals()

    # ── 查询 ────────────────────────────────────────────────
    def total_day(self, day: Optional[date] = None) -> Dict[str, float]:
        d = (day or date.today()).isoformat()
        t = self._totals.get("day:{}".format(d))
        return dict(t) if t else {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}

    def total_month(self, month: Optional[str] = None) -> Dict[str, float]:
        m = month or date.today().isoformat()[:7]
        t = self._totals.get("month:{}".format(m))
        return dict(t) if t else {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}

    def by_model(self, day: Optional[date] = None) -> Dict[str, Dict[str, float]]:
        d = (day or date.today()).isoformat()
        prefix = "model:"
        suffix = ":{}".format(d)
        out: Dict[str, Dict[str, float]] = {}
        for key, t in self._totals.items():
            if key.startswith(prefix) and key.endswith(suffix):
                out[key[len(prefix) : -len(suffix)]] = dict(t)
        return out

    def summary(self) -> Dict[str, Any]:
        today = self.total_day()
        month = self.total_month()
        return {
            "today": today,
            "this_month": month,
            "by_model_today": self.by_model(),
        }