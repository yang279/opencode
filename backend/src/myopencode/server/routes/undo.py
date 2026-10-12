"""回退路由：POST /sessions/{id}/undo 手动回退最近一次文件改动组。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ...core.backup import BackupManager

router = APIRouter()


@router.post("/sessions/{session_id}/undo")
async def undo_session(session_id: str, request: Request):
    state = request.app.state
    if not state.config.backup.enabled:
        raise HTTPException(status_code=400, detail="备份未启用")
    # 每次 undo 新建 BackupManager，与运行中 run 的备份实例隔离，避免并发串组
    backup = BackupManager(state.config.backup)
    backup.set_session(session_id)
    restored = backup.undo_last()
    return {"ok": True, "restored": restored}
