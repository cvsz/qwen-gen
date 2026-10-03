#!/usr/bin/env bash
# qwen-stack.sh - launch the full local-LLM stack with HDD-backed Qwen data
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${QWEN_STACK_COMPOSE:-$SCRIPT_DIR/docker-compose.fullstack.yml}"
DATA_DIR="${QWEN_DATA_DIR:-/mnt/qwen-gen-data}"
OPENWEBUI_HOST_PORT="${OPENWEBUI_HOST_PORT:-3011}"
NEXTCHAT_HOST_PORT="${NEXTCHAT_HOST_PORT:-3000}"
NEXTCHAT_DEFAULT_MODEL="${NEXTCHAT_DEFAULT_MODEL:-zCoder:latest}"
NEXTCHAT_CUSTOM_MODELS="${NEXTCHAT_CUSTOM_MODELS:-zCoder:latest,qwen2.5-coder}"
QWEN_HOST_PORT="${QWEN_HOST_PORT:-8787}"
QWEN_UID="${QWEN_UID:-$(id -u)}"
QWEN_GID="${QWEN_GID:-$(id -g)}"
BUILD="${BUILD:-true}"
DETACH="${DETACH:-false}"
ACTION="up"

usage() {
  cat <<'EOF'
Usage:
  ./qwen-stack.sh [--data-dir DIR] [--compose-file FILE] [--no-build] [--detach] [up|down|logs|ps|restart]

Defaults:
  data dir      /mnt/qwen-gen-data
  compose file   docker-compose.fullstack.yml
  action        up

Environment overrides:
  QWEN_DATA_DIR       Host directory mounted to qwen-gen /data
  QWEN_STACK_NETWORK_MODE Docker network mode (host by default for host Ollama)
  QWEN_LITELLM_BASE_URL LiteLLM URL used by the UIs and qwen-gen
  QWEN_OLLAMA_BASE_URL Ollama URL used by qwen-gen
  OPENWEBUI_HOST_PORT Host port published for the secondary Open WebUI
  NEXTCHAT_HOST_PORT  Host port published for NextChat
  NEXTCHAT_DEFAULT_MODEL Model selected by default in NextChat
  NEXTCHAT_CUSTOM_MODELS Comma-separated models exposed by NextChat
  QWEN_HOST_PORT      Host port published for qwen-gen
  QWEN_UID            Runtime user ID for qwen-gen data ownership
  QWEN_GID            Runtime group ID for qwen-gen data ownership
  QWEN_STACK_COMPOSE  Compose file path
  BUILD               Set to false to skip compose --build
  DETACH              Set to true to run detached
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

load_env_file() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
}

load_env_file "$SCRIPT_DIR/.env"
load_env_file "$SCRIPT_DIR/.env.ai"

while (($#)); do
  case "$1" in
    --data-dir)
      [[ $# -ge 2 ]] || die "--data-dir requires a value"
      DATA_DIR="$2"
      shift 2
      ;;
    --compose-file)
      [[ $# -ge 2 ]] || die "--compose-file requires a value"
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --qwen-host-port)
      [[ $# -ge 2 ]] || die "--qwen-host-port requires a value"
      QWEN_HOST_PORT="$2"
      shift 2
      ;;
    --no-build)
      BUILD=false
      shift
      ;;
    --detach|-d)
      DETACH=true
      shift
      ;;
    up|down|logs|ps|restart)
      ACTION="$1"
      shift
      break
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

[[ -f "$COMPOSE_FILE" ]] || die "compose file not found: $COMPOSE_FILE"
mkdir -p "$DATA_DIR"

export QWEN_DATA_DIR="$DATA_DIR"
export OPENWEBUI_HOST_PORT
export NEXTCHAT_HOST_PORT
export NEXTCHAT_DEFAULT_MODEL
export NEXTCHAT_CUSTOM_MODELS
export QWEN_HOST_PORT
export QWEN_UID
export QWEN_GID

cmd=(docker compose -f "$COMPOSE_FILE")
if [[ "$ACTION" == "up" ]]; then
  if [[ "$BUILD" == true ]]; then
    cmd+=(up --build)
  else
    cmd+=(up)
  fi
  if [[ "$DETACH" == true ]]; then
    cmd+=(-d)
  fi
else
  cmd+=("$ACTION")
fi

if (($#)); then
  cmd+=("$@")
fi

exec "${cmd[@]}"
