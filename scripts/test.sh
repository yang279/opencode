#!/usr/bin/env bash
# 运行后端单测（pytest）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

if [ -x .venv/bin/pytest ]; then
  .venv/bin/pytest -q
else
  pytest -q
fi