"""Skill 注册表：扫描 SKILL.md，解析 frontmatter，供 agent 渐进式加载。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import yaml

_CJK = re.compile(r"[\u4e00-\u9fff]")


def _bigrams(s: str) -> set:
    return {s[i : i + 2] for i in range(len(s) - 1)}


def _contains_key(key: str, text: str) -> bool:
    """关键词命中判定。

    - 精确子串命中直接通过；
    - 含中文时退化为字符 bigram 交并比（≥0.5），容忍「写小说」→「写一部小说」
      这类中间插入修饰词的变体，同时避免「小说」误命中「小明说笑」。
    """
    key = key.strip()
    if not key:
        return False
    if key in text:
        return True
    if not _CJK.search(key):
        return False
    kg = _bigrams(key)
    if not kg:
        return key in text
    tg = _bigrams(text)
    hit = len(kg & tg)
    return hit / len(kg) >= 0.5


@dataclass
class Skill:
    name: str
    description: str
    content: str
    path: str
    source: str  # "user" | "project"
    trigger: List[str] = field(default_factory=list)  # 触发关键词（确定性匹配用）


def _split_frontmatter(text: str) -> Tuple[Dict, str]:
    """把 SKILL.md 拆成 (frontmatter dict, 正文)。"""
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, text.strip()
    idx = text.find("\n---", 3)
    if idx == -1:
        return {}, text.strip()
    fm_raw = text[3:idx]
    body = text[idx + 4:]
    while body.startswith("\n"):
        body = body[1:]
    try:
        data = yaml.safe_load(fm_raw) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data, body.strip()


def _parse_trigger(fm: Dict) -> List[str]:
    """从 frontmatter 提取触发关键词（metadata.trigger），支持字符串/列表。"""
    meta = fm.get("metadata")
    raw = None
    if isinstance(meta, dict):
        raw = meta.get("trigger")
    elif isinstance(meta, list):
        for item in meta:
            if isinstance(item, dict) and "trigger" in item:
                raw = item["trigger"]
                break
    if raw is None:
        return []
    items: List[str] = []
    if isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw]
    else:
        # 按中英文标点切分
        text = str(raw)
        for ch in "、，,；;/\n":
            text = text.replace(ch, "|")
        items = [p.strip() for p in text.split("|")]
    return [k for k in items if k]


def parse_skill_md(path: str) -> Optional[Skill]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    fm, body = _split_frontmatter(text)
    if not fm.get("name") and not fm.get("description"):
        return None
    return Skill(
        name=str(fm.get("name") or os.path.basename(os.path.dirname(path))),
        description=str(fm.get("description") or ""),
        content=body,
        path=path,
        source="project",
        trigger=_parse_trigger(fm),
    )


def scan_skills(workdir: str) -> List[Skill]:
    """扫描用户级 + 项目级 skill 目录。"""
    roots: List[Tuple[str, str]] = [
        ("user", os.path.join(os.path.expanduser("~"), ".config", "myopencode", "skills")),
        ("project", os.path.join(workdir, ".myopencode", "skills")),
    ]
    skills: List[Skill] = []
    for source, root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            skill_file = os.path.join(root, name, "SKILL.md")
            if not os.path.isfile(skill_file):
                continue
            skill = parse_skill_md(skill_file)
            if skill is not None:
                skill.source = source
                skills.append(skill)
    return skills


class SkillRegistry:
    def __init__(self, skills: Optional[List[Skill]] = None) -> None:
        self._skills: Dict[str, Skill] = {s.name: s for s in (skills or [])}

    def list(self) -> List[Skill]:
        return sorted(self._skills.values(), key=lambda s: s.name)

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def match(self, user_content: str) -> Optional[Skill]:
        """确定性触发：用户消息命中某 skill 的触发关键词或名称时返回该 skill。"""
        text = (user_content or "").lower()
        for s in self.list():
            keys = list(s.trigger) + [s.name]
            if any(_contains_key(k.lower(), text) for k in keys):
                return s
        return None

    def system_prompt_section(self) -> str:
        if not self._skills:
            return ""
        lines = [
            "",
            "可用 Skills（需要时通过 load_skill 工具加载完整内容）：",
        ]
        for s in self.list():
            lines.append("- {}: {}".format(s.name, s.description))
        return "\n".join(lines)