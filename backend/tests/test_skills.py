import asyncio
import os
import tempfile

from myopencode.skills.load_skill_tool import LoadSkillTool
from myopencode.skills.registry import SkillRegistry, parse_skill_md
from myopencode.tools.base import ToolContext


def _write_skill(root, name, trigger, body="\n# Body\n"):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    fm = "---\nname: {}\ndescription: test skill\nmetadata:\n  trigger: {}\n---\n".format(
        name, trigger
    )
    path = os.path.join(d, "SKILL.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(fm + body)
    return path


def test_parse_trigger():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_skill(tmp, "novel", "写小说、创作故事、长篇小说")
        skill = parse_skill_md(path)
        assert skill.name == "novel"
        assert skill.trigger == ["写小说", "创作故事", "长篇小说"]


def test_match_trigger():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_skill(tmp, "novel", "写小说、创作故事")
        reg = SkillRegistry([parse_skill_md(path)])
        assert reg.match("请帮我写小说").name == "novel"
        assert reg.match("写一部小说").name == "novel"
        assert reg.match("用 novel 技能").name == "novel"
        assert reg.match("今天天气怎么样") is None


def test_load_skill_with_resource():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_skill(tmp, "novel", "写小说", body="\n# Body\n\n见 references/phase1.md\n")
        d = os.path.dirname(path)
        os.makedirs(os.path.join(d, "references"), exist_ok=True)
        with open(os.path.join(d, "references", "phase1.md"), "w", encoding="utf-8") as fh:
            fh.write("# Phase 1\nQ1: 题材？")
        reg = SkillRegistry([parse_skill_md(path)])
        tool = LoadSkillTool(reg)
        ctx = ToolContext(working_dir=tmp)

        r1 = asyncio.run(tool.execute({"name": "novel"}, ctx))
        assert "# Body" in r1.output
        assert "references/phase1.md" in r1.output

        r2 = asyncio.run(tool.execute({"name": "novel", "resource": "references/phase1.md"}, ctx))
        assert "Q1: 题材？" in r2.output

        r3 = asyncio.run(tool.execute({"name": "novel", "resource": "../etc/passwd"}, ctx))
        assert r3.error is True