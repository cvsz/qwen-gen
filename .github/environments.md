# GitHub Environments, Secrets & Variables

Setup guide for `cvsz/qwen-gen` CI/CD configuration.

## Quick Setup (GitHub CLI)

```bash
# Install gh CLI if needed: https://cli.github.com
gh auth login

# Run the bootstrap script
bash .github/scripts/setup-github-env.sh
```

Or configure manually via **Settings → Secrets and variables → Actions** on GitHub.

---

## Environments

| Environment | Purpose | Protection |
|-------------|---------|------------|
| `staging`   | Live provider tests on every push to `main` | None (auto-deploys) |
| `production`| Release builds (`v*.*.*` tags) | Required reviewers + wait timer |

### Create environments via CLI

```bash
# staging – no protection rules
gh api repos/cvsz/qwen-gen/environments/staging -X PUT \
  --field wait_timer=0

# production – requires manual approval before release
gh api repos/cvsz/qwen-gen/environments/production -X PUT \
  --field wait_timer=5 \
  --field reviewers='[{"type":"User","id":<YOUR_GITHUB_USER_ID>}]' \
  --field deployment_branch_policy='{"protected_branches":false,"custom_branch_policies":true}'
```

---

## Repository Variables (`vars.*`)

Set at **Settings → Secrets and variables → Actions → Variables**.

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHON_VERSION` | `3.12` | Python version used in CI |
| `DEFAULT_MODEL` | `qwen3-coder:latest` | Default model for dry-run tests |
| `DASHSCOPE_DEFAULT_MODEL` | `qwen-coder-turbo-latest` | DashScope default |
| `ENABLE_LIVE_TESTS` | `false` | Set `true` to run live provider integration tests |
| `RELEASE_DRAFT` | `false` | Set `true` to create releases as drafts |

### Set via CLI

```bash
gh variable set PYTHON_VERSION       --body "3.12"                     --repo cvsz/qwen-gen
gh variable set DEFAULT_MODEL        --body "qwen3-coder:latest"       --repo cvsz/qwen-gen
gh variable set DASHSCOPE_DEFAULT_MODEL --body "qwen-coder-turbo-latest" --repo cvsz/qwen-gen
gh variable set ENABLE_LIVE_TESTS    --body "false"                    --repo cvsz/qwen-gen
gh variable set RELEASE_DRAFT        --body "false"                    --repo cvsz/qwen-gen
```

---

## Repository Secrets (`secrets.*`)

Set at **Settings → Secrets and variables → Actions → Secrets**.
**Never commit actual key values.**

### Provider API Keys

| Secret | Provider | Where to get it |
|--------|----------|-----------------|
| `OPENAI_API_KEY` | OpenAI | https://platform.openai.com/api-keys |
| `OPENROUTER_API_KEY` | OpenRouter | https://openrouter.ai/keys |
| `DASHSCOPE_API_KEY` | Alibaba DashScope | https://dashscope.aliyun.com |
| `SILICONFLOW_API_KEY` | SiliconFlow | https://siliconflow.cn |
| `DEEPSEEK_API_KEY` | DeepSeek | https://platform.deepseek.com |
| `GROQ_API_KEY` | Groq | https://console.groq.com/keys |
| `TOGETHER_API_KEY` | Together AI | https://api.together.xyz/settings/api-keys |
| `FIREWORKS_API_KEY` | Fireworks AI | https://fireworks.ai/api-keys |
| `MISTRAL_API_KEY` | Mistral | https://console.mistral.ai/api-keys |
| `NVIDIA_API_KEY` | NVIDIA NIM | https://build.nvidia.com |
| `ANTHROPIC_API_KEY` | Anthropic | https://console.anthropic.com |
| `COHERE_API_KEY` | Cohere | https://dashboard.cohere.com/api-keys |
| `XAI_API_KEY` | xAI (Grok) | https://console.x.ai |
| `CEREBRAS_API_KEY` | Cerebras | https://cloud.cerebras.ai |
| `HYPERBOLIC_API_KEY` | Hyperbolic | https://app.hyperbolic.xyz/settings |
| `NOVITA_API_KEY` | Novita AI | https://novita.ai/settings |
| `FEATHERLESS_API_KEY` | Featherless | https://featherless.ai |
| `DEEPINFRA_API_KEY` | DeepInfra | https://deepinfra.com/dash |
| `SAMBANOVA_API_KEY` | SambaNova | https://cloud.sambanova.ai |
| `PERPLEXITY_API_KEY` | Perplexity | https://www.perplexity.ai/settings/api |

### Set via CLI (example)

```bash
# Replace <your-key> with your actual key
gh secret set OPENROUTER_API_KEY  --body "<your-key>"  --repo cvsz/qwen-gen
gh secret set DASHSCOPE_API_KEY   --body "<your-key>"  --repo cvsz/qwen-gen
gh secret set DEEPSEEK_API_KEY    --body "<your-key>"  --repo cvsz/qwen-gen
# ... repeat for other providers
```

### Environment-scoped secrets (staging/production)

```bash
# Staging: safe test keys (rate-limited / free-tier)
gh secret set OPENROUTER_API_KEY --body "<staging-key>" \
  --env staging --repo cvsz/qwen-gen

# Production: production keys (used only during releases)
gh secret set OPENROUTER_API_KEY --body "<prod-key>" \
  --env production --repo cvsz/qwen-gen
```

---

## How secrets/variables flow into workflows

```
┌─────────────────────────────────────────────────────────────┐
│  GitHub Repo Settings                                        │
│  ┌──────────────────┐   ┌──────────────────────────────┐   │
│  │  Variables        │   │  Secrets                     │   │
│  │  PYTHON_VERSION   │   │  OPENROUTER_API_KEY          │   │
│  │  DEFAULT_MODEL    │   │  DASHSCOPE_API_KEY           │   │
│  │  ENABLE_LIVE_TEST │   │  DEEPSEEK_API_KEY  ...       │   │
│  └────────┬─────────┘   └──────────────┬───────────────┘   │
└───────────┼──────────────────────────── ┼───────────────────┘
            │ vars.*                       │ secrets.*
            ▼                             ▼
┌────────────────────────────────────────────────────────────┐
│  Workflows                                                  │
│  ci.yml              – unit tests, lint, shellcheck        │
│  integration-test.yml – dry-run + live tests (staging env) │
│  release.yml         – creates GitHub Release (prod env)   │
└────────────────────────────────────────────────────────────┘
```
