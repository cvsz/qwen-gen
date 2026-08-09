# NextChat / Open WebUI parity notes

This repository started as a CLI/config generator, and now also includes a
lightweight local chat server. The practical parts of NextChat/Open WebUI that
map into `qwen-gen` are provider discovery, local gateway support, config
generation, and a browser chat surface for local use.

## Implemented in `qwen-gen`

- OpenAI-compatible provider presets for many hosted and local gateways
- NextChat local gateway support via `NEXTCHAT_BASE_URL`
- Open WebUI local gateway support via `OPEN_WEBUI_BASE_URL`
- Auto-detection of local NextChat/Open WebUI backends during `install-coder`
- Free-model sync with fallback catalogs for local gateways and OpenRouter
- Reusable prompt library management via `prompts add/import/export/list/remove/clone`
- Workspace skill management via `skills add/import/export/list/remove/share/clone`
- Plugin / extension manifest management via `plugins add/import/export/list/remove/share/clone`
- Pipeline / workflow manifest management via `pipelines add/import/export/list/remove/share/clone`
- Filter manifest management via `filters add/import/export/list/remove/share/clone`
- Action manifest management via `actions add/import/export/list/remove/share/clone`
- Automation manifest management via `automations add/import/export/list/remove/share/clone`
- Channel timeline management via `channels add/import/export/list/remove/share`
- Channel timeline duplication via `channels clone`
- File/attachment registry management via `files add/import/export/list/remove/share/clone` with Markdown, HTML, and JSON sharing
- Tool/MCP server registry management via `tools add/import/export/list/remove/clone`
- Knowledge-base registry management via `kb add/import/export/list/remove/clone`
- Knowledge-base ingestion/indexing scaffolding via `kb ingest` and `kb refresh`
- Knowledge-base bulk synchronization via `kb sync`
- Knowledge-base watch/continuous refresh via `kb watch`
- Knowledge-base web-source ingestion via `kb ingest-url`
- Knowledge-base retrieval/querying via `kb query`
- Knowledge-base browser panel with create/edit/delete/refresh/query plus import/export/sync/watch
- Browser-side web search with provider selection and save-to-knowledge support
- Full settings snapshot export/import/sync/watch via `snapshot export/import/sync/watch`
- Web search provider catalog plus provider fallback/merge and save-to-knowledge workflow via `web-search`
- Notes registry management via `notes add/import/export/list/remove/share/clone` with file and image support
- Folders / project workspace registry management via `folders add/import/export/list/remove/share/clone`
- Memories registry management via `memories add/import/export/list/remove/share/clone`
- Artifact registry management via `artifacts add/import/export/list/remove/share/clone`
- Conversation history management via `conversations add/import/export/list/remove/share` with folder, attachment, and image support
- Conversation/session duplication via `conversations clone`
- Conversation branch/fork from an in-chat message
- Browser conversation history manager with import/export/share/clone actions, transcript search, richer transcript summaries, and clear-context dividers
- Stronger first-load onboarding in the browser chat when models or conversations are missing
- Empty model and compare selectors when no models are configured
- Actionable empty provider and conversation lists when no models or chats exist yet
- Composer no-model gate with a direct add-presets path
- Compare-mode guard when the second model matches the primary model
- Compare-mode status pill warns when the second model matches the primary model
- Compare selector excludes the primary model as a valid second-model choice
- Webhook / notification target registry management via `webhooks add/import/export/list/remove/share/clone`
- Agent preset management via `agents add/import/export/list/remove/share`
- Agent preset duplication via `agents clone`
- Browser agent preset manager with import/export/share/clone actions, live preview, and apply-to-chat workflow
- Local browser chat server via `serve`, with `/api/models`, `/api/chat`, `/api/bootstrap`, `/api/conversations`, and `/api/prompt-templates`
- Browser file upload into the file registry via `/api/files`
- Browser file registry import/export/clone controls in the browser UI
- Browser file registry workflow with bulk selection, delete/clone/export selected, preview, search/filter, attachment chips, and tree/flat browsing
- Drag-and-drop file upload from the chat composer into the file registry
- File preview modal in the browser chat UI
- Markdown callout blocks in the browser chat renderer
- Markdown footnotes in the browser chat renderer
- Markdown mention-token highlighting in the browser chat renderer
- Read-aloud voice selection in the browser chat composer
- Markdown citation markers in the browser chat renderer
- Browser chat message source chips for assistant citations or references
- Browser chat source preview modal for assistant citations or references
- Browser file upload text detection that treats mislabeled text files as text instead of binary blobs
- PWA shell for the browser chat UI via `/manifest.webmanifest`, `/sw.js`, and an app icon
- Server-backed conversation persistence into `settings.json`
- Basic markdown rendering for chat responses in the browser UI
- Richer markdown rendering in the browser UI, including tables, task lists, strike-through, and inline math-style spans
- Streaming chat responses in the browser UI via OpenAI-compatible SSE
- Multi-model compare mode in the browser chat UI that fans out a single prompt to multiple configured models
- Stop/cancel and regenerate controls for the active chat turn
- Conversation search plus Markdown/JSON/HTML/ShareGPT/image export from the browser UI
- Quick new-chat and delete-chat actions in the browser header
- Automatic conversation title generation from the first user prompt
- Transcript copy action from the browser chat header
- Chat title rename action from the browser chat header
- Duplicate current-chat action in the browser header
- Quick pin/archive toggles for the active chat in the browser header
- In-chat transcript search with match navigation
- Conversation pin and archive controls in the browser sidebar
- Conversation list filters for all, pinned, and archived chats
- Browser workspace selector plus workspace CRUD in the sidebar
- Sidebar collapse/expand control with persistent state
- Theme switching for the browser chat UI
- Keyboard shortcuts help overlay and global focus shortcuts
- Scroll-to-latest control in the chat pane
- File upload into the browser chat registry with automatic attachment to the active conversation
- Drag-and-drop file upload into the browser chat registry with automatic attachment to the active conversation
- Composer attachment chips with inline removal and clear-all control
- File preview and copy flow for uploaded files in the browser chat registry
- Message-level controls in the browser UI for copy, edit, delete, and retry
- Copy code action for markdown code blocks in assistant messages
- Streaming generation status indicator in the browser chat header
- File registry attachments injected into chat context via `files`
- File registry search/filter in the browser UI for browsing by id, name, kind, path, description, content, and tags
- Unified search across prompts, skills, plugins, pipelines, filters, actions, automations, channels, files, agents, conversations, folders, tools, knowledge, notes, memories, webhooks, artifacts, and providers via `search`
- Validation and repair of generated Qwen Code settings

## Already Modeled in UI But Easy to Misread

These are implemented and should not be treated as missing:

- Notes UI
- Skill sharing/export controls in the browser UI
- File sharing/export controls in the browser UI
- Artifact preview panes
- Streaming typing indicator in the browser chat UI during assistant generation
- Rich message lifecycle controls in the browser UI, including copy, edit, delete, retry, and copy code

## Not transferable into this repo as-is

- RBAC / admin panel / user groups
- i18n and other locale-specific frontend behavior

## Upstream references

- NextChat: https://github.com/ChatGPTNextWeb/NextChat
- Open WebUI: https://github.com/open-webui/open-webui
