# Qwen Gen Checklist

## Completed

- [x] Local browser chat server with model selection, prompt templates, conversations, folders, and attachments
- [x] Browser-side file registry with upload, import/export/clone, preview, search, share/export, and attachment chips
- [x] Browser-side skills, memories, notes, artifacts, tools, webhooks, agents, and prompt templates management
- [x] Browser-side conversation history manager with import/export/share/clone actions
- [x] Browser-side agent preset manager with import/export/share/clone actions
- [x] Browser-side web search with save-to-knowledge support
- [x] Knowledge base CRUD, refresh, query, import, export, sync, and watch support in the browser API
- [x] CLI registry commands for prompts, skills, plugins, pipelines, filters, actions, automations, channels, files, tools, knowledge bases, notes, memories, artifacts, folders, conversations, webhooks, and agents
- [x] Parity notes maintained in `NEXTCHAT_OPENWEBUI_PARITY.md`

## In Progress

- [ ] Browser chat history UX still narrower than a full transcript manager
- [ ] Agent workspace UX still narrower than a full multi-pane editor
- [ ] File browser still narrower than a dedicated file manager/library

## Verification

- [x] `python3 -m py_compile qwen_omega.py test_qwen_omega.py`
- [x] `python3 -m unittest test_qwen_omega`
