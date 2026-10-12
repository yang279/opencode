import os

from myopencode.core.session_manager import SessionManager
from myopencode.core.session import Message


def test_atomic_save_and_reload(tmp_path):
    path = os.path.join(str(tmp_path), "sessions.json")
    sm = SessionManager(path=path)
    s = sm.create()
    s.append(Message(role="user", content="hi"))
    sm.save()

    assert not os.path.exists(path + ".tmp")
    with open(path) as fh:
        raw = fh.read()
    assert not raw.startswith("[")  # 加密落盘，非明文 JSON

    sm2 = SessionManager(path=path)
    sm2.load()
    assert sm2.sessions[s.session_id].messages[0].content == "hi"


def test_delete_and_list(tmp_path):
    path = os.path.join(str(tmp_path), "sessions.json")
    sm = SessionManager(path=path)
    a = sm.create()
    b = sm.create()
    assert len(sm.list()) == 2
    assert sm.delete(a.session_id) is True
    assert sm.delete(a.session_id) is False
    assert [x["id"] for x in sm.list()] == [b.session_id]


def test_list_newest_first(tmp_path):
    path = os.path.join(str(tmp_path), "sessions.json")
    sm = SessionManager(path=path)
    a = sm.create()
    b = sm.create()
    # list() 返回最新在前
    assert [x["id"] for x in sm.list()] == [b.session_id, a.session_id]


def test_ensure_default(tmp_path):
    path = os.path.join(str(tmp_path), "sessions.json")
    sm = SessionManager(path=path)
    sm.ensure_default()
    assert len(sm.sessions) == 1


def test_add_usage(tmp_path):
    path = os.path.join(str(tmp_path), "sessions.json")
    sm = SessionManager(path=path)
    s = sm.create()
    sm.add_usage(s.session_id, 100, 50)
    meta = sm.list()[0]
    assert meta["tokens_in"] == 100
    assert meta["tokens_out"] == 50

    sm.save()
    sm2 = SessionManager(path=path)
    sm2.load()
    assert sm2.sessions[s.session_id].tokens_in == 100
    assert sm2.sessions[s.session_id].tokens_out == 50


def test_resolve_question(tmp_path):
    import asyncio

    from myopencode.core.session import QuestionItem

    path = os.path.join(str(tmp_path), "sessions.json")
    sm = SessionManager(path=path)
    s = sm.create()
    loop = asyncio.new_event_loop()
    fut = loop.create_future()
    s.pending_questions["q1"] = QuestionItem(question_id="q1", question="选哪个?", future=fut)
    assert sm.resolve_question("q1", "A") is True
    assert fut.result() == "A"
    assert sm.resolve_question("missing", "x") is False
    loop.close()
