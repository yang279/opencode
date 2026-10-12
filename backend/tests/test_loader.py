from myopencode.config.loader import parse_config_dict


def test_defaults():
    cfg = parse_config_dict({})
    assert cfg.provider == "openai"
    assert cfg.permissions.max_output_bytes == 262144
    assert cfg.llm.timeout_seconds == 120.0
    assert cfg.llm.max_retries == 2


def test_llm_config_parse():
    cfg = parse_config_dict(
        {
            "llm": {
                "timeout_seconds": 30,
                "max_retries": 5,
                "fallback_providers": ["anthropic"],
                "pricing": {"m": {"in_per_mtok": 1.0, "out_per_mtok": 2.0}},
            }
        }
    )
    assert cfg.llm.timeout_seconds == 30
    assert cfg.llm.max_retries == 5
    assert cfg.llm.fallback_providers == ["anthropic"]
    assert cfg.llm.pricing["m"]["out_per_mtok"] == 2.0


def test_permissions_parse():
    cfg = parse_config_dict(
        {"permissions": {"deny_commands": ["rm"], "max_output_bytes": 100, "scrub_secrets": False}}
    )
    assert cfg.permissions.deny_commands == ["rm"]
    assert cfg.permissions.max_output_bytes == 100
    assert cfg.permissions.scrub_secrets is False
