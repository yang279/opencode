"""工具接口定义。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Protocol


@dataclass
class ToolResult:
    output: str
    diff: Any = None
    error: bool = False


async def read_bounded(proc: Any, limit: int, timeout: float) -> tuple:
    """按字节上限读取子进程 stdout（需 stderr 已合并），超时抛 asyncio.TimeoutError。

    返回 (bytes, truncated)。达到上限即停止读取并标记截断，避免无界缓冲。
    """
    out = bytearray()
    truncated = False

    async def _drain() -> None:
        nonlocal out, truncated
        while True:
            chunk = await proc.stdout.read(65536)
            if not chunk:
                return
            remaining = limit - len(out)
            if len(chunk) >= remaining:
                out += chunk[:remaining]
                truncated = True
                return
            out += chunk

    await asyncio.wait_for(_drain(), timeout=timeout)
    return bytes(out), truncated


class Tool(Protocol):
    name: str
    description: str
    json_schema: Dict[str, Any]
    category: str = "read"  # read / write / execute / skill / memory / mcp

    async def execute(self, args: Dict[str, Any], ctx: "ToolContext") -> ToolResult:
        ...  # pragma: no cover


@dataclass
class ToolContext:
    """执行上下文：工作目录 + 权限策略 + 是否需要审批回调 + 沙箱/备份。"""

    working_dir: str
    require_approval: Any = None  # 可选：async (tool, args) -> str 决策
    path_guard: Any = None  # 可选：PathGuard，越界拦截
    sandbox: Any = None  # 可选：Sandbox 门面
    backup: Any = None  # 可选：BackupManager，写前快照
    cancel_token: Any = None  # 可选：ProcessTracker，登记当前子进程供取消时必杀
    max_output_bytes: int = 262144  # 输出字节上限（256 KB）
    scrub_secrets: bool = True  # 输出进 LLM/前端前是否脱敏回扫

    def resolve_path(self, path: str, write: bool = False) -> str:
        import os

        if self.path_guard is not None:
            return self.path_guard.resolve(path, write=write)
        if os.path.isabs(path):
            return path
        return os.path.join(self.working_dir, path)


class ProcessTracker:
    """登记当前运行的子进程，cancel 时按进程组必杀（可附带容器清理回调）。"""

    def __init__(self) -> None:
        self.proc: Any = None
        self.on_kill: Any = None

    def register(self, proc: Any, on_kill: Any = None) -> None:
        self.proc = proc
        self.on_kill = on_kill

    def clear(self) -> None:
        self.proc = None
        self.on_kill = None

    def kill(self) -> None:
        import os
        import signal

        if self.on_kill is not None:
            try:
                self.on_kill()
            except Exception:  # pragma: no cover
                pass
        proc = self.proc
        if proc is None or proc.returncode is not None:
            return
        try:
            if os.name == "nt":  # Windows：taskkill /T 杀整棵进程树
                subprocess_run(
                    ["taskkill", "/T", "/F", "/PID", str(proc.pid)]
                )
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, AttributeError, OSError):
            try:
                proc.kill()
            except Exception:  # pragma: no cover
                pass


def subprocess_run(args: Any) -> None:
    import subprocess

    subprocess.run(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )