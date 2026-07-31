#!/usr/bin/env bash
# install-qwen-coder.sh — Qwen Coder one-shot installer
# Supports: Ollama (local), DashScope, OpenRouter, SiliconFlow
# Part of: qwen-gen / Qwen Omega ProMeta
set -Eeuo pipefail

VERSION="1.0.0"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OMEGA="$SCRIPT_DIR/qwen-omega.py"

# ── Defaults ────────────────────────────────────────────────────────────────
BACKEND="${BACKEND:-auto}"         # ollama | dashscope | openrouter | siliconflow | custom
MODEL="${MODEL:-}"                 # leave empty → choose best available
APPROVAL_MODE="${APPROVAL_MODE:-default}"
INSTALL_QWEN="${INSTALL_QWEN:-auto}"
OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
NON_INTERACTIVE="${NON_INTERACTIVE:-false}"
DRY_RUN="${DRY_RUN:-false}"
FREE_ONLY="${FREE_ONLY:-false}"
PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="${BIN_DIR:-$PREFIX/bin}"

# ── Qwen Coder model catalog ─────────────────────────────────────────────────
# Ordered: best first (largest context / most capable)
OLLAMA_CODER_MODELS=(
  "qwen2.5-coder:32b-instruct-q4_K_M"
  "qwen2.5-coder:14b-instruct-q4_K_M"
  "qwen2.5-coder:7b-instruct-q4_K_M"
  "qwen2.5-coder:3b-instruct-q4_K_M"
  "qwen2.5-coder:1.5b-instruct-q4_K_M"
  "qwen3-coder:latest"
)

DASHSCOPE_CODER_MODELS=(
  "qwen-coder-plus"
  "qwen-coder-turbo"
  "qwen2.5-coder-32b-instruct"
  "qwen2.5-coder-14b-instruct"
  "qwen2.5-coder-7b-instruct"
)

OPENROUTER_FREE_CODER_MODELS=(
  "qwen/qwen3-coder:free"
  "qwen/qwen-2.5-coder-32b-instruct:free"
)

SILICONFLOW_CODER_MODELS=(
  "Qwen/Qwen2.5-Coder-32B-Instruct"
  "Qwen/Qwen2.5-Coder-7B-Instruct"
)

# ── Helpers ──────────────────────────────────────────────────────────────────
red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
blue()   { printf '\033[34;1m%s\033[0m\n' "$*"; }
info()   { printf '  \033[34m==>\033[0m %s\n' "$*"; }
ok()     { printf '  \033[32m✔\033[0m  %s\n' "$*"; }
warn()   { printf '  \033[33m⚠\033[0m  %s\n' "$*" >&2; }
die()    { red "ERROR: $*" >&2; exit 1; }

hr() { printf '%s\n' "────────────────────────────────────────────────────────────────────────────────"; }

usage() {
  cat <<EOF
Qwen Coder Installer v${VERSION}

Usage:
  ./install-qwen-coder.sh [options]

Backend selection (auto-detected if omitted):
  --backend ollama        Local inference via Ollama (preferred, free)
  --backend dashscope     Alibaba DashScope API  (requires DASHSCOPE_API_KEY)
  --backend openrouter    OpenRouter :free tier  (requires OPENROUTER_API_KEY)
  --backend siliconflow   SiliconFlow API        (requires SILICONFLOW_API_KEY)
  --backend custom        Use --base-url + --env-key

Model options:
  --model NAME            Override auto-selected model
  --free                  Restrict to zero-cost models only (openrouter :free)
  --approval-mode MODE    plan|default|auto-edit|auto|yolo  (default: default)

Install options:
  --install-qwen          Force install @qwen-code/qwen-code via npm
  --skip-qwen             Skip npm install entirely
  --prefix PATH           Installation prefix (default: ~/.local)
  --dry-run               Print config without writing files
  --non-interactive       Error instead of prompting

Custom backend:
  --base-url URL          OpenAI-compatible endpoint
  --env-key NAME          Environment variable holding API key

  -h, --help              Show this help

Environment variables (all backends):
  OLLAMA_HOST             Ollama server URL    (default: http://127.0.0.1:11434)
  DASHSCOPE_API_KEY
  OPENROUTER_API_KEY
  SILICONFLOW_API_KEY

Examples:
  # Fully local — auto-pulls best Qwen Coder model into Ollama
  ./install-qwen-coder.sh --backend ollama

  # Cloud free tier (no credit card needed)
  export OPENROUTER_API_KEY='sk-or-v1-...'
  ./install-qwen-coder.sh --backend openrouter --free

  # DashScope (Alibaba official)
  export DASHSCOPE_API_KEY='sk-...'
  ./install-qwen-coder.sh --backend dashscope --model qwen-coder-plus

  # Custom vLLM / LM Studio endpoint
  ./install-qwen-coder.sh --backend custom --base-url http://127.0.0.1:8000/v1 --env-key MY_KEY
EOF
}

# ── Argument parsing ─────────────────────────────────────────────────────────
CUSTOM_BASE_URL=""
CUSTOM_ENV_KEY=""

while (($#)); do
  case "$1" in
    --backend)       [[ $# -ge 2 ]] || die "--backend requires a value"; BACKEND="$2"; shift 2 ;;
    --model)         [[ $# -ge 2 ]] || die "--model requires a value";   MODEL="$2";   shift 2 ;;
    --approval-mode) [[ $# -ge 2 ]] || die "--approval-mode requires a value"; APPROVAL_MODE="$2"; shift 2 ;;
    --base-url)      [[ $# -ge 2 ]] || die "--base-url requires a value"; CUSTOM_BASE_URL="$2"; shift 2 ;;
    --env-key)       [[ $# -ge 2 ]] || die "--env-key requires a value";  CUSTOM_ENV_KEY="$2";  shift 2 ;;
    --install-qwen)  INSTALL_QWEN=true; shift ;;
    --skip-qwen)     INSTALL_QWEN=false; shift ;;
    --free)          FREE_ONLY=true; shift ;;
    --dry-run)       DRY_RUN=true; shift ;;
    --non-interactive) NON_INTERACTIVE=true; shift ;;
    --prefix)        [[ $# -ge 2 ]] || die "--prefix requires a value"; PREFIX="$2"; BIN_DIR="$PREFIX/bin"; shift 2 ;;
    -h|--help)       usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

# ── Prerequisite check ───────────────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || die "python3 is required"
[[ -f "$OMEGA" ]] || die "qwen-omega.py not found at $OMEGA"

# ── Banner ───────────────────────────────────────────────────────────────────
blue ""; blue "  ██████  ██     ██ ███████ ███    ██      ██████  ██████  ██████  ███████ ██████"
blue "  ██   ██ ██     ██ ██      ████   ██     ██      ██    ██ ██   ██ ██      ██   ██"
blue "  ██   ██ ██  █  ██ █████   ██ ██  ██     ██      ██    ██ ██   ██ █████   ██████ "
blue "  ██   ██ ██ ███ ██ ██      ██  ██ ██     ██      ██    ██ ██   ██ ██      ██   ██"
blue "  ██████   ███ ███  ███████ ██   ████     ███████  ██████  ██████  ███████ ██   ██"
blue ""
info "Qwen Coder Installer v${VERSION}  •  backend: ${BACKEND}"
hr

# ── Auto-detect backend ──────────────────────────────────────────────────────
if [[ "$BACKEND" == "auto" ]]; then
  if command -v ollama >/dev/null 2>&1 || curl -sf "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    BACKEND="ollama"
    info "Auto-detected: Ollama"
  elif [[ -n "${DASHSCOPE_API_KEY:-}" ]]; then
    BACKEND="dashscope"
    info "Auto-detected: DashScope (DASHSCOPE_API_KEY is set)"
  elif [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    BACKEND="openrouter"
    info "Auto-detected: OpenRouter (OPENROUTER_API_KEY is set)"
  elif [[ -n "${SILICONFLOW_API_KEY:-}" ]]; then
    BACKEND="siliconflow"
    info "Auto-detected: SiliconFlow (SILICONFLOW_API_KEY is set)"
  else
    if [[ "$NON_INTERACTIVE" == true ]]; then
      die "Cannot auto-detect backend. Set an API key env var or pass --backend."
    fi
    yellow "No backend auto-detected. Choose:"
    select opt in "ollama (local)" "dashscope" "openrouter (free tier)" "siliconflow" "custom"; do
      case "$opt" in
        "ollama (local)")         BACKEND=ollama;      break ;;
        "dashscope")              BACKEND=dashscope;   break ;;
        "openrouter (free tier)") BACKEND=openrouter;  break ;;
        "siliconflow")            BACKEND=siliconflow; break ;;
        "custom")                 BACKEND=custom;      break ;;
      esac
    done
  fi
fi

# ── Backend configuration ────────────────────────────────────────────────────
OMEGA_ARGS=()
PULL_MODEL=""

case "$BACKEND" in

  ollama)
    # ── Ensure Ollama is reachable ──────────────────────────────────────────
    if ! command -v ollama >/dev/null 2>&1 && ! curl -sf "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
      warn "Ollama not found locally."
      if [[ "$NON_INTERACTIVE" == true ]]; then
        die "Install Ollama first: https://ollama.com/download"
      fi
      printf "Install Ollama now? [Y/n]: "
      read -r yn
      if [[ "${yn:-Y}" =~ ^[Yy]$ ]]; then
        info "Installing Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
      else
        die "Ollama required for --backend ollama"
      fi
    fi

    # ── Choose model ────────────────────────────────────────────────────────
    if [[ -z "$MODEL" ]]; then
      # Pick the largest model that fits available RAM heuristic
      TOTAL_RAM_GB=0
      if command -v free >/dev/null 2>&1; then
        TOTAL_RAM_GB=$(free -g | awk '/Mem:/{print $2}')
      fi

      if   (( TOTAL_RAM_GB >= 40 )); then MODEL="${OLLAMA_CODER_MODELS[0]}"  # 32b
      elif (( TOTAL_RAM_GB >= 20 )); then MODEL="${OLLAMA_CODER_MODELS[1]}"  # 14b
      elif (( TOTAL_RAM_GB >= 10 )); then MODEL="${OLLAMA_CODER_MODELS[2]}"  # 7b
      elif (( TOTAL_RAM_GB >=  5 )); then MODEL="${OLLAMA_CODER_MODELS[3]}"  # 3b
      else                                MODEL="${OLLAMA_CODER_MODELS[4]}"  # 1.5b
      fi
      info "RAM: ${TOTAL_RAM_GB}GB detected → selecting model: $MODEL"
    fi

    PULL_MODEL="$MODEL"
    OMEGA_ARGS+=(
      generate
      --provider ollama
      --models "$MODEL"
      --default-model "$MODEL"
      --approval-mode "$APPROVAL_MODE"
    )
    ;;

  dashscope)
    [[ -n "${DASHSCOPE_API_KEY:-}" ]] || die "DASHSCOPE_API_KEY is not set"
    [[ -z "$MODEL" ]] && MODEL="${DASHSCOPE_CODER_MODELS[0]}"
    OMEGA_ARGS+=(
      generate
      --provider dashscope
      --models "$(IFS=','; echo "${DASHSCOPE_CODER_MODELS[*]}")"
      --default-model "$MODEL"
      --approval-mode "$APPROVAL_MODE"
      --coder-only
    )
    ;;

  openrouter)
    [[ -n "${OPENROUTER_API_KEY:-}" ]] || die "OPENROUTER_API_KEY is not set"
    if [[ "$FREE_ONLY" == true || -z "${OPENROUTER_API_KEY:-}" ]]; then
      [[ -z "$MODEL" ]] && MODEL="${OPENROUTER_FREE_CODER_MODELS[0]}"
      OMEGA_ARGS+=(
        generate
        --provider openrouter
        --free
        --filter-model "coder|code"
        --default-model "$MODEL"
        --approval-mode "$APPROVAL_MODE"
      )
    else
      [[ -z "$MODEL" ]] && MODEL="${OPENROUTER_FREE_CODER_MODELS[0]}"
      OMEGA_ARGS+=(
        generate
        --provider openrouter
        --coder-only
        --default-model "$MODEL"
        --approval-mode "$APPROVAL_MODE"
      )
    fi
    ;;

  siliconflow)
    [[ -n "${SILICONFLOW_API_KEY:-}" ]] || die "SILICONFLOW_API_KEY is not set"
    [[ -z "$MODEL" ]] && MODEL="${SILICONFLOW_CODER_MODELS[0]}"
    OMEGA_ARGS+=(
      generate
      --provider siliconflow
      --models "$(IFS=','; echo "${SILICONFLOW_CODER_MODELS[*]}")"
      --default-model "$MODEL"
      --approval-mode "$APPROVAL_MODE"
      --coder-only
    )
    ;;

  litellm)
    [[ -z "$MODEL" ]] && MODEL="qwen3-coder"
    OMEGA_ARGS+=(
      generate
      --provider litellm
      --models "qwen3-coder,qwen2.5-coder-32b-instruct,qwen2.5-coder-7b-instruct"
      --default-model "$MODEL"
      --approval-mode "$APPROVAL_MODE"
    )
    ;;

  lmstudio)
    [[ -z "$MODEL" ]] && MODEL="qwen2.5-coder-7b-instruct"
    OMEGA_ARGS+=(
      generate
      --provider lmstudio
      --models "qwen2.5-coder-7b-instruct,qwen2.5-coder-14b-instruct,qwen2.5-coder-32b-instruct"
      --default-model "$MODEL"
      --approval-mode "$APPROVAL_MODE"
    )
    ;;

  nextchat)
    [[ -z "$MODEL" ]] && MODEL="qwen3-coder"
    OMEGA_ARGS+=(
      generate
      --provider nextchat
      --models "qwen3-coder,qwen2.5-coder-32b-instruct,qwen2.5-coder-7b-instruct"
      --default-model "$MODEL"
      --approval-mode "$APPROVAL_MODE"
    )
    ;;

  open_webui)
    [[ -z "$MODEL" ]] && MODEL="qwen2.5-coder:7b-instruct-q4_K_M"
    OMEGA_ARGS+=(
      generate
      --provider open_webui
      --models "qwen2.5-coder:7b-instruct-q4_K_M,qwen2.5-coder:32b-instruct-q4_K_M,qwen3-coder:latest"
      --default-model "$MODEL"
      --approval-mode "$APPROVAL_MODE"
    )
    ;;

  custom)
    [[ -n "$CUSTOM_BASE_URL" ]] || die "--backend custom requires --base-url"
    [[ -z "$MODEL" ]] && die "--backend custom requires --model"
    ENV_KEY="${CUSTOM_ENV_KEY:-OPENAI_API_KEY}"
    OMEGA_ARGS+=(
      generate
      --base-url "$CUSTOM_BASE_URL"
      --env-key  "$ENV_KEY"
      --models   "$MODEL"
      --default-model "$MODEL"
      --approval-mode "$APPROVAL_MODE"
    )
    ;;

  *)
    die "Unknown backend: $BACKEND (valid: ollama, dashscope, openrouter, siliconflow, custom)"
    ;;
esac

[[ "$DRY_RUN" == true ]] && OMEGA_ARGS+=(--dry-run)

# ── Install qwen-omega binary ────────────────────────────────────────────────
if [[ "$DRY_RUN" != true ]]; then
  mkdir -p "$BIN_DIR" "$HOME/.qwen"
  install -m 0755 "$OMEGA" "$BIN_DIR/qwen-omega"
  ok "Installed: $BIN_DIR/qwen-omega"
fi

# ── Install Qwen Code CLI (npm) ──────────────────────────────────────────────
install_qwen_code() {
  case "$INSTALL_QWEN" in
    true)
      command -v npm >/dev/null 2>&1 || die "npm required for --install-qwen"
      info "Installing @qwen-code/qwen-code globally..."
      npm install --global @qwen-code/qwen-code
      ok "Qwen Code installed"
      ;;
    auto)
      if ! command -v qwen >/dev/null 2>&1; then
        if command -v npm >/dev/null 2>&1; then
          info "qwen not found — installing via npm..."
          npm install --global @qwen-code/qwen-code
          ok "Qwen Code installed"
        else
          warn "qwen and npm unavailable; skipping Qwen Code CLI install"
        fi
      else
        ok "Qwen Code already installed: $(command -v qwen)"
      fi
      ;;
    false) ;;
    *) die "invalid INSTALL_QWEN value: $INSTALL_QWEN" ;;
  esac
}

install_qwen_code

# ── Pull Ollama model ────────────────────────────────────────────────────────
if [[ -n "$PULL_MODEL" && "$DRY_RUN" != true ]]; then
  info "Pulling Ollama model: $PULL_MODEL"
  if command -v ollama >/dev/null 2>&1; then
    if ollama pull "$PULL_MODEL"; then
      ok "Model ready: $PULL_MODEL"
    else
      warn "ollama pull failed; model may already exist"
    fi
  else
    # Try via REST API
    if curl -fsSL -X POST "${OLLAMA_HOST}/api/pull" \
      -d "{\"name\":\"$PULL_MODEL\",\"stream\":false}" \
      -H "Content-Type: application/json" >/dev/null; then
      ok "Model ready: $PULL_MODEL"
    else
      warn "Failed to pull $PULL_MODEL; run: ollama pull $PULL_MODEL"
    fi
  fi
fi

# ── Generate settings ────────────────────────────────────────────────────────
hr
info "Generating Qwen Code settings..."
python3 "$OMEGA" "${OMEGA_ARGS[@]}"

# ── Validate ─────────────────────────────────────────────────────────────────
if [[ "$DRY_RUN" != true ]]; then
  python3 "$OMEGA" validate && ok "Settings validated"
fi

# ── PATH hint ────────────────────────────────────────────────────────────────
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    yellow ""
    yellow "Add to ~/.bashrc or ~/.zshrc:"
    yellow "  export PATH=\"$BIN_DIR:\$PATH\""
    ;;
esac

# ── Summary ──────────────────────────────────────────────────────────────────
hr
green "✔  Qwen Coder installation complete!"
green ""
green "  Backend : $BACKEND"
green "  Model   : $MODEL"
green "  Mode    : $APPROVAL_MODE"
green ""
green "  Run: qwen"
green "  Diagnose: qwen-omega doctor"
green "  Re-run:   ./install-qwen-coder.sh --backend $BACKEND"
hr
