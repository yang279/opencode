"""会话 REST 接口：列表、新建、删除、历史消息。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/sessions")
async def list_sessions(request: Request):
    return request.app.state.sessions.list()


@router.post("/sessions")
async def create_session(request: Request):
    s = request.app.state.sessions.create()
    return {"id": s.session_id, "title": s.title}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    # 删除「正是正在运行」的那个会话时，才停掉对应任务；其他会话不受影响
    from ..ws import manager

    manager.cancel_running(session_id)
    if not request.app.state.sessions.delete(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, request: Request):
    s = request.app.state.sessions.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "id": s.session_id,
        "title": s.title,
        "messages": [m.to_dict() for m in s.messages],
    }