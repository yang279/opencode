"""RAG 知识库路由：上传、列表、删除。"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Request, UploadFile

router = APIRouter()


@router.post("/rag/upload")
async def rag_upload(request: Request, files: List[UploadFile]):
    rag = request.app.state.rag
    results = []
    for f in files:
        data = await f.read()
        results.append(rag.upload(f.filename or "doc", data))
    return {"results": results}


@router.get("/rag/docs")
async def rag_docs(request: Request):
    rag = request.app.state.rag
    return {"docs": rag.list_documents()}


@router.delete("/rag/docs/{doc_id}")
async def rag_delete(request: Request, doc_id: str):
    rag = request.app.state.rag
    ok = rag.delete(doc_id)
    return {"ok": ok}
