"""load_skill 内置工具：读取指定 skill 的正文，或按需读取其 references 等资源。

渐进披露：`load_skill(name)` 返回正文 + 可用资源清单；`load_skill(name, resource=...)`
读取 skill 目录内的具体资源文件（限制在 skill 目录内，防路径穿越）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from ..tools.base import ToolContext, ToolResult
from .registry import Skill, SkillRegistry

_MAX_LIST = 40


def _skill_dir(skill: Skill) -> str:
    return os.path.dirname(skill.path)


def _list_resources(skill: Skill) -> List[str]:
    root = _skill_dir(skill)
    out: List[str] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if fn == "SKILL.md" or fn.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), root)
                out.append(rel)
    except OSError:  # pragma: no cover
        return []
    return out[: _MAX_LIST]


def _read_resource(skill: Skill, resource: str) -> ToolResult:
    root = os.path.realpath(_skill_dir(skill))
    target = os.path.realpath(os.path.join(root, resource))
    if not (target == root or target.startswith(root + os.sep)):
        return ToolResult(output="非法资源路径：{}".format(resource), error=True)
    try:
        with open(target, "r", encoding="utf-8") as fh:
            return ToolResult(output=fh.read())
    except OSError as exc:
        return ToolResult(output="读取失败: {}".format(exc), error=True)


class LoadSkillTool:
    name = "load_skill"
    category = "skill"
    description = "加载指定 skill 的完整说明文档，或读取其 references 资源文件，用于执行该 skill 约定的任务"
    json_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "要加载的 skill 名称"},
            "resource": {
                "type": "string",
                "description": "可选：skill 内的资源相对路径（如 references/flows/phase1.md）",
            },
        },
        "required": ["name"],
    }

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        name = str(args.get("name", ""))
        skill = self.registry.get(name)
        if skill is None:
            return ToolResult(
                output="未找到 skill: {}。可用: {}".format(name, [s.name for s in self.registry.list()]),
                error=True,
            )
        resource = str(args.get("resource", "")).strip()
        if resource:
            return _read_resource(skill, resource)

        resources = _list_resources(skill)
        out = skill.content
        if resources:
            out += "\n\n## 可用资源（用 load_skill 的 resource 参数按需读取）\n" + "\n".join(
                "- {}".format(r) for r in resources
            )
        return ToolResult(output=out)