"""远程 MCP 客户端：JSON-RPC 2.0 over streamable HTTP（含 SSE 响应解析）。

MCP streamable HTTP 规范：单一 endpoint，POST 发 JSON-RPC 请求；响应可为
`application/json` 或 `text/event-stream`（SSE）。`Mcp-Session-Id` 响应头用于
会话保持，后续请求回传。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from .client import MCPError


def _parse_sse_messages(raw: bytes) -> List[Dict[str, Any]]:
    """解析 SSE 响应体，返回所有 `data:` 事件的 JSON-RPC 消息。"""
    messages: List[Dict[str, Any]] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            msg = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict):
            messages.append(msg)
    return messages


def _extract(data: Any, req_id: int) -> Dict[str, Any]:
    """从（可能为消息列表的）响应中挑出匹配 id 的 JSON-RPC 消息。"""
    if isinstance(data, list):
        for m in data:
            if isinstance(m, dict) and m.get("id") == req_id:
                return m
        return {}
    return data if isinstance(data, dict) else {}


class RemoteMCPClient:
    """连接一个远程 MCP server（streamable HTTP transport），暴露其 tools。

    对外接口与 MCPClient 对齐：start() / tools() / call_tool() / close()。
    """

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        sandbox: Any = None,
        transport: Any = None,
    ) -> None:
        self.url = url
        self.headers = dict(headers or {})
        self.sandbox = sandbox
        self._transport = transport  # 测试可注入 httpx transport
        self._client: Optional[httpx.AsyncClient] = None
        self._session_id: Optional[str] = None
        self._next_id = 1
        self._tools: List[Dict[str, Any]] = []
        self._server_info: Dict[str, Any] = {}

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=30.0, headers=self.headers, transport=self._transport
        )
        self._server_info = await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "myopencode", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized", {})
        result = await self._request("tools/list", {})
        self._tools = list(result.get("tools", []))

    async def _request(self, method: str, params: Dict[str, Any]) -> Any:
        req_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        resp = await self._post(payload)
        data = await self._parse_response(resp)
        msg = _extract(data, req_id)
        if msg.get("error"):
            err = msg["error"]
            message = err.get("message", "MCP error") if isinstance(err, dict) else str(err)
            raise MCPError(message)
        return msg.get("result")

    async def _notify(self, method: str, params: Dict[str, Any]) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            resp = await self._post(payload)
            await resp.aread()  # 通知不关心响应体
        except Exception:  # pragma: no cover - 通知失败不影响主流程
            pass

    async def _post(self, payload: Dict[str, Any]) -> httpx.Response:
        assert self._client is not None
        headers = {"Accept": "application/json, text/event-stream"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        resp = await self._client.post(self.url, json=payload, headers=headers)
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid
        resp.raise_for_status()
        return resp

    async def _parse_response(self, resp: httpx.Response) -> Any:
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            return _parse_sse_messages(await resp.aread())
        return resp.json()

    def tools(self) -> List[Dict[str, Any]]:
        return self._tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("tools/call", {"name": name, "arguments": arguments})

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
