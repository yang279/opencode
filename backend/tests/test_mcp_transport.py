"""远程 MCP（streamable HTTP）客户端测试。"""
import asyncio
import json

import httpx
import pytest

from myopencode.config.loader import parse_config_dict
from myopencode.mcp.client import MCPError
from myopencode.mcp.remote import RemoteMCPClient, _extract, _parse_sse_messages


def _ok_handler(request):
    body = json.loads(request.content)
    method = body.get("method")
    req_id = body.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "mock"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "echo", "description": "回显", "inputSchema": {"type": "object", "properties": {}}}]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": "ok"}]}
    else:
        return httpx.Response(202)
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": result})


def test_remote_client_list_and_call():
    async def _run():
        client = RemoteMCPClient("http://mock/mcp", transport=httpx.MockTransport(_ok_handler))
        await client.start()
        assert client.tools()[0]["name"] == "echo"
        result = await client.call_tool("echo", {"x": 1})
        assert result["content"][0]["text"] == "ok"
        await client.close()

    asyncio.run(_run())


def test_remote_client_sse_response():
    def sse_handler(request):
        body = json.loads(request.content)
        method = body.get("method")
        req_id = body.get("id")
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05"}
        elif method == "tools/list":
            result = {"tools": []}
        else:
            result = {"content": [{"type": "text", "text": "streamed"}]}
        payload = json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream", "Mcp-Session-Id": "sess-1"},
            content="event: message\ndata: {}\n\n".format(payload),
        )

    async def _run():
        client = RemoteMCPClient("http://mock/mcp", transport=httpx.MockTransport(sse_handler))
        await client.start()
        assert client._session_id == "sess-1"
        await client.close()

    asyncio.run(_run())


def test_remote_client_call_error():
    def err_handler(request):
        body = json.loads(request.content)
        method = body.get("method")
        req_id = body.get("id")
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05"}
        elif method == "tools/list":
            result = {"tools": [{"name": "x", "inputSchema": {}}]}
        else:
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": "boom"}},
            )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": result})

    async def _run():
        client = RemoteMCPClient("http://mock/mcp", transport=httpx.MockTransport(err_handler))
        await client.start()
        with pytest.raises(MCPError):
            await client.call_tool("x", {})
        await client.close()

    asyncio.run(_run())


def test_parse_sse_messages():
    raw = b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'
    msgs = _parse_sse_messages(raw)
    assert msgs == [{"jsonrpc": "2.0", "id": 1, "result": {}}]
    assert _extract(msgs, 1) == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert _extract(msgs, 99) == {}


def test_mcp_remote_config_parse():
    cfg = parse_config_dict(
        {
            "mcp_servers": {
                "remote": {"url": "http://localhost:8080/mcp", "transport": "http", "headers": {"Authorization": "Bearer x"}}
            }
        }
    )
    srv = cfg.mcp_servers["remote"]
    assert srv.url == "http://localhost:8080/mcp"
    assert srv.transport == "http"
    assert srv.headers["Authorization"] == "Bearer x"