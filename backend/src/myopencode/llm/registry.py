"""Provider 注册与工厂。"""
from __future__ import annotations

from typing import Dict, Type

from ..config.schema import AppConfig, ProviderConfig
from .base import LLMProvider

_PROVIDERS: Dict[str, Type] = {}
_IMPORTED = False

# 意图识别默认小模型（快 + 准，未显式配置 intent.model 时使用）
RECOGNITION_FALLBACK_MODEL = "qwen3.8-flash"


def register(name: str, cls: Type) -> None:
    _PROVIDERS[name] = cls


def _lazy_import() -> None:
    global _IMPORTED
    if _IMPORTED:
        return
    _IMPORTED = True
    from .ollama_provider import OllamaProvider

    register("ollama", OllamaProvider)
    try:
        from .openai_provider import OpenAIProvider

        register("openai", OpenAIProvider)
    except Exception:  # pragma: no cover
        pass
    try:
        from .anthropic_provider import AnthropicProvider

        register("anthropic", AnthropicProvider)
    except Exception:  # pragma: no cover
        pass


def create_named_provider(
    name: str, pc: ProviderConfig, model: str | None = None
) -> LLMProvider:
    """按名称 + ProviderConfig 实例化 provider（供摘要等独立模型复用）。"""
    _lazy_import()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError("未知 provider: {!r}，可用: {}".format(name, sorted(_PROVIDERS)))
    return cls(api_key=pc.api_key, base_url=pc.base_url, model=model)


def create_provider(config: AppConfig) -> LLMProvider:
    """根据配置实例化主对话 provider。"""
    name = config.resolve_provider()
    pc: ProviderConfig = config.providers.get(name, ProviderConfig())
    return create_named_provider(name, pc, config.resolve_model())


def create_fallback_providers(config: AppConfig) -> list:
    """实例化备用 provider 链（config.llm.fallback_providers 顺序，去重并排除主 provider）。"""
    out = []
    seen = {config.resolve_provider()}
    for fb in config.llm.fallback_providers:
        if not fb or fb in seen:
            continue
        seen.add(fb)
        pc = config.providers.get(fb, ProviderConfig())
        out.append(create_named_provider(fb, pc, pc.model))
    return out


def create_lite_provider(config: AppConfig):
    """模型路由用的小模型 provider：复用主 provider 连接，只换模型名。

    `config.llm.lite_model` 未配置时返回 None（路由关闭，全走主模型）。
    """
    if not config.llm.lite_model:
        return None
    name = config.resolve_provider()
    pc = config.providers.get(name, ProviderConfig())
    return create_named_provider(name, pc, config.llm.lite_model)


def create_summary_provider(config: AppConfig) -> LLMProvider:
    """为摘要任务构造 provider：优先独立摘要模型，否则回退主 provider。"""
    mc = config.memory
    if mc.summary_provider:
        pc = ProviderConfig(
            api_key=mc.summary_api_key,
            base_url=mc.summary_base_url,
            model=mc.summary_model,
        )
        return create_named_provider(mc.summary_provider, pc, mc.summary_model)
    return create_provider(config)


def create_recognition_provider(config: AppConfig) -> LLMProvider:
    """为意图识别构造 provider。

    优先级：
    1. 配置了 intent.provider → 完全独立的识别模型
    2. 仅配置了 intent.model   → 复用主 provider 的连接(key/base_url)，只换模型名
    3. 都未配置                → 复用主连接，模型换成小模型默认值（快 + 准，不思考）
    """
    ic = config.intent
    if ic.provider:
        pc = ProviderConfig(
            api_key=ic.api_key,
            base_url=ic.base_url,
            model=ic.model,
        )
        return create_named_provider(ic.provider, pc, ic.model)
    name = config.resolve_provider()
    pc = config.providers.get(name, ProviderConfig())
    model = ic.model or RECOGNITION_FALLBACK_MODEL
    return create_named_provider(name, pc, model)


def available_providers() -> list:
    _lazy_import()
    return sorted(_PROVIDERS)