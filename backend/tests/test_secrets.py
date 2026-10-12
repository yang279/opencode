import json
import os

import myopencode.config.loader as loader
from myopencode.config.schema import ProviderConfig, default_config
from myopencode.security import secrets


def test_file_fallback_roundtrip(tmp_path, monkeypatch):
    # 强制走文件兜底，避免命中系统钥匙串
    monkeypatch.setattr(secrets, "_mac_available", lambda: False)
    monkeypatch.setattr(secrets, "_linux_available", lambda: False)
    monkeypatch.setattr(secrets, "_file_dir", lambda: str(tmp_path))

    assert secrets.set_secret("test.k", "v123")
    assert secrets.get_secret("test.k") == "v123"
    assert secrets.delete_secret("test.k") is True
    assert secrets.get_secret("test.k") is None


def test_strip_secrets():
    cfg = default_config()
    cfg.providers["openai"] = ProviderConfig(api_key="sk-xxx", base_url="https://x", model="m")
    cfg.intent.api_key = "ik"
    cfg.memory.summary_api_key = "sk"
    data = loader._strip_secrets(
        {
            "providers": {"openai": {"api_key": "sk-xxx"}},
            "intent": {"api_key": "ik"},
            "memory": {"summary_api_key": "sk"},
        }
    )
    assert data["providers"]["openai"]["api_key"] is None
    assert data["intent"]["api_key"] is None
    assert data["memory"]["summary_api_key"] is None


def test_save_hydrate_migrate(tmp_path, monkeypatch):
    store = {}
    monkeypatch.setattr(loader, "set_secret", lambda n, v: store.__setitem__(n, v))
    monkeypatch.setattr(loader, "get_secret", lambda n: store.get(n))

    cfg = default_config()
    cfg.providers["openai"] = ProviderConfig(api_key="sk-plain", base_url="https://x", model="m")
    cfg.intent.api_key = "intent-key"
    cfg.memory.summary_api_key = "sum-key"

    p = os.path.join(str(tmp_path), "myopencode.json")
    loader.save_config(cfg, p)
    with open(p) as fh:
        on_disk = json.load(fh)
    assert on_disk["providers"]["openai"]["api_key"] is None
    assert store["provider.openai.api_key"] == "sk-plain"

    cfg2 = loader.load_config(p)
    assert cfg2.providers["openai"].api_key == "sk-plain"
    assert cfg2.intent.api_key == "intent-key"
    assert cfg2.memory.summary_api_key == "sum-key"

    # 迁移：磁盘残留明文 → 载入后迁入 store 并回写剥离
    store.clear()
    with open(p) as fh:
        legacy = json.load(fh)
    legacy["providers"]["openai"]["api_key"] = "legacy-plain"
    with open(p, "w") as fh:
        json.dump(legacy, fh)
    loader.load_config(p)
    assert store["provider.openai.api_key"] == "legacy-plain"
    with open(p) as fh:
        after = json.load(fh)
    assert after["providers"]["openai"]["api_key"] is None
