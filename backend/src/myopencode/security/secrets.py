"""密钥安全存储：优先系统钥匙串，失败回退 chmod 600 文件。

后端选型：
- macOS   : `security find/add/delete-generic-password`
- Linux   : `secret-tool`（libsecret）
- Windows : 无可靠 CLI 可逆检索（cmdkey 不可读回），回退 chmod 600 文件
- 任何 CLI 失败 → chmod 600 文件兜底

密钥不再明文写入主配置 JSON；主配置里该字段始终为 null。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional

SERVICE = "myopencode"


def _file_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "myopencode", "secrets")


def _sanitize(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._-") or "key"


def _file_path(name: str) -> str:
    return os.path.join(_file_dir(), _sanitize(name))


def _run(args, input: Optional[str] = None):
    try:
        return subprocess.run(
            args, input=input, capture_output=True, text=True, timeout=10
        )
    except Exception:  # pragma: no cover
        return None


# ── 后端可用性 ─────────────────────────────────────────────
def _mac_available() -> bool:
    return sys.platform == "darwin" and shutil.which("security") is not None


def _linux_available() -> bool:
    return sys.platform.startswith("linux") and shutil.which("secret-tool") is not None


# ── macOS keychain ─────────────────────────────────────────
def _mac_get(name: str) -> Optional[str]:
    p = _run(["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"])
    if p is None or p.returncode != 0:
        return None
    return p.stdout.rstrip("\r\n")


def _mac_set(name: str, value: str) -> bool:
    _run(["security", "delete-generic-password", "-s", SERVICE, "-a", name])
    p = _run(
        ["security", "add-generic-password", "-s", SERVICE, "-a", name, "-w", value, "-U"]
    )
    return p is not None and p.returncode == 0


def _mac_delete(name: str) -> bool:
    p = _run(["security", "delete-generic-password", "-s", SERVICE, "-a", name])
    return p is not None and p.returncode == 0


# ── Linux secret-tool ──────────────────────────────────────
def _linux_get(name: str) -> Optional[str]:
    p = _run(["secret-tool", "lookup", "service", SERVICE, "user", name])
    if p is None or p.returncode != 0:
        return None
    return p.stdout.rstrip("\r\n")


def _linux_set(name: str, value: str) -> bool:
    p = _run(
        ["secret-tool", "store", "--label", "myopencode", "service", SERVICE, "user", name],
        input=value,
    )
    return p is not None and p.returncode == 0


def _linux_delete(name: str) -> bool:
    p = _run(["secret-tool", "clear", "service", SERVICE, "user", name])
    return p is not None and p.returncode == 0


# ── 文件兜底（chmod 600）───────────────────────────────────
def _file_get(name: str) -> Optional[str]:
    try:
        with open(_file_path(name), "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _file_set(name: str, value: str) -> bool:
    path = _file_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, value.encode("utf-8"))
    finally:
        os.close(fd)
    return True


def _file_delete(name: str) -> bool:
    try:
        os.remove(_file_path(name))
    except OSError:
        pass
    return True


# ── 公共 API ───────────────────────────────────────────────
def get_secret(name: str) -> Optional[str]:
    """读取密钥；钥匙串优先，未命中回退文件。"""
    if _mac_available():
        v = _mac_get(name)
        if v is not None:
            return v
    elif _linux_available():
        v = _linux_get(name)
        if v is not None:
            return v
    return _file_get(name)


def set_secret(name: str, value: str) -> bool:
    """写入密钥（value 为空则删除）。CLI 后端成功时同步清掉文件副本。"""
    if not value:
        return delete_secret(name)
    if _mac_available():
        if _mac_set(name, value):
            _file_delete(name)
            return True
    elif _linux_available():
        if _linux_set(name, value):
            _file_delete(name)
            return True
    return _file_set(name, value)


def delete_secret(name: str) -> bool:
    if _mac_available():
        _mac_delete(name)
    elif _linux_available():
        _linux_delete(name)
    return _file_delete(name)
