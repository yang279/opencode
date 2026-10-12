"""端到端 WS 测试：FastAPI 装配 + WebSocket + FakeProvider 全链路。"""
import json

from fastapi.testclient import TestClient

from myopencode.config.schema import default_config
from myopencode.server import app as app_mod

from fakes import FakeLLMProvider, text


def test_ws_end_to_end(monkeypatch):
    cfg = default_config()
    cfg.provider = "ollama"  # 避免依赖 openai/anthropic SDK，OllamaProvider 构造无网络
    cfg.intent.enabled = False
    cfg.safety.enabled = False
    cfg.memory.enabled = False
    cfg.reflexion.enabled = False
    cfg.sandbox.enabled = False

    provider = FakeLLMProvider([[text("E2E 回复")]])
    monkeypatch.setattr(app_mod, "create_provider", lambda c: provider)

    app = app_mod.create_app(cfg, token="e2e-token")

    with TestClient(app) as client:
        session_id = app.state.sessions.list()[0]["id"]
        with client.websocket_connect("/ws?token=e2e-token") as ws:
            ws.send_text(
                json.dumps(
                    {"type": "user_message", "content": "你好", "session_id": session_id}
                )
            )
            types = []
            for _ in range(50):
                msg = ws.receive_json()
                types.append(msg["type"])
                if msg["type"] == "done":
                    break
            assert "assistant_text" in types
            assert types[-1] == "done"