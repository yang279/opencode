# myopencode — 架构设计

一个**桌面版 AI 编程 Agent**（类 opencode）。在桌面 App 里与 LLM 对话，让 Agent 自主读写文件、执行命令、搜索代码，带交互式权限审批。

## 1. 总体架构与进程模型

```
┌──────────────────── Tauri 桌面应用 ────────────────────┐
│                                                        │
│   ┌─────────────────────┐      ┌─────────────────────┐ │
│   │   Rust 壳层 (轻)      │      │  Python sidecar      │ │
│   │   · 窗口/托盘/对话框  │      │  · FastAPI + WebSocket│ │
│   │   · sidecar 生命周期  │──────▶  · Agent 循环         │ │
│   │   · stdout 握手       │ stdout │  · LLM Provider     │ │
│   │     (拿 port+token)  │ 握手   │  · 工具系统          │ │
│   └─────────┬───────────┘      │  · 权限审批          │ │
│             │ Tauri IPC        └──────────▲──────────┘ │
│   ┌─────────▼───────────┐                 │ 本地 WS     │
│   │  React 前端          │  ◀────(直连)─────┘            │
│   │  · Chat / 文件 / 终端 │                              │
│   │  · 审批弹窗 / diff    │                              │
│   └─────────────────────┘                               │
└─────────────────────────────────────────────────────────┘
```

关键决策：

- **Rust 保持轻薄**：不做业务转发，只负责拉起/重启 sidecar、从 stdout 读取握手信息（`port` + `token`）、通过 Tauri command 把连接信息暴露给前端、以及桌面原生能力（文件对话框、托盘、通知）。
- **前端直连 Python 本地 WebSocket**：携带 `token` 鉴权，避免 Rust 中间转发（少一层延迟与复杂度）。
- **命令与事件分离**：
  - 一次性请求走 HTTP REST（如读取配置、列出工作区文件、健康检查）。
  - 持续性双向流走 WebSocket（对话、工具执行、审批）。

### 1.1 启动时序

```
Tauri 启动
  └─ Rust spawn "myopencode-sidecar"（sidecar 二进制 / dev: python -m myopencode）
        └─ Python 启动 FastAPI，随机端口 + 生成 token
             └─ 向 stdout 打印握手行: {"port": 8787, "token": "..."}
        └─ Rust 读到握手 → 存端口/token
  └─ Tauri command "get_backend_info" → 前端拿到 {port, token}
  └─ React 建立 WebSocket(ws://127.0.0.1:{port}/ws?token=...)
```

## 2. 目录结构

```
my-opencode/
├── src-tauri/                # Rust 壳层 (Tauri 2.0)
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── build.rs
│   ├── capabilities/
│   │   └── default.json
│   └── src/
│       ├── main.rs           # 只调 lib::run()
│       ├── lib.rs            # 命令注册 + run()
│       └── sidecar.rs        # 生命周期 + 握手
├── frontend/                 # React + Vite + TS + Ant Design
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── components/
│       │   ├── ChatPanel.tsx
│       │   ├── MessageList.tsx
│       │   ├── FileExplorer.tsx
│       │   ├── TerminalPanel.tsx
│       │   ├── DiffView.tsx
│       │   └── ApprovalDialog.tsx
│       ├── lib/
│       │   ├── wsClient.ts
│       │   └── api.ts
│       └── types/
│           └── events.ts
├── backend/                  # Python sidecar
│   ├── pyproject.toml
│   ├── src/myopencode/
│   │   ├── __main__.py       # 入口（dev）
│   │   ├── server/
│   │   │   ├── __init__.py
│   │   │   ├── app.py        # FastAPI 装配
│   │   │   ├── ws.py         # WS 连接 + 事件路由
│   │   │   └── routes/
│   │   │       ├── __init__.py
│   │   │       ├── health.py
│   │   │       └── workspace.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── events.py     # 事件类型定义
│   │   │   ├── session.py    # 会话状态
│   │   │   └── agent.py      # Agent 循环
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── base.py       # Provider 接口
│   │   │   ├── openai_provider.py
│   │   │   ├── anthropic_provider.py
│   │   │   ├── ollama_provider.py
│   │   │   └── registry.py
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── base.py       # Tool 接口
│   │   │   ├── files.py
│   │   │   ├── shell.py
│   │   │   ├── search.py
│   │   │   └── registry.py
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── schema.py
│   │   │   └── loader.py
│   │   └── security/
│   │       ├── __init__.py
│   │       └── policy.py     # 权限策略
│   └── tests/
├── scripts/
│   ├── dev.sh                # 一键启动三端
│   └── build-sidecar.sh      # PyInstaller 打包 sidecar
├── docs/
│   └── architecture.md
└── README.md
```

## 3. 后端模块设计（Python）

### 3.1 事件流（`core/events.py`）

所有跨端通信统一为「事件」结构，JSON 序列化，通过 WS 双向传输：

```jsonc
// 前端 → 后端
{ "type": "user_message",  "content": "..." }
{ "type": "tool_approval", "id": "...", "decision": "once" | "always" | "reject" }
{ "type": "cancel" }
{ "type": "config_update", "config": {...} }

// 后端 → 前端
{ "type": "assistant_text",  "delta": "..." }          // 流式增量
{ "type": "tool_call_start", "id": "...", "name": "read_file", "args": {...} }
{ "type": "tool_call_end",   "id": "...", "result": "...", "diff": "...?" }
{ "type": "approval_request","id": "...", "tool": "...", "args": {...} }  // 需审批
{ "type": "state_snapshot",  "state": {...} }          // 会话/工作区状态
{ "type": "error",           "message": "..." }
```

### 3.2 Agent 循环（`core/agent.py`）

与 opencode 一致的主循环：

```
while 会话未结束:
    events = llm.stream(messages, tools)          # 流式返回
    for e in events:
        if e 是文本:  emit("assistant_text")
        if e 是 tool_call:
            emit("tool_call_start")
            if 需要审批: emit("approval_request") 并 await 用户决策
            if 拒绝: 把拒绝结果回填，continue
            result, diff = tool.execute()          # 执行
            emit("tool_call_end")
            把 tool 调用+结果追加到 messages
    if 本轮无 tool_call: break（纯文本回复，结束）
```

### 3.3 LLM Provider 抽象（`llm/`）

统一接口 `LLMProvider`：

```python
class LLMProvider(Protocol):
    def stream(self, messages: list[Message], tools: list[ToolSchema]) -> AsyncIterator[LLMEvent]:
        ...
```

- `OpenAIProvider`（`openai` SDK，含 OpenAI 兼容协议）
- `AnthropicProvider`（`anthropic` SDK，native tool use）
- `OllamaProvider`（openai 兼容 HTTP，本地模型）

`registry.py` 按 config 选择 provider + model。

### 3.4 工具系统（`tools/`）

统一 `Tool` 接口：

```python
class Tool(Protocol):
    name: str
    description: str
    json_schema: dict        # JSON Schema，传给 LLM
    async def execute(self, args: dict) -> ToolResult:
        ...
```

MVP 工具：
- `read_file` / `write_file` / `edit_file`（精确字符串替换，返回 diff）
- `list_dir` / `glob` / `grep`
- `run_shell`（执行命令，走权限审批）

### 3.5 权限系统（`security/policy.py`）

- **范围**：工具级 allow/deny、命令级 allowlist、工作目录 scope（工具只作用于工作区）。
- **策略**：`once`（本次允许）/ `always`（记住了允许）/ `reject`（拒绝）。
- **流程**：工具执行前查 `policy` → 命中非 `once`/未决 → 向前端发 `approval_request` → await 用户决策。
- **沙箱预留**：`sandbox` 接口留空，后续可接容器/隔离执行。

### 3.6 配置（`config/`）

`myopencode.json`（工作区根或用户目录）：

```jsonc
{
  "model": "openai/gpt-4o",
  "provider": "openai",
  "providers": {
    "openai":   { "api_key": "..." },
    "anthropic": { "api_key": "..." },
    "ollama":   { "base_url": "http://localhost:11434" }
  },
  "working_dir": "/Users/you/project",
  "permissions": {
    "allow_commands": ["ls", "git status"],
    "deny_commands": ["rm -rf"]
  }
}
```

## 4. Rust 壳层（`src-tauri/`）

- `sidecar.rs`：`spawn()`、`restart()`、`shutdown()`、`wait_handshake()`（读 stdout 拿 `{port,token}`）、`health_check()`。
- `lib.rs`：注册 Tauri command：
  - `get_backend_info() -> {port, token}`
  - `restart_backend()`
  - `choose_directory() -> path`（原生文件对话框）
- 生命周期：窗口关闭时优雅退出 sidecar。

## 5. 前端（React + Ant Design）

- `wsClient.ts`：WS 连接管理（重连、鉴权 token）、`on(event, handler)` / `emit(event, payload)`。
- 面板：
  - `ChatPanel`：对话流，markdown 渲染，流式增量。
  - `FileExplorer`：工作区文件树（REST `/workspace/tree`）。
  - `TerminalPanel`：`run_shell`/`git` 输出与粘贴命令。
  - `DiffView`：`edit_file` 的 diff 展示。
  - `ApprovalDialog`：审批弹窗（once/always/reject）。
- 由 `App.tsx` 做 `split-pane` 布局。

## 6. 通信协议约定

| 场景 | 协议 | 端点 |
|---|---|---|
| 健康检查 | HTTP GET | `/health` |
| 读配置 | HTTP GET | `/config` |
| 更新配置 | HTTP PUT | `/config` |
| 工作区文件树 | HTTP GET | `/workspace/tree` |
| 读文件内容 | HTTP GET | `/workspace/file?path=...` |
| 对话/工具/审批 | WebSocket | `/ws?token=...` |

## 7. 安全边界

- WS 与 HTTP 全部绑定 `127.0.0.1`，仅本机可访问。
- `token` 由 Python 每次启动随机生成，经 Rust stdout 握手 → 前端，不落盘。
- 工具默认受工作目录 scope 约束 + 命令 allow/deny 策略。
- 所有需要副作用（写文件/执行命令）的操作走 `approval_request` 审批。

## 8. 构建与发布

- **开发**：`scripts/dev.sh` 同时起 Python backend + Vite dev + Tauri dev。
- **发布**：`scripts/build-sidecar.sh` 用 PyInstaller 把 Python 打成单文件 sidecar；Tauri `externalBin` 引用它，再 `tauri build` 出安装包。