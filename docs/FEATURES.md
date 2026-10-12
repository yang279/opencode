# myopencode Agent — 功能与机制说明

本文档描述 myopencode 的**功能全景与关键机制**：架构、工具调用、记忆、上下文处理、安全、成本治理、会话管理等。进程模型与启动时序见 [architecture.md](architecture.md)，二者互补。

---

## 1. 总览

myopencode 是一个**桌面版 AI 编程 Agent**（类 opencode）：在桌面 App 里与 LLM 对话，让 Agent 自主读写文件、执行命令、搜索代码，带交互式审批与安全护栏。

三进程分工（详见 `architecture.md`）：

| 层 | 技术 | 职责 |
|---|---|---|
| Rust 壳层 | Tauri 2.0 | 窗口、sidecar 生命周期、握手、崩溃 hook |
| Python sidecar | FastAPI + WebSocket | Agent 循环、LLM Provider、工具、权限、记忆、安全 |
| 前端 | React + Vite + TS + Ant Design | 聊天界面、工具/审批/提问卡片、用量/诊断面板，直连本地 WebSocket |

一次任务的能力闭环：**意图识别 → 模型路由 → ReAct 主循环（LLM ⇄ 工具）→ Reflexion 验证/重试 → 落库 + 记忆固化**。

---

## 2. 核心架构

### 2.1 两层循环：Reflexion（外）+ ReAct（内）

```
run(user_input)
  └─ 意图识别(_recognize_intent) → 设定 active_tools + 意图类别
  └─ skill 触发(_dispatch_skill) → 注入 skill 全文
  └─ _run_episode：
        ┌── Reflexion 外层（最多 max_attempts=2 次，含首试）──────────┐
        │   1. _loop 跑一次完整 ReAct（最多 20 轮）                    │
        │   2. ReflexionController.judge() 判定是否成功                │
        │        verifier: error_free | verify_command | llm | none    │
        │   3. 失败且 allow_retry → critique() 生成反思 → 回填消息重试 │
        └─────────────────────────────────────────────────────────────┘
```

**ReAct 内循环**（`agent._loop`）：每轮 `_build_messages` 组装上下文 → 流式调用 LLM → 收集 `tool_call` / 文本 → 若有工具调用则逐个 `_run_tool` 执行并回填结果，否则纯文本即结束。

**Reflexion 验证器**（`core/reflexion.py`）：
- `error_free`（默认）：无工具执行错误即成功
- `verify_command`：代码类意图（code_edit/code_read/execute）额外跑一次验证命令
- `llm`：让 LLM 判定是否完成（输出 yes/no）
- `none`：永不重试
- 预算联动：`budget_aware=true` 时，预算超限则不再重试

### 2.2 循环内编排工具

`plan` / `delegate` 不是系统级两阶段，而是模型在循环内主动调用的普通工具：

- **`plan`**：把任务拆成带依赖的步骤，仅返回步骤清单文本供模型后续执行
- **`delegate`**：并行派多个子代理执行互不依赖的子任务（`asyncio.gather`，子代理内不弹审批、不向用户提问），返回汇总结果。子代理受 `config.subagent` 策略约束：工具子集 `tools`、专用命令白名单 `allow_commands`、`allow_write`/`allow_execute`、`budget_usd`（单次 delegate 总成本软上限，超限告警）、`max_rounds`（单子任务 ReAct 轮次上限）；`subagent.enabled=false` 可整体关闭 delegate。

### 2.3 意图识别

三类识别器串联（`intent/pipeline.py`）：`SemanticRecognizer`（LLM 分类）→ `ToolRecognizer`（工具剪枝 + 破坏性 gating）→ `RagRecognizer`（预留）。

分类体系（`intent/schema.py`）：`code_edit / code_read / explore / execute / question / plan / compose / chat`。每类映射到允许的工具组——例如 `code_read` 只保留 read 组，`code_edit` 保留 read+write+execute+mcp，`question/chat` 不调用工具。意图识别用小模型（默认 `qwen3.8-flash`，快 + 省成本）。

### 2.4 模型路由

配置 `llm.lite_model` 后，**简单意图**（默认 `question` / `chat`）自动走小模型，其余走主模型（`agent.route_provider`）。未配置则全部走主模型。小模型复用主 provider 连接、只换模型名。

---

## 3. 工具系统：怎么调用

### 3.1 工具清单

| 工具 | 类别 | 说明 |
|---|---|---|
| `read_file` | read | 读取文件（256KB 截断） |
| `write_file` | write | 创建/覆盖写文件，返回 diff |
| `edit_file` | write | 精确字符串替换（old_string 必须唯一） |
| `list_dir` | read | 列目录（含过滤/上限/递归） |
| `glob` | read | 通配符匹配文件（跳过 `.git/node_modules/__pycache__`） |
| `grep` | read | 正则搜索文件内容 |
| `run_shell` | execute | 执行 shell 命令（超时 + 输出上限 + 取消必杀） |
| `run_code` | execute | 沙箱内执行 python / wasm 代码 |
| `ask_user` | interrupt | 向用户提问（单选/多选/自填） |
| `plan` | plan | 任务拆解为步骤 |
| `delegate` | plan | 并行子代理 |
| `load_skill` | skill | 渐进式加载 skill 正文/references |
| `save/recall/list/forget_memory` | memory | 长期记忆工具（开启记忆时） |
| `mcp_<server>_<tool>` | mcp | 外部 MCP server 注入的工具 |

### 3.2 调用链路

```
LLM 返回 tool_call
  └─ agent._run_tool(tool_id, name, raw_args)
       ├─ 特殊拦截：
       │    ask_user  → 阻塞等待用户回答（并行子代理内禁止提问）
       │    plan      → 调用规划器产出步骤文本
       │    delegate  → 并行派子代理
       └─ 普通工具：
            1. run_shell 先做命令级强制拦截(check_command)
            2. 需要审批 → 弹审批等待决策(reject 则取消任务)
            3. 组装 ToolContext(working_dir / path_guard / sandbox /
               backup / cancel_token / max_output_bytes / scrub_secrets)
            4. 执行 tool.execute
            5. 结果 _sanitize_result：256KB 截断 + secret 脱敏
            6. 读类工具结果可触发注入扫描(SafetyGate)
            7. emit tool_call_end → 结果回填为 tool 消息
```

### 3.3 ToolContext

每次工具执行都带一个上下文对象（`tools/base.py`），统一注入：工作目录、`PathGuard`（越界拦截）、`Sandbox`（隔离后端）、`BackupManager`（写前快照）、`ProcessTracker`（取消必杀）、输出上限（默认 256KB）、secret 脱敏开关。

---

## 4. 记忆系统：怎么做

三层记忆（`memory/`）：

| 层 | 组件 | 作用 |
|---|---|---|
| 短期 | `ShortTermMemory` | 滚动压缩：超窗折叠旧消息 -> 摘要 |
| 长期·语义 | `MemoryStore` facts | 跨会话稳定事实（用户偏好、项目约定） |
| 长期·场景 | `MemoryStore` episodes | 历史会话摘要（本次会话排除） |

### 4.1 短期滚动压缩（`short_term.py`）

```
compact(messages, prior_summary, model):
    window = resolve_context_window(model) or config.context_window_tokens  # 默认 24000
    keep   = min(config.keep_recent_tokens=8000, window)
    if total_tokens(messages) <= window: 返回原文
    否则：从尾部向前保留最近 keep tokens，其余折叠
          -> summarize_conversation(折叠部分, prior_summary) 生成新摘要
```

- **真正的裁剪**：折叠后 `session.messages` 被替换为保留段，避免每轮重复摘要，也防止持久化膨胀
- **摘要防丢**：LLM 摘要超时/返回空时回退 `prior_summary`

### 4.2 长期记忆（`manager.py`）

- `build_context` 时按最近一条用户消息检索：语义 facts（`search_facts`）+ 场景 episodes（`search_episodes`，排除自己），注入 system 段
- 会话结束 `finalize_session`：整段会话总结成 episode；可选从摘要自动抽取事实存入语义记忆

### 4.3 Summarizer（`summarizer.py`）

独立的 LLM 摘要助手（可配 `memory.summary_model` 单独模型，未配置回退主 provider），提供 `summarize_conversation`（滚动合并摘要）、`summarize_session`（会话总结）、`extract_facts`（事实抽取），均带超时兜底。

---

## 5. 上下文处理

### 5.1 构建链路

每轮 LLM 调用前，`agent._build_messages` 组装最终 system prompt 与消息列表：

```
system prompt = 基础 system_prompt
              + skills 简介段（可用 skill 名称+描述）
              + 长期记忆段（语义 facts + 场景 episodes，可选）
              + 会话摘要段（## 会话摘要）
              + 意图段（## 意图：当前用户意图…）
              + skill 正文（命中触发的 skill 全文）
              + ask_user 使用约定（引导模型用 options/multi 提问）
messages     = 裁剪/摘要后的历史消息（含工具结果）
```

### 5.2 Token 估算与窗口对齐

- `estimate_tokens`：CJK 按 1 字 1 token，其余按 4 字符 1 token（修正了原先 `len//4` 对中文低估 4~8 倍的问题）
- `resolve_context_window(model)`：按模型名子串映射已知窗口（deepseek 128k / claude 200k / gpt-4o 128k / llama3 8k / qwen 32k），保留 20% 余量；未命中回退 `config.context_window_tokens`

### 5.3 结果截断与脱敏

- 工具输出进入 LLM/历史/前端前统一 `_sanitize_result`：超过 `permissions.max_output_bytes`（默认 256KB）截断 + `scrub_secrets` 时递归脱敏（密钥/Bearer/敏感键名 -> `***`）

---

## 6. 交互与安全

### 6.1 提问 `ask_user`

需要用户补充信息时，模型调用 `ask_user`，主循环立即停下（不先跑其它工具）。支持：
- **单选**（默认）：`options=[{label, description?, recommended?}]`，点选即提交 label
- **多选**：`multi=true`，勾选后提交，答案序列化为 JSON 数组字符串
- **自填**：无选项或输入自定义文本

### 6.2 审批

`PermissionPolicy.needs_approval`：读类工具（read/list_dir/glob/grep/load_skill）与记忆工具免审批；`write_file / edit_file / run_shell / run_code / mcp_*` 需审批（可「总是允许」本会话记住）。`run_shell` 额外先走命令级校验。

**命令 allow/deny**（`check_command`）：按 shell 段首 token 的 basename 精确匹配，优先级 `deny_commands`（硬拒）> `allow_all_commands`（放行）> `allow_commands` 白名单 > `default_deny_commands`（默认拒绝，企业态；设为 `false` 则回退 deny-only 默认放行）。堵住 `echo rm` 这类前缀绕过。

### 6.3 安全护栏

- **前置拦截**：规则命中恶意意图后用识别小模型二次精排，仍判风险则弹确认（可阻止）
- **工具结果注入扫描**：`read_file / grep / mcp_*` 返回内容做高精度注入检测
- **内容审核**：最终回答审核（默认关，避免延迟）
- **密钥**：API key 存系统钥匙串（`secrets.py`），配置里永远为 null；失败回退 `chmod 600` 文件
- **数据 at-rest 加密**：`sessions.json` / 用量 / 审计 / 备份写盘统一走 AES-256-GCM（`security/crypto.py`，主密钥在钥匙串），旧明文兼容读取
- **路径护栏**：`PathGuard` 归一化 realpath，写操作严格限工作目录，读操作限工作目录 + 额外读取路径
- **写保护路径**：`sandbox.protect_paths`（glob 模式）命中即拒绝写，默认保护 `.git/**`、`myopencode.json`、`**/.env*`、`**/*.key`、`**/*.pem`、`~/.aws/**`、`~/.ssh/**`
- **沙箱**：可插拔后端 `container`（Docker/podman）/`seatbelt`（macOS）/`pathguard`（仅路径护栏），自动降级；`sandbox.allow_pathguard_fallback=false`（默认）时无真隔离则**禁用 execute 工具**（返回明确错误），避免静默直跑
- **`/undo`**：每次 run 视为一个改动组，写前自动快照，`/undo` 逆序恢复最近一组

---

## 7. 成本治理与可观测

### 7.1 成本治理

- **预算护栏**（`llm/budget.py`）：日/月预算，花费达 80% 发 warning，超限且 `budget_hard_stop=true` 硬停当前任务（抛 `BudgetExceededError`）
- **用量落库**（`llm/usage_store.py`）：JSONL 明细（含 `session_id`）+ 按日/月/模型聚合，均加密落盘
- **按会话成本归因**：`GET /usage/sessions` 按 session 聚合 cost/tokens/count；`GET /usage?session_id=` 按会话过滤明细
- **账单导出**：`GET /usage/export` 导出 CSV（含 session_id 列）
- **全局并发限流**：`llm.max_concurrent_calls`（>0 时用 asyncio 信号量限制跨会话 LLM 并发）
- **delegate 精确预算**：`subagent.budget_usd` 用 contextvar 精确统计组内成本（不跨会话串扰）
- **告警 webhook**：配置 `observability.alert_webhook_url` 后，预算告警/超限时 POST 通知

### 7.2 可观测

| 组件 | 说明 |
|---|---|
| `metrics` | 计数器/直方图（工具调用、错误、预算、run 耗时） |
| `tracing` | span 环形缓冲（`/traces` 查询，注入 trace/span/session 上下文） |
| `telemetry` | 轻量 OTLP 导出（配置 `otlp_endpoint` 开启） |
| `audit` | append-only JSONL 审计（谁/何时/做什么/审批决定，加密落盘，`/diagnostics/export` 导出） |
| 诊断 | `GET /diagnostics`（provider/沙箱/开关/内存磁盘/最近 span） |
| 崩溃日志 | Rust panic + 前端未捕获异常 -> `~/.config/myopencode/logs/crash.log` |

---

## 8. 会话与恢复

- **多会话并发**：不同会话并行执行；同一会话运行中拒绝新消息（提示「任务执行中」）
- **恢复 `resume`**：中断（未正常完成）的会话可继续上次任务（`execution_state.active`）；恢复前自动回退中断残留的不完整工具轮（`_repair_interrupted`），避免把「无工具结果的 tool_call」发给 LLM
- **持久化**：`sessions.json` 加密落盘，原子写（临时文件 + `os.replace`）；消息随滚动压缩裁剪，重启靠摘要恢复

---

## 9. LLM 接入

- **Provider 抽象**（`llm/base.py`）：统一 `stream(messages, tools, ...)` 流式接口，产出 `text` / `tool_call` 事件
- **多 Provider**：OpenAI / Anthropic / Ollama 统一注册
- **韧性**（`llm/retry.py`）：首 token 前失败才重试/降级（限流/5xx/超时判定），流中途失败直接上抛；指数退避
- **降级链**：`llm.fallback_providers` 顺序切换备用 provider
- **独立小模型**：意图识别、摘要、记忆抽取可各自配置独立模型

---

## 10. 前端交互

- **双向通道**：一次性请求走 REST（配置/会话/用量/诊断），持续流走 WebSocket（对话/工具/审批/提问事件）
- **界面布局**：左侧会话列表 + 「工具与信息」「配置」按钮；右侧聊天区 + 底部终端
- **消息卡片**：思考时间线（可展开）、工具行（折叠显示参数/结果/diff）、审批卡、提问卡（单/多选）、安全卡
- **辅助面板**：「工具与信息」弹窗含 Skills / 工具 / 用量预算 / 诊断四个 Tab
- **终端**：默认隐藏，`F12` 切换显示，含工具输出的彩色分级
- **用量面板**：预算状态胶囊 + 日/月费用卡片 + 进度条（主题橙，接近/超限变色）+ 按模型明细
- **崩溃上报**：`window.error` / `unhandledrejection` 捕获后 POST `/crash`

---

_相关文件索引：`core/agent.py`（主循环）、`core/reflexion.py`（验证重试）、`tools/`（工具）、`memory/`（记忆）、`intent/`（意图）、`llm/`（provider/预算/用量）、`security/`（策略/安全/密钥/加密）、`config/schema.py`（全部配置）、`server/`（路由/WS）。_