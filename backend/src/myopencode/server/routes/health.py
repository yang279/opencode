"""健康检查、配置读取与热更新。"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from ... import __version__
from ...config.loader import parse_config_dict, save_config
from ...core.backup import BackupManager
from ...core.metrics import render_prometheus
from ...core.reflexion import ReflexionController
from ...intent.pipeline import build_intent_pipeline
from ...llm import usage
from ...llm.budget import BudgetGuard
from ...llm.registry import available_providers, create_provider, create_recognition_provider
from ...security.content_filter import ContentFilter
from ...security.policy import PermissionPolicy
from ...security.safety import SafetyGate
from ...tools.sandbox import Sandbox

router = APIRouter()

_SENSITIVE_KEYS = ("api_key", "summary_api_key")


def _redact_config_dict(d: dict) -> dict:
    """脱敏配置：把所有敏感的 key 字段置 None，绝不让明文离开后端。"""
    d = dict(d)
    for name, pc in d.get("providers", {}).items():
        if isinstance(pc, dict) and pc.get("api_key"):
            pc = dict(pc)
            pc["api_key"] = None
            d["providers"][name] = pc
    for section in ("intent", "memory"):
        obj = d.get(section)
        if isinstance(obj, dict):
            for k in _SENSITIVE_KEYS:
                if obj.get(k):
                    obj = dict(obj)
                    obj[k] = None
                    d[section] = obj
    return d


def _preserve_secrets(body: dict, current) -> None:
    """PUT /config 时：body 里为空的敏感字段回填当前值，避免覆盖丢 key。"""
    providers = body.get("providers")
    if isinstance(providers, dict):
        for name, pc in providers.items():
            if isinstance(pc, dict) and not pc.get("api_key"):
                old_pc = current.providers.get(name)
                if old_pc is not None and old_pc.api_key:
                    pc["api_key"] = old_pc.api_key

    intent = body.get("intent")
    if isinstance(intent, dict) and not intent.get("api_key") and current.intent.api_key:
        intent["api_key"] = current.intent.api_key

    memory = body.get("memory")
    if isinstance(memory, dict) and not memory.get("summary_api_key") and current.memory.summary_api_key:
        memory["summary_api_key"] = current.memory.summary_api_key


@router.get("/health")
async def health(request: Request):
    return {
        "status": "ok",
        "version": __version__,
        "provider": request.app.state.config.provider,
        "available_providers": available_providers(),
    }


@router.get("/metrics")
async def metrics(request: Request):
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(render_prometheus(request.app.state.metrics))


@router.get("/config")
async def get_config(request: Request):
    return _redact_config_dict(asdict(request.app.state.config))


@router.put("/config")
async def update_config(request: Request):
    body = await request.json()
    state = request.app.state
    _preserve_secrets(body, state.config)

    try:
        new_config = parse_config_dict(body)
        provider = create_provider(new_config)
        recognition_provider = create_recognition_provider(new_config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    policy = PermissionPolicy(new_config.permissions)
    sandbox = Sandbox(new_config.sandbox, new_config.working_dir)
    backup = BackupManager(new_config.backup)

    state.config = new_config
    state.provider = provider
    state.policy = policy
    state.sandbox = sandbox
    state.backup = backup
    usage.configure(new_config.llm.pricing)
    state.agent.set_provider(provider)
    state.agent.set_config(new_config)
    state.agent.set_intent(build_intent_pipeline(new_config, recognition_provider))
    state.agent.set_safety(SafetyGate(new_config.safety, recognition_provider))
    state.agent.set_content_filter(ContentFilter(new_config.safety, recognition_provider))

    usage_store = getattr(state, "usage_store", None)
    if usage_store is not None:
        new_budget = BudgetGuard(new_config.llm, usage_store)
        usage.set_budget_sink(new_budget.record)
        state.budget = new_budget
        state.agent.set_budget(new_budget)

    new_reflexion = ReflexionController(
        new_config.reflexion,
        provider,
        budget=getattr(state, "budget", None),
        metrics=getattr(state, "metrics", None),
    )
    state.reflexion = new_reflexion
    state.agent.set_reflexion(new_reflexion)

    audit = getattr(state, "audit", None)
    if audit is not None:
        audit.record("config_update", changed_keys=sorted(body.keys()))

    saved_path = save_config(new_config)
    return {"ok": True, "config": _redact_config_dict(asdict(new_config)), "saved_to": saved_path}