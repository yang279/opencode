"""RAG 服务编排：上传/抽取/清洗/分块/向量化 + 多路检索（语义+BM25）→ RRF 融合 → LLM 重排。"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np

from ..config.schema import RagConfig
from .bm25 import BM25Index
from .chunker import Chunk, chunk_text, dedup_chunks
from .clean import clean_text
from .embedder import Embedder
from .extract import extract_text, file_ext
from .reranker import Reranker
from .store import RagStore

_logger = logging.getLogger("myopencode.rag")

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(name: str) -> str:
    return _SAFE_NAME_RE.sub("_", os.path.basename(name or "doc")) or "doc"


class RagService:
    def __init__(
        self,
        config: RagConfig,
        embedder: Optional[Embedder] = None,
        reranker: Optional[Reranker] = None,
    ) -> None:
        self.config = config
        self.embedder = embedder
        self.reranker = reranker
        self.store = RagStore(config.index_file, config.docs_dir)
        self.allowed = {e.lower() for e in config.allowed_extensions}
        # 检索内存索引（与 store 同步）
        self._chunks: List[Dict[str, Any]] = []
        self._vectors: Optional[np.ndarray] = None  # (M, dim) L2 归一化
        self._vec_indices: List[int] = []  # 全局 chunk 下标
        self._bm25 = BM25Index()
        self._reload_index()

    # ── 摄取 ────────────────────────────────────────────────────────
    async def upload(self, name: str, data: bytes) -> Dict[str, Any]:
        ext = file_ext(name)
        if ext not in self.allowed:
            return {"name": name, "skipped": True, "error": "不支持的类型: {}".format(ext or "(无扩展名)")}

        sha = hashlib.sha256(data).hexdigest()
        existing = self.store.get_by_sha256(sha)
        if existing:
            return {"name": name, "doc_id": existing, "chunks": 0, "skipped": True, "error": "已存在（内容相同）"}

        text = self._extract_safe(name, data)
        if not text or not text.strip():
            return {"name": name, "skipped": True, "error": "未提取到文本"}

        kind = self._clean_kind(ext)
        text = clean_text(text, kind=kind, clean_pdf=self.config.clean_pdf)
        chunks: List[Chunk] = chunk_text(
            text, ext,
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
        inserted = self.store.add_chunks(doc_id, chunks)
        self.store.set_chunk_count(doc_id, len(chunks))
        await self._embed_and_store(inserted)
        self._reload_index()
        return {"name": name, "doc_id": doc_id, "chunks": len(chunks), "skipped": False}

    def _extract_safe(self, name: str, data: bytes) -> str:
        try:
            return extract_text(name, data, self.allowed)
        except Exception as exc:
            _logger.warning("rag.extract_failed", extra={"file": name, "error": str(exc)})
            return ""

    def list_documents(self) -> List[Dict[str, Any]]:
        return self.store.list_documents()

    def delete(self, doc_id: str) -> bool:
        raw_path = self.store.delete_document(doc_id)
        if raw_path:
            try:
                os.remove(raw_path)
            except OSError:
                pass
        self._reload_index()
        return raw_path is not None

    async def reindex(self) -> Dict[str, Any]:
        """补全缺失向量 + 重建内存索引。"""
        if self.embedder is not None and self.embedder.available:
            missing = self.store.chunks_without_embedding()
            if missing:
                await self._embed_and_store(missing)
        self._reload_index()
        return {"chunks": len(self._chunks), "vectors": int(self._vectors.shape[0]) if self._vectors is not None else 0}

    async def _embed_and_store(self, rows: List[Dict[str, Any]]) -> None:
        if self.embedder is None or not self.embedder.available or not rows:
            return
        try:
            vecs = await self.embedder.embed([r["text"] for r in rows])
        except Exception as exc:
            _logger.warning("rag.embed_failed", extra={"error": str(exc)})
            return  # 向量化失败不中断：chunk 保持 NULL，BM25 仍可检索
        for r, v in zip(rows, vecs):
            self.store.update_embedding(r["id"], np.asarray(v, dtype=np.float32).tobytes())

    # ── 检索（三段）─────────────────────────────────────────────────
    async def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        top_k = top_k or self.config.top_k
        if not self._chunks:
            return []

        fused_scores: Dict[int, float] = {}
        for rank, gi in enumerate(await self._semantic_recall(query)):
            fused_scores[gi] = fused_scores.get(gi, 0.0) + 1.0 / (self.config.rrf_k + rank + 1)
        if self.config.bm25_enabled:
            for rank, (gi, _score) in enumerate(self._bm25.search(query, self.config.per_path_recall)):
                fused_scores[gi] = fused_scores.get(gi, 0.0) + 1.0 / (self.config.rrf_k + rank + 1)

        fused = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)[: self.config.fusion_candidates]

        if self.reranker is not None and len(fused) > 1:
            cand = [self._chunks[i] for i, _ in fused]
            order = await self.reranker.rerank(query, cand)
            fused = [fused[i] for i in order]

        return self._finalize(fused, top_k)

    async def _semantic_recall(self, query: str) -> List[int]:
        if self._vectors is None or not self._vec_indices:
            return []
        if self.embedder is None or not self.embedder.available:
            return []
        try:
            vecs = await self.embedder.embed([query])
        except Exception as exc:
            _logger.warning("rag.embed_query_failed", extra={"error": str(exc)})
            return []
        if not vecs:
            return []
        qv = np.asarray(vecs[0], dtype=np.float32)
        norm = np.linalg.norm(qv)
        if norm == 0:
            return []
        sims = self._vectors @ (qv / norm)
        top = np.argsort(-sims)[: self.config.per_path_recall]
        return [self._vec_indices[int(i)] for i in top]

    def _finalize(self, fused: List[Any], top_k: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        per_doc: Dict[str, int] = {}
        total_tokens = 0
        for gi, score in fused:
            c = self._chunks[gi]
            if per_doc.get(c["doc_id"], 0) >= self.config.max_per_doc:
                continue
            toks = c.get("token_count") or 0
            if total_tokens + toks > self.config.injection_max_tokens and out:
                break
            per_doc[c["doc_id"]] = per_doc.get(c["doc_id"], 0) + 1
            total_tokens += toks
            out.append({"text": c["text"], "heading": c["heading"], "source": c["source"], "score": round(float(score), 4)})
            if len(out) >= top_k:
                break
        return out

    # ── 内部 ────────────────────────────────────────────────────────
    def _reload_index(self) -> None:
        rows = self.store.load_all_chunks()
        self._chunks = [
            {"id": r["id"], "doc_id": r["doc_id"], "text": r["text"],
             "heading": r["heading"], "token_count": r["token_count"], "source": r["source"]}
            for r in rows
        ]
        self._vec_indices = []
        vecs: List[np.ndarray] = []
        for i, r in enumerate(rows):
            if r.get("embedding"):
                v = np.frombuffer(r["embedding"], dtype=np.float32).copy()
                if v.size:
                    vecs.append(v)
                    self._vec_indices.append(i)
        if vecs:
            mat = np.vstack(vecs)
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._vectors = mat / norms
        else:
            self._vectors = None
        self._bm25.build([c["text"] for c in self._chunks])

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
