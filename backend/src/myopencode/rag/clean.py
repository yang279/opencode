"""文本清洗：通用基础 + PDF/Word 专项 + 代码保护。

清洗分层：
- 通用（所有类型）：去 BOM / 控制字符、换行归一、全角空格
- PDF/Word 专项（clean_pdf 开关）：去页眉页脚/页码、连字符断词、断行合并
- 代码：只做换行归一 + BOM + 控制字符，保留缩进与空白
"""
from __future__ import annotations

import re
from typing import List

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")

_SENTENCE_END = "。！？!?；;：:"

# 独立成行的页眉/页脚/页码
_PAGE_NOISE_RE = re.compile(
    r"^\s*(?:"
    r"第\s*\d+\s*页(?:\s*共\s*\d+\s*页)?"          # 第3页 / 第3页共10页
    r"|page\s+\d+\s*(?:of\s+\d+)?"                 # Page 3 of 10
    r"|\d+\s*/\s*\d+"                              # 3 / 10
    r"|\d+"
    r")\s*$",
    re.IGNORECASE,
)

# 英文连字符断词：hyphen-\n ation -> hyphenation
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\s*\n\s*(\w)")

# 下一行不合并的信号：列表 / 标题 / 代码 / 编号
_NOT_JOIN_PREFIX_RE = re.compile(r"^\s*(?:[-*•#>|=]|\d+[\.、\)]|`{3,})")


def clean_text(text: str, *, kind: str, clean_pdf: bool = True) -> str:
    """清洗单份文档文本。kind ∈ {pdf, docx, markdown, code, text}。"""
    if not text:
        return ""
    text = text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)

    if kind == "code":
        return text.strip()

    text = text.replace("\u3000", " ")

    if clean_pdf and kind in ("pdf", "docx"):
        text = _remove_page_noise(text)
        text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)

    if kind in ("pdf", "docx", "text"):
        text = _join_broken_lines(text)

    if kind == "markdown":
        text = _MULTI_BLANK_RE.sub("\n\n", text)
    else:
        text = _MULTI_SPACE_RE.sub(" ", text)
        text = _MULTI_BLANK_RE.sub("\n\n", text)

    return text.strip()


def _remove_page_noise(text: str) -> str:
    return "\n".join(
        line for line in text.split("\n") if not _PAGE_NOISE_RE.match(line)
    )


def _join_broken_lines(text: str) -> str:
    """把 PDF 抽取中段落内部的硬换行合并；保留列表/标题/空行。"""
    lines = text.split("\n")
    out: List[str] = []
    for line in lines:
        if not out or not line.strip():
            out.append(line)
            continue
        prev = out[-1]
        if _should_join(prev, line):
            out[-1] = prev.rstrip() + " " + line.lstrip()
        else:
            out.append(line)
    return "\n".join(out)


def _should_join(prev: str, nxt: str) -> bool:
    if not prev.strip() or not nxt.strip():
        return False
    if prev.rstrip()[-1] in _SENTENCE_END:
        return False  # 上一行已到句尾
    if _NOT_JOIN_PREFIX_RE.match(nxt):
        return False  # 下一行是列表/标题/编号/代码
    return True