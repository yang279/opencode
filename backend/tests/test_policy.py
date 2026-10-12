from myopencode.config.schema import PermissionsConfig
from myopencode.security.policy import PermissionPolicy, _iter_command_leads


def _policy(**kw):
    return PermissionPolicy(PermissionsConfig(**kw))


def test_deny_first_token_exact():
    p = _policy(deny_commands=["rm", "sudo", "shutdown"])
    assert p.check_command("rm -rf /") is not None
    assert p.check_command("/usr/bin/rm x") is not None
    assert p.check_command("sudo rm -rf /") is not None
    assert p.check_command("cat f; shutdown now") is not None


def test_deny_does_not_match_arg():
    p = _policy(deny_commands=["rm"], default_deny_commands=False)
    assert p.check_command("echo rm") is None
    assert p.check_command('pgrep -f "/bin/rm"') is None


def test_deny_respects_quotes_and_operators():
    p = _policy(deny_commands=["rm"], default_deny_commands=False)
    assert p.check_command('echo "a;b"') is None
    assert p.check_command("ls && rm x") is not None
    assert p.check_command("grep foo | cat") is None


def test_allow_list_exact():
    p = _policy(allow_commands=["ls", "cat"])
    assert p.check_command("ls -l") is None
    assert p.check_command("rm x") is not None
    assert p.check_command("echo hi") is not None


def test_allow_all():
    p = _policy(allow_all_commands=True, deny_commands=["rm"])
    assert p.check_command("ls -l") is None
    assert p.check_command("rm x") is not None  # deny 优先


def test_iter_leads():
    leads = list(_iter_command_leads("echo hi; rm -rf / && cat x | grep y"))
    assert leads == ["echo", "rm", "cat", "grep"]


def test_default_deny_rejects_unlisted():
    p = _policy()
    assert p.check_command("ls -l") is not None
    assert p.check_command("echo hi") is not None


def test_default_deny_allows_allowlist_only():
    p = _policy(allow_commands=["ls", "cat"])
    assert p.check_command("ls -l") is None
    assert p.check_command("cat x") is None
    assert p.check_command("rm x") is not None


def test_default_deny_allow_all_escape():
    p = _policy(allow_all_commands=True, deny_commands=["rm"])
    assert p.check_command("ls -l") is None
    assert p.check_command("rm x") is not None


def test_default_deny_off_legacy_allow():
    p = _policy(default_deny_commands=False)
    assert p.check_command("ls -l") is None
