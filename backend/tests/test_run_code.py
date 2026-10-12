"""run_code 的 wasm 优雅降级测试。"""
from myopencode.tools.run_code import RunCodeTool


def test_wasm_enum_without_runner(monkeypatch):
    monkeypatch.setattr("myopencode.tools.run_code._wasm_runner_binary", lambda: None)
    t = RunCodeTool()
    assert t.json_schema["properties"]["language"]["enum"] == ["python"]


def test_wasm_enum_with_runner(monkeypatch):
    monkeypatch.setattr(
        "myopencode.tools.run_code._wasm_runner_binary",
        lambda: "/usr/bin/wasm-runner",
    )
    t = RunCodeTool()
    assert t.json_schema["properties"]["language"]["enum"] == ["python", "wasm"]