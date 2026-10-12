# 一键打包桌面应用（Windows）：Python sidecar + wasm-runner + 前端 + Tauri，产出 .exe/.msi
# 在 Windows 机器（或 Windows CI）上运行：
#   powershell -ExecutionPolicy Bypass -File scripts/package-windows.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Target = (rustc -vV | Select-String "host:").Line.Split(" ")[2].Trim()

Write-Host "==> [1/4] 打包 Python sidecar"
Set-Location "$Root\backend"
if (-not (Test-Path .venv-build)) { python -m venv .venv-build }
& .\.venv-build\Scripts\pip install -q -e ".[providers]" pyinstaller
& .\.venv-build\Scripts\pyinstaller --onefile --name myopencode-sidecar --collect-all myopencode --hidden-import yaml sidecar_entry.py
New-Item -ItemType Directory -Force -Path "$Root\src-tauri\binaries" | Out-Null
Copy-Item "dist\myopencode-sidecar.exe" "$Root\src-tauri\binaries\myopencode-sidecar-$Target.exe"

Write-Host "==> [2/4] 构建 wasm-runner"
Set-Location $Root
cargo build --release --manifest-path src-tauri/wasm-runner/Cargo.toml
Copy-Item "src-tauri\wasm-runner\target\release\wasm-runner.exe" "src-tauri\binaries\wasm-runner-$Target.exe"

Write-Host "==> [3/4] 前端依赖 + 构建"
Set-Location "$Root\frontend"
if (-not (Test-Path node_modules)) { npm install }
npm install -D "@tauri-apps/cli@^2"
npm run build

Write-Host "==> [4/4] Tauri 打包"
npx tauri build --target $Target

Write-Host ""
Write-Host "完成，产物见 src-tauri/target/release/bundle/"