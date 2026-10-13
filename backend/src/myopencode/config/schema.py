"""配置数据结构定义。

使用 dataclass 定义，便于 JSON 序列化与默认值合并。仅依赖标准库。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 默认写保护路径：命中即拒绝写（相对工作目录的 glob 模式）
DEFAULT_PROTECT_PATHS = [
    ".git/**",
    "myopencode.json",
    "**/.env*",
    "**/*.key",
    "**/*.pem",
    "~/.aws/**",
    "~/.ssh/**",
]


@dataclass
class ProviderConfig:
    """单个 LLM Provider 的连接配置。"""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionsConfig:
    """权限策略配置。"""

    allow_commands: List[str] = field(default_factory=list)
    deny_commands: List[str] = field(default_factory=list)
    allow_all_commands: bool = False
    # 企业态：未配置白名单时命令默认拒绝（False=保持旧版默认放行，deny-only）
    default_deny_commands: bool = True
    require_approval_for_write: bool = True
    require_approval_for_shell: bool = True
    # 工具输出进入 LLM/前端前的字节上限（超出截断）
    max_output_bytes: int = 262144  # 256 KB
    # 工具输出进入 LLM/历史前是否做 secret 回扫脱敏
    scrub_secrets: bool = True


@dataclass
class McpServerConfig:
    """单个 MCP server 的连接配置（stdio 或远程 streamable HTTP）。"""

    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    # transport: stdio | http（streamable HTTP，含 SSE 响应解析）
    transport: str = "stdio"
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class MemoryConfig:
    """记忆模块配置：短期滚动压缩 + 长期（语义/场景）记忆。"""

    enabled: bool = True
    # 短期记忆（滚动压缩）：超过窗口才惰性折叠
    context_window_tokens: int = 24000
    keep_recent_tokens: int = 8000
    # 长期·语义记忆
    semantic_enabled: bool = True
    semantic_max_facts: int = 200
    auto_extract: bool = True
    # 长期·场景记忆
    episodic_enabled: bool = True
    episodic_max_entries: int = 500
    # 独立摘要模型（未配置则回退主 provider）
    summary_provider: Optional[str] = None
    summary_model: Optional[str] = None
    summary_api_key: Optional[str] = None
    summary_base_url: Optional[str] = None


@dataclass
class IntentConfig:
    """意图识别配置：语义识别 + 工具识别（剪枝/gating）+ RAG 预留。"""

    enabled: bool = True
    # 独立识别模型（未配置则回退到 registry 的小模型默认值，见 RECOGNITION_FALLBACK_MODEL）
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    # 语义识别开关
    semantic_enabled: bool = True
    # 工具识别：剪枝 + 安全 gating
    tool_enabled: bool = True
    gate_destructive: bool = True
    # 识别超时（秒）
    timeout: float = 10.0
    # 纯分类采样：快 + 准，禁用思考
    temperature: float = 0.0
    max_tokens: int = 64
    disable_thinking: bool = True


@dataclass
class ContainerSandboxConfig:
    """容器沙箱后端配置（Docker/podman，跨平台，Windows 可用）。"""

    image: str = "myopencode-sandbox:latest"
    cpus: Optional[float] = 1.0
    memory: str = "512m"
    runtime: str = "auto"  # auto | docker | colima | podman


@dataclass
class SafetyConfig:
    """安全护栏配置：前置恶意意图拦截 + 间接注入检测 + 内容审核。"""

    enabled: bool = True
    # 规则命中后用识别小模型二次精排，仍判有风险才弹确认
    llm_confirm: bool = True
    confirm_timeout: float = 10.0
    # 工具返回（read_file/grep/MCP）的高精度注入扫描
    scan_tool_results: bool = True
    # 最终回答内容审核（默认关，避免引入回答延迟）
    content_filter_enabled: bool = False
    content_filter_timeout: float = 10.0
    content_action: str = "warn"  # warn | block


@dataclass
class LLMConfig:
    """主 LLM 调用韧性配置：超时 / 重试 / 退避 / 降级链。"""

    timeout_seconds: float = 120.0
    max_retries: int = 2
    backoff_base: float = 1.0
    backoff_max: float = 8.0
    # 主 provider 首 token 前失败且重试耗尽后，依次切换的备用 provider 名
    fallback_providers: List[str] = field(default_factory=list)
    # 成本价格表：model -> {"in_per_mtok": ..., "out_per_mtok": ...}（每百万 token 价格）
    pricing: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # 成本治理：预算上限（None 表示不限额）
    daily_budget_usd: Optional[float] = None
    monthly_budget_usd: Optional[float] = None
    # 单次请求最大生成 token 数（None 表示不限制，沿用 provider 默认）
    per_request_max_tokens: Optional[int] = None
    # 跨会话的 LLM 并发上限（0=不限；>0 时全局信号量限制并发调用）
    max_concurrent_calls: int = 0
    # 预算超限时是否硬停当前任务（True=硬停，False=仅告警）
    budget_hard_stop: bool = True
    # 模型路由：简单意图走更便宜的小模型（复用主 provider 连接，只换模型名）
    lite_model: Optional[str] = None
    simple_intents: List[str] = field(default_factory=lambda: ["question", "chat"])


@dataclass
class PlanningConfig:
    """Plan-and-Execute 编排配置：规划器拆解任务 + 分步执行 + 验证/重试 + 并行子任务。"""

    enabled: bool = True
    max_steps: int = 8
    allow_parallel: bool = True
    max_parallel: int = 3
    verify: bool = True
    max_retries: int = 1
    verify_command: Optional[str] = None  # 可选：每步后执行的验证命令
    # 命中这些意图类别时跳过规划（直接 ReAct），省一次规划 LLM 往返
    skip_intents: List[str] = field(default_factory=lambda: ["question", "chat"])


@dataclass
class SubagentPolicyConfig:
    """delegate 子代理策略：并行子任务的工具/命令/预算约束。"""

    enabled: bool = True
    # 子代理可用工具子集（None=继承主代理；列表=仅这些工具名）
    tools: Optional[List[str]] = None
    # 子代理专用命令白名单（非空时覆盖主配置 allow_commands）
    allow_commands: List[str] = field(default_factory=list)
    # 额外禁止命令（与主配置 deny_commands 取并集）
    deny_commands: List[str] = field(default_factory=list)
    # 是否允许写文件 / 执行命令·代码
    allow_write: bool = True
    allow_execute: bool = True
    # 子代理是否重新弹审批（默认 False=免审批，沿用委托语义）
    require_approval: bool = False
    # 单次 delegate 总成本软上限（美元）；None=不限
    budget_usd: Optional[float] = None
    # 单个子任务最多 ReAct 轮次（0=沿用默认 20）
    max_rounds: int = 0


@dataclass
class ReflexionConfig:
    """Reflexion 外层：整轮尝试结束后自我批评 + 可配置 verifier + 预算内重试。"""

    enabled: bool = True
    max_attempts: int = 2  # 含首次尝试（1 = 不重试）
    # verifier：error_free | verify_command | llm | none（none=永不重试）
    verifier: str = "error_free"
    use_critique: bool = True  # 失败时生成自我批评再重试
    budget_aware: bool = True  # 重试前检查预算护栏
    critique_timeout: float = 30.0


@dataclass
class SandboxConfig:
    """沙箱配置：可插拔后端（container/seatbelt/pathguard）+ 路径护栏。"""

    enabled: bool = True
    # auto | container | seatbelt | pathguard | none（auto 自动降级）
    backend: str = "auto"
    allow_network: bool = False
    container: ContainerSandboxConfig = field(default_factory=ContainerSandboxConfig)
    extra_read_paths: List[str] = field(default_factory=list)
    extra_write_paths: List[str] = field(default_factory=list)
    deny_write_outside_workspace: bool = True
    # 无可用容器/seatbelt 时是否允许降级到 pathguard（False=禁用 execute 工具）
    allow_pathguard_fallback: bool = False
    # 写保护路径（glob 模式，相对工作目录；命中则拒绝写）
    protect_paths: List[str] = field(default_factory=lambda: list(DEFAULT_PROTECT_PATHS))


@dataclass
class BackupConfig:
    """备份配置：写前快照 + journal，供 /undo 手动回退。"""

    enabled: bool = True
    retain_on_success: bool = True


@dataclass
class RagConfig:
    """RAG 知识库配置：文档摄取、清洗、分块、向量化与检索注入。"""

    enabled: bool = False
    # 允许上传/索引的文件扩展名（小写，含点）
    allowed_extensions: List[str] = field(
        default_factory=lambda: [
            ".pdf",
            ".docx",
            ".md",
            ".markdown",
            ".txt",
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".rs",
            ".go",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".cs",
            ".rb",
            ".sh",
            ".yml",
            ".yaml",
            ".json",
            ".toml",
            ".html",
            ".css",
            ".sql",
        ]
    )
    # 存储位置：原始文件与 SQLite 索引
    docs_dir: str = "~/.config/myopencode/rag/docs"
    index_file: str = "~/.config/myopencode/rag/index.sqlite3"
    # 分块：目标大小 / overlap / 硬上限（token）
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 75
    chunk_max_tokens: int = 1000
    # 清洗：PDF/Word 专项（去页眉页脚/页码、断行合并、连字符）与 chunk 去重
    clean_pdf: bool = True
    dedup: bool = True
    # 向量化与检索
    embedding_model: str = "text-embedding-3-large"
    embedding_provider: Optional[str] = None
    contextualize: bool = False
    contextualize_model: Optional[str] = None
    top_k: int = 5
    intents_to_trigger: List[str] = field(default_factory=lambda: ["question", "chat"])
    # 多路召回 + 融合 + 重排
    bm25_enabled: bool = True
    rrf_k: float = 60.0
    per_path_recall: int = 20
    fusion_candidates: int = 20
    rerank_model: Optional[str] = None
    # 注入过滤
    max_per_doc: int = 2
    injection_max_tokens: int = 2000


@dataclass
class ObservabilityConfig:
    """可观测配置：结构化日志 + 审计 + 指标。"""

    log_level: str = "info"
    log_file: Optional[str] = "~/.config/myopencode/logs/myopencode.log"
    audit_enabled: bool = True
    audit_file: Optional[str] = "~/.config/myopencode/audit.jsonl"
    metrics_enabled: bool = True
    otlp_endpoint: Optional[str] = None  # 预留：OpenTelemetry 导出端点
    alert_webhook_url: Optional[str] = None  # 预算告警/超限时的 webhook 通知地址


@dataclass
class AppConfig:
    """应用顶层配置。"""

    provider: str = "openai"
    model: Optional[str] = None
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    working_dir: str = "."
    permissions: PermissionsConfig = field(default_factory=PermissionsConfig)
    system_prompt: Optional[str] = None
    mcp_servers: Dict[str, McpServerConfig] = field(default_factory=dict)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    intent: IntentConfig = field(default_factory=IntentConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    planning: PlanningConfig = field(default_factory=PlanningConfig)
    subagent: SubagentPolicyConfig = field(default_factory=SubagentPolicyConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    reflexion: ReflexionConfig = field(default_factory=ReflexionConfig)
    rag: RagConfig = field(default_factory=RagConfig)

    def resolve_provider(self) -> str:
        return self.provider

    def resolve_model(self) -> Optional[str]:
        if self.model:
            return self.model
        p = self.providers.get(self.provider)
        return p.model if p else None


DEFAULT_MODEL = "deepseek-v4-pro"

DEFAULT_SYSTEM_PROMPT = (
    "You are a coding assistant. You help the user by reading files, searching "
    "code, editing files, and running shell commands. Always explain what you are "
    "about to do before invoking a tool. Prefer small, reversible edits."
)


def default_config() -> AppConfig:
    return AppConfig(model=DEFAULT_MODEL, system_prompt=DEFAULT_SYSTEM_PROMPT)