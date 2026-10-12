"""记忆只读调试接口。"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/memory")
async def get_memory(request: Request):
    store = request.app.state.memory
    return {
        "facts": [
            {
                "id": f.id,
                "content": f.content,
                "category": f.category,
                "importance": f.importance,
                "times_used": f.times_used,
            }
            for f in store.list_facts()
        ],
        "episodes": [
            {
                "id": e.id,
                "session_id": e.session_id,
                "title": e.title,
                "summary": e.summary,
                "message_count": e.message_count,
            }
            for e in store.list_episodes()
        ],
    }