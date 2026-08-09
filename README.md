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

### 3 · Cloud deployment

```bash
# Build and run the same browser chat interface in a container
docker build -t qwen-gen .
docker run --rm -p 8787:8787 \
  -e QWEN_SETTINGS=/data/settings.json \
  -e QWEN_HOST=0.0.0.0 \
  -e QWEN_PORT=8787 \
  -v qwen-gen-data:/data \
  qwen-gen

# Or use Compose
docker compose up --build
```

Keep the `/data` volume attached so conversations, prompt libraries, files,
and other browser state survive restarts.

See [CLOUD.md](CLOUD.md) for the container and ingress notes.

For a ready-to-run HDD-backed launch, use `./qwen-cloud.sh`.

For the merged local-LLM stack, use `./qwen-stack.sh` and see [FULL_STACK.md](FULL_STACK.md).

To discover provider-declared free chat models and then publish only those with
current quota:

```bash
./sync-free-models.sh --timeout 20
./qwen-free.sh --settings /mnt/qwen-gen-data/settings.json \
  --env-root /home/cvsz/qwen-gen --timeout 60 \
  --litellm-config /home/cvsz/qwen-gen/litellm-config.yaml
docker compose -f docker-compose.fullstack.yml up -d --force-recreate litellm open-webui nextchat
```

The catalog sync finds declared free routes, while `qwen-free.sh` sends a real
chat probe and prunes the runtime allowlist. Media-only models are excluded,
and routes without current quota or valid credentials are not advertised.

---

### 4 · DashScope — official Alibaba Qwen API

```bash
export DASHSCOPE_API_KEY='sk-...'

# Install with flagship coder model
./install-qwen-coder.sh --backend dashscope --model qwen-coder-plus

# Turbo (faster, cheaper)
./install-qwen-coder.sh --backend dashscope --model qwen-coder-turbo
```

---

### 5 · SiliconFlow (China mainland optimized)

```bash
export SILICONFLOW_API_KEY='sk-...'
./install-qwen-coder.sh --backend siliconflow
```

---

### 6 · Any OpenAI-compatible provider

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

# NextChat / Open WebUI local gateways
qwen-omega install-coder --backend nextchat
qwen-omega install-coder --backend open_webui

# Auto-detect from local gateway URLs
NEXTCHAT_BASE_URL='http://127.0.0.1:3000/api/openai/v1' \
qwen-omega install-coder

# Local browser chat UI backed by your qwen-gen settings, with stronger first-load onboarding when models or conversations are missing, empty model selectors when no models are configured, an explicit composer no-model gate, actionable empty provider and conversation lists, transcript search, richer conversation summaries, clear-context dividers, markdown callouts, footnotes, citation markers, mention-token highlighting, read-aloud voice selection, message source chips, source preview modal, drag-and-drop and paste file upload, file registry import/export/clone, bulk file-library actions, tree/flat file browsing, file preview, multi-model compare, export, ShareGPT sharing, share-image support, conversation/agent bulk actions, and PWA install support
qwen-omega serve --settings ~/.qwen/settings.json
```

See [NEXTCHAT_OPENWEBUI_PARITY.md](NEXTCHAT_OPENWEBUI_PARITY.md) for a short scope note on what this repo does and does not model from NextChat and Open WebUI.
See [NEXTCHAT_OPENWEBUI_SOURCE_AUDIT.md](NEXTCHAT_OPENWEBUI_SOURCE_AUDIT.md) for the file-by-file upstream chat interface review notes.

---

### 7 · CI / headless environment

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

### 8 · Model filtering & discovery

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

# Batch-generate one settings file per provider
./qwen-gen.sh --free
./qwen-gen.sh --providers openai,openrouter --free --coder-only
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
qwen-omega prompts       Manage reusable prompt templates
qwen-omega skills        Manage reusable workspace skills
qwen-omega plugins       Manage reusable plugin and extension manifests
qwen-omega pipelines     Manage reusable pipeline and workflow manifests
qwen-omega filters       Manage reusable filter manifests
qwen-omega actions       Manage reusable action manifests
qwen-omega automations   Manage reusable scheduled automation manifests
qwen-omega channels      Manage reusable shared channels and timelines
qwen-omega agents        Manage reusable model presets and agent wrappers
qwen-omega tools         Manage reusable tool/MCP server registries
qwen-omega kb            Manage reusable knowledge base registries
qwen-omega snapshot      Export or restore the full qwen-gen settings tree
qwen-omega notes         Manage reusable notes
qwen-omega folders       Manage reusable conversation folders and project workspaces
qwen-omega files         Manage reusable files and attachments
qwen-omega artifacts     Manage reusable artifacts
qwen-omega conversations  Manage reusable conversation histories and shares
qwen-omega memories      Manage reusable long-term memory facts and preferences
qwen-omega webhooks      Manage reusable webhook and notification targets
qwen-omega web-search    Search the web, list providers, and optionally save results to knowledge
qwen-omega search        Search across prompts, skills, plugins, pipelines, filters, actions, automations, channels, files, agents, conversations, folders, tools, knowledge, notes, memories, webhooks, and artifacts
qwen-omega validate      Validate current settings schema
qwen-omega repair        Fix legacy modelProviders shapes
qwen-omega doctor        Inspect node/npm/qwen and validate settings
qwen-omega providers     List all 30+ provider presets
qwen-gen.sh              Batch-generate one settings file per provider
```

---

### 9 · Prompt libraries

```bash
# Add a reusable prompt template
qwen-omega prompts add \
  --name "Code Review" \
  --content "Review this diff for bugs." \
  --tag review

# Import a folder of Markdown prompt files
qwen-omega prompts import ./prompts

# Export the current prompt library
qwen-omega prompts export ./promptTemplates.json

# Clone an existing prompt template
qwen-omega prompts clone --id code-review --new-id code-review-copy --name "Code Review Copy"
```

---

### 10 · Workspace skills

```bash
# Add a reusable skill
qwen-omega skills add \
  --name "Planning" \
  --content "Help organize the work." \
  --tag workflow

# Import Markdown or JSON skills
qwen-omega skills import ./skills

# Export or share a single skill
qwen-omega skills export ./skills.json
qwen-omega skills share --id planning ./planning.md
qwen-omega skills share --id planning --format json ./planning.json

# Clone a skill
qwen-omega skills clone --id planning --new-id planning-copy --name "Planning Copy"
```

---

### 10.5 · Plugins and extensions

```bash
# Add a reusable plugin manifest
qwen-omega plugins add \
  --name "Search Booster" \
  --content "Enhance search with external APIs." \
  --tool web-search \
  --event chat.created

# Import, export, and share plugin manifests
qwen-omega plugins import ./plugins
qwen-omega plugins export ./plugins.json
qwen-omega plugins share --id search-booster ./search-booster.md
qwen-omega plugins share --id search-booster --format html ./search-booster.html

# Clone a plugin manifest
qwen-omega plugins clone --id search-booster --new-id search-booster-copy --name "Search Booster Copy"
```

---

### 10.6 · Pipelines and workflows

```bash
# Add a reusable pipeline manifest
qwen-omega pipelines add \
  --name "Moderation" \
  --content "Review content before publishing." \
  --tool web-search \
  --event chat.created

# Import, export, and share pipeline manifests
qwen-omega pipelines import ./pipelines
qwen-omega pipelines export ./pipelines.json
qwen-omega pipelines share --id moderation ./moderation.md
qwen-omega pipelines share --id moderation --format html ./moderation.html

# Clone a pipeline manifest
qwen-omega pipelines clone --id moderation --new-id moderation-copy --name "Moderation Copy"
```

---

### 10.7 · Filters and actions

```bash
# Add reusable filter and action manifests
qwen-omega filters add \
  --name "Safety Filter" \
  --content "Block unsafe outputs before delivery." \
  --event chat.created

qwen-omega actions add \
  --name "Ticket Action" \
  --content "Open an issue when a user asks for escalation." \
  --tool web-search

# Import, export, and share filter/action manifests
qwen-omega filters import ./filters
qwen-omega filters export ./filters.json
qwen-omega filters share --id safety-filter ./safety-filter.md

# Clone a filter manifest
qwen-omega filters clone --id safety-filter --new-id safety-filter-copy --name "Safety Filter Copy"

qwen-omega actions import ./actions
qwen-omega actions export ./actions.json
qwen-omega actions share --id ticket-action --format html ./ticket-action.html

# Clone an action manifest
qwen-omega actions clone --id ticket-action --new-id ticket-action-copy --name "Ticket Action Copy"
```

---

### 10.8 · Automations

```bash
# Add a scheduled automation
qwen-omega automations add \
  --name "Daily Summary" \
  --content "Summarize the last 24 hours of work." \
  --schedule "0 9 * * *" \
  --timezone "UTC" \
  --model qwen3-coder:latest

# Import, export, and share automation manifests
qwen-omega automations import ./automations
qwen-omega automations export ./automations.json
qwen-omega automations share --id daily-summary ./daily-summary.md
qwen-omega automations share --id daily-summary --format html ./daily-summary.html

# Clone an automation
qwen-omega automations clone --id daily-summary --new-id daily-summary-copy --name "Daily Summary Copy"
```

---

### 10.9 · Channels

```bash
# Add a shared channel timeline
qwen-omega channels add \
  --title "Team Updates" \
  --message "system: Keep updates short." \
  --message "assistant: Daily status goes here." \
  --tag team

# Import, export, and share channel timelines
qwen-omega channels import ./channels
qwen-omega channels export ./channels.json
qwen-omega channels share --id team-updates ./team-updates.md
qwen-omega channels share --id team-updates --format html ./team-updates.html
qwen-omega channels clone --id team-updates --new-id team-updates-copy ./channels.json
```

---

### 11 · Tool registries

```bash
# Add a reusable MCP/tool server definition
qwen-omega tools add \
  --name Search \
  --endpoint http://127.0.0.1:3001/mcp \
  --type mcp \
  --tag search

# Import a JSON registry
qwen-omega tools import ./toolServers.json

# Export the current registry
qwen-omega tools export ./toolServers.json

# Clone a tool/MCP server
qwen-omega tools clone --id search --new-id search-copy --name "Search Copy"
```

---

### 12 · Agent presets

```bash
# Add a reusable agent preset
qwen-omega agents add \
  --name "Mentor" \
  --base-model qwen3-coder:latest \
  --system-prompt "Help with release planning and code review." \
  --tool search \
  --knowledge docs \
  --skill planning \
  --param temperature=0.2

# Import or export agent presets
qwen-omega agents import ./agents
qwen-omega agents export ./agents.json

# Share one agent as Markdown or JSON
qwen-omega agents share --id mentor ./mentor.md
qwen-omega agents share --id mentor --format json ./mentor.json

# Clone an existing agent preset
qwen-omega agents clone --settings ./agents.json --id mentor --name "Mentor Copy"
```

The browser agent manager also supports import/export/share/clone for saved presets.

---

### 13 · Files and attachments

```bash
# Add a reusable file record
qwen-omega files add \
  --name "Handoff" \
  --content "This is the handoff file." \
  --kind markdown \
  --description "Project handoff notes."

# Import a folder of attachments or a JSON manifest
qwen-omega files import ./files
qwen-omega files export ./files.json

# Share one file as Markdown, HTML, or JSON
qwen-omega files share --id handoff ./handoff.md
qwen-omega files share --id handoff --format html ./handoff.html
qwen-omega files share --id handoff --format json ./handoff.json

# Clone a file record
qwen-omega files clone --id handoff --new-id handoff-copy --name "Handoff Copy"
```

The browser file registry also supports import/export/share/clone for saved file records.

---

### 14 · Knowledge bases

```bash
# Add a knowledge base registry entry
qwen-omega kb add \
  --name "Product Docs" \
  --source-dir /tmp/docs \
  --tag docs

# Import a JSON manifest
qwen-omega kb import ./knowledgeBases.json

# Ingest web pages into a knowledge index
qwen-omega kb ingest-url --base-id web-release https://example.com/release ./kb-web-index.json

# Refresh an existing registered base after source changes
qwen-omega kb refresh --base-id docs ./kb-index.json

# Refresh all registered knowledge bases and export rebuilt indexes
qwen-omega kb sync ./kb-sync-out

# Continuously refresh registered knowledge bases
qwen-omega kb watch --iterations 5 ./kb-sync-out

# Export or restore the full settings tree
qwen-omega snapshot export ./qwen-snapshot.json
qwen-omega snapshot import ./qwen-snapshot.json
qwen-omega snapshot sync ./qwen-snapshot.json
qwen-omega snapshot sync --mode push ./qwen-snapshot.json
qwen-omega snapshot sync --mode pull ./qwen-snapshot.json
qwen-omega snapshot watch --iterations 5 ./qwen-snapshot.json

# Export the current registry
qwen-omega kb export ./knowledgeBases.json
qwen-omega kb ingest ./docs ./kb-index.json

# Clone an existing knowledge base
qwen-omega kb clone --id docs --new-id docs-copy --name "Docs Copy"

# Query an ingested index for relevant chunks
qwen-omega kb query --settings ./settings.json release

# The browser KB panel also supports create/edit/delete/refresh/query plus import/export/sync/watch
# for registered knowledge bases and indexes.

# Search the web and save result pages to knowledge
qwen-omega web-search --list-providers
qwen-omega web-search --provider duckduckgo \
  --save-to-knowledge --base-id release-search release ./release-search-index.json

# Use a provider-aware JSON search API
export QWEN_EXTERNAL_SEARCH_ALLOWED_HOSTS=search.example.com
qwen-omega web-search --provider external \
  --engine-url 'https://search.example.com/search' \
  --save-to-knowledge --base-id release-search release ./release-search-index.json

# Merge results across fallback providers
qwen-omega web-search --provider external \
  --fallback-provider brave \
  --engine-url 'https://search.example.com/search' \
  release
```

Remote web retrieval accepts only HTTP(S) URLs that resolve to public IP
addresses; loopback, private, link-local, reserved, credential-bearing, and
unsafe redirect targets are rejected. An external search endpoint that receives
an API key must be listed in `QWEN_EXTERNAL_SEARCH_ALLOWED_HOSTS`. Browser API
sync/watch requests never choose an arbitrary filesystem destination: exports
are written beneath `<settings-directory>/knowledge-exports`. Webhook share and
dry-run output omits secret values.

---

### 15 · Notes and artifacts

```bash
# Add a note
qwen-omega notes add \
  --title "Review" \
  --body "Check the diff for regressions." \
  --file handoff \
  --image preview.png \
  --tag review

# Share a note as Markdown or HTML
qwen-omega notes share --id review ./review.md
qwen-omega notes share --id review --format html ./review.html

# Clone a note record
qwen-omega notes clone --id review --new-id review-copy --title "Review Copy"

# Add an artifact
qwen-omega artifacts add \
  --title "Release Notes" \
  --content "Release notes content." \
  --kind markdown

# Share an artifact as Markdown, HTML, or JSON
qwen-omega artifacts share --id release-notes ./release-notes.md
qwen-omega artifacts share --id release-notes --format html ./release-notes.html
qwen-omega artifacts share --id release-notes --format json ./release-notes.json

# Clone an artifact record
qwen-omega artifacts clone --id release-notes --new-id release-notes-copy --title "Release Notes Copy"

# Add a memory or a webhook target
qwen-omega memories add \
  --title "Preferences" \
  --content "Prefer concise answers." \
  --scope user

# Clone a memory
qwen-omega memories clone --id preferences --new-id preferences-copy --title "Preferences Copy"

qwen-omega webhooks add \
  --name "Ops Alerts" \
  --url "http://127.0.0.1:9000/webhook" \
  --event chat.created

# Clone a webhook target
qwen-omega webhooks clone --id ops-alerts --new-id ops-alerts-copy --name "Ops Alerts Copy"

# Add a folder and file a conversation into it
qwen-omega folders add \
  --name "Project Alpha" \
  --system-prompt "Be concise and project-aware."

# Clone a folder workspace
qwen-omega folders clone --id project-alpha --new-id project-alpha-copy --name "Project Alpha Copy"

qwen-omega conversations add \
  --title "Alpha Chat" \
  --folder project-alpha \
  --file handoff \
  --image cover.png \
  --transcript "assistant: Working in a project folder."

# Import or export either registry with JSON or Markdown inputs
qwen-omega notes import ./notes
qwen-omega artifacts import ./artifacts.json

# Clone a conversation session or shared channel
qwen-omega conversations clone --id planning --new-id planning-copy ./conversations.json
qwen-omega channels clone --id team-updates --new-id team-updates-copy ./channels.json
```

---

### 16 · Unified search

```bash
# Search all registries
qwen-omega search review

# Restrict search to one registry
qwen-omega search --kind notes release
qwen-omega search --kind artifacts diagram
```

---

### 17 · Conversation histories

```bash
# Add a transcript
qwen-omega conversations add \
  --title "Planning" \
  --transcript "assistant: We should ship on Friday.\nuser: Agreed." \
  --tag planning

# Import Markdown or JSON transcripts
qwen-omega conversations import ./transcripts

# Export saved conversations
qwen-omega conversations export ./conversations.json

# Share a single conversation as Markdown or HTML
qwen-omega conversations share --id planning ./planning.md
qwen-omega conversations share --id planning --format html ./planning.html
```

The browser conversation manager also supports import/export/share/clone for saved transcripts.

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
      "selectedType": "openai",
      "adminEmails": [
        "cvsitem@gmail.com",
        "seaza@msn.com",
        "sea@zeaz.dev"
      ]
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
