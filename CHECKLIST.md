# Qwen Gen Checklist

## Completed

- [x] Local browser chat server with model selection, prompt templates, conversations, folders, and attachments
- [x] Browser-side file registry with upload, import/export/clone, preview, search, share/export, attachment chips, bulk library selection, and tree/flat browsing
- [x] Browser-side skills, memories, notes, artifacts, tools, webhooks, agents, and prompt templates management
- [x] Browser-side conversation history manager with import/export/share/clone actions and richer transcript summaries
- [x] Stronger first-load onboarding panel when models or conversations are missing
- [x] Empty model selector state when no models are configured
- [x] Actionable empty provider and conversation lists when nothing is configured yet
- [x] Composer no-model gate with direct add-presets path
- [x] Compare-mode guard when the second model matches the primary model
- [x] Compare-mode status pill warns when the second model matches the primary model
- [x] Compare selector excludes the primary model as a valid second-model choice
- [x] Cloud deployment scaffold with Dockerfile and container entrypoint
- [x] Cloud deployment notes for persistent browser chat state behind an ingress
- [x] HDD-backed cloud helper script with `/mnt/qwen-gen-data` default
- [x] Full-stack compose file for Ollama, LiteLLM, Open WebUI, NextChat, and qwen-gen
- [x] Full-stack helper script with `/mnt/qwen-gen-data` default
- [x] Browser-side conversation context divider with clear/revert actions
- [x] Browser-side chat markdown callouts and footnotes
- [x] Browser-side chat read-aloud voice selection
- [x] Browser-side chat markdown citation markers
- [x] Browser-side chat message source chips for assistant citations or references
- [x] Browser-side chat source preview modal for assistant citations or references
- [x] Browser-side agent preset manager with import/export/share/clone actions and apply-to-chat workflow
- [x] Browser-side web search with save-to-knowledge support
- [x] Knowledge base CRUD, refresh, query, import, export, sync, and watch support in the browser API
- [x] CLI registry commands for prompts, skills, plugins, pipelines, filters, actions, automations, channels, files, tools, knowledge bases, notes, memories, artifacts, folders, conversations, webhooks, and agents
- [x] Batch settings generator script for all providers via `qwen-gen.sh`
- [x] Parity notes maintained in `NEXTCHAT_OPENWEBUI_PARITY.md`

## Verification

- [x] `python3 -m py_compile qwen_omega.py test_qwen_omega.py`
- [x] `python3 -m unittest test_qwen_omega`
