# Qwen Omega ProMeta

Production-oriented Qwen Code configuration generator and automated installer.

## Safety and schema guarantees

- Generates Qwen Code settings schema `$version: 4`.
- Writes `modelProviders.<protocol>` as an array, preventing `existingModels.filter is not a function`.
- Never stores API key values in `settings.json`; model entries use `envKey`.
- Creates timestamped backups before replacing settings.
- Writes configuration atomically with mode `0600`.
- `--free` accepts only explicit `:free`, `openrouter/free`, or zero-pricing metadata.
- Repairs legacy comma-separated and wrapped `{protocol,models}` provider shapes.

---

## Installation

### Quick start — Qwen Coder (recommended)

#### Option A: Install via pip / PyPI

```bash
pip install qwen-omega-prometa

# Run anywhere
qwen-omega install-coder
```

#### Option B: Standalone zero-install executable

```bash
# Download compressed single-file executable from latest release
curl -fsSL https://github.com/cvsz/qwen-gen/releases/latest/download/qwen-omega -o qwen-omega
chmod +x qwen-omega

./qwen-omega install-coder
```

#### Option C: Shell script / source repo

```bash
git clone https://github.com/cvsz/qwen-gen && cd qwen-gen

# Fully local — Ollama auto-selected, model size matched to your RAM
./install-qwen-coder.sh

# Free cloud tier — no credit card needed
export OPENROUTER_API_KEY='sk-or-v1-...'
./install-qwen-coder.sh --backend openrouter --free

# Alibaba DashScope (official Qwen API)
export DASHSCOPE_API_KEY='sk-...'
./install-qwen-coder.sh --backend dashscope --model qwen-coder-plus

# Preview before writing anything
./install-qwen-coder.sh --dry-run
```

Or via the generator directly:

```bash
# Equivalent using qwen-omega install-coder subcommand
qwen-omega install-coder                                        # auto-detect
qwen-omega install-coder --backend ollama                       # force local
qwen-omega install-coder --backend openrouter --free --dry-run  # preview
```

---

## Suggested workflows

### 1 · Local coding assistant (Ollama, zero cost)

```bash
# Install Ollama: https://ollama.com/download
./install-qwen-coder.sh --backend ollama

# Override auto-selected model
./install-qwen-coder.sh --backend ollama --model qwen2.5-coder:7b-instruct-q4_K_M

# Use yolo mode inside Qwen Code (auto-approve file edits)
./install-qwen-coder.sh --backend ollama --approval-mode yolo
```

> Model auto-selection by available RAM:
> | RAM | Model |
> |-----|-------|
> | ≥ 40 GB | qwen2.5-coder:32b-instruct-q4_K_M |
> | ≥ 20 GB | qwen2.5-coder:14b-instruct-q4_K_M |
> | ≥ 10 GB | qwen2.5-coder:7b-instruct-q4_K_M |
> | ≥ 5 GB  | qwen2.5-coder:3b-instruct-q4_K_M |
> | < 5 GB  | qwen2.5-coder:1.5b-instruct-q4_K_M |

---

### 2 · Free cloud tier (OpenRouter `:free`)

```bash
export OPENROUTER_API_KEY='sk-or-v1-...'

# Coder models only, zero-cost, auto-write settings
./install-qwen-coder.sh --backend openrouter --free

# Or with the generic installer (all free models across all families)
./install.sh --provider openrouter --free
```

---

### 3 · DashScope — official Alibaba Qwen API

```bash
export DASHSCOPE_API_KEY='sk-...'

# Install with flagship coder model
./install-qwen-coder.sh --backend dashscope --model qwen-coder-plus

# Turbo (faster, cheaper)
./install-qwen-coder.sh --backend dashscope --model qwen-coder-turbo
```

---

### 4 · SiliconFlow (China mainland optimized)

```bash
export SILICONFLOW_API_KEY='sk-...'
./install-qwen-coder.sh --backend siliconflow
```

---

### 5 · Any OpenAI-compatible provider

```bash
# Custom vLLM / LM Studio / LiteLLM gateway
export MY_API_KEY='...'
./install.sh \
  --base-url 'http://127.0.0.1:8000/v1' \
  --env-key MY_API_KEY \
  --default-model qwen2.5-coder-32b-instruct

# Explicit model list — skips live /models discovery
qwen-omega generate \
  --base-url 'http://127.0.0.1:4000/v1' \
  --env-key LITELLM_API_KEY \
  --models 'qwen3-coder,qwen2.5-coder-32b-instruct,deepseek-coder'
```

---

### 6 · CI / headless environment

```bash
# Non-interactive, errors instead of prompts
NON_INTERACTIVE=true \
OPENROUTER_API_KEY="$SECRET_KEY" \
./install-qwen-coder.sh --backend openrouter --free

# Or via environment variables only
PROVIDER=dashscope \
DASHSCOPE_API_KEY="$KEY" \
DEFAULT_MODEL=qwen-coder-plus \
APPROVAL_MODE=auto-edit \
./install.sh
```

---

### 7 · Model filtering & discovery

```bash
# List all provider presets
qwen-omega providers
qwen-omega providers --query qwen

# Discover models, show coder-only, minimum 32k context
qwen-omega generate \
  --provider openrouter \
  --coder-only \
  --min-context 32768 \
  --dry-run

# Filter by regex
qwen-omega generate \
  --provider openrouter \
  --filter-model 'qwen.*coder' \
  --exclude-regex 'instruct-vl' \
  --limit 10 \
  --dry-run
```

---

### 8 · Repair / maintenance

```bash
# Diagnose installation
qwen-omega doctor

# Validate current settings.json
qwen-omega validate

# Repair legacy schema (comma-string or wrapped providers)
qwen-omega repair
qwen-omega repair --dry-run   # preview changes without writing
```

---

## How to Get API Provider Keys

| Provider | Environment Variable | Sign-Up / API Key Portal | Notes / Free Tier |
|---|---|---|---|
| **Alibaba DashScope (Qwen)** | `DASHSCOPE_API_KEY` | [dashscope.aliyun.com](https://dashscope.aliyun.com) | Official Qwen provider |
| **OpenRouter** | `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) | Free `:free` models available |
| **OpenAI** | `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Official GPT models |
| **DeepSeek** | `DEEPSEEK_API_KEY` | [platform.deepseek.com](https://platform.deepseek.com) | DeepSeek Coder models |
| **SiliconFlow** | `SILICONFLOW_API_KEY` | [siliconflow.cn](https://siliconflow.cn) | Fast inference in Asia |
| **Groq** | `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | Ultra-fast LPU inference |
| **Fireworks AI** | `FIREWORKS_API_KEY` | [fireworks.ai/api-keys](https://fireworks.ai/api-keys) | High-performance open models |
| **Together AI** | `TOGETHER_API_KEY` | [api.together.xyz](https://api.together.xyz) | Open-source model suite |
| **NVIDIA NIM** | `NVIDIA_API_KEY` | [build.nvidia.com](https://build.nvidia.com) | Free trial credits |
| **Anthropic** | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Claude models |
| **Mistral AI** | `MISTRAL_API_KEY` | [console.mistral.ai](https://console.mistral.ai) | Codestral & Mistral models |
| **Cerebras** | `CEREBRAS_API_KEY` | [cloud.cerebras.ai](https://cloud.cerebras.ai) | Ultra-fast CS-3 inference |
| **Moonshot (Kimi)** | `MOONSHOT_API_KEY` | [platform.moonshot.cn](https://platform.moonshot.cn) | Kimi long-context models |
| **Novita AI** | `NOVITA_API_KEY` | [novita.ai](https://novita.ai) | Pay-as-you-go open models |
| **SambaNova** | `SAMBANOVA_API_KEY` | [cloud.sambanova.ai](https://cloud.sambanova.ai) | SN40L engine speed |

---

## Generator commands reference

```
qwen-omega generate      Discover models and write settings.json
qwen-omega install-coder One-shot Qwen Coder setup (backend auto-detect)
qwen-omega validate      Validate current settings schema
qwen-omega repair        Fix legacy modelProviders shapes
qwen-omega doctor        Inspect node/npm/qwen and validate settings
qwen-omega providers     List all 30+ provider presets
```

---

## Output structure

```json
{
  "$version": 4,
  "modelProviders": {
    "openai": [
      {
        "id": "model-id",
        "name": "model id",
        "baseUrl": "https://provider.example/v1",
        "envKey": "PROVIDER_API_KEY",
        "generationConfig": {
          "timeout": 120000,
          "maxRetries": 3
        }
      }
    ]
  },
  "security": {
    "auth": {
      "selectedType": "openai"
    }
  },
  "model": {
    "name": "model-id",
    "maxSessionTurns": -1
  },
  "tools": {
    "approvalMode": "default"
  }
}
```

Use `/model` inside Qwen Code to switch models and `/doctor` to inspect authentication.
