#!/usr/bin/env sh
set -eu

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

SETTINGS_PATH="${QWEN_SETTINGS:-/data/settings.json}"
HOST="${QWEN_HOST:-0.0.0.0}"
PORT="${QWEN_PORT:-${PORT:-8787}}"

configure_litellm_defaults() {
  [ "${QWEN_AUTO_CONFIGURE:-1}" = "0" ] && return 0
  [ "${QWEN_PROVIDER:-litellm}" = "litellm" ] || return 0

  local base_url="${LITELLM_BASE_URL:-}"
  local model="${QWEN_DEFAULT_MODEL:-qwen2.5-coder}"
  local retries="${QWEN_CONFIGURE_RETRIES:-30}"
  local attempt=1

  [ -n "$base_url" ] || return 0
  [ -n "${LITELLM_API_KEY:-}" ] || return 0

  if [ "${QWEN_AUTO_CONFIGURE_FORCE:-0}" != "1" ] && [ -s "$SETTINGS_PATH" ] \
    && grep -Fq '"modelProviders"' "$SETTINGS_PATH" \
    && grep -Fq '"id"' "$SETTINGS_PATH"; then
    return 0
  fi

  while ! qwen-omega generate \
    --settings "$SETTINGS_PATH" \
    --provider litellm \
    --base-url "$base_url" \
    --env-key LITELLM_API_KEY \
    --models "$model" \
    --default-model "$model" \
    --no-backup; do
    if [ "$attempt" -ge "$retries" ]; then
      echo "ERROR: unable to configure qwen-gen for LiteLLM after ${retries} attempts" >&2
      return 1
    fi
    echo "Waiting for LiteLLM at ${base_url} (attempt ${attempt}/${retries})..." >&2
    attempt=$((attempt + 1))
    sleep 2
  done
}

configure_litellm_defaults

exec qwen-omega serve --settings "$SETTINGS_PATH" --host "$HOST" --port "$PORT"
