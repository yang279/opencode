"""FastAPI 应用装配：注入配置、provider、工具、权限、skills、agent、mcp。"""
from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from typing import Callable, Optional

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from ..config.schema import AppConfig
from ..core.agent import Agent
from ..core.audit import AuditLogger
from ..core.backup import BackupManager
from ..core import metrics as metrics_mod
from ..core.metrics import Metrics
from ..core.reflexion import ReflexionController
from ..core.session_manager import SessionManager
from ..core.telemetry import TelemetryExporter
from ..intent.pipeline import build_intent_pipeline
from ..llm import usage
from ..llm.budget import BudgetGuard
from ..llm.registry import create_provider, create_recognition_provider, create_summary_provider
from ..llm.usage_store import UsageStore
from ..mcp.registry import McpRegistry
from ..memory.manager import MemoryManager
from ..memory.short_term import ShortTermMemory
from ..memory.store import MemoryStore
from ..memory.summarizer import Summarizer
from ..memory.tools import (
    ForgetMemoryTool,
    ListMemoryTool,
    RecallMemoryTool,
    SaveMemoryTool,
)
from ..rag.service import RagService
from ..security.content_filter import ContentFilter
from ..security.policy import PermissionPolicy
from ..security.safety import SafetyGate
from ..skills.load_skill_tool import LoadSkillTool
from ..skills.registry import SkillRegistry, scan_skills
from ..tools.registry import ToolRegistry
from ..tools.sandbox import Sandbox
from .routes import crash, diagnostics, health, memory, meta, sessions, undo, usage as usage_routes, workspace, rag
from .ws import manager, websocket_endpoint


def create_app(
    config: AppConfig,
    token: str | None = None,
    on_startup: Optional[Callable[["FastAPI"], None]] = None,
) -> FastAPI:
    token = token or secrets.token_hex(16)

    provider = create_provider(config)
    usage.configure(config.llm.pricing)
    skill_registry = SkillRegistry(scan_skills(config.working_dir))

    memory_store = MemoryStore()
    memory_store.load()
    summarizer = Summarizer(create_summary_provider(config))
    short_term = ShortTermMemory(summarizer, config.memory)
    memory_manager = MemoryManager(config.memory, memory_store, summarizer, short_term)

    recognition_provider = create_recognition_provider(config)
    intent_pipeline = build_intent_pipeline(config, recognition_provider)
    safety_gate = SafetyGate(config.safety, recognition_provider)
    content_filter = ContentFilter(config.safety, recognition_provider)

    sandbox = Sandbox(config.sandbox, config.working_dir)
    backup = BackupManager(config.backup)
    metrics = Metrics()
    metrics_mod.set_default(metrics)
    audit = AuditLogger(config.observability.audit_file, config.observability.audit_enabled)

    extra_tools = [LoadSkillTool(skill_registry)]
    if config.memory.enabled:
        extra_tools.extend(
            [
                SaveMemoryTool(memory_store),
                RecallMemoryTool(memory_store),
                ListMemoryTool(memory_store),
                ForgetMemoryTool(memory_store),
            ]
        )
    tools = ToolRegistry(extra=extra_tools)
    policy = PermissionPolicy(config.permissions)
    session_manager = SessionManager()
    session_manager.load()
    session_manager.ensure_default()
    usage.set_usage_sink(session_manager.add_usage)
    usage_store = UsageStore()
    budget = BudgetGuard(config.llm, usage_store)
    usage.set_budget_sink(budget.record)
    reflexion = ReflexionController(config.reflexion, provider, budget=budget, metrics=metrics)
    mcp_registry = McpRegistry(config.mcp_servers, sandbox=sandbox)
    rag_service = RagService(config.rag)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 先连接 MCP server 并注入其工具，再打印握手，确保「握手」=「启动完成」
        await mcp_registry.connect_all()
        for t in mcp_registry.tools():
            tools.add(t)
        telemetry = None
        if config.observability.otlp_endpoint:
            telemetry = TelemetryExporter(config.observability.otlp_endpoint)
            telemetry.start()
        if on_startup is not None:
            on_startup(app)
        yield
        if telemetry is not None:
            telemetry.stop()
        session_manager.save()
        memory_store.save()
        await mcp_registry.close_all()

    app = FastAPI(title="myopencode backend", lifespan=lifespan)

    # 前端开发时从 Vite(5173) 直连，需要允许跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.config = config
    app.state.token = token
    app.state.provider = provider
    app.state.tools = tools
    app.state.policy = policy
    app.state.sessions = session_manager
    app.state.skills = skill_registry
    app.state.mcp = mcp_registry
    app.state.memory = memory_store
    app.state.sandbox = sandbox
    app.state.backup = backup
    app.state.metrics = metrics
    app.state.audit = audit
    app.state.usage_store = usage_store
    app.state.budget = budget
    app.state.reflexion = reflexion
    app.state.rag = rag_service

    # 组装 agent 并绑定到连接管理器（emit 广播到所有 WS 连接）
    agent = Agent(
        config=config,
        provider=provider,
        tools=tools,
        policy=policy,
        emit=manager.broadcast,
        skills_section=skill_registry.system_prompt_section(),
        skills=skill_registry,
        memory=memory_manager,
        intent=intent_pipeline,
        sandbox=sandbox,
        backup=backup,
        metrics=metrics,
        audit=audit,
        safety=safety_gate,
        content_filter=content_filter,
        budget=budget,
        reflexion=reflexion,
    )
    manager.bind_agent(agent)
    manager.bind_sessions(session_manager)
    manager.bind_audit(audit)
    app.state.agent = agent

    app.include_router(health.router)
    app.include_router(workspace.router)
    app.include_router(meta.router)
    app.include_router(sessions.router)
    app.include_router(memory.router)
    app.include_router(undo.router)
    app.include_router(usage_routes.router)
    app.include_router(diagnostics.router)
    app.include_router(crash.router)
    app.include_router(rag.router)

    @app.websocket("/ws")
    async def ws_route(ws: WebSocket) -> None:
        provided = ws.query_params.get("token", "")
        if provided != token:
            await ws.close(code=4401, reason="unauthorized")
            return
        await websocket_endpoint(ws)

    return app


def get_token(app: FastAPI) -> str:
    return app.state.token