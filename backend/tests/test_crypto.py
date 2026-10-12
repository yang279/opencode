import base64
import os

from myopencode.security import crypto


def _seed(monkeypatch):
    monkeypatch.setenv("MYOPENCODE_MASTER_KEY", base64.b64encode(os.urandom(32)).decode())
    crypto._reset_cache()


def test_encrypt_decrypt_roundtrip(monkeypatch):
    _seed(monkeypatch)
    ct = crypto.encrypt(b"hello world")
    assert ct != b"hello world"
    assert crypto.is_encrypted(ct)
    assert crypto.decrypt(ct) == b"hello world"


def test_decrypt_plaintext_passthrough(monkeypatch):
    _seed(monkeypatch)
    assert crypto.decrypt(b"plain") == b"plain"
    assert crypto.is_encrypted(b"plain") is False


def test_str_roundtrip(monkeypatch):
    _seed(monkeypatch)
    s = '{"a": 1, "b": "中文"}'
    enc = crypto.encrypt_str(s)
    assert enc != s
    assert crypto.decrypt_str(enc) == s


def test_decrypt_str_passthrough(monkeypatch):
    _seed(monkeypatch)
    assert crypto.decrypt_str("not base64!!!") == "not base64!!!"
    plain_b64 = base64.b64encode(b"plain").decode()
    assert crypto.decrypt_str(plain_b64) == plain_b64


def test_decrypt_wrong_key_raises_valueerror(monkeypatch):
    _seed(monkeypatch)
    ct = crypto.encrypt(b"secret")
    # 换一把钥匙再解 → 应抛 ValueError（而非 cryptography 的 InvalidTag）
    _seed(monkeypatch)
    import pytest

    with pytest.raises(ValueError):
        crypto.decrypt(ct)


def test_session_manager_encrypted_roundtrip(tmp_path, monkeypatch):
    _seed(monkeypatch)
    from myopencode.core.session_manager import SessionManager

    path = str(tmp_path / "sessions.json")
    m1 = SessionManager(path=path)
    m1.create()
    m1.save()

    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    assert not raw.startswith("[")  # 落盘为密文，非明文 JSON

    m2 = SessionManager(path=path)
    m2.load()
    assert len(m2.sessions) == 1
