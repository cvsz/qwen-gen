#!/usr/bin/env bash
# qwen-gen.sh - batch wrapper for qwen-omega generate across all providers
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OMEGA="${OMEGA:-$SCRIPT_DIR/qwen-omega.py}"
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/generated-settings}"
PROVIDERS_CSV=""
PREVIEW_ONLY=false

PROVIDERS=(
  ai21
  anyscale
  azure-openai
  baichuan
  bedrock
  cerebras
  cloudflare
  cohere
  dashscope
  deepinfra
  deepseek
  featherless
  fireworks
  friendli
  github
  groq
  hunyuan
  hyperbolic
  litellm
  lmstudio
  minimax
  mistral
  moonshot
  nextchat
  novita
  nvidia
  ollama
  open_webui
  openai
  openrouter
  perplexity
  sagemaker
  sambanova
  siliconflow
  stepfun
  tgi
  together
  vllm
  xai
  yi
  zhipu
)

usage() {
  cat <<'EOF'
Usage:
  ./qwen-gen.sh [--output-dir DIR] [--providers CSV] [--dry-run] [generate flags...]

Options:
  --output-dir DIR   Write one settings file per provider into DIR
  --providers CSV    Limit generation to a comma-separated subset of providers
  --dry-run          Print the qwen-omega commands without running them
  -h, --help         Show this help

Any other flags are forwarded to:
  qwen-omega generate --provider PROVIDER --settings OUTPUT

Examples:
  ./qwen-gen.sh --free
  ./qwen-gen.sh --providers openai,openrouter --free --coder-only
  ./qwen-gen.sh --dry-run --include-regex 'coder|code'
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

join_by() {
  local IFS="$1"
  shift
  printf '%s' "$*"
}

SELECTED_PROVIDERS=()
FORWARD_ARGS=()

while (($#)); do
  case "$1" in
    --output-dir)
      [[ $# -ge 2 ]] || die "--output-dir requires a value"
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --providers)
      [[ $# -ge 2 ]] || die "--providers requires a value"
      PROVIDERS_CSV="$2"
      shift 2
      ;;
    --dry-run)
      PREVIEW_ONLY=true
      shift
      ;;
    --settings|--provider)
      die "qwen-gen.sh manages --settings and --provider itself; use --output-dir and --providers"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -n "$PROVIDERS_CSV" ]]; then
  IFS=',' read -r -a SELECTED_PROVIDERS <<<"$PROVIDERS_CSV"
else
  SELECTED_PROVIDERS=("${PROVIDERS[@]}")
fi

[[ -f "$OMEGA" ]] || die "qwen-omega not found at $OMEGA"
mkdir -p "$OUTPUT_DIR"

failures=0
for provider in "${SELECTED_PROVIDERS[@]}"; do
  provider="${provider//[[:space:]]/}"
  [[ -n "$provider" ]] || continue
  outfile="$OUTPUT_DIR/${provider}.json"
  cmd=(
    python3
    "$OMEGA"
    generate
    --provider "$provider"
    --settings "$outfile"
    "${FORWARD_ARGS[@]}"
  )
  if [[ "$PREVIEW_ONLY" == true ]]; then
    printf '%q ' "${cmd[@]}"
    printf '\n'
    continue
  fi
  printf '==> %s\n' "$provider"
  if "${cmd[@]}"; then
    printf 'OK: %s\n' "$outfile"
  else
    printf 'FAIL: %s\n' "$provider" >&2
    failures=$((failures + 1))
  fi
done

if (( failures > 0 )); then
  printf 'Completed with %d failure(s)\n' "$failures" >&2
  exit 1
fi

if [[ "$PREVIEW_ONLY" == true ]]; then
  printf 'Previewed %d provider(s)\n' "${#SELECTED_PROVIDERS[@]}"
else
  printf 'Generated %d provider settings file(s) in %s\n' "${#SELECTED_PROVIDERS[@]}" "$OUTPUT_DIR"
fi
