#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="1.0.0"
PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="${BIN_DIR:-$PREFIX/bin}"
INSTALL_QWEN="${INSTALL_QWEN:-auto}"
PROVIDER="${PROVIDER:-}"
BASE_URL="${BASE_URL:-${OPENAI_BASE_URL:-}}"
ENV_KEY="${ENV_KEY:-}"
DEFAULT_MODEL="${DEFAULT_MODEL:-}"
APPROVAL_MODE="${APPROVAL_MODE:-default}"
FREE_ONLY="${FREE_ONLY:-false}"
FILTER_MODEL="${FILTER_MODEL:-}"
CODER_ONLY="${CODER_ONLY:-false}"
MIN_CONTEXT="${MIN_CONTEXT:-}"
NON_INTERACTIVE="${NON_INTERACTIVE:-false}"

usage() {
  cat <<'EOF'
Qwen Omega ProMeta automated installer

Usage:
  ./install.sh [options]

Options:
  --provider NAME       openai, openrouter, nvidia, groq, together, fireworks,
                        deepinfra, cerebras, mistral, dashscope, ollama, litellm,
                        siliconflow, featherless, novita, hyperbolic, anyscale,
                        friendli, sambanova, deepseek, ai21, perplexity, cloudflare
  --base-url URL        custom OpenAI-compatible base URL
  --env-key NAME        environment variable containing the API key
  --default-model ID    default Qwen Code model
  --approval-mode MODE  plan|default|auto-edit|auto|yolo (default: default)
  --free                configure only explicitly free/zero-priced models
  --install-qwen        install/update @qwen-code/qwen-code globally with npm
  --skip-qwen           do not install Qwen Code
  --non-interactive     fail instead of prompting
  --prefix PATH         installation prefix (default: ~/.local)
  -h, --help            show help

Examples:
  export OPENAI_API_KEY='sk-...'
  ./install.sh --provider openai

  export OPENROUTER_API_KEY='sk-or-v1-...'
  ./install.sh --provider openrouter --free

  export OLLAMA_API_KEY='ollama'
  ./install.sh --provider ollama --default-model qwen3-coder:latest
EOF
}

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

while (($#)); do
  case "$1" in
    --provider) [[ $# -ge 2 ]] || die "--provider requires a value"; PROVIDER="$2"; shift 2 ;;
    --base-url) [[ $# -ge 2 ]] || die "--base-url requires a value"; BASE_URL="$2"; shift 2 ;;
    --env-key) [[ $# -ge 2 ]] || die "--env-key requires a value"; ENV_KEY="$2"; shift 2 ;;
    --default-model) [[ $# -ge 2 ]] || die "--default-model requires a value"; DEFAULT_MODEL="$2"; shift 2 ;;
    --approval-mode) [[ $# -ge 2 ]] || die "--approval-mode requires a value"; APPROVAL_MODE="$2"; shift 2 ;;
    --filter-model) [[ $# -ge 2 ]] || die "--filter-model requires a value"; FILTER_MODEL="$2"; shift 2 ;;
    --coder-only) CODER_ONLY=true; shift ;;
    --min-context) [[ $# -ge 2 ]] || die "--min-context requires a value"; MIN_CONTEXT="$2"; shift 2 ;;
    --free) FREE_ONLY=true; shift ;;
    --install-qwen) INSTALL_QWEN=true; shift ;;
    --skip-qwen) INSTALL_QWEN=false; shift ;;
    --non-interactive) NON_INTERACTIVE=true; shift ;;
    --prefix) [[ $# -ge 2 ]] || die "--prefix requires a value"; PREFIX="$2"; BIN_DIR="$PREFIX/bin"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

command -v python3 >/dev/null 2>&1 || die "python3 is required"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "$SCRIPT_DIR/qwen-omega.py" ]] || die "qwen-omega.py not found beside install.sh"

if [[ -z "$PROVIDER" && -z "$BASE_URL" ]]; then
  if [[ "$NON_INTERACTIVE" == true || ! -t 0 ]]; then
    die "provide --provider or --base-url"
  fi
  printf 'Provider [openai]: '
  read -r PROVIDER
  PROVIDER="${PROVIDER:-openai}"
fi

mkdir -p "$BIN_DIR" "$HOME/.qwen"
install -m 0755 "$SCRIPT_DIR/qwen-omega.py" "$BIN_DIR/qwen-omega"
info "Installed generator: $BIN_DIR/qwen-omega"

case "$INSTALL_QWEN" in
  true)
    command -v npm >/dev/null 2>&1 || die "npm is required for --install-qwen"
    info "Installing/updating Qwen Code"
    npm install --global @qwen-code/qwen-code
    ;;
  auto)
    if ! command -v qwen >/dev/null 2>&1; then
      if command -v npm >/dev/null 2>&1; then
        info "Qwen Code not found; installing with npm"
        npm install --global @qwen-code/qwen-code
      else
        printf 'WARNING: qwen and npm are unavailable; generator installed only.\n' >&2
      fi
    fi
    ;;
  false) ;;
  *) die "invalid INSTALL_QWEN value: $INSTALL_QWEN" ;;
esac

ARGS=(generate --approval-mode "$APPROVAL_MODE")
[[ -n "$PROVIDER" ]] && ARGS+=(--provider "$PROVIDER")
[[ -n "$BASE_URL" ]] && ARGS+=(--base-url "$BASE_URL")
[[ -n "$ENV_KEY" ]] && ARGS+=(--env-key "$ENV_KEY")
[[ -n "$DEFAULT_MODEL" ]] && ARGS+=(--default-model "$DEFAULT_MODEL")
[[ -n "$FILTER_MODEL" ]] && ARGS+=(--filter-model "$FILTER_MODEL")
[[ "$CODER_ONLY" == true ]] && ARGS+=(--coder-only)
[[ -n "$MIN_CONTEXT" ]] && ARGS+=(--min-context "$MIN_CONTEXT")
[[ "$FREE_ONLY" == true ]] && ARGS+=(--free)

"$BIN_DIR/qwen-omega" "${ARGS[@]}"
"$BIN_DIR/qwen-omega" validate

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    printf '\nAdd this to ~/.bashrc or ~/.zshrc:\n  export PATH="%s:$PATH"\n' "$BIN_DIR"
    ;;
esac

cat <<EOF

Installation complete.

Commands:
  qwen-omega doctor
  qwen-omega validate
  qwen-omega repair
  qwen

Inside Qwen Code:
  /model
  /doctor
EOF
