# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [1.3.0] — 2026-07-31

### Added

- **LiteLLM, LM Studio, NextChat, Open WebUI Provider Integrations**
  - Preset endpoints and default port configurations (`http://127.0.0.1:4000/v1`, `http://127.0.0.1:1234/v1`, `http://127.0.0.1:3000/api/openai/v1`, `http://127.0.0.1:8080/v1`)
  - Dedicated `CODER_CATALOG` model lists for all 4 local/web UI backends
  - Environment key auto-detection (`LITELLM_API_KEY`, `LMSTUDIO_API_KEY`, `NEXTCHAT_API_KEY`, `OPEN_WEBUI_API_KEY`)
  - Backend options added to both Python CLI (`--backend`) and `install-qwen-coder.sh` installer script
- **Documentation & Operations**
  - **`RUNBOOK.md`**: Operations runbook for CLI commands, testing, building, CI/CD, and troubleshooting
  - **API Provider Portal Guide**: Complete reference table in `README.md` for getting API keys across 15+ providers
- **Infrastructure & GitHub Secrets Sync**
  - Full secret synchronization script for 18 provider API keys
  - Live repository variable synchronization for 19 provider base URLs and CI controls

### Fixed

- `--dry-run` operations without `--models` or active credentials now synthesize default model configurations without throwing missing API key errors.

---

## [1.2.0] — 2026-07-31

### Added

- **Python package (`pyproject.toml`)** — `qwen-omega-prometa` now pip-installable
  - `pip install qwen-omega-prometa` installs `qwen-omega` console script globally
  - Pure stdlib, zero runtime dependencies
  - Fully typed classifiers, SPDX license expression, PEP 621 compliant
- **`qwen_omega.py`** — canonical module (underscore name, importable as `import qwen_omega`)
- **`qwen-omega.py`** — backward-compatible shim (existing scripts unchanged)
- **Standalone zipapp** (`dist/qwen-omega`) — single executable file, runs without install
- **`build.yml`** GitHub Actions workflow — builds wheel + sdist + zipapp on every push/PR
- **`publish.yml`** GitHub Actions workflow — publishes to PyPI via OIDC trusted publishing
- **Release pipeline** — 3-job chain: build → GitHub Release → PyPI publish
  - All artifacts attached to every release: `.whl`, `.tar.gz` (sdist), zipapp, legacy archive, `SHA256SUMS`
- **`build-check` job in `ci.yml`** — catches build regressions on every PR

### Changed

- `release.yml` rewritten into `build → release → publish` job chain
- `test_qwen_omega.py` updated to import `qwen_omega` module directly (no more `importlib` path hack)

---

## [1.1.0] — 2026-07-31

### Added

- **`install-qwen-coder.sh`** — dedicated one-shot Qwen Coder installer
  - Auto-detects backend: Ollama → DashScope → OpenRouter → SiliconFlow
  - RAM-aware Ollama model selection (1.5b / 3b / 7b / 14b / 32b via `/proc/meminfo`)
  - Automatic `ollama pull` with REST API fallback
  - Automatic install of `@qwen-code/qwen-code` via `npm` when missing
  - Flags: `--backend`, `--model`, `--free`, `--approval-mode`, `--dry-run`, `--non-interactive`, `--prefix`

- **`qwen-omega install-coder` subcommand** (`qwen-omega.py`)
  - `CODER_CATALOG`: curated model lists per backend (ollama, dashscope, openrouter, siliconflow)
  - `_detect_ram_gb()`: `/proc/meminfo`-based RAM detection for model size selection
  - Backend validation: checks required env keys before attempting API calls
  - Ollama subprocess pull with graceful error recovery
  - Flags: `--backend {auto,ollama,dashscope,openrouter,siliconflow}`, `--model`, `--free`, `--approval-mode`, `--dry-run`

- **GitHub repository templates and workflows**
  - CI: Python 3.10–3.13 test matrix, ruff lint, shellcheck, dry-run smoke tests
  - Release: tag-triggered archive build, version verification, changelog extraction
  - CodeQL: weekly security scan for Python
  - Dependency Review: blocks PRs with high-severity vulnerable dependencies
  - Issue templates: Bug Report, Feature Request, Provider Request
  - Pull Request template with type checklist and safety checklist
  - `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`

### Changed

- `VERSION` bumped to `1.1.0` in `qwen-omega.py`
- `README.md` rewritten with 8 concrete suggested workflows

---

## [1.0.0] — 2026-07-31

### Added

- **`qwen-omega.py`** — core configuration generator and validator
  - 30+ provider presets (OpenAI, OpenRouter, NVIDIA, Groq, Together, Fireworks, DeepInfra, Cerebras, Mistral, DashScope, Ollama, LiteLLM, SiliconFlow, Featherless, Novita, Hyperbolic, Anyscale, FriendliAI, SambaNova, DeepSeek, AI21, Perplexity, Cloudflare, vLLM, LM Studio, TGI, SageMaker, Bedrock, Azure OpenAI, GitHub Models, xAI, Cohere, 01.AI, Zhipu, Moonshot, Baichuan, MiniMax, StepFun, Hunyuan)
  - Subcommands: `generate`, `validate`, `repair`, `doctor`, `providers`
  - Model filtering: `--filter-model`, `--coder-only`, `--min-context`, `--include-regex`, `--exclude-regex`, `--limit`
  - Free model catalog fallback for OpenRouter with `KNOWN_FREE_MODELS`
  - Atomic `settings.json` writes (mode `0600`, `os.replace`)
  - Timestamped backup before every overwrite
  - Schema `$version: 4` enforcement
  - Legacy provider shape repair (comma-string, wrapped `{protocol,models}`)

- **`install.sh`** — general-purpose installer with all provider options
- **`install-qwen-coder.sh`** baseline (v1.0 minimal, full version in v1.1.0)
- **`uninstall.sh`** — removes installed binary and config
- **`test_qwen_omega.py`** — unit tests for core functions
- **`example-settings.json`** — reference settings.json output
- **`README.md`** — project documentation

[Unreleased]: https://github.com/cvsz/qwen-gen/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/cvsz/qwen-gen/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/cvsz/qwen-gen/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/cvsz/qwen-gen/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/cvsz/qwen-gen/releases/tag/v1.0.0
