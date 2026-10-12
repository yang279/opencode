import os

from myopencode.llm.usage_store import UsageStore
from myopencode.server.routes.usage import _read_records


def test_usage_store_encrypted_and_readable(tmp_path):
    store = UsageStore(base_dir=str(tmp_path))
    store.record("gpt-4o", "s1", 100, 50, 0.5)

    records_path = os.path.join(str(tmp_path), "records.jsonl")
    with open(records_path, "r", encoding="utf-8") as fh:
        line = fh.read().strip()
    assert not line.startswith("{")  # 落盘为密文

    recs = _read_records(records_path)
    assert len(recs) == 1
    assert recs[0]["model"] == "gpt-4o"
    assert recs[0]["cost"] == 0.5

    # 聚合文件同样加密，重新加载后仍能聚合出成本
    store2 = UsageStore(base_dir=str(tmp_path))
    assert store2.total_day()["cost"] == 0.5