"""RAG 索引存储：SQLite（标准库），文档元数据 + chunk 文本 + 向量 BLOB。

schema:
- docs(id TEXT PK, name, source_path, sha256 UNIQUE, size, ext, chunk_count, created_at)
- chunks(id TEXT PK, doc_id, seq, text, heading, token_count, embedding BLOB NULL)
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_path TEXT,
    sha256 TEXT UNIQUE,
    size INTEGER,
    ext TEXT,
    chunk_count INTEGER DEFAULT 0,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    heading TEXT DEFAULT '',
    token_count INTEGER DEFAULT 0,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
"""


class RagStore:
    def __init__(self, index_file: str, docs_dir: str) -> None:
        self.index_file = os.path.expanduser(index_file)
        self.docs_dir = os.path.expanduser(docs_dir)
        os.makedirs(self.docs_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.index_file) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.index_file)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── 文档 ──────────────────────────────────────────────────────
    def get_by_sha256(self, sha256: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT id FROM docs WHERE sha256 = ?", (sha256,)
        ).fetchone()
        return row["id"] if row else None

    def add_document(
        self, name: str, sha256: str, size: int, ext: str, source_path: Optional[str] = None
    ) -> str:
        doc_id = uuid.uuid4().hex
        self._conn.execute(
            "INSERT INTO docs (id, name, source_path, sha256, size, ext, chunk_count, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (doc_id, name, source_path, sha256, size, ext, time.time()),
        )
        self._conn.commit()
        return doc_id

    def set_chunk_count(self, doc_id: str, count: int) -> None:
        self._conn.execute(
            "UPDATE docs SET chunk_count = ? WHERE id = ?", (count, doc_id)
        )
        self._conn.commit()

    def list_documents(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, name, source_path, sha256, size, ext, chunk_count, created_at"
            " FROM docs ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_document(self, doc_id: str) -> Optional[str]:
        """删除文档及 chunk，返回原始文件路径（供调用方删除）。"""
        row = self._conn.execute(
            "SELECT source_path FROM docs WHERE id = ?", (doc_id,)
        ).fetchone()
        if row is None:
            return None
        self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self._conn.execute("DELETE FROM docs WHERE id = ?", (doc_id,))
        self._conn.commit()
        return row["source_path"]

    # ── chunks ────────────────────────────────────────────────────
    def add_chunks(self, doc_id: str, chunks: List[Any]) -> None:
        """chunks: list of Chunk（.text/.heading/.token_count）。embedding 后补。"""
        for i, c in enumerate(chunks):
            self._conn.execute(
                "INSERT OR REPLACE INTO chunks (id, doc_id, seq, text, heading, token_count, embedding)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, doc_id, i, c.text, c.heading, c.token_count, None),
            )
        self._conn.commit()

    def count_chunks(self, doc_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return row["n"] if row else 0

    def close(self) -> None:
        self._conn.close()