"""结构化附件（Claude 式文档块）：Message 序列化 + content_parts + agent 落库。"""
import asyncio
import base64

from fastapi.testclient import TestClient

from myopencode.config.schema import default_config
from myopencode.core.agent import Agent
from myopencode.core.session import Message, Session
from myopencode.server import app as app_mod
from myopencode.tools.registry import ToolRegistry

from fakes import FakeLLMProvider, text


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _client(monkeypatch):
    cfg = default_config()
    cfg.provider = "ollama"
    cfg.intent.enabled = False
    cfg.safety.enabled = False
    cfg.memory.enabled = False
    cfg.reflexion.enabled = False
    cfg.sandbox.enabled = False
    monkeypatch.setattr(app_mod, "create_provider", lambda c: FakeLLMProvider([]))
    app = app_mod.create_app(cfg, token="t")
    return TestClient(app)


def test_message_attachment_roundtrip():
    att = [{"name": "a.txt", "media_type": "text/plain", "data_b64": _b64("hello")}]
    m = Message(role="user", content="看看", attachments=att)
    d = m.to_dict()
    assert d["attachments"] == att
    assert Message.from_dict(d).attachments == att


def test_no_attachments_returns_plain_string():
    assert Message(role="user", content="plain").content_parts("anthropic") == "plain"


def test_content_parts_text_block():
    m = Message(role="user", content="总结", attachments=[
        {"name": "a.txt", "media_type": "text/plain", "data_b64": _b64("hello world")},
    ])
    parts = m.content_parts("anthropic")
    assert isinstance(parts, list)
    assert {"type": "text", "text": "总结"} in parts
    assert any("hello world" in p["text"] for p in parts if p["type"] == "text")


def test_content_parts_image_and_pdf_anthropic_native():
    m = Message(role="user", content="", attachments=[
        {"name": "a.png", "media_type": "image/png", "data_b64": base64.b64encode(b"\x89PNG").decode()},
        {"name": "b.pdf", "media_type": "application/pdf", "data_b64": _b64("pdf-bytes")},
    ])
    parts = m.content_parts("anthropic")
    types = {p["type"] for p in parts}
    assert "image" in types
    assert "document" in types


def test_content_parts_openai_image_url_and_skips_pdf():
    m = Message(role="user", content="hi", attachments=[
        {"name": "a.png", "media_type": "image/png", "data_b64": base64.b64encode(b"\x89PNG").decode()},
        {"name": "b.pdf", "media_type": "application/pdf", "data_b64": _b64("pdf")},
        {"name": "c.txt", "media_type": "text/plain", "data_b64": _b64("txt")},
    ])
    parts = m.content_parts("openai")
    types = {p["type"] for p in parts}
    assert types == {"text", "image_url"}
    img = next(p for p in parts if p["type"] == "image_url")
    assert img["image_url"]["url"].startswith("data:image/png;base64,")


def test_extract_pdf_endpoint_blank(monkeypatch):
    from pypdf import PdfWriter
    import io as _io

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = _io.BytesIO()
    w.write(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()

    client = _client(monkeypatch)
    with client:
        r = client.post("/workspace/extract-pdf", json={"data_b64": b64})
    assert r.status_code == 200
    assert "text" in r.json()


def test_extract_pdf_endpoint_invalid(monkeypatch):
    client = _client(monkeypatch)
    with client:
        r = client.post(
            "/workspace/extract-pdf",
            json={"data_b64": base64.b64encode(b"not a pdf").decode()},
        )
    assert r.json().get("error")


def test_agent_run_persists_attachments_and_title(tmp_path):
    cfg = default_config()
    cfg.working_dir = str(tmp_path)
    cfg.sandbox.enabled = False
    events = []

    async def emit(ev):
        events.append(ev)

    agent = Agent(
        config=cfg,
        provider=FakeLLMProvider([[text("收到")]]),
        tools=ToolRegistry(),
        emit=emit,
    )
    session = Session(session_id="s1", title="新对话")
    atts = [{"name": "a.txt", "media_type": "text/plain", "data_b64": _b64("hello")}]

    asyncio.run(agent.run(session, "", atts))

    user = [m for m in session.messages if m.role == "user"][-1]
    assert user.attachments == atts
    assert session.title == "a.txt"
    assert events[-1]["type"] == "done"