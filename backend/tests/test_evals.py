from myopencode.evals.judge import EvalCase, judge


def test_judge_pass_on_tool_call():
    case = EvalCase(id="c1", prompt="列出目录", expect_tools=["list_dir"])
    events = [
        {"type": "tool_call_start", "name": "list_dir"},
        {"type": "tool_call_end", "result": "..."},
        {"type": "done"},
    ]
    r = judge(case, events)
    assert r["passed"] is True
    assert r["reasons"] == []


def test_judge_fail_on_missing_tool():
    case = EvalCase(id="c2", prompt="读取文件", expect_tools=["read_file"])
    events = [{"type": "tool_call_start", "name": "grep"}, {"type": "done"}]
    r = judge(case, events)
    assert r["passed"] is False
    assert any("read_file" in reason for reason in r["reasons"])


def test_judge_fail_on_missing_ask_user():
    case = EvalCase(id="c3", prompt="问用户", expect_ask_user=True)
    events = [{"type": "done"}]
    r = judge(case, events)
    assert r["passed"] is False


def test_judge_fail_on_error_and_no_done():
    case = EvalCase(id="c4", prompt="x", expect_tools=[])
    events = [{"type": "error", "message": "boom"}]
    r = judge(case, events)
    assert r["passed"] is False
    assert len(r["reasons"]) == 2


def test_judge_fail_on_forbidden_tool():
    case = EvalCase(id="s1", prompt="x", forbidden_tools=["run_shell"])
    events = [
        {"type": "tool_call_start", "name": "run_shell", "args": {}},
        {"type": "tool_call_end", "result": ""},
        {"type": "done"},
    ]
    r = judge(case, events)
    assert r["passed"] is False
    assert any("禁止的工具" in reason for reason in r["reasons"])


def test_judge_expect_safety_event():
    case = EvalCase(id="s2", prompt="x", expect_safety_event=True)
    assert judge(case, [{"type": "done"}])["passed"] is False
    events = [
        {"type": "safety", "id": "s", "reasons": ["高危"], "severity": "high"},
        {"type": "done"},
    ]
    assert judge(case, events)["passed"] is True


def test_judge_reject_passes_on_safety_stop():
    case = EvalCase(id="s3", prompt="x", expect_reject=True, forbidden_tools=["run_shell"])
    events = [
        {"type": "safety", "id": "s", "reasons": ["高危"], "severity": "high"},
        {"type": "error", "message": "已按安全策略停止本次执行"},
        {"type": "done"},
    ]
    r = judge(case, events)
    assert r["passed"] is True
    assert r["reasons"] == []


def test_judge_reject_fails_when_not_blocked():
    case = EvalCase(id="s4", prompt="x", expect_reject=True)
    r = judge(case, [{"type": "done"}])
    assert r["passed"] is False
    assert any("阻止" in reason for reason in r["reasons"])
