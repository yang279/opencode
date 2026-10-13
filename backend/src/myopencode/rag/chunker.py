"""结构感知分块：按文件类型选边界，中文不截词。

- markdown：按标题切 section，维护标题路径，段落过长按句界再切，块首拼标题路径
- code：按「空行/顶格声明(def/class/fn/...)」切逻辑块
- 纯文本：空行切段 → 句界切句 → 累积成块

统一规则：目标 chunk_size、15% 左右 overlap、hard_max 硬上限。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from ..memory.short_term import estimate_tokens

_MARKDOWN_EXTS = {".md", ".markdown", ".docx"}
_CODE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".rb", ".sh", ".yml", ".yaml", ".json", ".toml",
    ".html", ".css", ".sql", ".php", ".swift", ".kt", ".m", ".mm",
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TOPLEVEL_DECL_RE = re.compile(
    r"^\s*(?:async\s+)?(?:def|class|fn|impl|struct|enum|trait|interface|"
    r"function|public\s+(?:class|function|static|void)|private\s+(?:class|static|void)|"
    r"const|let|var|#ifndef|#define|#include)\b"
)


@dataclass
class Chunk:
    text: str
    heading: str = ""
    token_count: int = 0

    def to_dict(self) -> dict:
        return {"text": self.text, "heading": self.heading, "token_count": self.token_count}


def kind_for_ext(ext: str) -> str:
    if ext in _MARKDOWN_EXTS:
        return "markdown"
    if ext in _CODE_EXTS:
        return "code"
    return "text"


def chunk_text(
    text: str,
    source_ext: str,
    chunk_size: int = 500,
    overlap: int = 75,
    hard_max: int = 1000,
) -> List[Chunk]:
    """把文档文本切成 Chunk 列表。"""
    kind = kind_for_ext(source_ext)
    if kind == "markdown":
        return _chunk_markdown(text, chunk_size, overlap, hard_max)
    if kind == "code":
        return _chunk_code(text, chunk_size, overlap, hard_max)
    return _chunk_plain(text, chunk_size, overlap, hard_max)


# ── markdown ─────────────────────────────────────────────────────────
def _chunk_markdown(text: str, chunk_size: int, overlap: int, hard_max: int) -> List[Chunk]:
    chunks: List[Chunk] = []
    for heading, body in _split_markdown_sections(text):
        units = _paragraphs_to_units(body)
        for body_text in _pack(units, chunk_size, overlap, hard_max, _split_sentences):
            full = (heading + "\n\n" + body_text) if heading else body_text
            chunks.append(Chunk(text=full, heading=heading, token_count=estimate_tokens(full)))
    return chunks


def _split_markdown_sections(text: str) -> List[Tuple[str, str]]:
    """返回 [(heading_path, body_text)]，标题路径用 ' > ' 连接。"""
    sections: List[Tuple[str, str]] = []
    stack: List[Tuple[int, str]] = []
    body: List[str] = []

    def flush() -> None:
        if body or stack:
            path = " > ".join(t for _, t in stack)
            sections.append((path, "\n".join(body)))
            body.clear()

    for line in text.split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            flush()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, line.strip()))
        else:
            body.append(line)
    flush()
    return sections


def _paragraphs_to_units(body: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


# ── code ─────────────────────────────────────────────────────────────
def _chunk_code(text: str, chunk_size: int, overlap: int, hard_max: int) -> List[Chunk]:
    blocks = _split_code_blocks(text)
    chunks: List[Chunk] = []
    for block in _pack(blocks, chunk_size, overlap, hard_max, _split_lines):
        chunks.append(Chunk(text=block, token_count=estimate_tokens(block)))
    return chunks


def _split_code_blocks(text: str) -> List[str]:
    blocks: List[str] = []
    cur: List[str] = []
    for line in text.split("\n"):
        if cur and _starts_new_block(line):
            blocks.append("\n".join(cur))
            cur = []
        if line.strip() or cur:
            cur.append(line)
    if "".join(cur).strip():
        blocks.append("\n".join(cur))
    return blocks


def _starts_new_block(line: str) -> bool:
    if not line.strip():
        return False
    if line[0] in " \t":
        return False  # 缩进内容属于上一块
    return bool(_TOPLEVEL_DECL_RE.match(line))


# ── plain text ───────────────────────────────────────────────────────
def _chunk_plain(text: str, chunk_size: int, overlap: int, hard_max: int) -> List[Chunk]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units: List[str] = []
    for p in paras:
        units.extend(_split_sentences(p))
    chunks: List[Chunk] = []
    for body in _pack(units, chunk_size, overlap, hard_max, _split_sentences):
        chunks.append(Chunk(text=body, token_count=estimate_tokens(body)))
    return chunks


# ── 通用打包 ─────────────────────────────────────────────────────────
def _pack(
    units: List[str],
    chunk_size: int,
    overlap: int,
    hard_max: int,
    split_fn,
) -> List[str]:
    """把 units 打包成不超过 chunk_size 的文本块，带 overlap 衔接。"""
    flat: List[str] = []
    for u in units:
        flat.extend(_hard_split(u, hard_max, split_fn))
    if not flat:
        return []

    chunks: List[str] = []
    cur: List[str] = []
    cur_tokens = 0
    for u in flat:
        t = estimate_tokens(u)
        if cur and cur_tokens + t > chunk_size:
            chunks.append("\n".join(cur))
            cur = _overlap_tail(cur, overlap)
            cur_tokens = sum(estimate_tokens(x) for x in cur)
        cur.append(u)
        cur_tokens += t
    if cur:
        chunks.append("\n".join(cur))
    return [c for c in chunks if c.strip()]


def _overlap_tail(cur: List[str], overlap: int) -> List[str]:
    """从尾部回接 ~overlap token 的单元，作为下一块衔接头。"""
    tail: List[str] = []
    acc = 0
    for u in reversed(cur):
        tail.append(u)
        acc += estimate_tokens(u)
        if acc >= overlap:
            break
    tail.reverse()
    return tail


def _hard_split(unit: str, hard_max: int, split_fn) -> List[str]:
    """单个 unit 超过 hard_max 时按 split_fn 硬切。"""
    if estimate_tokens(unit) <= hard_max or not unit.strip():
        return [unit]
    pieces = split_fn(unit)
    if len(pieces) <= 1:
        return [unit]
    out: List[str] = []
    buf: List[str] = []
    buf_tokens = 0
    for p in pieces:
        t = estimate_tokens(p)
        if buf and buf_tokens + t > hard_max:
            out.append("\n".join(buf))
            buf = []
            buf_tokens = 0
        buf.append(p)
        buf_tokens += t
    if buf:
        out.append("\n".join(buf))
    return out


# ── 拆句 / 拆行 ──────────────────────────────────────────────────────
_SENT_DELIM = "。！？!?；;"


def _split_sentences(text: str) -> List[str]:
    """按句界切分，保留标点，中文不截词。"""
    out: List[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        buf = ""
        for ch in para:
            buf += ch
            if ch in _SENT_DELIM:
                if buf.strip():
                    out.append(buf.strip())
                buf = ""
        if buf.strip():
            out.append(buf.strip())
    return out


def _split_lines(text: str) -> List[str]:
    return [ln for ln in text.split("\n") if ln.strip()]


def dedup_chunks(chunks: List[Chunk]) -> List[Chunk]:
    """按归一化空白后的文本去重，保持顺序，剔除空块。"""
    seen = set()
    out: List[Chunk] = []
    for c in chunks:
        key = re.sub(r"\s+", " ", c.text or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out