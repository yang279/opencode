"""测试全局夹具：为所有测试注入随机会话加密密钥，避免触碰真实钥匙串。"""
import base64
import os

import pytest

from myopencode.security import crypto


@pytest.fixture(autouse=True)
def _seed_master_key(monkeypatch):
    monkeypatch.setenv("MYOPENCODE_MASTER_KEY", base64.b64encode(os.urandom(32)).decode())
    crypto._reset_cache()
    yield
    crypto._reset_cache()
