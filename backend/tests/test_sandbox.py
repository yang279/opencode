"""沙箱选型与显式降级测试。"""
from myopencode.config.schema import SandboxConfig
from myopencode.tools import sandbox as sb


def _no_real_backend(monkeypatch):
    monkeypatch.setattr(sb.ContainerBackend, "available", staticmethod(lambda: False))
    monkeypatch.setattr(sb.SeatbeltBackend, "available", staticmethod(lambda: False))


def test_auto_fallback_disabled(monkeypatch):
    _no_real_backend(monkeypatch)
    s = sb.Sandbox(SandboxConfig(backend="auto", allow_pathguard_fallback=False), "/tmp")
    assert s.backend_name == "disabled"
    assert s.disabled is True
    assert "沙箱不可用" in s.disabled_reason()


def test_auto_fallback_pathguard(monkeypatch):
    _no_real_backend(monkeypatch)
    s = sb.Sandbox(SandboxConfig(backend="auto", allow_pathguard_fallback=True), "/tmp")
    assert s.backend_name == "pathguard"
    assert s.disabled is False


def test_explicit_none_is_native():
    s = sb.Sandbox(SandboxConfig(backend="none"), "/tmp")
    assert s.backend_name == "pathguard"
    assert s.disabled is False


def test_explicit_pathguard_is_native():
    s = sb.Sandbox(SandboxConfig(backend="pathguard"), "/tmp")
    assert s.backend_name == "pathguard"


def test_seatbelt_profile_builds():
    profile = sb._build_profile("/tmp/work", allow_network=False)
    assert "(deny file-write*)" in profile
    assert "(subpath" in profile
    assert "(deny network*)" in profile