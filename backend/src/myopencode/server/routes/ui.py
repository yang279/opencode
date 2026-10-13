"""UI 外观路由：自定义背景图上传 / 读取 / 删除。"""
from __future__ import annotations

import base64
import os
from typing import List, Optional

from fastapi import APIRouter, UploadFile

router = APIRouter()

_MAX_BYTES = 10 * 1024 * 1024
_ALLOWED_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_UI_DIR = os.path.expanduser("~/.config/myopencode/ui")


def _background_paths() -> List[str]:
    if not os.path.isdir(_UI_DIR):
        return []
    return sorted(
        os.path.join(_UI_DIR, f)
        for f in os.listdir(_UI_DIR)
        if f.startswith("background.")
    )


def _current() -> Optional[str]:
    paths = _background_paths()
    return paths[0] if paths else None


@router.put("/ui/background")
async def put_background(file: UploadFile):
    ext = os.path.splitext(file.filename or "")[1].lower()
    mime = _ALLOWED_EXT.get(ext)
    if not mime:
        return {"ok": False, "error": "不支持的图片类型（仅 png/jpg/jpeg/webp/gif）"}
    data = await file.read()
    if len(data) > _MAX_BYTES:
        return {"ok": False, "error": "图片超过 10MB 上限"}
    os.makedirs(_UI_DIR, exist_ok=True)
    for p in _background_paths():
        try:
            os.remove(p)
        except OSError:
            pass
    with open(os.path.join(_UI_DIR, "background" + ext), "wb") as fh:
        fh.write(data)
    return {"ok": True}


@router.get("/ui/background")
async def get_background():
    path = _current()
    if path is None:
        return {"exists": False, "data_url": None}
    ext = os.path.splitext(path)[1].lower()
    mime = _ALLOWED_EXT.get(ext, "image/png")
    with open(path, "rb") as fh:
        data = fh.read()
    return {
        "exists": True,
        "data_url": "data:{};base64,{}".format(mime, base64.b64encode(data).decode("ascii")),
    }


@router.delete("/ui/background")
async def delete_background():
    removed = False
    for p in _background_paths():
        try:
            os.remove(p)
            removed = True
        except OSError:
            pass
    return {"ok": removed}
