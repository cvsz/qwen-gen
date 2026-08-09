#!/usr/bin/env bash
# qwen-free.sh - keep only free models that pass a real chat probe
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/qwen-free.py" "$@"
