#!/usr/bin/env python3
"""极简 MCP server（stdio JSON-RPC 2.0），用于测试 myopencode 的 MCP 集成。

暴露两个工具：echo（回显）、add（两数相加）。
用法（在 myopencode.json 里配置）：
  "mcp_servers": {
    "mock": { "command": "python3", "args": ["examples/mcp_servers/mock_server.py"] }
  }
"""
import json
import sys


def handle(method, params):
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mock-mcp", "version": "1.0.0"},
        }
    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": "echo",
                    "description": "回显输入文本",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                    },
                },
                {
                    "name": "add",
                    "description": "计算两个数字之和",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number"},
                            "b": {"type": "number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            ]
        }
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if name == "echo":
            return {"content": [{"type": "text", "text": "echo: " + str(args.get("text", ""))}], "isError": False}
        if name == "add":
            try:
                total = float(args.get("a", 0)) + float(args.get("b", 0))
                return {"content": [{"type": "text", "text": str(total)}], "isError": False}
            except Exception:
                return {"content": [{"type": "text", "text": "invalid numbers"}], "isError": True}
        return {"content": [{"type": "text", "text": "unknown tool"}], "isError": True}
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method", "")
        if msg.get("id") is None or method.startswith("notifications/"):
            continue
        result = handle(method, msg.get("params", {}))
        if result is not None:
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)


if __name__ == "__main__":
    main()