"""沙箱门面：可插拔后端 + 自动选型 + 路径护栏。

后端（隔离强度由高到低，`backend=auto` 自动降级）：
- container：Docker/podman 容器（跨平台真隔离，Windows 可用）
- seatbelt ：macOS `sandbox-exec`（OS 沙箱）
- pathguard/none：仅路径护栏 + 命令白名单（无 OS 隔离）

路径护栏（PathGuard）独立于后端，永远作用于文件工具，是三平台统一底座。
"""
from __future__ import annotations

import os
import shutil
import uuid
from typing import Callable, List, Optional

from ..config.schema import SandboxConfig
from .pathguard import PathGuard

_SANDBOX_EXEC = "/usr/bin/sandbox-exec"


def _real(path: str) -> str:
    return os.path.realpath(os.path.abspath(path))


def _native_shell(command: str) -> List[str]:
    """平台感知的宿主 shell 兜底：Windows cmd.exe，POSIX bash。"""
    if os.name == "nt":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", command]
    return ["/bin/bash", "-lc", command]


def _subprocess_run(args: List[str]) -> None:
    import subprocess

    try:
        subprocess.run(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:  # pragma: no cover
        pass


# ── macOS seatbelt ──────────────────────────────────────────────
def _build_profile(
    working_dir: str,
    allow_network: bool,
    extra_write_paths: Optional[List[str]] = None,
) -> str:
    write_subpaths = [
        '(subpath "{}")'.format(_real(working_dir)),
        '(subpath "/private/tmp")',
    ]
    for p in extra_write_paths or []:
        write_subpaths.append('(subpath "{}")'.format(_real(p)))
    rules = [
        "(version 1)",
        "(allow default)",
        "(deny file-write*)",
        "(allow file-write* {})".format(" ".join(write_subpaths)),
    ]
    if not allow_network:
        rules.append("(deny network*)")
    return " ".join(rules)


class SeatbeltBackend:
    """macOS sandbox-exec 隔离。"""

    name = "seatbelt"

    def __init__(self, working_dir: str, config: SandboxConfig) -> None:
        self.working_dir = _real(working_dir)
        self.config = config
        self.__name__ = self.name

    @staticmethod
    def available() -> bool:
        return os.name == "posix" and bool(
            shutil.which("sandbox-exec") or os.path.exists(_SANDBOX_EXEC)
        )

    @staticmethod
    def _binary() -> str:
        found = shutil.which("sandbox-exec")
        return found or _SANDBOX_EXEC

    def wrap_shell(self, command: str) -> List[str]:
        return self.wrap_argv(["/bin/bash", "-lc", command])

    def wrap_argv(self, argv: List[str]) -> List[str]:
        profile = _build_profile(
            self.working_dir,
            self.config.allow_network,
            self.config.extra_write_paths,
        )
        return [self._binary(), "-p", profile, *argv]

    def wrap_python(self, code_file: str) -> List[str]:
        import sys

        return self.wrap_argv([sys.executable, code_file])


# ── Docker/podman 容器 ─────────────────────────────────────────
class ContainerBackend:
    """容器隔离：跨平台（Docker Desktop / colima / WSL2 / podman）。"""

    name = "container"

    def __init__(self, working_dir: str, config: SandboxConfig) -> None:
        self.working_dir = _real(working_dir)
        self.config = config
        self._runtime = self._find_runtime()
        self._container_name: Optional[str] = None
        self.__name__ = self.name

    @staticmethod
    def _find_runtime() -> Optional[str]:
        for c in ("docker", "podman"):
            if shutil.which(c):
                return c
        return None

    @staticmethod
    def available() -> bool:
        return ContainerBackend._find_runtime() is not None

    @property
    def runtime(self) -> str:
        return self._runtime or "docker"

    def _base(
        self,
        interactive: bool = False,
        extra_mounts: Optional[List[str]] = None,
    ) -> List[str]:
        cc = self.config.container
        argv: List[str] = [self.runtime, "run", "--rm"]
        self._container_name = "myopencode-{}".format(uuid.uuid4().hex[:12])
        argv += ["--name", self._container_name]
        if not self.config.allow_network:
            argv.append("--network=none")
        if cc.cpus:
            argv += ["--cpus", str(cc.cpus)]
        if cc.memory:
            argv += ["--memory", str(cc.memory)]
        if interactive:
            argv.append("-i")
        argv += ["-v", "{}:/workspace".format(self.working_dir)]
        for i, p in enumerate(self.config.extra_write_paths):
            argv += ["-v", "{}:/mnt/extra{}".format(_real(p), i)]
        for i, p in enumerate(self.config.extra_read_paths):
            argv += ["-v", "{}:/mnt/read{}:ro".format(_real(p), i)]
        for mount in extra_mounts or []:
            argv += ["-v", mount]
        argv += ["-w", "/workspace", cc.image or "python:3.11-slim"]
        return argv

    def wrap_shell(self, command: str) -> List[str]:
        return self._base() + ["bash", "-lc", command]

    def wrap_argv(self, argv: List[str]) -> List[str]:
        return self._base(interactive=True) + argv

    def wrap_python(self, code_file: str) -> List[str]:
        # 把代码文件挂进容器 /tmp/usercode.py，用容器自带 python 执行
        mount = "{}:/tmp/usercode.py".format(os.path.realpath(code_file))
        return self._base(extra_mounts=[mount]) + ["python", "/tmp/usercode.py"]

    def kill_last(self) -> None:
        if not self._container_name:
            return
        _subprocess_run([self.runtime, "kill", self._container_name])
        _subprocess_run([self.runtime, "rm", "-f", self._container_name])
        self._container_name = None


class NativeBackend:
    """pathguard/none 兜底：宿主直跑，无 OS 隔离。"""

    name = "pathguard"

    def __init__(self, working_dir: str, config: SandboxConfig) -> None:
        self.working_dir = _real(working_dir)
        self.config = config
        self.__name__ = self.name

    def wrap_shell(self, command: str) -> List[str]:
        return _native_shell(command)

    def wrap_argv(self, argv: List[str]) -> List[str]:
        return argv

    def wrap_python(self, code_file: str) -> List[str]:
        import sys

        return [sys.executable, code_file]

    def kill_last(self) -> None:
        pass


# ── 门面 ────────────────────────────────────────────────────────
class Sandbox:
    """沙箱门面：持有 PathGuard + 选型后的后端。"""

    def __init__(self, config: SandboxConfig, working_dir: str) -> None:
        self.config = config
        self.working_dir = _real(working_dir)
        self.path_guard = PathGuard(
            working_dir,
            extra_read_paths=config.extra_read_paths,
            extra_write_paths=config.extra_write_paths,
            deny_write_outside_workspace=config.deny_write_outside_workspace,
        )
        self._backend = self._select(config)

    @property
    def backend(self):
        return self._backend

    @property
    def backend_name(self) -> str:
        return getattr(self._backend, "name", "pathguard")

    def _select(self, config: SandboxConfig):
        if not config.enabled or config.backend == "none":
            return NativeBackend(self.working_dir, config)

        want = config.backend if config.backend != "auto" else None
        if want:
            if want == "container" and ContainerBackend.available():
                return ContainerBackend(self.working_dir, config)
            if want == "seatbelt" and SeatbeltBackend.available():
                return SeatbeltBackend(self.working_dir, config)
            if want == "pathguard":
                return NativeBackend(self.working_dir, config)
            # 指定但不可用 → 降级 pathguard
            return NativeBackend(self.working_dir, config)

        # auto：container → seatbelt → pathguard
        if ContainerBackend.available():
            return ContainerBackend(self.working_dir, config)
        if SeatbeltBackend.available():
            return SeatbeltBackend(self.working_dir, config)
        return NativeBackend(self.working_dir, config)

    def wrap_shell(self, command: str) -> List[str]:
        return self._backend.wrap_shell(command)

    def wrap_argv(self, argv: List[str]) -> List[str]:
        return self._backend.wrap_argv(argv)

    def wrap_python(self, code_file: str) -> List[str]:
        return self._backend.wrap_python(code_file)

    def kill_callback(self) -> Optional[Callable[[], None]]:
        """返回杀死「当前运行中的容器」的回调；非容器后端返回 None。"""
        if isinstance(self._backend, ContainerBackend):
            return self._backend.kill_last
        return None