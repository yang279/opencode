"""run_code 工具：在隔离沙箱中执行代码片段。

- language=python：按沙箱后端执行（container 用容器 python / seatbelt 用宿主 python 包裹 / 兜底直跑）。
- language=wasm：调用独立 `wasm-runner`（wasmtime/WASI）执行编译好的 WASM 模块。
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from typing import Any, Dict, List

from ..core import metrics
from ..core import tracing
from .base import ToolContext, ToolResult, read_bounded


def _wasm_runner_binary() -> str:
    env = os.environ.get("MYOPENCODE_WASM_RUNNER")
    if env:
        return env
    exe = getattr(sys, "executable", "")
    if exe and os.path.isabs(exe):
        name = "wasm-runner.exe" if os.name == "nt" else "wasm-runner"
        return os.path.join(os.path.dirname(exe), name)
    return "wasm-runner"


async def _run_argv(argv: List[str], cwd: str, timeout: int, ctx: ToolContext) -> ToolResult:
    kw: Dict[str, Any] = dict(
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
    )
    if os.name == "posix":
        kw["start_new_session"] = True
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
        return ToolResult(output="代码执行超时({}s)".format(timeout), error=True)
    except Exception as exc:  # pragma: no cover
        return ToolResult(output="执行失败: {}".format(exc), error=True)
    finally:
        if ctx.cancel_token is not None:
            ctx.cancel_token.clear()
    text = out.decode("utf-8", errors="replace")
    if truncated:
        text += "\n…[输出已达上限 {} 字节，已截断]".format(limit)
    return ToolResult(
        output=text,
        error=proc.returncode != 0,
    )


class RunCodeTool:
    name = "run_code"
    category = "execute"
    description = "在隔离沙箱中执行代码片段（python 或 wasm）"
    json_schema = {
        "type": "object",
        "properties": {
            "language": {"type": "string", "enum": ["python", "wasm"]},
            "code": {"type": "string", "description": "代码内容"},
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["language", "code"],
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        language = str(args.get("language", "python")).lower()
        code = str(args.get("code", ""))
        timeout = int(args.get("timeout", 30))

        if language == "wasm":
            return await self._run_wasm(code, timeout, ctx)
        return await self._run_python(code, timeout, ctx)

    async def _run_python(self, code: str, timeout: int, ctx: ToolContext) -> ToolResult:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(code)
            path = fh.name
        try:
            if ctx.sandbox is not None:
                argv = ctx.sandbox.wrap_python(path)
            else:
                argv = [sys.executable, path]
            return await _run_argv(argv, ctx.working_dir, timeout, ctx)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    async def _run_wasm(self, code: str, timeout: int, ctx: ToolContext) -> ToolResult:
        # code 应是编译好的 .wasm 文件路径（相对工作目录）
        if ctx.path_guard is not None:
            wasm_path = ctx.path_guard.resolve(code, write=False)
        else:
            wasm_path = ctx.resolve_path(code)
        if not os.path.isfile(wasm_path):
            return ToolResult(output="找不到 wasm 模块: {}".format(code), error=True)
        argv = [
            _wasm_runner_binary(),
            "run-wasm",
            "--dir",
            ctx.working_dir,
        ]
        if ctx.sandbox is not None and ctx.sandbox.config.allow_network:
            argv.append("--allow-net")
        argv.append(wasm_path)
        try:
            return await _run_argv(argv, ctx.working_dir, timeout, ctx)
        except FileNotFoundError:
            return ToolResult(output="wasm-runner 未安装/未打包", error=True)