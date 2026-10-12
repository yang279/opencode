#!/usr/bin/env bash
# Python 静态检查（ruff）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

if [ -x .venv/bin/ruff ]; then
  .venv/bin/ruff check src tests
else
  ruff check src tests
fi
