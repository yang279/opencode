"""Skills 与 Tools 列表接口。"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/skills")
async def list_skills(request: Request):
    return [
        {"name": s.name, "description": s.description, "source": s.source}
        for s in request.app.state.skills.list()
    ]


@router.get("/tools")
async def list_tools(request: Request):
    # 仅返回 MCP 外部工具（内置工具不在前端展示）
    return [
        t for t in request.app.state.tools.list_meta() if t["name"].startswith("mcp_")
    ]