"""诊断自检与诊断包导出。"""
from __future__ import annotations

import io
import json
import os
import zipfile
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ... import __version__
from ...core import tracing
from ...core.metrics import render_prometheus

router = APIRouter()


def _get_rusage_maxrss() -> int | None:
    try:
        import resource  # POSIX only

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:  # pragma: no cover
        return None


def _dir_size(path: str | None) -> int | None:
    if not path:
        return None
    path = os.path.expanduser(path)
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    continue
        return total
    except OSError:
        return None


@router.get("/diagnostics")
async def diagnostics(request: Request):
    state = request.app.state
    cfg = state.config

    sandbox = getattr(state, "sandbox", None)
    metrics = getattr(state, "metrics", None)
    audit = getattr(state, "audit", None)
    mcp = getattr(state, "mcp", None)

    provider_configured = bool(
        cfg.providers.get(cfg.resolve_provider()) and
        cfg.providers.get(cfg.resolve_provider()).api_key
    )

    metrics_snapshot = metrics.snapshot() if metrics is not None else {}
    # 只暴露计数总量，不暴露直方图明细，避免体积过大
    counters = {
        k: v for k, v in metrics_snapshot.get("counters", {}).items()
    }

    return {
        "status": "ok",
        "version": __version__,
        "provider": {
            "name": cfg.resolve_provider(),
            "model": cfg.resolve_model(),
            "configured": provider_configured,
            "fallbacks": cfg.llm.fallback_providers,
        },
        "sandbox": {
            "enabled": cfg.sandbox.enabled,
            "backend": sandbox.backend_name if sandbox is not None else "unknown",
            "allow_network": cfg.sandbox.allow_network,
        },
        "mcp": {
            "configured": list(cfg.mcp_servers.keys()),
            "connected": list(getattr(mcp, "_clients", {}).keys()) if mcp is not None else [],
        },
        "features": {
            "memory": cfg.memory.enabled,
            "intent": cfg.intent.enabled,
            "planning": cfg.planning.enabled,
            "safety": cfg.safety.enabled,
            "backup": cfg.backup.enabled,
            "content_filter": cfg.safety.content_filter_enabled,
        },
        "metrics": {"counters": counters},
        "process": {
            "maxrss_bytes": _get_rusage_maxrss(),
        },
        "disk": {
            "logs": _dir_size(cfg.observability.log_file),
            "audit": _dir_size(getattr(audit, "path", None)),
        },
    }


@router.get("/traces")
async def traces(request: Request, limit: int = 200):
    session_id = request.query_params.get("session_id")
    return {"spans": tracing.snapshot_spans(session_id=session_id, limit=limit)}


@router.get("/diagnostics/export")
async def diagnostics_export(request: Request):
    state = request.app.state
    cfg = state.config
    metrics = getattr(state, "metrics", None)
    audit = getattr(state, "audit", None)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 脱敏配置（复用 health 的脱敏逻辑）
        from .health import _redact_config_dict

        zf.writestr("config.json", json.dumps(_redact_config_dict(asdict(cfg)), ensure_ascii=False, indent=2))
        zf.writestr("diagnostics.json", json.dumps(await diagnostics(request), ensure_ascii=False, indent=2))
        if metrics is not None:
            zf.writestr("metrics.prom", render_prometheus(metrics))

        log_file = cfg.observability.log_file
        if log_file:
            lp = os.path.expanduser(log_file)
            if os.path.exists(lp):
                zf.write(lp, "logs/myopencode.log")

        audit_path = getattr(audit, "path", None)
        if audit_path and os.path.exists(os.path.expanduser(audit_path)):
            zf.write(os.path.expanduser(audit_path), "audit.jsonl")

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=myopencode-diagnostics.zip"},
    )