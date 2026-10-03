# Cloud Deployment

This repository can run as the same browser chat interface on a cloud host.
The cloud shape is simple:

- the app binds to `0.0.0.0`
- settings live on a writable volume
- the browser UI is served from the same `qwen-omega serve` entrypoint
- model access comes from the provider keys you inject into the container
- the full-stack helper uses the host Ollama at `127.0.0.1:11434`

## Docker

```bash
docker build -t qwen-gen .
docker run --rm -p 8787:8787 \
  -e QWEN_SETTINGS=/data/settings.json \
  -e QWEN_HOST=0.0.0.0 \
  -e QWEN_PORT=8787 \
  -v qwen-gen-data:/data \
  qwen-gen
```

Open the UI at:

- `http://localhost:8787/ai.html`
- `http://localhost:8787/`

For the default HDD-backed launch on `/mnt/qwen-gen-data`, use `./qwen-cloud.sh`.

The live `qwen.zeaz.dev` deployment on this host runs the full stack helper with
qwen-gen published on port `8091` to match the existing Cloudflare Tunnel
ingress. This keeps the public qwen-gen UI on the same LiteLLM gateway as the
other browser clients.

## Docker Compose

```bash
docker compose up --build
```

For the merged local-LLM stack with Ollama, LiteLLM, Open WebUI, NextChat, and
qwen-gen, use:

```bash
./qwen-stack.sh
```

Use `./qwen-stack.sh --detach` for a background launch.

To rebuild the persisted model list from `.env.ai` and keep only models that
answer a real chat probe, run:

```bash
./qwen-free.sh --settings /mnt/qwen-gen-data/settings.json \
  --env-root /home/cvsz/qwen-gen --timeout 60 \
  --litellm-config /home/cvsz/qwen-gen/litellm-config.yaml
```

To inspect every provider-declared free chat model, run the catalog sync. It
does not prove current quota, so run the real probe above before publishing:

```bash
./sync-free-models.sh --timeout 20
./qwen-free.sh --settings /mnt/qwen-gen-data/settings.json \
  --env-root /home/cvsz/qwen-gen --timeout 60 \
  --litellm-config /home/cvsz/qwen-gen/litellm-config.yaml
docker compose -f docker-compose.fullstack.yml up -d --force-recreate litellm open-webui nextchat
```

## Cloud variables

Set these in your cloud runtime or container service:

- `QWEN_SETTINGS=/data/settings.json`
- `QWEN_HOST=127.0.0.1`
- `QWEN_PORT=8787`
- `NEXTCHAT_HOST_PORT=3000` for the public NextChat route (`chat.zeaz.dev`)
- `OPENWEBUI_HOST_PORT=3011` for the secondary Open WebUI route
- `QWEN_STACK_NETWORK_MODE=host` for the Linux deployment where containers must
  reach the host Ollama service
- `NEXTCHAT_BASE_URL=http://127.0.0.1:4000/v1` for the LiteLLM backend
- `NEXTCHAT_DEFAULT_MODEL=zCoder:latest` for the default local model
- `NEXTCHAT_CUSTOM_MODELS=zCoder:latest,qwen2.5-coder` for the validated local models exposed in NextChat
- `litellm-config.yaml` as the runtime allowlist of probe-validated routes
- `QWEN_DATA_DIR=/mnt/qwen-gen-data` for the persistent qwen-gen state volume
- provider keys such as `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `DASHSCOPE_API_KEY`
- for the full stack, also set `LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`, and
  `WEBUI_SECRET_KEY`

## Notes

- The UI already includes the NextChat/Open WebUI-style browser chat surface.
- `settings.json` is the persistent state file for conversations, files, and prompt libraries.
- Keep the settings volume attached so chats and uploads survive restarts.
- Put the service behind HTTPS and access control before exposing it publicly.
- The full-stack compose file is documented in [FULL_STACK.md](FULL_STACK.md).
