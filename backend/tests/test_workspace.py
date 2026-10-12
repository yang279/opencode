import os

from myopencode.__main__ import _default_workspace, _is_root_path, _normalize_working_dir


def test_default_workspace_creates_dir(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    ws = _default_workspace()
    assert ws == str(home / "myopencode")
    assert os.path.isdir(ws)


def test_normalize_creates_missing_dir(tmp_path):
    target = tmp_path / "nested" / "missing"
    out = _normalize_working_dir(str(target))
    assert os.path.isdir(out)
    assert out == os.path.realpath(str(target))


def test_normalize_root_falls_back(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    out = _normalize_working_dir("/")
    assert out == os.path.realpath(str(home / "myopencode"))
    assert os.path.isdir(out)


def test_is_root_path():
    assert _is_root_path("/") is True
    assert _is_root_path("/some/dir") is False