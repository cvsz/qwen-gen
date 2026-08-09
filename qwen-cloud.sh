#!/usr/bin/env bash
# qwen-cloud.sh - run the browser chat container with the HDD mount by default
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${IMAGE:-qwen-gen:latest}"
DATA_DIR="${QWEN_DATA_DIR:-/mnt/qwen-gen-data}"
SETTINGS_PATH="${QWEN_SETTINGS:-/data/settings.json}"
HOST="${QWEN_HOST:-0.0.0.0}"
PORT="${QWEN_PORT:-8787}"
BUILD_IMAGE="${BUILD_IMAGE:-true}"

usage() {
  cat <<'EOF'
Usage:
  ./qwen-cloud.sh [--data-dir DIR] [--port PORT] [--image NAME] [--no-build] [docker args...]

Defaults:
  data dir   /mnt/qwen-gen-data
  image      qwen-gen:latest
  host       0.0.0.0
  port       8787

Environment overrides:
  QWEN_DATA_DIR   Persistent host directory for /data
  QWEN_SETTINGS   Container settings path (default: /data/settings.json)
  QWEN_HOST      Container bind host (default: 0.0.0.0)
  QWEN_PORT      Container port (default: 8787)
  IMAGE          Container image name (default: qwen-gen:latest)
  BUILD_IMAGE    Set to false to skip docker build
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --data-dir)
      [[ $# -ge 2 ]] || die "--data-dir requires a value"
      DATA_DIR="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || die "--port requires a value"
      PORT="$2"
      shift 2
      ;;
    --image)
      [[ $# -ge 2 ]] || die "--image requires a value"
      IMAGE="$2"
      shift 2
      ;;
    --no-build)
      BUILD_IMAGE=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

[[ -d "$DATA_DIR" ]] || die "data directory not found: $DATA_DIR"

if [[ "$BUILD_IMAGE" == true ]]; then
  docker build -t "$IMAGE" "$SCRIPT_DIR"
fi

ENV_ARGS=()
for env_file in "$SCRIPT_DIR/.env" "$SCRIPT_DIR/.env.ai"; do
  [[ -f "$env_file" ]] || continue
  ENV_ARGS+=(--env-file "$env_file")
done

exec docker run --rm \
  -p "${PORT}:${PORT}" \
  -e "QWEN_SETTINGS=${SETTINGS_PATH}" \
  -e "QWEN_HOST=${HOST}" \
  -e "QWEN_PORT=${PORT}" \
  "${ENV_ARGS[@]}" \
  -v "${DATA_DIR}:/data" \
  "$@" \
  "$IMAGE"
