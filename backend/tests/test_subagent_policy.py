"""子代理策略（SubagentPolicy）单元测试。"""
from myopencode.config.schema import PermissionsConfig, SubagentPolicyConfig
from myopencode.security.policy import PermissionPolicy


def _sp(**kw):
    return SubagentPolicyConfig(**kw)


def _policy(subagent=None, **perms):
    return PermissionPolicy(
        PermissionsConfig(**perms), delegated=True, subagent=subagent
    )


def test_subagent_tool_allowlist():
    p = _policy(_sp(tools=["read_file", "grep"]))
    assert p.restrict_tool("read_file", "read") is None
    assert p.restrict_tool("write_file", "write") is not None
    assert p.restrict_tool("run_shell", "execute") is not None


def test_subagent_allow_write_false():
    p = _policy(_sp(allow_write=False))
    assert p.restrict_tool("edit_file", "write") is not None
    assert p.restrict_tool("read_file", "read") is None


def test_subagent_allow_execute_false():
    p = _policy(_sp(allow_execute=False))
    assert p.restrict_tool("run_shell", "execute") is not None
    assert p.restrict_tool("run_code", "execute") is not None
    assert p.restrict_tool("write_file", "write") is None


def test_subagent_command_allowlist_overrides():
    p = _policy(
        _sp(allow_commands=["ls"]),
        allow_commands=["ls", "git"],
        default_deny_commands=True,
    )
    assert p.check_command("ls -l") is None
    assert p.check_command("git status") is not None


def test_subagent_deny_union():
    p = _policy(_sp(deny_commands=["curl"]), deny_commands=["rm"], default_deny_commands=False)
    assert p.check_command("rm -rf /") is not None
    assert p.check_command("curl http://x") is not None
    assert p.check_command("ls -l") is None


def test_subagent_require_approval_true():
    p = _policy(_sp(require_approval=True), require_approval_for_write=True)
    assert p.needs_approval("write_file", {"path": "x"}) is not None


def test_subagent_require_approval_default_false():
    p = _policy(_sp(), require_approval_for_write=True)
    assert p.needs_approval("write_file", {"path": "x"}) is None