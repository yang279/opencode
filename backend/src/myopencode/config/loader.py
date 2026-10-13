"""从 JSON 文件加载配置，做浅层校验并合并默认值。"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from ..security.secrets import get_secret, set_secret

from .schema import (
    AppConfig,
    BackupConfig,
    ContainerSandboxConfig,
    DEFAULT_PROTECT_PATHS,
    IntentConfig,
    LLMConfig,
    McpServerConfig,
    MemoryConfig,
    ObservabilityConfig,
    PermissionsConfig,
    PlanningConfig,
    ProviderConfig,
    RagConfig,
    SafetyConfig,
    SandboxConfig,
    SubagentPolicyConfig,
    default_config,
)

CONFIG_FILENAME = "myopencode.json"


def _as_dict(data: Any) -> Dict[str, Any]:
    return data if isinstance(data, dict) else {}


def user_config_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "myopencode", CONFIG_FILENAME)


def load_config(path: Optional[str] = None) -> AppConfig:
    """加载配置。未指定路径时按优先级查找：工作区 → 用户目录。

    密钥从系统钥匙串水合（文件里为 null）；若文件里仍残留明文密钥则迁移进钥匙串
    并回写剥离后的配置。
    """
    resolved: Optional[str] = None
    if path and os.path.isfile(path):
        resolved = path
    else:
        cwd = os.getcwd()
        candidates = [
            os.path.join(cwd, CONFIG_FILENAME),
            user_config_path(),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                resolved = candidate
                break

    if resolved is not None:
        config = _parse(_load_json(resolved))
        migrated = _migrate_plaintext_secrets(config)
        _hydrate_missing_secrets(config)
        if migrated:
            save_config(config, resolved)
        return config

    config = default_config()
    _hydrate_missing_secrets(config)
    return config


def parse_config_dict(data: Dict[str, Any]) -> AppConfig:
    """从 dict 解析完整配置（供 PUT /config 热更新复用）。"""
    return _parse(data)


def save_config(config: AppConfig, path: Optional[str] = None) -> str:
    """序列化配置并写入磁盘（密钥剥离入钥匙串），默认写到用户目录。返回写入路径。"""
    from dataclasses import asdict

    _extract_secrets_to_store(config)
    data = _strip_secrets(asdict(config))
    path = path or user_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return path


def _secret_key_for_provider(name: str) -> str:
    return "provider.{}.api_key".format(name)


def _migrate_plaintext_secrets(config: AppConfig) -> bool:
    """把文件里残留的明文密钥写入钥匙串，返回是否有迁移发生。"""
    changed = False
    for name, pc in config.providers.items():
        if pc.api_key:
            set_secret(_secret_key_for_provider(name), pc.api_key)
            changed = True
    if config.intent.api_key:
        set_secret("intent.api_key", config.intent.api_key)
        changed = True
    if config.memory.summary_api_key:
        set_secret("memory.summary_api_key", config.memory.summary_api_key)
        changed = True
    return changed


def _hydrate_missing_secrets(config: AppConfig) -> None:
    """用钥匙串里的密钥补齐文件里为空的字段。"""
    for name, pc in config.providers.items():
        if not pc.api_key:
            pc.api_key = get_secret(_secret_key_for_provider(name))
    if not config.intent.api_key:
        config.intent.api_key = get_secret("intent.api_key")
    if not config.memory.summary_api_key:
        config.memory.summary_api_key = get_secret("memory.summary_api_key")


def _extract_secrets_to_store(config: AppConfig) -> None:
    """把当前配置里的密钥写入钥匙串（供 save 前调用）。"""
    for name, pc in config.providers.items():
        if pc.api_key:
            set_secret(_secret_key_for_provider(name), pc.api_key)
    if config.intent.api_key:
        set_secret("intent.api_key", config.intent.api_key)
    if config.memory.summary_api_key:
        set_secret("memory.summary_api_key", config.memory.summary_api_key)


def _strip_secrets(data: Dict[str, Any]) -> Dict[str, Any]:
    """把序列化 dict 里的密钥字段置 null（避免明文落盘）。"""
    providers = data.get("providers")
    if isinstance(providers, dict):
        for pc in providers.values():
            if isinstance(pc, dict):
                pc["api_key"] = None
    intent = data.get("intent")
    if isinstance(intent, dict):
        intent["api_key"] = None
    memory = data.get("memory")
    if isinstance(memory, dict):
        memory["summary_api_key"] = None
    return data


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return _as_dict(data)


def _parse(data: Dict[str, Any]) -> AppConfig:
    cfg = default_config()

    if "provider" in data and data["provider"]:
        cfg.provider = str(data["provider"])
    if "model" in data and data["model"] is not None:
        cfg.model = str(data["model"])
    if "working_dir" in data and data["working_dir"]:
        cfg.working_dir = str(data["working_dir"])
    if "system_prompt" in data and data["system_prompt"]:
        cfg.system_prompt = str(data["system_prompt"])

    cfg.providers = _parse_providers(data.get("providers"))
    cfg.permissions = _parse_permissions(data.get("permissions"))
    cfg.mcp_servers = _parse_mcp_servers(data.get("mcp_servers"))
    cfg.memory = _parse_memory(data.get("memory"))
    cfg.intent = _parse_intent(data.get("intent"))
    cfg.sandbox = _parse_sandbox(data.get("sandbox"))
    cfg.backup = _parse_backup(data.get("backup"))
    cfg.observability = _parse_observability(data.get("observability"))
    cfg.planning = _parse_planning(data.get("planning"))
    cfg.subagent = _parse_subagent(data.get("subagent"))
    cfg.llm = _parse_llm(data.get("llm"))
    cfg.safety = _parse_safety(data.get("safety"))
    cfg.rag = _parse_rag(data.get("rag"))
    return cfg


def _parse_providers(raw: Any) -> Dict[str, ProviderConfig]:
    out: Dict[str, ProviderConfig] = {}
    for name, obj in _as_dict(raw).items():
        obj = _as_dict(obj)
        out[str(name)] = ProviderConfig(
            api_key=obj.get("api_key"),
            base_url=obj.get("base_url"),
            model=obj.get("model"),
            extra=obj.get("extra", {}),
        )
    return out


def _parse_permissions(raw: Any) -> PermissionsConfig:
    obj = _as_dict(raw)
    return PermissionsConfig(
        allow_commands=list(obj.get("allow_commands", [])),
        deny_commands=list(obj.get("deny_commands", [])),
        allow_all_commands=bool(obj.get("allow_all_commands", False)),
        default_deny_commands=bool(obj.get("default_deny_commands", True)),
        require_approval_for_write=bool(obj.get("require_approval_for_write", True)),
        require_approval_for_shell=bool(obj.get("require_approval_for_shell", True)),
        max_output_bytes=int(obj.get("max_output_bytes", 262144)),
        scrub_secrets=bool(obj.get("scrub_secrets", True)),
    )


def _parse_mcp_servers(raw: Any) -> Dict[str, McpServerConfig]:
    out: Dict[str, McpServerConfig] = {}
    for name, obj in _as_dict(raw).items():
        obj = _as_dict(obj)
        out[str(name)] = McpServerConfig(
            command=obj.get("command"),
            args=list(obj.get("args", [])),
            env=_as_dict(obj.get("env")),
            url=obj.get("url"),
            transport=str(obj.get("transport", "stdio")),
            headers=_as_dict(obj.get("headers")),
        )
    return out


def _parse_memory(raw: Any) -> MemoryConfig:
    obj = _as_dict(raw)
    return MemoryConfig(
        enabled=bool(obj.get("enabled", True)),
        context_window_tokens=int(obj.get("context_window_tokens", 24000)),
        keep_recent_tokens=int(obj.get("keep_recent_tokens", 8000)),
        semantic_enabled=bool(obj.get("semantic_enabled", True)),
        semantic_max_facts=int(obj.get("semantic_max_facts", 200)),
        auto_extract=bool(obj.get("auto_extract", True)),
        episodic_enabled=bool(obj.get("episodic_enabled", True)),
        episodic_max_entries=int(obj.get("episodic_max_entries", 500)),
        summary_provider=obj.get("summary_provider"),
        summary_model=obj.get("summary_model"),
        summary_api_key=obj.get("summary_api_key"),
        summary_base_url=obj.get("summary_base_url"),
    )


def _parse_intent(raw: Any) -> IntentConfig:
    obj = _as_dict(raw)
    return IntentConfig(
        enabled=bool(obj.get("enabled", True)),
        provider=obj.get("provider"),
        model=obj.get("model"),
        api_key=obj.get("api_key"),
        base_url=obj.get("base_url"),
        semantic_enabled=bool(obj.get("semantic_enabled", True)),
        tool_enabled=bool(obj.get("tool_enabled", True)),
        gate_destructive=bool(obj.get("gate_destructive", True)),
        timeout=float(obj.get("timeout", 10.0)),
        temperature=float(obj.get("temperature", 0.0)),
        max_tokens=int(obj.get("max_tokens", 64)),
        disable_thinking=bool(obj.get("disable_thinking", True)),
    )


def _parse_sandbox(raw: Any) -> SandboxConfig:
    obj = _as_dict(raw)
    cc = _as_dict(obj.get("container"))
    return SandboxConfig(
        enabled=bool(obj.get("enabled", True)),
        backend=str(obj.get("backend", "auto")),
        allow_network=bool(obj.get("allow_network", False)),
        container=ContainerSandboxConfig(
            image=str(cc.get("image", "myopencode-sandbox:latest")),
            cpus=float(cc.get("cpus", 1.0)) if cc.get("cpus") is not None else None,
            memory=str(cc.get("memory", "512m")),
            runtime=str(cc.get("runtime", "auto")),
        ),
        extra_read_paths=list(obj.get("extra_read_paths", [])),
        extra_write_paths=list(obj.get("extra_write_paths", [])),
        deny_write_outside_workspace=bool(obj.get("deny_write_outside_workspace", True)),
        allow_pathguard_fallback=bool(obj.get("allow_pathguard_fallback", False)),
        protect_paths=list(obj.get("protect_paths", DEFAULT_PROTECT_PATHS)),
    )


def _parse_backup(raw: Any) -> BackupConfig:
    obj = _as_dict(raw)
    return BackupConfig(
        enabled=bool(obj.get("enabled", True)),
        retain_on_success=bool(obj.get("retain_on_success", True)),
    )


def _parse_observability(raw: Any) -> ObservabilityConfig:
    obj = _as_dict(raw)
    return ObservabilityConfig(
        log_level=str(obj.get("log_level", "info")),
        log_file=obj.get("log_file", "~/.config/myopencode/logs/myopencode.log"),
        audit_enabled=bool(obj.get("audit_enabled", True)),
        audit_file=obj.get("audit_file", "~/.config/myopencode/audit.jsonl"),
        metrics_enabled=bool(obj.get("metrics_enabled", True)),
        otlp_endpoint=obj.get("otlp_endpoint"),
    )


def _parse_planning(raw: Any) -> PlanningConfig:
    obj = _as_dict(raw)
    return PlanningConfig(
        enabled=bool(obj.get("enabled", True)),
        max_steps=int(obj.get("max_steps", 8)),
        allow_parallel=bool(obj.get("allow_parallel", True)),
        max_parallel=int(obj.get("max_parallel", 3)),
        verify=bool(obj.get("verify", True)),
        max_retries=int(obj.get("max_retries", 1)),
        verify_command=obj.get("verify_command"),
        skip_intents=list(obj.get("skip_intents", ["question", "chat"])),
    )


def _parse_subagent(raw: Any) -> SubagentPolicyConfig:
    obj = _as_dict(raw)
    tools = obj.get("tools")
    return SubagentPolicyConfig(
        enabled=bool(obj.get("enabled", True)),
        tools=list(tools) if tools is not None else None,
        allow_commands=list(obj.get("allow_commands", [])),
        deny_commands=list(obj.get("deny_commands", [])),
        allow_write=bool(obj.get("allow_write", True)),
        allow_execute=bool(obj.get("allow_execute", True)),
        require_approval=bool(obj.get("require_approval", False)),
        budget_usd=float(obj["budget_usd"]) if obj.get("budget_usd") is not None else None,
        max_rounds=int(obj.get("max_rounds", 0)),
    )


def _parse_llm(raw: Any) -> LLMConfig:
    obj = _as_dict(raw)
    return LLMConfig(
        timeout_seconds=float(obj.get("timeout_seconds", 120.0)),
        max_retries=int(obj.get("max_retries", 2)),
        backoff_base=float(obj.get("backoff_base", 1.0)),
        backoff_max=float(obj.get("backoff_max", 8.0)),
        fallback_providers=list(obj.get("fallback_providers", [])),
        pricing=_as_dict(obj.get("pricing")),
        max_concurrent_calls=int(obj.get("max_concurrent_calls", 0)),
    )


def _parse_safety(raw: Any) -> SafetyConfig:
    obj = _as_dict(raw)
    return SafetyConfig(
        enabled=bool(obj.get("enabled", True)),
        llm_confirm=bool(obj.get("llm_confirm", True)),
        confirm_timeout=float(obj.get("confirm_timeout", 10.0)),
        scan_tool_results=bool(obj.get("scan_tool_results", True)),
        content_filter_enabled=bool(obj.get("content_filter_enabled", False)),
        content_filter_timeout=float(obj.get("content_filter_timeout", 10.0)),
        content_action=str(obj.get("content_action", "warn")),
    )


def _parse_rag(raw: Any) -> RagConfig:
    obj = _as_dict(raw)
    raw_exts = obj.get("allowed_extensions")
    exts = [str(e).lower() for e in raw_exts] if raw_exts else list(RagConfig().allowed_extensions)
    return RagConfig(
        enabled=bool(obj.get("enabled", False)),
        allowed_extensions=exts,
        docs_dir=str(obj.get("docs_dir", "~/.config/myopencode/rag/docs")),
        index_file=str(obj.get("index_file", "~/.config/myopencode/rag/index.sqlite3")),
        chunk_size_tokens=int(obj.get("chunk_size_tokens", 500)),
        chunk_overlap_tokens=int(obj.get("chunk_overlap_tokens", 75)),
        chunk_max_tokens=int(obj.get("chunk_max_tokens", 1000)),
        clean_pdf=bool(obj.get("clean_pdf", True)),
        dedup=bool(obj.get("dedup", True)),
        embedding_model=str(obj.get("embedding_model", "text-embedding-3-large")),
        embedding_provider=obj.get("embedding_provider"),
        contextualize=bool(obj.get("contextualize", False)),
        contextualize_model=obj.get("contextualize_model"),
        top_k=int(obj.get("top_k", 5)),
        intents_to_trigger=list(obj.get("intents_to_trigger", ["question", "chat"])),
        bm25_enabled=bool(obj.get("bm25_enabled", True)),
        rrf_k=float(obj.get("rrf_k", 60.0)),
        per_path_recall=int(obj.get("per_path_recall", 20)),
        fusion_candidates=int(obj.get("fusion_candidates", 20)),
        rerank_model=obj.get("rerank_model"),
        max_per_doc=int(obj.get("max_per_doc", 2)),
        injection_max_tokens=int(obj.get("injection_max_tokens", 2000)),
    )