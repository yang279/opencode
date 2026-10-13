"""RAG 服务编排：上传文件 → 抽取 → 清洗 → 分块 → 去重 → 落库。

embedding/检索留待后续 Phase 接入（当前 chunk 的 embedding 为 NULL）。
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, List

from ..config.schema import RagConfig
from .chunker import Chunk, chunk_text, dedup_chunks
from .clean import clean_text
from .extract import extract_text, file_ext
from .store import RagStore

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(name: str) -> str:
    return _SAFE_NAME_RE.sub("_", os.path.basename(name or "doc")) or "doc"


class RagService:
    def __init__(self, config: RagConfig) -> None:
        self.config = config
        self.store = RagStore(config.index_file, config.docs_dir)
        self.allowed = {e.lower() for e in config.allowed_extensions}

    def upload(self, name: str, data: bytes) -> Dict[str, Any]:
        """处理单份上传，返回 {name, doc_id?, chunks?, skipped, error?}。"""
        ext = file_ext(name)
        if ext not in self.allowed:
            return {"name": name, "skipped": True, "error": "不支持的类型: {}".format(ext or "(无扩展名)")}

        sha = hashlib.sha256(data).hexdigest()
        existing = self.store.get_by_sha256(sha)
        if existing:
            return {"name": name, "doc_id": existing, "chunks": 0, "skipped": True, "error": "已存在（内容相同）"}

        text = extract_text(name, data, self.allowed)
        if not text.strip():
            return {"name": name, "skipped": True, "error": "未提取到文本"}

        kind = self._clean_kind(ext)
        text = clean_text(text, kind=kind, clean_pdf=self.config.clean_pdf)
        chunks: List[Chunk] = chunk_text(
            text,
            ext,
            chunk_size=self.config.chunk_size_tokens,
            overlap=self.config.chunk_overlap_tokens,
            hard_max=self.config.chunk_max_tokens,
        )
        if self.config.dedup:
            chunks = dedup_chunks(chunks)
        if not chunks:
            return {"name": name, "skipped": True, "error": "清洗/分块后无有效内容"}

        raw_path = self._save_raw(sha, name, data)
        doc_id = self.store.add_document(name, sha, len(data), ext, source_path=raw_path)
        self.store.add_chunks(doc_id, chunks)
        self.store.set_chunk_count(doc_id, len(chunks))
        return {"name": name, "doc_id": doc_id, "chunks": len(chunks), "skipped": False}

    def list_documents(self) -> List[Dict[str, Any]]:
        return self.store.list_documents()

    def delete(self, doc_id: str) -> bool:
        raw_path = self.store.delete_document(doc_id)
        if raw_path:
            try:
                os.remove(raw_path)
            except OSError:
                pass
        return raw_path is not None

    def _clean_kind(self, ext: str) -> str:
        if ext == ".pdf":
            return "pdf"
        if ext == ".docx":
            return "docx"
        if ext in (".md", ".markdown"):
            return "markdown"
        if ext in {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".c",
                   ".cpp", ".h", ".cs", ".rb", ".sh", ".yml", ".yaml", ".json",
                   ".toml", ".html", ".css", ".sql"}:
            return "code"
        return "text"

    def _save_raw(self, sha: str, name: str, data: bytes) -> str:
        path = os.path.join(self.store.docs_dir, "{}-{}".format(sha[:16], _safe_name(name)))
        with open(path, "wb") as fh:
            fh.write(data)
        return path