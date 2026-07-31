#!/usr/bin/env bash
set -Eeuo pipefail
BIN="${BIN_DIR:-$HOME/.local/bin}/qwen-omega"
rm -f "$BIN"
printf 'Removed %s\n' "$BIN"
printf 'Qwen settings were preserved at %s\n' "$HOME/.qwen/settings.json"
