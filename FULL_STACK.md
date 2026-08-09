# Full Stack

This repository can be run as a merged stack:

- `Ollama` for local models, running on the host at `127.0.0.1:11434`
- `LiteLLM` for a shared OpenAI-compatible gateway
- `NextChat` for the public lightweight chat UI
- `Open WebUI` for a secondary local workspace UI
- `qwen-gen` for generation, settings, and operator workflows

## Topology

```text
Users
  ├─ Open WebUI  -> http://127.0.0.1:3011
  ├─ NextChat    -> http://127.0.0.1:3000
  └─ qwen-gen    -> http://127.0.0.1:8787 -> LiteLLM -> http://127.0.0.1:4000/v1
                                                               |
                                                            Ollama -> http://127.0.0.1:11434
```

## Local run

```bash
./qwen-stack.sh
```

Use `./qwen-stack.sh --detach` to start the stack in the background.

## Ports

- `Ollama`: `11434` on the host
- `LiteLLM`: `4000`
- `NextChat`: `3000` (public `chat.zeaz.dev`)
- `Open WebUI`: `3011` (secondary local UI)
- `qwen-gen`: `8787` by default (`8091` for the public systemd deployment)

## Connections

- This deployment uses host networking because the live Docker bridge cannot
  reach the host Ollama listener. Override `QWEN_STACK_NETWORK_MODE` and the
  endpoint variables together only on a runtime where bridge-to-host access is
  explicitly allowed.
- NextChat points to the host-networked LiteLLM process via
  `BASE_URL=http://127.0.0.1:4000/v1` (override with
  `NEXTCHAT_BASE_URL` when the Compose project name differs).
- Open WebUI points to LiteLLM via `OPENAI_API_BASE_URL=http://127.0.0.1:4000/v1`
- qwen-gen is automatically seeded with the `litellm` provider on first boot and
  points to `http://127.0.0.1:4000/v1` using `LITELLM_MASTER_KEY`.
- LiteLLM exposes only the models that passed the latest real chat probe:
  `zCoder:latest` and `qwen2.5-coder`. The runtime config is an allowlist, so
  provider-declared free models without current quota are not advertised.
- NextChat selects `zCoder:latest` by default through `DEFAULT_MODEL` and
  exposes the validated local aliases `zCoder:latest,qwen2.5-coder` through
  `CUSTOM_MODELS`.
- The live qwen-gen settings are health-filtered from `.env.ai`; the primary
  model is LiteLLM and direct host Ollama is retained as the fallback.

## Notes

- Set `LITELLM_MASTER_KEY` to a stable secret before using the gateway.
- Set `WEBUI_SECRET_KEY` to a stable secret before using the secondary Open WebUI.
- Open WebUI runs with offline-mode flags here so the stack boots without
  waiting on first-run Hugging Face model downloads.
- Use `NEXTCHAT_CODE` if you want access control on the public NextChat route.
- Refresh the provider-declared discovery catalog with:

  ```bash
  ./sync-free-models.sh --timeout 20
  ```

  The sync only accepts provider-declared free models (or explicit `*_FREE_MODEL`
  hints), removes media-only models, and exposes cloud entries as
  `free/<provider>/<model-id>`. It is discovery metadata, not a quota check;
  run the real probe below before exposing its output.
- Set `QWEN_AUTO_CONFIGURE=0` if you want to manage qwen-gen settings manually.
- Recheck free providers after changing `.env.ai` with:

  ```bash
  ./qwen-free.sh --settings /mnt/qwen-gen-data/settings.json \
    --env-root /home/cvsz/qwen-gen --timeout 60 \
    --litellm-config /home/cvsz/qwen-gen/litellm-config.yaml
  ```

  This sends a minimal chat probe to each discovered free candidate, keeps only
  successful models, prunes LiteLLM to matching aliases, and enables qwen-gen
  request fallback across the survivors. Recreate `litellm`, `open-webui`, and
  `nextchat` after changing the runtime config.
- If UFW is enabled, allow the current Compose bridge subnet to reach host port
  `11434`; the live host uses a scoped rule for the qwen stack rather than
  publishing Ollama through Compose.
- `qwen-gen` still manages the broader Qwen provider generation workflow.
