"""用量与成本接口：汇总 + 明细查询 + 账单导出。"""
from __future__ import annotations

import csv
import io
import json
import os
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ...security import crypto

router = APIRouter()


def _read_records(path: str):
    """解密读取 records.jsonl，逐行返回 dict（损坏/明文行自动跳过）。"""
    records = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return records
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(crypto.decrypt_str(line))
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records


@router.get("/usage/summary")
async def usage_summary(request: Request):
    state = request.app.state
    store = getattr(state, "usage_store", None)
    budget = getattr(state, "budget", None)
    day = store.summary() if store is not None else {
        "today": {"tokens_in": 0, "tokens_out": 0, "cost": 0.0},
        "this_month": {"tokens_in": 0, "tokens_out": 0, "cost": 0.0},
        "by_model_today": {},
    }
    status = budget.status() if budget is not None else {
        "daily_spent": 0.0, "daily_budget": None,
        "monthly_spent": 0.0, "monthly_budget": None,
        "over": False, "warning": False, "hard_stop": True,
    }
    return {"budget": status, **day}


@router.get("/usage")
async def usage_records(
    request: Request,
    limit: int = 500,
    model: Optional[str] = None,
    session_id: Optional[str] = None,
):
    state = request.app.state
    store = getattr(state, "usage_store", None)
    if store is None:
        return {"records": []}
    records = []
    for rec in reversed(_read_records(os.path.join(store.base, "records.jsonl"))):
        if model and rec.get("model") != model:
            continue
        if session_id and rec.get("session_id") != session_id:
            continue
        records.append(rec)
        if len(records) >= limit:
            break
    return {"records": records}


@router.get("/usage/sessions")
async def usage_by_session(request: Request):
    """按会话聚合成本归因（tokens/cost/count）。"""
    state = request.app.state
    store = getattr(state, "usage_store", None)
    if store is None:
        return {"sessions": []}
    agg: dict = {}
    for rec in _read_records(os.path.join(store.base, "records.jsonl")):
        sid = rec.get("session_id") or "(未归属)"
        a = agg.setdefault(sid, {"session_id": sid, "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "count": 0})
        a["tokens_in"] = int(a["tokens_in"]) + int(rec.get("input_tokens", 0))
        a["tokens_out"] = int(a["tokens_out"]) + int(rec.get("output_tokens", 0))
        a["cost"] = float(a["cost"]) + float(rec.get("cost", 0.0))
        a["count"] += 1
    sessions = sorted(agg.values(), key=lambda x: x["cost"], reverse=True)
    return {"sessions": sessions}


@router.get("/usage/export")
async def usage_export(request: Request):
    """导出用量明细为 CSV 账单。"""
    state = request.app.state
    store = getattr(state, "usage_store", None)
    if store is None:
        return Response("", media_type="text/csv")

    records = _read_records(os.path.join(store.base, "records.jsonl"))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ts", "model", "session_id", "input_tokens", "output_tokens", "cost"])
    for r in records:
        writer.writerow(
            [
                r.get("ts", ""),
                r.get("model", ""),
                r.get("session_id", ""),
                r.get("input_tokens", 0),
                r.get("output_tokens", 0),
                r.get("cost", 0.0),
            ]
        )
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage.csv"},
    )