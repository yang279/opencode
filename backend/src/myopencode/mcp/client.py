"""精简 MCP 客户端：JSON-RPC 2.0 over stdio（新行分隔）。"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional


class MCPError(Exception):
    pass


class MCPClient:
    """连接一个 MCP server（stdio transport），暴露其 tools。"""

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        sandbox: Any = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.sandbox = sandbox
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._stdin = None
        self._reader_task: Optional[asyncio.Task] = None
        self._pending: Dict[int, asyncio.Future] = {}
        self._next_id = 1
        self._tools: List[Dict[str, Any]] = []
        self._server_info: Dict[str, Any] = {}

    async def start(self) -> None:
        env = {**os.environ, **self.env}
        argv = [self.command, *self.args]
        if self.sandbox is not None:
            argv = self.sandbox.wrap_argv(argv)
        self.proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
        self._stdin = self.proc.stdin
        self._reader_task = asyncio.create_task(self._read_loop())

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

    async def _read_loop(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and "id" in msg and msg["id"] is not None:
                fut = self._pending.pop(msg["id"], None)
                if fut is not None and not fut.done():
                    if "error" in msg:
                        err = msg["error"]
                        message = err.get("message", "MCP error") if isinstance(err, dict) else str(err)
                        fut.set_exception(MCPError(message))
                    else:
                        fut.set_result(msg.get("result"))
            # notifications（无 id）直接忽略

    async def _request(self, method: str, params: Dict[str, Any]) -> Any:
        req_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        self._send(json.dumps(payload))
        return await asyncio.wait_for(fut, timeout=30)

    async def _notify(self, method: str, params: Dict[str, Any]) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self._send(json.dumps(payload))

    def _send(self, text: str) -> None:
        if self._stdin is None:
            raise MCPError("MCP client 未连接")
        self._stdin.write((text + "\n").encode())

    def tools(self) -> List[Dict[str, Any]]:
        return self._tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("tools/call", {"name": name, "arguments": arguments})

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None
        if self.proc is not None:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass