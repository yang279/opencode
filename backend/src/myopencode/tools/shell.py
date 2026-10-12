"""Shell 工具：执行命令（走权限审批 + 可选沙箱 + 取消必杀）。"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List

from ..core import metrics
from ..core import tracing
from .base import ToolContext, ToolResult, read_bounded


def _native_shell(command: str) -> List[str]:
    if os.name == "nt":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", command]
    return ["/bin/bash", "-lc", command]


class ShellTool:
    name = "run_shell"
    category = "execute"
    description = "在终端中执行 shell 命令"
    json_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["command"],
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = args.get("command", "")
        if ctx.sandbox is not None and ctx.sandbox.disabled:
            return ToolResult(output=ctx.sandbox.disabled_reason(), error=True)
        timeout = int(args.get("timeout", 30))
        argv: List[str] = self._argv(command, ctx)
        kw: Dict[str, Any] = dict(
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=ctx.working_dir,
        )
        if os.name == "posix":
            kw["start_new_session"] = True  # 独立进程组，便于 killpg

        backend = ctx.sandbox.backend_name if ctx.sandbox is not None else "native"
        metrics.incr("sandbox_call_total", backend=backend)
        proc = await asyncio.create_subprocess_exec(*argv, **kw)
        on_kill = ctx.sandbox.kill_callback() if ctx.sandbox is not None else None
        if ctx.cancel_token is not None:
            ctx.cancel_token.register(proc, on_kill=on_kill)
        limit = int(getattr(ctx, "max_output_bytes", 262144))
        try:
            with tracing.span("sandbox.exec", backend=backend):
                out, truncated = await read_bounded(proc, limit, timeout)
            if truncated and ctx.cancel_token is not None:
                ctx.cancel_token.kill()
        except asyncio.TimeoutError:
            if ctx.cancel_token is not None:
                ctx.cancel_token.kill()
            return ToolResult(output="命令超时({}s)".format(timeout), error=True)
        except Exception as exc:  # pragma: no cover
            return ToolResult(output="执行失败: {}".format(exc), error=True)
        finally:
            if ctx.cancel_token is not None:
                ctx.cancel_token.clear()
        text = out.decode("utf-8", errors="replace")
        if truncated:
            text += "\n…[输出已达上限 {} 字节，已截断]".format(limit)
        return ToolResult(output=text)

    def _argv(self, command: str, ctx: ToolContext) -> List[str]:
        if ctx.sandbox is not None:
            return ctx.sandbox.wrap_shell(command)
        return _native_shell(command)
