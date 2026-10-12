# 构建 Rust wasm-runner（wasmtime/WASI），输出到 src-tauri/binaries 供 externalBin 打包（Windows）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

cargo build --release --manifest-path src-tauri/wasm-runner/Cargo.toml

New-Item -ItemType Directory -Force -Path "src-tauri/binaries" | Out-Null
$Target = (rustc -vV | Select-String "host:").Line.Split(" ")[2].Trim()
Copy-Item "src-tauri\wasm-runner\target\release\wasm-runner.exe" "src-tauri\binaries\wasm-runner-$Target.exe"
Write-Host "完成: src-tauri/binaries/wasm-runner-$Target.exe"
