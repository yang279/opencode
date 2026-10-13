"""WebSocket 连接管理与事件路由。"""
from __future__ import annotations

import asyncio
import hashlib
import json
from functools import partial
from typing import Any, Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

from ..core import events as E
from ..core import tracing


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._agent = None  # 延迟绑定 Agent
        self._sessions = None  # SessionManager
        self._audit = None  # AuditLogger
        self._tasks: Dict[str, asyncio.Task] = {}

    def bind_agent(self, agent: Any) -> None:
        self._agent = agent

    def bind_sessions(self, sessions: Any) -> None:
        self._sessions = sessions

    def bind_audit(self, audit: Any) -> None:
        self._audit = audit

    def cancel_running(self, session_id: str | None = None) -> None:
        """取消正在运行的 agent 任务。

        session_id 为 None：取消全部运行中的任务（停止/关停）。
        session_id 有值：仅取消该会话的任务，避免误伤其他并发会话。
        """
        if session_id is not None:
            task = self._tasks.get(session_id)
            if task is None:
                return
            if self._agent is not None:
                self._agent.cancel(session_id)
            if not task.done():
                task.cancel()
            self._tasks.pop(session_id, None)
            return
        if self._agent is not None:
            self._agent.cancel()
        for sid, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
            self._tasks.pop(sid, None)

    def _on_task_done(self, session_id: str, task: asyncio.Task) -> None:
        if self._tasks.get(session_id) is task:
            self._tasks.pop(session_id, None)
        if self._sessions is not None:
            self._sessions.save()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        if self._agent is not None:
            await ws.send_text(json.dumps(E.state_snapshot({"connected": True})))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, event: Dict[str, Any]) -> None:
        if not self._connections:
            return
        text = json.dumps(event, ensure_ascii=False)
        stale = []
        for ws in list(self._connections):
            try:
                await ws.send_text(text)
            except Exception:  # pragma: no cover
                stale.append(ws)
        for ws in stale:
            self._connections.discard(ws)

    async def handle(self, ws: WebSocket, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send_text(json.dumps(E.error("非法 JSON")))
            return

        etype = data.get("type")
        if etype == E.EVENT_USER_MESSAGE:
            content = data.get("content", "")
            attachments = data.get("attachments") or []
            session_id = data.get("session_id", "")
            if self._agent is None or self._sessions is None:
                await self.broadcast(E.error("后端尚未就绪"))
                return
            existing = self._tasks.get(session_id)
            if existing is not None and not existing.done():
                await self.broadcast(E.error("该会话任务执行中，请先停止当前任务"))
                return
            session = self._sessions.get(session_id)
            if session is None:
                await self.broadcast(E.error("会话不存在: {}".format(session_id)))
                return
            tracing.new_trace(session_id)
            if self._audit is not None:
                self._audit.record(
                    "user_message",
                    content_hash="sha256:" + hashlib.sha256(content.encode()).hexdigest()[:16],
                )
            task = asyncio.create_task(
                self._agent.run(session, content, list(attachments))
            )
            task.add_done_callback(partial(self._on_task_done, session_id))
            self._tasks[session_id] = task
        elif etype == E.EVENT_TOOL_APPROVAL:
            if self._sessions is not None:
                self._sessions.resolve_approval(
                    data.get("id", ""), data.get("decision", "reject")
                )
        elif etype == E.EVENT_ASK_USER_REPLY:
            if self._sessions is not None:
                self._sessions.resolve_question(data.get("id", ""), data.get("answer", ""))
        elif etype == E.EVENT_SAFETY_REPLY:
            if self._sessions is not None:
                self._sessions.resolve_safety(
                    data.get("id", ""), data.get("decision", "abort")
                )
        elif etype == E.EVENT_CANCEL:
            self.cancel_running(data.get("session_id"))
        elif etype == E.EVENT_RESUME:
            session_id = data.get("session_id", "")
            if self._agent is None or self._sessions is None:
                await self.broadcast(E.error("后端尚未就绪"))
                return
            existing = self._tasks.get(session_id)
            if existing is not None and not existing.done():
                await self.broadcast(E.error("该会话任务执行中，请先停止当前任务"))
                return
            session = self._sessions.get(session_id)
            if session is None:
                await self.broadcast(E.error("会话不存在: {}".format(session_id)))
                return
            tracing.new_trace(session_id)
            if self._audit is not None:
                self._audit.record("resume")
            task = asyncio.create_task(self._agent.resume(session))
            task.add_done_callback(partial(self._on_task_done, session_id))
            self._tasks[session_id] = task
        elif etype == E.EVENT_CONFIG_UPDATE:
            await self.broadcast(E.error("config_update 暂未实现"))
        else:
            await self.broadcast(E.error("未知事件类型: {}".format(etype)))


manager = ConnectionManager()


async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            await manager.handle(ws, raw)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)