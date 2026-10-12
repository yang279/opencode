#!/usr/bin/env bash
# 构建 Rust `wasm-runner`（wasmtime/WASI 沙箱），输出到 src-tauri/binaries 供 externalBin 打包。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CARGO="${CARGO:-cargo}"
"$CARGO" build --release --manifest-path src-tauri/wasm-runner/Cargo.toml

mkdir -p src-tauri/binaries
BIN="src-tauri/wasm-runner/target/release/wasm-runner"
TARGET="$(rustc -vV 2>/dev/null | sed -n 's/host: //p' | head -1)"
if [ -n "$TARGET" ]; then
  cp "$BIN" "src-tauri/binaries/wasm-runner-$TARGET"
  echo "完成: src-tauri/binaries/wasm-runner-$TARGET"
else
  cp "$BIN" "src-tauri/binaries/wasm-runner"
  echo "完成: src-tauri/binaries/wasm-runner"
fi