# Contributing to Qwen Omega ProMeta

Thanks for your interest in contributing! This guide covers how to report issues, propose changes, and submit pull requests.

## Table of contents

- [Code of Conduct](#code-of-conduct)
- [Getting started](#getting-started)
- [Development setup](#development-setup)
- [Running tests](#running-tests)
- [Submitting a pull request](#submitting-a-pull-request)
- [Adding a new provider preset](#adding-a-new-provider-preset)
- [Commit style](#commit-style)
- [Versioning](#versioning)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). Please read it before contributing.

---

## Getting started

1. **Fork** the repository and clone your fork:
   ```bash
   git clone https://github.com/<your-username>/qwen-gen
   cd qwen-gen
   ```

2. Create a **feature branch**:
   ```bash
   git checkout -b feat/your-feature-name
   ```

---

## Development setup

No external dependencies are required for the core (`qwen-omega.py` uses only the Python standard library).

Optional dev tools:
```bash
pip install pytest ruff
```

---

## Running tests

```bash
# Unit tests
python -m pytest test_qwen_omega.py -v

# Dry-run smoke test (no API key needed)
python qwen-omega.py install-coder --backend ollama \
  --model qwen2.5-coder:7b-instruct-q4_K_M --dry-run

# Lint
ruff check qwen-omega.py
ruff format --check qwen-omega.py

# Shell syntax check
bash -n install.sh
bash -n install-qwen-coder.sh
```

All checks are also run automatically in CI on every PR.

---

## Submitting a pull request

1. Make sure all tests pass locally.
2. Update `CHANGELOG.md` under `## [Unreleased]`.
3. If you changed user-visible behavior, update `README.md`.
4. Bump `VERSION` in `qwen-omega.py` if you're releasing (follow [SemVer](#versioning)).
5. Open a PR — the template will guide you through the checklist.

---

## Adding a new provider preset

Edit the `PRESETS` dict in `qwen-omega.py`:

```python
"myprovider": ProviderPreset(
    "My Provider",             # Human-readable name
    "openai",                  # Protocol (always "openai" for OpenAI-compat)
    "https://api.myprovider.com/v1",  # Base URL
    "MYPROVIDER_API_KEY",      # Env var name
),
```

Then:
- Add an entry to the `--provider` option description in `install.sh`.
- Add an example to the `README.md` **Suggested workflows** section if relevant.
- Open a PR using the **Provider Request** template.

---

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add siliconflow provider preset
fix: handle empty model list after --coder-only filter
docs: add CI/headless workflow example
chore: bump version to 1.2.0
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

| Change | Version bump |
|--------|-------------|
| Breaking change to CLI flags or settings schema | MAJOR |
| New subcommand, new flag, new provider | MINOR |
| Bug fix, documentation, CI | PATCH |

When bumping the version:
1. Update `VERSION` in `qwen-omega.py`.
2. Update `VERSION` in `install-qwen-coder.sh`.
3. Add a `## [x.y.z] — YYYY-MM-DD` section to `CHANGELOG.md`.
4. Tag the commit: `git tag v1.2.0 && git push --tags`.
