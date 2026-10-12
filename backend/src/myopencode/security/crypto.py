"""透明加解密：AES-256-GCM，主密钥存系统钥匙串，密文带版本前缀。

密文格式（二进制）：
    MAGIC(4) + nonce(12) + ciphertext(+tag)
文本存储统一用 base64 编码成单行字符串，便于 JSONL append-only。

主密钥来源优先级：
    1. 环境变量 `MYOPENCODE_MASTER_KEY`（base64，测试/无钥匙串环境用）
    2. 系统钥匙串（复用 secrets.py 的 SERVICE="myopencode" 下 "master-key"），
       不存在则随机生成 32 字节并写入

调用方需用 try/except 包裹解密：密钥丢失/变更时解密失败属预期，
上层按「读取失败即视为空」处理即可，不崩溃主流程。
"""
from __future__ import annotations

import base64
import os
import threading
from typing import Optional

MAGIC = b"MXE1"

_key_cache: Optional[bytes] = None
_key_lock = threading.Lock()


def _key_from_keychain() -> bytes:
    from .secrets import get_secret, set_secret

    b64 = get_secret("master-key")
    if b64:
        try:
            raw = base64.b64decode(b64)
            if len(raw) == 32:
                return raw
        except Exception:
            pass
    key = os.urandom(32)
    set_secret("master-key", base64.b64encode(key).decode("ascii"))
    return key


def _master_key() -> bytes:
    global _key_cache
    if _key_cache is not None:
        return _key_cache
    with _key_lock:
        if _key_cache is not None:
            return _key_cache
        env = os.environ.get("MYOPENCODE_MASTER_KEY")
        if env:
            try:
                _key_cache = base64.b64decode(env)
            except Exception:
                _key_cache = _key_from_keychain()
        else:
            _key_cache = _key_from_keychain()
        return _key_cache


def _reset_cache() -> None:
    global _key_cache
    with _key_lock:
        _key_cache = None


def is_encrypted(data: bytes) -> bool:
    return data.startswith(MAGIC)


def encrypt(data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    ct = AESGCM(_master_key()).encrypt(nonce, data, MAGIC)
    return MAGIC + nonce + ct


def decrypt(data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not data.startswith(MAGIC):
        return data
    nonce = data[len(MAGIC) : len(MAGIC) + 12]
    ct = data[len(MAGIC) + 12 :]
    try:
        return AESGCM(_master_key()).decrypt(nonce, ct, MAGIC)
    except Exception as exc:
        # 密钥丢失/变更、密文损坏 → 统一抛 ValueError，让上层「读取失败即视为空」的
        # except ValueError 分支生效（AESGCM 原抛 InvalidTag，不属于 ValueError）。
        raise ValueError("解密失败: {}".format(exc)) from exc


def encrypt_str(s: str) -> str:
    return base64.b64encode(encrypt(s.encode("utf-8"))).decode("ascii")


def decrypt_str(s: str) -> str:
    try:
        raw = base64.b64decode(s)
    except Exception:
        return s
    if not raw.startswith(MAGIC):
        return s
    return decrypt(raw).decode("utf-8")