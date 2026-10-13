# myopencode

桌面版 AI 编程 Agent（类 opencode）：在桌面 App 里与 LLM 对话，让 Agent 自主读写文件、执行命令、搜索代码，带交互式权限审批。

- **壳层**：Tauri 2.0（Rust）——只负责窗口 + sidecar 生命周期
- **后端**：Python sidecar（FastAPI + WebSocket）——Agent 循环、LLM Provider、工具、权限
- **前端**：React + Vite + TypeScript + Ant Design——直连本地 WebSocket
- **LLM**：OpenAI / Anthropic / Ollama 多 Provider 统一抽象（流式）

架构详见 [docs/architecture.md](docs/architecture.md)。

## 目录结构

```
my-opencode/
├── src-tauri/    Rust 壳层（sidecar 拉起 + 握手）
├── frontend/     React 前端（Chat / 文件树 / 终端 / 审批）
├── backend/      Python sidecar（server / core / llm / tools / skills / mcp / security / config）
├── scripts/      dev.sh 一键启动、build-sidecar.sh 打包、gen-icons.py 图标
├── examples/     myopencode.json 示例配置、skills / mcp_servers 示例
└── docs/         architecture.md
```

## 快速开始（开发模式）

```bash
# 1. 启动后端 + 前端（端口 8787，token dev-token）
./scripts/dev.sh

# 打开 http://localhost:5173
```

接入真实 LLM 前，需在配置里填好 provider 的 API Key（见下文「接入真实 LLM」）。

### 只起后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e .
MYOPENCODE_TOKEN=dev-token MYOPENCODE_PORT=8787 .venv/bin/python -m myopencode
# 向 stdout 打印握手行：{"port": 8787, "token": "dev-token"}
```

## 接入真实 LLM

把 `examples/myopencode.json` 复制为工作区根目录的 `myopencode.json`（或 `~/.config/myopencode/myopencode.json`），改 `provider` 为 `openai` / `anthropic` / `ollama`，并填好对应 `api_key`。

```bash
# 需额外安装 provider SDK
cd backend && .venv/bin/pip install -e ".[providers]"
```

### 模型路由（可选）

配置 `llm.lite_model`（复用主 provider 的连接、只换模型名），简单意图（默认 `question` / `chat`）会自动走小模型，复杂任务走主模型；`llm.simple_intents` 可自定义意图列表。

```json
{
  "llm": {
    "lite_model": "qwen3.8-flash",
    "simple_intents": ["question", "chat"]
  }
}
```

未配置 `lite_model` 时所有请求都走主模型（路由关闭）。

## Skills

Agent 支持渐进式加载 Skill：启动时把每个 Skill 的「名称 + 描述」注入 system prompt，LLM 需要时调用 `load_skill` 工具读取完整正文。

放置位置（两个目录都会扫描，同名以用户级优先）：

- 用户级：`~/.config/myopencode/skills/<name>/SKILL.md`
- 项目级：`<工作区>/.myopencode/skills/<name>/SKILL.md`

`SKILL.md` 格式（frontmatter + 正文）：

```markdown
---
name: code-review
description: 对代码变更做审查，从正确性、安全、可读性等维度输出分级建议
---

# 具体做法
...
```

示例见 `examples/skills/code-review/SKILL.md`。前端「工具与信息」弹窗的 Skills / 工具标签页可查看当前加载的内容。

Skill 触发：除模型自觉调用 `load_skill` 外，还支持 frontmatter `metadata.trigger` 关键词确定性触发（中文按 bigram 容错匹配，`写一部小说` 可命中 `写小说`）。

## MCP 集成

支持接入外部 MCP server（Model Context Protocol），其工具会自动注入 Agent，走统一审批（默认需确认）。支持两种 transport：

- **stdio**：`command` + `args` + `env` 拉起本地 server
- **streamable HTTP**：`url` 单 endpoint，响应支持 JSON 与 SSE（可配 `headers` 鉴权）

在 `myopencode.json` 里配置：

```json
{
  "mcp_servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
      "env": {}
    },
    "remote": {
      "url": "http://localhost:8080/mcp",
      "transport": "http",
      "headers": { "Authorization": "Bearer ..." }
    }
  }
}
```

- 工具命名为 `mcp_<server>_<tool>`，在侧边栏「工具」tab 可见
- MCP 工具默认触发审批弹窗（安全起见）
- 本地测试可用内置 mock server：`examples/mcp_servers/mock_server.py`

## 知识库（RAG）

上传文档到本地知识库，后台自动**抽取 → 清洗 → 分块 → 索引**（检索注入对话为下一阶段）。

- 支持类型：PDF、Word(.docx)、Markdown、纯文本、代码
- 入口：侧边栏「工具与信息 → 知识库」Tab 上传（多选）；或 `POST /rag/upload`
- 流水线：sha256 去重 → 抽取（pypdf / python-docx）→ 清洗（去页眉页脚/断行合并，`rag.clean_pdf` 开关）→ 结构感知分块（~500 token、15% overlap）→ chunk 去重 → SQLite 索引
- 存储：原始文件 `~/.config/myopencode/rag/docs/`，索引 `~/.config/myopencode/rag/index.sqlite3`
- 配置：`myopencode.json` 的 `rag` 块（`enabled` / `allowed_extensions` / `chunk_size_tokens` / `clean_pdf` / `dedup` 等）

> 当前阶段只做摄取与索引；向量化（`text-embedding-3-large`）与检索注入对话（提问时自动引用知识库）待接入。

## 权限与命令策略

- 写文件 / `run_shell` / `run_code` / MCP 工具默认走审批弹窗（读类与记忆工具免审批）。
- `run_shell` 额外先做命令级校验（`security/policy.py::check_command`），按 shell 段首 token 的 basename 精确匹配，优先级：`deny_commands`（硬拒）> `allow_all_commands`（放行）> `allow_commands` 白名单 > `default_deny_commands`。
- `permissions.default_deny_commands` 默认 `true`（企业态）：未列入白名单的命令一律硬拒；个人开发可设 `allow_all_commands: true` 或关闭该开关退回“放行 + 审批兜底”。
- 写保护：`sandbox.protect_paths`（glob）命中即拒绝写，默认保护 `.git/**`、`myopencode.json`、`.env*`、`*.key`、`*.pem`、`~/.aws/**`、`~/.ssh/**`。
- 沙箱 `sandbox.allow_pathguard_fallback=false`（默认）时，无 Docker/sandbox-exec 就禁用 `run_shell`/`run_code`（不静默降级直跑）。
- 子代理：`subagent` 配置约束 `delegate`（工具子集 `tools`、命令白名单 `allow_commands`、`allow_write`/`allow_execute`、`budget_usd` 软上限、`max_rounds` 轮次）。

## 打包成桌面应用

前置：Rust 工具链（`rustup default stable`）、Xcode Command Line Tools（`xcode-select --install`）。

```bash
# 1. 打包 Python 后端为 sidecar（生成 src-tauri/binaries/myopencode-sidecar-<triple>）
./scripts/build-sidecar.sh

# 2. 安装 Tauri CLI（本地 devDependency，无需全局权限）
cd frontend && npm install -D @tauri-apps/cli@^2 && cd ..

# 3. 打包（先构建前端 → release 编译 Rust → 生成 .app / .dmg）
./frontend/node_modules/.bin/tauri build
```

产物：

- `src-tauri/target/release/bundle/macos/myopencode.app`（macOS 应用包）
- `src-tauri/target/release/bundle/dmg/myopencode_0.1.0_x64.dmg`（安装镜像）

> sidecar 会打进 `myopencode.app/Contents/MacOS/`，与主二进制同目录，运行时会自动拉起。
> 本地构建的包未签名，仅限本机使用；分发需配置代码签名（Apple Developer 证书）。

### 开发模式（Tauri dev）

```bash
# 需先起后端（Tauri 会自行拉起前端 Vite）
MYOPENCODE_SIDECAR=".venv/bin/python -m myopencode" \
MYOPENCODE_PYTHONPATH="$PWD/backend/src" \
./frontend/node_modules/.bin/tauri dev
```

## 测试

```bash
# 后端：lint + 单元/集成测试
cd backend && .venv/bin/python -m ruff check src tests && .venv/bin/python -m pytest -q

# 前端：组件测试 + 类型检查 + 构建
cd frontend && npm test && npm run build

# 评测（需已配置 provider）：离线跑黄金集，产出 pass rate
cd backend && .venv/bin/python -m myopencode.evals.run_evals

# 安全红队评测（提示注入/越狱/凭证外泄/高危破坏）：只跑 security 标签集
cd backend && .venv/bin/python -m myopencode.evals.run_evals --tag security
```

CI 已配置于 `.github/workflows/ci.yml`（ruff+pytest / npm build+test / cargo check 三路并行）。

安全扫描独立于 `.github/workflows/security.yml`（每周定时 + push/PR 触发）：

- Python：`pip-audit`（依赖漏洞）
- Node：`npm audit --omit=dev`（生产依赖 high/critical 阻断）+ 全量 informational
- Rust：`cargo-deny`（advisories + license + bans，配置见 `src-tauri/deny.toml`）
- secret：`gitleaks`（配置见 `.gitleaks.toml`）
- SBOM：`anchore/sbom-action`（syft，SPDX JSON 产物）

## 崩溃日志

Rust 主进程 panic 与前端未捕获异常（`error` / `unhandledrejection`）都会写入 `~/.config/myopencode/logs/crash.log`（结构化、已脱敏），可在「工具与信息 → 诊断」导出或直接查看。

## 环境变量（开发）

| 变量 | 默认 | 说明 |
|---|---|---|
| `MYOPENCODE_HOST` | `127.0.0.1` | 后端监听地址 |
| `MYOPENCODE_PORT` | `0`(自动) | 后端端口 |
| `MYOPENCODE_TOKEN` | 随机 | 固定鉴权 token |
| `VITE_BACKEND_PORT` | `8787` | 前端直连端口 |
| `VITE_BACKEND_TOKEN` | `dev-token` | 前端直连 token |

## 待办（下一步可做）

- [ ] RAG / 知识库 + 语义缓存（摄取/索引已完成，向量化 + 检索注入待做）
- [ ] 自动更新（Tauri updater）
- [ ] `edit_file` diff 的可视化渲染增强
- [x] 依赖漏洞扫描 / SBOM、CI 接入 secret scan（gitleaks）
- [ ] 代码签名 + 公证（需 Apple Developer 证书）
