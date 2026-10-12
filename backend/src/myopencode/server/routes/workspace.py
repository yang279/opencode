"""工作区文件浏览与读取（受 working_dir scope 约束）。"""
from __future__ import annotations

import os
from typing import Dict, List

from fastapi import APIRouter, Request

router = APIRouter()


def _scope(root: str, rel: str) -> str:
    base = os.path.abspath(root)
    target = os.path.abspath(os.path.join(base, rel))
    if not target.startswith(base + os.sep) and target != base:
        return None  # 越界
    return target


def _walk(root: str) -> List[Dict]:
    entries = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "__pycache__", "dist", "target")]
        rel = os.path.relpath(dirpath, root)
        for d in dirs:
            entries.append({"path": os.path.join(rel, d), "type": "dir"})
        for f in files:
            entries.append({"path": os.path.join(rel, f), "type": "file"})
        if len(entries) > 2000:
            break
    return entries


@router.get("/workspace/tree")
async def workspace_tree(request: Request):
    root = os.path.abspath(request.app.state.config.working_dir)
    entries = _walk(root)
    return {"root": root, "entries": entries}


@router.get("/workspace/file")
async def workspace_file(request: Request, path: str):
    root = os.path.abspath(request.app.state.config.working_dir)
    target = _scope(root, path)
    if target is None:
        return {"error": "路径越界"}
    if not os.path.isfile(target):
        return {"error": "文件不存在"}
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as fh:
            return {"path": path, "content": fh.read()}
    except OSError as exc:
        return {"error": str(exc)}