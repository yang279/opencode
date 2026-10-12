#!/usr/bin/env bash
# 一键启动开发环境：Python 后端 + Vite 前端（+ 可选 Tauri dev）。
#
# 用法：
#   scripts/dev.sh            # 起后端 + 前端
#   scripts/dev.sh --tauri    # 起后端 + Tauri(内部拉起前端)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 固定开发端口/token，前端通过 VITE_* 变量直连后端
export MYOPENCODE_HOST="${MYOPENCODE_HOST:-127.0.0.1}"
export MYOPENCODE_PORT="${MYOPENCODE_PORT:-8787}"
export MYOPENCODE_TOKEN="${MYOPENCODE_TOKEN:-dev-token}"
export VITE_BACKEND_PORT="$MYOPENCODE_PORT"
export VITE_BACKEND_TOKEN="$MYOPENCODE_TOKEN"

echo "==> 准备 Python 后端"
if [ ! -d "backend/.venv" ]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install -q -e backend

echo "==> 启动后端 (port=$MYOPENCODE_PORT token=$MYOPENCODE_TOKEN)"
backend/.venv/bin/python -m myopencode &
BACKEND_PID=$!

cleanup() {
  echo "==> 停止后端"
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

if [ "${1:-}" = "--tauri" ]; then
  echo "==> 启动 Tauri dev（会自行拉起 Vite）"
  cd src-tauri
  npm run tauri dev --prefix ../frontend 2>/dev/null || true
  # 若未配置 tauri cli，回退提示
  echo "提示: 请先安装 Tauri CLI：npm i -g @tauri-apps/cli"
else
  echo "==> 启动前端 Vite (http://localhost:5173)"
  cd frontend
  if [ ! -d node_modules ]; then npm install; fi
  npm run dev
fi