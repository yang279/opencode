"""UI 背景图路由：上传 / 读取 / 删除、类型与大小校验。"""
import asyncio
import base64
import io

from starlette.datastructures import UploadFile

from myopencode.server.routes import ui as ui_mod

# 1x1 透明 PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def _upload(name: str, data: bytes):
    return UploadFile(filename=name, file=io.BytesIO(data))


def test_background_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_mod, "_UI_DIR", str(tmp_path))
    assert asyncio.run(ui_mod.get_background())["exists"] is False

    res = asyncio.run(ui_mod.put_background(_upload("bg.png", _PNG)))
    assert res["ok"] is True

    got = asyncio.run(ui_mod.get_background())
    assert got["exists"] is True
    assert got["data_url"].startswith("data:image/png;base64,")

    assert asyncio.run(ui_mod.delete_background())["ok"] is True
    assert asyncio.run(ui_mod.get_background())["exists"] is False


def test_background_rejects_bad_type(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_mod, "_UI_DIR", str(tmp_path))
    res = asyncio.run(ui_mod.put_background(_upload("evil.exe", b"x")))
    assert res["ok"] is False


def test_background_replaces_previous(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_mod, "_UI_DIR", str(tmp_path))
    asyncio.run(ui_mod.put_background(_upload("old.png", _PNG)))
    asyncio.run(ui_mod.put_background(_upload("new.jpg", _PNG)))
    paths = ui_mod._background_paths()
    assert len(paths) == 1
    assert paths[0].endswith("background.jpg")