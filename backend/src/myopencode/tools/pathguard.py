"""路径护栏：realpath 归一化 + 越界拦截。

所有文件工具读写前都必须经过这里，防止 `../../` 或软链逃逸出工作目录。
写操作默认严格限制在工作目录（除非显式加入 extra_write_paths）；
读操作默认限制在工作目录 + extra_read_paths。
"""
from __future__ import annotations

import os
from typing import Iterable, List, Optional


class PathDeniedError(PermissionError):
    """路径越界被拦截。"""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__("路径被沙箱拦截: {!r}（{}）".format(path, reason))


def _realpath(path: str) -> str:
    # normcase 处理 Windows 大小写不敏感与盘符/分隔符归一；POSIX 下为恒等
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _within(target: str, roots: Iterable[str]) -> bool:
    for root in roots:
        # 用 commonpath 做前后缀判定，正确处理 root="/" 这种边界
        # （否则 root + os.sep == "//" 会让根目录下的任何路径都被误判为越界）
        try:
            if os.path.commonpath([target, root]) == root:
                return True
        except ValueError:  # Windows 不同盘符
            continue
    return False


class PathGuard:
    """根据工作目录与额外允许路径，判定某个读写路径是否合法。"""

    def __init__(
        self,
        working_dir: str,
        extra_read_paths: Optional[List[str]] = None,
        extra_write_paths: Optional[List[str]] = None,
        deny_write_outside_workspace: bool = True,
    ) -> None:
        self.working_dir = _realpath(working_dir)
        self._read_roots = [_realpath(p) for p in (extra_read_paths or [])]
        self._write_roots = [_realpath(p) for p in (extra_write_paths or [])]
        self.deny_write_outside_workspace = deny_write_outside_workspace

    def resolve(self, path: str, write: bool = False) -> str:
        """归一化并校验路径，返回真实路径；越界抛 PathDeniedError。"""
        raw = path if os.path.isabs(path) else os.path.join(self.working_dir, path)
        real = _realpath(raw)
        if write:
            if self.deny_write_outside_workspace and not _within(
                real, [self.working_dir, *self._write_roots]
            ):
                raise PathDeniedError(path, "写操作超出工作目录")
        else:
            if not _within(real, [self.working_dir, *self._read_roots]):
                raise PathDeniedError(path, "读操作超出工作目录")
        return real
