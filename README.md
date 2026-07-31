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

## Installation

```bash
unzip qwen-omega-prometa-final.zip
cd qwen-omega-prometa

export OPENAI_API_KEY='sk-...'
./install.sh --provider openai
```

OpenRouter verified-free models:

```bash
export OPENROUTER_API_KEY='sk-or-v1-...'
./install.sh --provider openrouter --free
```

Ollama:

```bash
export OLLAMA_API_KEY='ollama'
./install.sh --provider ollama --default-model qwen3-coder:latest
```

Custom gateway:

```bash
export ZEAZ_API_KEY='...'
./install.sh \
  --base-url 'https://gateway.example.com/v1' \
  --env-key ZEAZ_API_KEY
```

## Generator commands

```bash
qwen-omega doctor
qwen-omega validate
qwen-omega repair

qwen-omega generate \
  --provider openrouter \
  --free \
  --include-regex 'qwen|deepseek|coder' \
  --default-model 'qwen/qwen3-coder:free'
```

Generate from an explicit model list without querying `/models`:

```bash
qwen-omega generate \
  --base-url 'http://127.0.0.1:4000/v1' \
  --env-key LITELLM_API_KEY \
  --models 'qwen3-coder,deepseek-coder,gpt-4.1'
```

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
