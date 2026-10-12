#!/usr/bin/env bash
# 一键打包桌面应用：sidecar + 前端 + Rust，产出 .app/.dmg(macOS) 或 .exe(Windows)。
#
# 用法：./scripts/package.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> [1/5] 确保 Rust 工具链"
rustup default stable >/dev/null 2>&1 || true

echo "==> [2/5] 安装前端依赖 + Tauri CLI"
(cd frontend && [ -d node_modules ] || npm install)
(cd frontend && npm install -D @tauri-apps/cli@^2 >/dev/null 2>&1 || true)

echo "==> [3/5] 打包 Python sidecar"
./scripts/build-sidecar.sh

echo "==> [4/5] 构建 wasm-runner"
./scripts/build-wasm-runner.sh

echo "==> [5/5] Tauri 打包"
./frontend/node_modules/.bin/tauri build

echo ""
echo "✅ 打包完成，产物："
echo "   macOS: src-tauri/target/release/bundle/dmg/*.dmg"
echo "   Windows: src-tauri/target/release/bundle/nsis/*.exe"