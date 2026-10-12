import os
import tempfile

from myopencode.config.schema import LLMConfig
from myopencode.llm.budget import BudgetGuard
from myopencode.llm.usage_store import UsageStore
from myopencode.server.routes.usage import _read_records


def _guard(**kw):
    cfg = LLMConfig(**kw)
    store = UsageStore(base_dir=tempfile.mkdtemp())
    return BudgetGuard(cfg, store), store


def test_usage_store_accumulates():
    store = UsageStore(base_dir=tempfile.mkdtemp())
    store.record("gpt-4o", "s1", 1000, 500, 0.001)
    store.record("gpt-4o", "s2", 500, 250, 0.0005)
    today = store.total_day()
    assert today["tokens_in"] == 1500
    assert today["tokens_out"] == 750
    assert abs(today["cost"] - 0.0015) < 1e-9
    summary = store.summary()
    assert summary["this_month"]["tokens_in"] == 1500
    assert "gpt-4o" in summary["by_model_today"]


def test_budget_under_warning_over():
    guard, store = _guard(daily_budget_usd=1.0, monthly_budget_usd=10.0)
    assert guard.status()["over"] is False
    # 每日花到 0.8 → warning
    store.record("gpt-4o", "s1", 0, 0, 0.8)
    st = guard.status()
    assert st["warning"] is True
    assert st["over"] is False
    # 超过 1.0 → over
    store.record("gpt-4o", "s1", 0, 0, 0.3)
    assert guard.status()["over"] is True


def test_budget_hard_stop_flag():
    guard, store = _guard(daily_budget_usd=1.0, budget_hard_stop=True)
    store.record("gpt-4o", "s1", 0, 0, 1.5)
    st = guard.status()
    assert st["over"] is True
    assert st["hard_stop"] is True
    assert "$" in guard.message(st)


def test_budget_record_attaches_session():
    guard, store = _guard()
    guard.record("sess-42", "gpt-4o", 100, 50, 0.5)
    recs = _read_records(os.path.join(store.base, "records.jsonl"))
    assert len(recs) == 1
    assert recs[0]["session_id"] == "sess-42"
