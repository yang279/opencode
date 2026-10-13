#!/usr/bin/env bash
# 用 PyInstaller 将 Python 后端打包为单文件 sidecar，
# 输出到 src-tauri/binaries/myopencode-sidecar（供 Tauri externalBin 使用）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

if [ ! -d .venv-build ]; then
  python3 -m venv .venv-build
fi
.venv-build/bin/pip install -q -e ".[providers]" pyinstaller

.venv-build/bin/pyinstaller \
  --onefile \
  --name myopencode-sidecar \
  --collect-all myopencode \
  --hidden-import yaml \
  --hidden-import pypdf \
  sidecar_entry.py

mkdir -p "$ROOT/src-tauri/binaries"
# Tauri externalBin 按 base-name{-target-triple} 查找 sidecar
TARGET="$(rustc -vV 2>/dev/null | sed -n 's/host: //p' | head -1)"
if [ -n "$TARGET" ]; then
  cp dist/myopencode-sidecar "$ROOT/src-tauri/binaries/myopencode-sidecar-$TARGET"
  echo "完成: $ROOT/src-tauri/binaries/myopencode-sidecar-$TARGET"
else
  cp dist/myopencode-sidecar "$ROOT/src-tauri/binaries/myopencode-sidecar"
  echo "完成: $ROOT/src-tauri/binaries/myopencode-sidecar"
fi