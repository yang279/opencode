"""权限策略：决定某次工具调用是否需要审批，及命令 allow/deny 判断。"""
from __future__ import annotations

import os
import shlex
from typing import Any, Dict, Iterator, List, Optional

from ..config.schema import PermissionsConfig

# 审批决策常量
APPROVE_ONCE = "once"
APPROVE_ALWAYS = "always"
REJECT = "reject"


class PermissionPolicy:
    def __init__(self, config: PermissionsConfig, delegated: bool = False) -> None:
        self.config = config
        # delegated=True 用于并行子 agent：不弹审批（在父步骤已授权范围内自主执行）
        self.delegated = delegated
        # 已「always allow」的工具，后续跳过审批
        self._always_allow_tools: set = set()

    def mark_always(self, tool: str) -> None:
        self._always_allow_tools.add(tool)

    def needs_approval(self, tool: str, args: Dict[str, Any]) -> Optional[str]:
        """返回需要审批的原因；不需要则返回 None。"""
        if self.delegated:
            return None
        if tool in self._always_allow_tools:
            return None
        if tool in (
            "read_file",
            "list_dir",
            "glob",
            "grep",
            "load_skill",
            "save_memory",
            "recall_memory",
            "list_memory",
            "forget_memory",
        ):
            return None
        if tool.startswith("mcp_"):
            return "执行 MCP 工具需要确认: {}".format(tool)
        if tool in ("write_file", "edit_file"):
            if self.config.require_approval_for_write:
                return "写文件操作需要确认"
            return None
        if tool == "run_shell":
            command = str(args.get("command", ""))
            if not self.config.require_approval_for_shell:
                return None
            return "执行命令需要确认: {}".format(command)
        if tool == "run_code":
            return "在沙箱中执行代码需要确认: {}".format(
                str(args.get("language", ""))
            )
        return None

    def check_command(self, command: str) -> Optional[str]:
        """分级命令校验：返回拒绝原因（None=放行，之后仍走审批开关）。

        优先级：
        1. deny_commands 命中任一命令段首 token → 硬拒（绝不执行，也不再弹审批）
        2. allow_all_commands → 放行
        3. 配置了 allow_commands → 每段首 token 都需命中白名单（其余拒绝）
        4. 都未配置 → 默认放行（deny-only 模式，由审批开关兜底）

        匹配用「段首 token 的 basename 精确相等」，而非整串 startswith，
        从而 `echo rm` 放行、`rm -rf /` 硬拒，堵住前缀绕过。
        """
        leads = list(_iter_command_leads(command or ""))
        if not leads:
            return None
        for name in leads:
            for deny in self.config.deny_commands:
                if not deny:
                    continue
                if name == deny:
                    return "命令命中禁用名单: {}".format(deny)
        if self.config.allow_all_commands:
            return None
        if self.config.allow_commands:
            for name in leads:
                if name not in self.config.allow_commands:
                    return "命令不在允许名单内: {}".format(name)
        return None


def _iter_command_leads(command: str) -> Iterator[str]:
    """按 shell 控制符切段，产出每段首 token 的 basename（忽略空段）。

    尊重单/双引号与反斜杠转义，`;`/`&`/`|`/换行按控制符切段；
    `&&`/`||` 视为整体分隔。`$()`、反引号内嵌命令暂按同一段处理（P0 范围）。
    """
    i, n = 0, len(command)
    buf: List[str] = []
    quote: Optional[str] = None

    def flush() -> Optional[str]:
        if not buf:
            return None
        seg = "".join(buf)
        buf.clear()
        tok = _first_word(seg)
        if not tok:
            return None
        return os.path.basename(tok)

    while i < n:
        c = command[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ('"', "'"):
            quote = c
            buf.append(c)
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            buf.append(c)
            buf.append(command[i + 1])
            i += 2
            continue
        if c in ";\n":
            lead = flush()
            if lead:
                yield lead
            i += 1
            continue
        if c == "&":
            i += 2 if (i + 1 < n and command[i + 1] == "&") else 1
            lead = flush()
            if lead:
                yield lead
            continue
        if c == "|":
            i += 2 if (i + 1 < n and command[i + 1] == "|") else 1
            lead = flush()
            if lead:
                yield lead
            continue
        buf.append(c)
        i += 1
    lead = flush()
    if lead:
        yield lead


def _first_word(seg: str) -> str:
    """取段内首个单词（忽略前导空白，尊重引号）。"""
    try:
        tokens = shlex.split(seg, posix=(os.name != "nt"))
        if tokens:
            return tokens[0]
    except ValueError:
        pass
    stripped = seg.strip()
    if not stripped:
        return ""
    return stripped.split()[0]