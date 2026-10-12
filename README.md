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

支持接入外部 MCP server（Model Context Protocol），其工具会自动注入 Agent，走统一审批（默认需确认）。当前支持 **stdio transport**（`command` + `args` + `env`）。

在 `myopencode.json` 里配置：

```json
{
  "mcp_servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
      "env": {}
    }
  }
}
```

- 工具命名为 `mcp_<server>_<tool>`，在侧边栏「工具」tab 可见
- MCP 工具默认触发审批弹窗（安全起见）
- 本地测试可用内置 mock server：`examples/mcp_servers/mock_server.py`

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
```

CI 已配置于 `.github/workflows/ci.yml`（ruff+pytest / npm build+test / cargo check 三路并行）。

## 环境变量（开发）

| 变量 | 默认 | 说明 |
|---|---|---|
| `MYOPENCODE_HOST` | `127.0.0.1` | 后端监听地址 |
| `MYOPENCODE_PORT` | `0`(自动) | 后端端口 |
| `MYOPENCODE_TOKEN` | 随机 | 固定鉴权 token |
| `VITE_BACKEND_PORT` | `8787` | 前端直连端口 |
| `VITE_BACKEND_TOKEN` | `dev-token` | 前端直连 token |

## 当前进度

### 核心
- [x] Agent 主循环：ReAct + Reflexion（verifier/critique 重试）+ 循环内 `plan` / `delegate` 并行
- [x] 工具集：read/write/edit_file、list_dir/glob/grep、run_shell/run_code、ask_user（单选/多选/自填）、load_skill，可扩展 MCP
- [x] 交互：审批（命令 allow/deny + 写操作）、安全确认、`/undo`、`resume`、取消
- [x] 意图识别 + skill 确定性触发（bigram 容错匹配）

### 企业级能力
- [x] 成本治理：日/月预算硬停、用量明细/聚合、账单 CSV 导出、告警 webhook
- [x] 可观测：metrics / tracing / OTLP telemetry / 审计日志 / 诊断导出
- [x] 记忆：短期滚动压缩（模型窗口对齐）+ 长期语义/场景记忆
- [x] 安全：密钥进钥匙串、命令策略、sandbox（container/seatbelt/pathguard）、内容/工具结果扫描、secret 脱敏、数据 at-rest 加密（AES-256-GCM）

### 工程质量
- [x] 后端：ruff + pytest（含 agent 集成测试、加密、预算、评测判定器）
- [x] 前端：vitest + testing-library（MessageList 状态）
- [x] CI：GitHub Actions（ruff+pytest / npm build+test / cargo check）
- [x] evals：黄金集 + 规则判定器 + 离线运行器

## 待办（下一步可做）

- [ ] 模型路由（成本/质量：简单任务走小模型、复杂走大模型）
- [ ] RAG / 知识库 + 语义缓存
- [ ] 崩溃上报（Sentry）+ 自动更新（Tauri updater）
- [ ] MCP 远程 transport（SSE / streamable HTTP）
- [ ] `edit_file` diff 的可视化渲染增强
- [ ] 依赖漏洞扫描 / SBOM、CI 接入 secret scan（gitleaks）
- [ ] 代码签名 + 公证（需 Apple Developer 证书）
