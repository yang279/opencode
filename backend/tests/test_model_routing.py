from myopencode.core.agent import route_provider
from myopencode.config.schema import default_config
from myopencode.llm.registry import create_lite_provider


class _FakeProvider:
    pass


def test_route_provider_lite_on_simple():
    lite = _FakeProvider()
    main = _FakeProvider()
    assert route_provider(lite, main, "question", ["question", "chat"]) is lite
    assert route_provider(lite, main, "chat", ["question", "chat"]) is lite


def test_route_provider_main_on_complex():
    lite = _FakeProvider()
    main = _FakeProvider()
    assert route_provider(lite, main, "code_edit", ["question", "chat"]) is main
    assert route_provider(lite, main, None, ["question", "chat"]) is main


def test_route_provider_main_when_no_lite():
    main = _FakeProvider()
    assert route_provider(None, main, "question", ["question", "chat"]) is main


def test_create_lite_provider_disabled_by_default():
    cfg = default_config()
    assert cfg.llm.lite_model is None
    assert create_lite_provider(cfg) is None