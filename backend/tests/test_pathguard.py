"""写保护路径（protect_paths）测试。"""
import pytest

from myopencode.config.schema import SandboxConfig
from myopencode.tools.pathguard import PathDeniedError, PathGuard


def test_protect_git(tmp_path):
    g = PathGuard(str(tmp_path), protect_paths=[".git/**"])
    with pytest.raises(PathDeniedError):
        g.resolve(".git/config", write=True)


def test_protect_config_file(tmp_path):
    g = PathGuard(str(tmp_path), protect_paths=["myopencode.json"])
    with pytest.raises(PathDeniedError):
        g.resolve("myopencode.json", write=True)


def test_protect_env_glob(tmp_path):
    g = PathGuard(str(tmp_path), protect_paths=["**/.env*"])
    with pytest.raises(PathDeniedError):
        g.resolve("sub/.env.production", write=True)


def test_normal_write_allowed(tmp_path):
    g = PathGuard(str(tmp_path), protect_paths=[".git/**"])
    assert g.resolve("src/foo.txt", write=True)


def test_read_not_affected(tmp_path):
    g = PathGuard(str(tmp_path), protect_paths=["myopencode.json"])
    assert g.resolve("myopencode.json", write=False)


def test_default_protect_paths():
    cfg = SandboxConfig()
    assert ".git/**" in cfg.protect_paths
    assert "myopencode.json" in cfg.protect_paths
    assert "**/.env*" in cfg.protect_paths