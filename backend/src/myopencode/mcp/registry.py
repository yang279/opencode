"""MCP 注册表：根据配置连接多个 server，汇总其工具。"""
from __future__ import annotations

import sys
from typing import Any, Dict, List

from ..config.schema import McpServerConfig
from .client import MCPClient
from .remote import RemoteMCPClient
from .tool import McpTool


class McpRegistry:
    def __init__(self, servers: Dict[str, McpServerConfig], sandbox: Any = None) -> None:
        self._config = servers
        self._sandbox = sandbox
        self._clients: Dict[str, Any] = {}
        self._tools: List[McpTool] = []

    async def connect_all(self) -> None:
        for name, cfg in self._config.items():
            if cfg.url:
                client: Any = RemoteMCPClient(cfg.url, headers=cfg.headers, sandbox=self._sandbox)
            elif cfg.command is not None:
                client = MCPClient(cfg.command, cfg.args, cfg.env, self._sandbox)
            else:
                print("MCP server {!r} 未配置 command/url，跳过".format(name), file=sys.stderr)
                continue
            try:
                await client.start()
            except Exception as exc:
                print("MCP server {!r} 连接失败: {}".format(name, exc), file=sys.stderr)
                await client.close()
                continue
            self._clients[name] = client
            for spec in client.tools():
                self._tools.append(McpTool(name, client, spec))

    def tools(self) -> List[McpTool]:
        return self._tools

    async def close_all(self) -> None:
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
        self._tools.clear()