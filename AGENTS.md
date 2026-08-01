# AGENTS.md

## Purpose

This repository is `qwen-gen`, a Qwen-oriented generator, settings manager, and local browser chat server.

The source of truth is `qwen_omega.py`. It contains:
- the CLI entrypoint
- settings generation and repair logic
- registry CRUD for prompts, skills, plugins, pipelines, filters, actions, automations, channels, agents, tools, knowledge bases, notes, memories, files, artifacts, folders, conversations, and webhooks
- the local `serve` HTTP server
- the embedded browser chat UI
- the embedded browser KB panel with create/edit/delete/refresh/query/import/export/sync/watch flows
- browser conversation and agent bulk actions for import/export/share/clone
- browser file registry import/export/share/clone controls

## Working Rules

- Keep code, comments, docs, and generated technical text in English.
- Prefer small, targeted edits in `qwen_omega.py` unless a refactor is clearly safer.
- Preserve existing user changes in the worktree.
- Use `apply_patch` for manual file edits.
- Validate after each meaningful UI or CLI change.
- When changing the embedded HTML/JS/CSS template, always run `python3 -m py_compile qwen_omega.py` and the focused unit tests.

## Core Surfaces

### 1. CLI Generator and Installer

`qwen-omega` is the main command.

Important commands:
- `generate` - discover models and write `settings.json`
- `install-coder` - one-shot setup for a Qwen Coder environment
- `validate` - validate the current settings schema
- `repair` - repair legacy provider shapes
- `doctor` - inspect installation and validate settings
- `providers` - list available provider presets
- `search` - search across local registries
- `web-search` - search providers and optionally save results to knowledge
- `serve` - start the local browser chat server

The repo also exposes registry management commands for:
- `prompts`
- `skills`
- `plugins`
- `pipelines`
- `filters`
- `actions`
- `automations`
- `channels`
- `tools`
- `kb`
- `snapshot`
- `notes`
- `folders`
- `memories`
- `files`
- `artifacts`
- `conversations`
- `webhooks`
- `agents`

### 2. Browser Chat Server

The `serve` command exposes:
- HTML routes for `/`, `/chat`, `/ai.html`, and `/platform/ai.html`
- `GET /api/models`
- `POST /api/chat`
- `GET /api/bootstrap`
- `GET/POST /api/conversations`
- `GET/POST /api/prompt-templates`
- `GET/POST /api/files`
- `manifest.webmanifest`
- `sw.js`
- `qwen-gen-icon.svg`

The browser UI already includes:
- model selection and provider presets
- compare mode across multiple models
- prompt templates
- workspace folders
- conversation list with pin/archive/filter/search
- transcript search
- conversation import/export/share/clone controls
- file import/export/share/clone, upload, attachment chips, and file preview
- copy/export/share actions
- message-level copy/edit/delete/retry
- prompt insertion from skills, memories, notes, and artifacts
- agent import/export/share/clone controls
- theme toggle
- keyboard shortcut overlay
- PWA shell support

### 3. Settings and Data Model

`settings.json` is the canonical persisted state.

Important invariants:
- settings schema is `$version: 4`
- provider models are stored as arrays under `modelProviders.<provider>`
- API keys are never written into settings
- writes should be atomic
- backups should be created before replacing settings

The repository also supports snapshot export/import/sync for full settings-tree portability.

## Feature Map

### Prompt Libraries

Use `prompts` for reusable prompt templates.

Support includes:
- list
- add / replace
- remove
- import
- export
- clone
- share

### Skills

Use `skills` for reusable prompt-side skill blocks and instructions.

Support includes:
- list
- add / replace
- remove
- import
- export
- share
- clone

### Plugin, Pipeline, Filter, Action, Automation Registries

These registry types follow the same lifecycle pattern:
- list
- add / replace
- remove
- import
- export
- share
- clone

### Channels

Channel timelines support:
- add
- remove
- import
- export
- share
- clone

### Files

File records support:
- add
- remove
- import
- export
- share
- clone
- browser upload into the file registry
- attachment chips in the chat composer
- preview in the browser UI

### Knowledge Bases

Knowledge base support includes:
- registry CRUD
- ingest
- ingest-url
- refresh
- sync
- watch
- query

### Conversations

Conversation support includes:
- add
- remove
- import
- export
- share
- clone
- branch/fork from a message in the browser UI

### Folders

Folders represent workspaces or project containers.

Support includes:
- add
- remove
- import
- export
- share
- clone

### Memories, Notes, Artifacts, Webhooks, Agents, Tools

These are all first-class registries with shared CRUD and sharing patterns.

The browser UI exposes inline editors and preview panes for most of them.

## Browser UI Notes

The UI template is embedded in `qwen_omega.py`, so HTML structure, CSS, and JavaScript live in the same file.

When editing the UI:
- keep state and DOM references consistent
- update `renderTemplates()`, `renderMessages()`, `renderAll()`, and relevant event handlers together
- verify any new element IDs are referenced in `els`
- avoid breaking the f-string brace escaping around embedded JavaScript

Current UI priorities already implemented in code:
- compact desktop sidebar
- premium panel styling
- distinct user/assistant/system message bubbles
- template gallery drawer with search, categories, compare, copy, apply, and append
- compare/copy features aligned with the general Open WebUI / NextChat workflow

## Important Files

- [`qwen_omega.py`](/home/cvsz/qwen-gen/qwen_omega.py) - main implementation
- [`test_qwen_omega.py`](/home/cvsz/qwen-gen/test_qwen_omega.py) - primary regression coverage
- [`README.md`](/home/cvsz/qwen-gen/README.md) - user-facing install and usage guide
- [`NEXTCHAT_OPENWEBUI_PARITY.md`](/home/cvsz/qwen-gen/NEXTCHAT_OPENWEBUI_PARITY.md) - scope note for parity and non-parity
- [`example-settings.json`](/home/cvsz/qwen-gen/example-settings.json) - canonical settings example

## Verification Workflow

After changing code:

1. Run `python3 -m py_compile qwen_omega.py`
2. Run `python3 -m unittest test_qwen_omega`
3. If the browser UI changed, restart the service and verify the served HTML
4. If behavior changed, inspect the relevant HTTP or CLI command output

Useful checks:
- `systemctl --user restart qwen-omega.service`
- `systemctl --user status qwen-omega.service --no-pager`
- `curl -fsS http://127.0.0.1:8091/`
- `curl -fsS https://qwen.zeaz.dev/`

## Deployment Notes

The live browser chat is served by the user service:
- `qwen-omega.service`
- current local bind is `127.0.0.1:8091`

If the live UI must change, restart the service after the code update and verify the external URL.

## Safe Editing Guidance

- Do not remove unrelated user work.
- Do not rewrite large sections unless the feature needs it.
- Keep tests aligned with any new IDs, labels, or UI copy introduced in the embedded template.
- If a change touches both CLI and UI, update the relevant tests in the same pass.
- Prefer evidence from code and tests over assumptions about feature coverage.
