#!/usr/bin/env bash
# .github/scripts/setup-github-env.sh
#
# Bootstrap GitHub Environments, Variables, and Secrets for cvsz/qwen-gen.
# Requires:  gh CLI (https://cli.github.com)  +  gh auth login
#
# Usage:
#   bash .github/scripts/setup-github-env.sh
#
set -euo pipefail

REPO="cvsz/qwen-gen"

# ── Colour helpers ────────────────────────────────────────────────────────────
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
blue()   { printf '\033[34m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*"; }

hr() { printf '%.0s─' {1..72}; printf '\n'; }

# ── Pre-flight ────────────────────────────────────────────────────────────────
if ! command -v gh >/dev/null 2>&1; then
  red "ERROR: gh CLI not found. Install from https://cli.github.com"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  red "ERROR: Not authenticated. Run: gh auth login"
  exit 1
fi

hr
blue "  qwen-gen GitHub Environment Bootstrap"
hr

# ── 1. Create Environments ────────────────────────────────────────────────────
blue "1/3  Creating environments…"

# staging – no wait, no required reviewers
gh api "repos/${REPO}/environments/staging" -X PUT \
  --silent --field wait_timer=0 || true
green "     ✔ staging"

# production – 5-min wait timer
gh api "repos/${REPO}/environments/production" -X PUT \
  --silent --field wait_timer=5 || true
green "     ✔ production"

# ── 2. Repository Variables ───────────────────────────────────────────────────
blue "2/3  Setting repository variables…"

set_var() {
  gh variable set "$1" --body "$2" --repo "$REPO" 2>/dev/null && \
    green "     ✔ $1 = $2" || yellow "     ~ $1 already set (skipped)"
}

set_var PYTHON_VERSION            "3.12"
set_var DEFAULT_MODEL             "qwen3-coder:latest"
set_var DASHSCOPE_DEFAULT_MODEL   "qwen-coder-turbo-latest"
set_var ENABLE_LIVE_TESTS         "false"
set_var RELEASE_DRAFT             "false"

# ── 3. Secrets (placeholder prompt) ──────────────────────────────────────────
blue "3/3  Secrets…"
cat <<'EOF'

  Secrets are NOT set automatically (never store keys in scripts).
  Run the commands below for each provider you want to use:

  ┌─ Repository-level secrets ──────────────────────────────────────────────┐
  │  gh secret set OPENROUTER_API_KEY   --repo cvsz/qwen-gen               │
  │  gh secret set DASHSCOPE_API_KEY    --repo cvsz/qwen-gen               │
  │  gh secret set DEEPSEEK_API_KEY     --repo cvsz/qwen-gen               │
  │  gh secret set OPENAI_API_KEY       --repo cvsz/qwen-gen               │
  │  gh secret set GROQ_API_KEY         --repo cvsz/qwen-gen               │
  │  gh secret set TOGETHER_API_KEY     --repo cvsz/qwen-gen               │
  │  gh secret set FIREWORKS_API_KEY    --repo cvsz/qwen-gen               │
  │  gh secret set MISTRAL_API_KEY      --repo cvsz/qwen-gen               │
  │  gh secret set SILICONFLOW_API_KEY  --repo cvsz/qwen-gen               │
  │  gh secret set NOVITA_API_KEY       --repo cvsz/qwen-gen               │
  │  gh secret set XAI_API_KEY          --repo cvsz/qwen-gen               │
  │  gh secret set CEREBRAS_API_KEY     --repo cvsz/qwen-gen               │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─ Environment-scoped secrets (optional, overrides repo-level) ───────────┐
  │  gh secret set OPENROUTER_API_KEY --env staging     --repo cvsz/qwen-gen│
  │  gh secret set OPENROUTER_API_KEY --env production  --repo cvsz/qwen-gen│
  └─────────────────────────────────────────────────────────────────────────┘

  To enable live integration tests after adding secrets:
    gh variable set ENABLE_LIVE_TESTS --body "true" --repo cvsz/qwen-gen

EOF

hr
green "  Bootstrap complete!"
green "  View at: https://github.com/${REPO}/settings/secrets/actions"
hr
