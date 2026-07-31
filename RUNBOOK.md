# Qwen Omega ProMeta — Operational Runbook

Comprehensive operational guide for maintaining, troubleshooting, testing, and deploying **Qwen Omega ProMeta** (`qwen-gen`).

---

## Table of Contents

1. [Overview & Architecture](#1-overview--architecture)
2. [CLI Quick Reference](#2-cli-quick-reference)
3. [Local Development & Testing](#3-local-development--testing)
4. [Environment Setup (`.env`)](#4-environment-setup-env)
5. [GitHub Actions CI/CD Operations](#5-github-actions-cicd-operations)
6. [Release & Packaging Guide](#6-release--packaging-guide)
7. [Troubleshooting & FAQs](#7-troubleshooting--faqs)

---

## 1. Overview & Architecture

**Qwen Omega ProMeta** generates and validates configuration files (`settings.json`) for Qwen Code and OpenAI-compatible LLM tools.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Qwen Omega ProMeta                              │
│                                                                             │
│  ┌───────────────────────┐   ┌───────────────────┐   ┌──────────────────┐  │
│  │   qwen_omega.py       │   │  install.sh       │   │ install-qwen-    │  │
│  │  (Canonical Module)   │   │ (Generic Installer│   │  coder.sh        │  │
│  └───────────┬───────────┘   └─────────┬─────────┘   └────────┬─────────┘  │
│              │                         │                      │            │
│              ▼                         ▼                      ▼            │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        ~/.qwen/settings.json                          │  │
│  │                        (v4 Schema, Mode 0600)                         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Core Module**: `qwen_omega.py` (pure Python stdlib, zero third-party runtime dependencies).
- **Backward-Compat Shim**: `qwen-omega.py` (delegates directly to `qwen_omega`).
- **One-Shot Installer**: `install-qwen-coder.sh` (auto-detects hardware/backends and sets up Qwen Coder).

---

## 2. CLI Quick Reference

```bash
# 1. High-level Qwen Coder setup (auto-detects backend & hardware)
qwen-omega install-coder

# 2. Force specific backends
qwen-omega install-coder --backend ollama
qwen-omega install-coder --backend openrouter --free
qwen-omega install-coder --backend dashscope
qwen-omega install-coder --backend litellm
qwen-omega install-coder --backend lmstudio
qwen-omega install-coder --backend nextchat
qwen-omega install-coder --backend open_webui

# 3. Dry-run (preview generated JSON without writing to disk)
qwen-omega install-coder --backend ollama --dry-run
qwen-omega generate --provider openrouter --free --dry-run

# 4. Diagnostics & Repair
qwen-omega doctor      # Inspect node/npm/qwen installation & validate settings
qwen-omega validate    # Check current settings.json schema validity
qwen-omega repair      # Repair legacy modelProviders shapes
qwen-omega providers   # List all 30+ supported provider presets
```

---

## 3. Local Development & Testing

### Running Tests

```bash
# Run unit tests via pytest
python3 -m pytest test_qwen_omega.py -v

# Run linters and formatting checks
ruff check qwen_omega.py install-qwen-coder.sh --select E,W,F,I
ruff format --check qwen_omega.py qwen-omega.py test_qwen_omega.py
shellcheck install.sh install-qwen-coder.sh uninstall.sh
```

### Auto-Formatting Code

```bash
ruff format qwen_omega.py qwen-omega.py test_qwen_omega.py
```

---

## 4. Environment Setup (`.env`)

For local testing against live provider APIs, create a `.env` file in the project root:

```bash
# Copy template or populate .env
cat <<'EOF' > .env
OPENAI_API_KEY="sk-proj-..."
OPENROUTER_API_KEY="sk-or-v1-..."
DASHSCOPE_API_KEY="sk-..."
DEEPSEEK_API_KEY="sk-..."
GROQ_API_KEY="gsk_..."
EOF

# Export variables into shell session
set -a && source .env && set +a
```

---

## 5. GitHub Actions CI/CD Operations

### Synchronizing Repository Secrets & Variables

Use `gh` CLI to sync local `.env` variables and secrets to GitHub:

```bash
# Sync secrets
set -a && source .env && set +a
gh secret set OPENAI_API_KEY --body "$OPENAI_API_KEY" --repo cvsz/qwen-gen
gh secret set OPENROUTER_API_KEY --body "$OPENROUTER_API_KEY" --repo cvsz/qwen-gen
gh secret set DASHSCOPE_API_KEY --body "$DASHSCOPE_API_KEY" --repo cvsz/qwen-gen

# Enable live integration testing in CI
gh variable set ENABLE_LIVE_TESTS --body "true" --repo cvsz/qwen-gen
```

---

## 6. Release & Packaging Guide

### Building Packages Locally

```bash
# 1. Clean previous build artifacts
rm -rf dist build *.egg-info

# 2. Build Python wheel and source distribution (sdist)
python3 -m build --wheel --sdist

# 3. Build standalone zero-install single-file executable (zipapp)
python3 -m zipapp qwen_omega.py \
  --output dist/qwen-omega \
  --python '/usr/bin/env python3' \
  --compress

# 4. Generate SHA256 checksums
cd dist && sha256sum * > SHA256SUMS && cat SHA256SUMS
```

### Triggering an Automated GitHub Release

```bash
# 1. Update VERSION in qwen_omega.py and pyproject.toml
# 2. Add entry to CHANGELOG.md
# 3. Commit and tag release
git commit -am "bump version to v1.2.0"
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin main --tags
```

---

## 7. Troubleshooting & FAQs

### Problem: `ERROR: environment variable DASHSCOPE_API_KEY is unset`
- **Cause**: Selected backend requires an API key that is not present in the environment.
- **Fix**: Export the requested API key (`export DASHSCOPE_API_KEY="sk-..."`) or use a local backend (`--backend ollama`).

### Problem: `existingModels.filter is not a function` in Qwen Code
- **Cause**: Corrupted legacy `settings.json` where `modelProviders.<protocol>` was written as an object instead of an array.
- **Fix**: Run `qwen-omega repair` to convert legacy shapes to `$version: 4` array syntax.

### Problem: CI pipeline failing on `ruff format`
- **Fix**: Run `ruff format qwen_omega.py qwen-omega.py test_qwen_omega.py` locally and commit the formatted files.
