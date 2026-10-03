# NextChat / Open WebUI Source Audit

This file records the upstream chat-interface files that were reviewed while updating `qwen-gen`.

## Reviewed NextChat Files

- `app/components/chat.tsx`
  - Mapped to `qwen_omega.py` message rendering, message actions, exports, prompt templates, and chat-state handling.
  - Applied in `qwen-gen`:
    - richer conversation summaries in the sidebar
    - clear-context dividers with revert controls
    - transcript export/share flows

- `docs/synchronise-chat-logs-en.md`
  - Reviewed as the upstream chat-log synchronization workflow.
  - `qwen-gen` currently models local browser persistence and import/export paths, but not the external UpStash-backed sync backend.

## Reviewed Open WebUI Files

- `backend/open_webui/routers/files.py`
  - Mapped to `qwen_omega.py` file registry upload and file-processing flow.
  - Applied in `qwen-gen`:
    - robust text-file detection for mislabeled uploads
    - browser file registry upload / preview / clone / export workflow

- `src/lib/components/chat/Messages/Markdown/MarkdownTokens.svelte`
  - Mapped to `qwen_omega.py` markdown rendering and message formatting.
  - `qwen-gen` already covers tables, lists, code blocks, task lists, strike-through, and inline math-style spans.

## Practical Result

The browser chat UI now includes:

- transcript summaries and snippets in the sidebar
- stronger first-load onboarding when models or conversations are missing
- empty model and compare selector states when no models are configured
- actionable empty provider and conversation lists when no models or chats exist yet
- composer no-model gate with a direct add-presets path
- compare-mode guard when the second model matches the primary model
- compare-mode status pill warns when the second model matches the primary model
- compare selector excludes the primary model as a valid second-model choice
- clear-context cut points for conversations
- markdown callout blocks from colon-fence style content
- markdown footnote blocks from inline references and definitions
- markdown mention-token highlighting for @, #, and $ tokens
- browser read-aloud voice selection for message playback
- markdown citation markers for inline bracketed references
- browser message source chips for assistant citations and references
- browser source preview modal for assistant citations and references
- safer file upload detection for text-like files
- tree/flat file registry browsing for nested paths
- bulk file-library actions

## Still External or Out of Scope

- Upstash-backed cross-device chat-log sync
- RBAC / admin-panel behavior
- i18n / locale-specific UI behavior
