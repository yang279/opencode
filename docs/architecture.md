# myopencode — 架构设计

一个**桌面版 AI 编程 Agent**（类 opencode）。在桌面 App 里与 LLM 对话，让 Agent 自主读写文件、执行命令、搜索代码，带交互式权限审批、沙箱隔离、预算护栏与可观测。

## 1. 总体架构与进程模型

```
┌──────────────────── Tauri 桌面应用 ────────────────────┐
│                                                        │
│   ┌─────────────────────┐      ┌─────────────────────┐ │
│   │   Rust 壳层 (轻)      │      │  Python sidecar      │ │
│   │   · 窗口/对话框       │      │  · FastAPI + WebSocket│ │
│   │   · sidecar 生命周期  │──────▶  · Agent 循环         │ │
│   │   · stdout 握手       │ stdout │  · LLM Provider     │ │
│   │   · panic hook       │ 握手   │  · 工具/沙箱/记忆    │ │
│   └─────────┬───────────┘      └──────────▲──────────┘ │
│             │ Tauri IPC        (仅拿 port+token)│ 本地 WS │
│   ┌─────────▼───────────┐                 │            │
│   │  React 前端          │  ◀────(直连)─────┘            │
│   │  · Chat / 工具 / 审批 │                              │
│   │  · 终端 / 用量 / 诊断 │                              │
│   └─────────────────────┘                               │
└─────────────────────────────────────────────────────────┘
```

关键决策：

- **Rust 保持轻薄**：不做业务转发，只负责拉起/重启 sidecar、从 stdout 读握手（`port`+`token`）、通过 Tauri command 暴露连接信息、桌面原生能力（文件对话框）+ 崩溃 hook。
- **前端直连 Python 本地 WebSocket**：携带 `token` 鉴权，避免 Rust 中间转发。
- **命令与事件分离**：一次性请求走 HTTP REST（配置/会话/用量/诊断），持续性双向流走 WebSocket（对话/工具/审批/提问）。

### 1.1 启动时序

```
Tauri 启动
  └─ Rust 后台线程 spawn sidecar（发布: myopencode-sidecar / dev: python -m myopencode）
        └─ Python 起 FastAPI，随机端口 + 生成 token
             └─ lifespan startup 完成后向 stdout 打印握手: {"port": ..., "token": "..."}
        └─ Rust read_handshake 扫描 stdout（忽略杂散行，超时 30s）
             └─ wait_port_ready 再探测端口真正就绪
  └─ Tauri command "get_backend_info" → 前端拿到 {port, token}
  └─ React 建立 WebSocket(ws://127.0.0.1:{port}/ws?token=...)
```

握手失败自动重试 3 次（间隔 2s），仍失败发 `backend-error`。

## 2. 目录结构

```
my-opencode/
├── src-tauri/                # Rust 壳层 (Tauri 2.0)
│   └── src/
│       ├── main.rs           # 只调 lib::run()
│       ├── lib.rs            # 命令注册 + 启动 + 后台拉起 sidecar
│       ├── sidecar.rs        # sidecar 生命周期 + 握手 + 端口探测
│       └── crash.rs          # panic hook → 写崩溃日志
├── frontend/                 # React + Vite + TS + Ant Design
│   └── src/
│       ├── main.tsx          # 入口 + 全局错误上报
│       ├── App.tsx
│       ├── components/       # ChatPanel / MessageList / FileExplorer /
│       │                     # TerminalPanel / DiffView / ApprovalDialog /
│       │                     # UsagePanel / AuxPanelModal / AskUserCard ...
│       ├── hooks/            # useAgent（WS 事件订阅与状态）
│       ├── lib/              # wsClient.ts / api.ts
│       └── types/            # events.ts
├── backend/src/myopencode/   # Python sidecar
│   ├── __main__.py           # 入口：握手 + uvicorn
│   ├── config/               # schema.py（配置 dataclass）/ loader.py（JSON→配置）
│   ├── server/               # app.py（装配）/ ws.py（WS 连接 + 事件路由）
│   │   └── routes/           # health/config/workspace/sessions/memory/undo/
│   │                         # usage/diagnostics/crash/meta
│   ├── core/                 # agent / session / session_manager / events /
│   │                         # reflexion / planner / backup / audit / alerts /
│   │                         # observability / tracing / metrics / telemetry / errors
│   ├── llm/                  # base / openai / anthropic / ollama / registry /
│   │                         # retry / budget / usage / usage_store
│   ├── tools/                # base / files / shell / search / run_code /
│   │                         # ask_user / plan_tool / delegate_tool /
│   │                         # pathguard / sandbox / registry
│   ├── memory/               # manager / short_term / summarizer / store / schema / tools
│   ├── intent/               # pipeline / semantic / tool_select / schema / rag(预留)
│   ├── security/             # policy / safety / content_filter / secrets / crypto
│   ├── skills/               # registry / load_skill_tool
│   ├── mcp/                  # client(stdio) / remote(streamable HTTP) / registry / tool
│   └── evals/                # judge / run_evals
├── sandbox/                  # Dockerfile（容器沙箱镜像 myopencode-sandbox）
├── scripts/                  # dev.sh / build-sidecar.sh / gen-icons.py
├── examples/                 # myopencode.json / skills / mcp_servers
└── docs/                     # architecture.md / FEATURES.md
```

## 3. 后端模块设计（Python）

### 3.1 事件流（`core/events.py`）

所有跨端通信统一为「事件」dict（JSON 序列化），WS 双向传输：

- 前端 → 后端：`user_message` / `tool_approval` / `ask_user_reply` / `safety_reply` / `cancel` / `resume` / `config_update`
- 后端 → 前端：`assistant_text`(流式) / `tool_call_start` / `tool_call_end` / `approval_request` / `ask_user` / `safety` / `content_flag` / `intent` / `plan` / `plan_step` / `progress` / `reflection` / `degraded` / `budget_warning` / `budget_exceeded` / `state_snapshot` / `error` / `done`

### 3.2 Agent 循环（`core/agent.py`）

两层循环：**Reflexion（外）+ ReAct（内）**，入口 `run(user_input)`：

```
run(user_input)
  └─ 意图识别(_recognize_intent) → active_tools + 意图类别
  └─ skill 触发(_dispatch_skill) → 注入 skill 全文
  └─ _run_episode:
        ┌── Reflexion 外层（最多 max_attempts）────────────────┐
        │   1. _loop 跑一轮 ReAct（最多 20 轮）                 │
        │   2. ReflexionController.judge() 判定成功            │
        │   3. 失败且可重试 → critique() 反思 → 回填消息重试     │
        └──────────────────────────────────────────────────────┘

_loop 每轮：
  _check_budget → _build_messages（system + 记忆 + 摘要 + skill + 意图）
  → LLM 流式调用（信号量限流 + retry/fallback）
  → 收集 tool_calls / text
  → 有 tool_call 则逐个 _run_tool 执行并回填，无则纯文本结束
```

`_run_tool` 分派：`ask_user`（阻塞提问）/ `plan`（拆步骤）/ `delegate`（并行子代理）特殊拦截；普通工具走「子代理限制 → 命令校验 → 审批 → ToolContext 执行 → 脱敏截断 → 注入扫描」。

### 3.3 LLM Provider 抽象（`llm/`）

统一 `stream(messages, tools, ...) → AsyncIterator[LLMEvent]`，产出 `text` / `tool_call`。

- `OpenAIProvider`（openai SDK + OpenAI 兼容协议）/ `AnthropicProvider` / `OllamaProvider`
- `registry.py`：按 config 选 provider + model；`create_lite_provider`（模型路由小模型）、`create_fallback_providers`（降级链）
- `retry.py`：首 token 前失败才重试/降级，指数退避
- `budget.py` + `usage.py` + `usage_store.py`：成本护栏、token 归因、按日/月/模型/会话聚合（加密落盘）

### 3.4 工具系统（`tools/`）

统一 `Tool` 接口（`name/description/json_schema/execute`），`ToolContext` 注入 working_dir / PathGuard / Sandbox / Backup / cancel_token / 输出上限 / secret 脱敏。

| 工具 | 类别 | 说明 |
|---|---|---|
| `read_file` / `list_dir` / `glob` / `grep` | read | 读文件 / 列目录 / 通配 / 正则 |
| `write_file` / `edit_file` | write | 覆盖写 / 精确替换（返回 diff） |
| `run_shell` / `run_code` | execute | shell 命令 / 沙箱内 python/wasm |
| `ask_user` | interrupt | 提问（单/多选/自填，阻塞） |
| `plan` / `delegate` | plan | 拆步骤 / 并行子代理 |
| `load_skill` | skill | 渐进加载 skill 正文 |
| `save/recall/list/forget_memory` | memory | 长期记忆（开启时注入） |
| `mcp_<server>_<tool>` | mcp | 外部 MCP 工具 |

### 3.5 记忆系统（`memory/`）

- **短期** `short_term.py`：滚动压缩——超窗折叠旧消息 → 摘要（真正裁剪 `session.messages`）
- **长期·语义** `store.py` facts：跨会话稳定事实（用户偏好/项目约定）
- **长期·场景** `store.py` episodes：历史会话摘要
- **摘要** `summarizer.py`：独立摘要助手（可配 `memory.summary_model`），带超时兜底

### 3.6 权限与安全（`security/` + `tools/sandbox.py`）

- **权限策略** `policy.py`：读类/记忆免审批；write/execute/mcp 走审批（once/always/reject）；`run_shell` 先做命令级校验
- **命令 allow/deny**：按 shell 段首 token 的 basename 精确匹配，`deny > allow_all > allow_commands 白名单 > default_deny_commands`（默认拒绝）
- **沙箱** `sandbox.py`：`container`(Docker/podman) / `seatbelt`(macOS sandbox-exec) / `pathguard`(仅路径) 三级；`allow_pathguard_fallback=false`（默认）无真隔离则禁用 execute 工具
- **路径护栏** `pathguard.py`：realpath 归一化 + 越界拦截 + `protect_paths` 写保护
- **密钥** `secrets.py`：API key 存系统钥匙串；`crypto.py`：sessions/usage/audit/backup AES-256-GCM 落盘加密
- **安全护栏** `safety.py`：前置恶意意图拦截 + 工具结果注入扫描；`content_filter.py`：最终回答审核（默认关）
- **回退** `backup.py` + `/undo`：写前快照，逆序恢复最近改动组

### 3.7 意图识别（`intent/`）

`pipeline.py` 串联三类识别器：`semantic`(LLM 分类) → `tool_select`(工具剪枝 + 破坏性 gating) → `rag`(预留)。分类体系：`code_edit / code_read / explore / execute / question / plan / compose / chat`，每类映射允许的工具组。

### 3.8 模型路由与预算

- **模型路由**：`llm.lite_model` 配置后，简单意图（默认 question/chat）走小模型，其余走主模型（复用主 provider 连接）
- **预算护栏**：日/月预算，80% 告警、超限硬停（`budget_hard_stop`）；`subagent.budget_usd` 精确限制 delegate 子代理成本
- **并发限流**：`llm.max_concurrent_calls` 全局信号量

### 3.9 MCP（`mcp/`）

- **stdio**（`client.py`）：`command + args + env` 拉起本地 server，新行分隔 JSON-RPC
- **streamable HTTP**（`remote.py`）：`url` 单 endpoint，POST JSON-RPC，响应支持 `application/json` 与 `text/event-stream`（SSE），`Mcp-Session-Id` 会话保持
- 工具命名为 `mcp_<server>_<tool>`，默认触发审批

### 3.10 可观测（`core/`）

| 组件 | 说明 |
|---|---|
| `metrics` | 计数器/直方图（工具调用、错误、预算、run 耗时） |
| `tracing` | contextvars 链路 + span 环形缓冲 |
| `telemetry` | 轻量 OTLP 导出（`otlp_endpoint` 开启） |
| `audit` | append-only JSONL（谁/何时/做什么/审批决定，加密） |
| `alerts` | 预算告警 webhook（`alert_webhook_url`） |
| `observability` | 结构化 JSON 日志（stderr + 文件）+ secret 脱敏 |

### 3.11 配置（`config/schema.py`）

顶层 `AppConfig` 聚合：`provider/model/providers`、`working_dir`、`permissions`、`mcp_servers`、`memory`、`intent`、`sandbox`、`subagent`、`backup`、`observability`、`planning`、`llm`、`safety`、`reflexion`。`loader.py` 从 `myopencode.json`（工作区根或用户目录）解析并合并默认值。

## 4. Rust 壳层（`src-tauri/`）

- `sidecar.rs`：`start_and_wait()` / `shutdown()` / `read_handshake()`（超时 30s、忽略杂散行）/ `wait_port_ready()` / `default_working_dir()`（`~/myopencode`）
- `lib.rs`：注册 `get_backend_info` / `restart_backend` / `choose_directory`；后台拉起 sidecar + 重试 3 次
- `crash.rs`：panic hook 写 `~/.config/myopencode/logs/crash.log`
- 生命周期：窗口关闭优雅退出 sidecar（整组 SIGKILL）

## 5. 前端（React + Ant Design）

- `wsClient.ts`：WS 连接管理（重连、token 鉴权）
- 面板/组件：ChatPanel（对话流）、MessageList（消息卡片：思考/工具/审批/提问/安全）、FileExplorer、TerminalPanel（F12 切换）、DiffView、ApprovalDialog、UsagePanel（预算/费用）、AuxPanelModal（Skills/工具/用量/诊断 Tab）
- `main.tsx`：全局 `error`/`unhandledrejection` 捕获 → POST `/crash`

## 6. 通信协议约定

| 场景 | 协议 | 端点 |
|---|---|---|
| 健康检查 | GET | `/health` |
| 指标 | GET | `/metrics` |
| 读/改配置 | GET/PUT | `/config` |
| 工作区树 / 读文件 | GET | `/workspace/tree` `/workspace/file?path=` |
| 会话列表/创建/删除/消息 | GET/POST/DELETE/GET | `/sessions` `/sessions/{id}` `/sessions/{id}/messages` |
| 撤销 | POST | `/sessions/{id}/undo` |
| 记忆 | GET | `/memory` |
| Skills / 工具清单 | GET | `/skills` `/tools` |
| 用量汇总/明细/按会话/导出 | GET | `/usage/summary` `/usage` `/usage/sessions` `/usage/export` |
| 诊断 / 追踪 / 导出 | GET | `/diagnostics` `/traces` `/diagnostics/export` |
| 崩溃上报 | POST | `/crash` |
| 对话/工具/审批/提问 | WS | `/ws?token=...` |

## 7. 安全边界

- WS 与 HTTP 绑定 `127.0.0.1`，仅本机可访问；token 每次启动随机生成，经 Rust stdout 握手 → 前端，不落盘。
- 工具受工作目录 scope + 命令 allow/deny + `protect_paths` 写保护约束。
- 写文件/执行命令/代码/MCP 走 `approval_request` 审批；`run_shell` 额外做命令级校验。
- 密钥进系统钥匙串；sessions/用量/审计/备份 AES-256-GCM 加密落盘；日志/结果统一脱敏。
- Tauri release 关闭 devtools + 配置 CSP。

## 8. 构建与发布

- **开发**：`scripts/dev.sh` 同时起 Python backend + Vite dev + Tauri dev。
- **发布**：`scripts/build-sidecar.sh`（PyInstaller 单文件 sidecar）+ `tauri build` 出 `.app`/`.dmg`；容器沙箱镜像 `docker build -t myopencode-sandbox:latest ./sandbox`。
