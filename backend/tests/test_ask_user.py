from myopencode.core import events as E
from myopencode.core.agent import Agent


def test_normalize_options_strings_and_dicts():
    out = Agent._normalize_options(["悬疑", {"label": "言情", "recommended": True}])
    assert out == [
        {"label": "悬疑", "description": None, "recommended": False},
        {"label": "言情", "description": None, "recommended": True},
    ]


def test_normalize_options_ignores_empty():
    assert Agent._normalize_options(["", "   ", 123, {"label": ""}, "科幻"]) == [
        {"label": "科幻", "description": None, "recommended": False},
    ]
    assert Agent._normalize_options(None) == []


def test_ask_user_event_options_and_multi():
    ev = E.ask_user("q1", "题材？", [{"label": "悬疑", "recommended": True}], multi=True)
    assert ev["type"] == "ask_user"
    assert ev["options"] == [{"label": "悬疑", "recommended": True}]
    assert ev["multi"] is True

    ev2 = E.ask_user("q2", "还有吗？")
    assert "options" not in ev2
    assert "multi" not in ev2