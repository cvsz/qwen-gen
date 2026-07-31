# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.x (latest) | ✅ Active |
| < 1.0 | ❌ No longer supported |

## Reporting a vulnerability

**Please do not file public GitHub issues for security vulnerabilities.**

Report security issues privately using GitHub's advisory system:

👉 **[Report a vulnerability](https://github.com/cvsz/qwen-gen/security/advisories/new)**

### What to include

- A clear description of the vulnerability and its impact.
- Steps to reproduce (command line, environment variables used, etc.).
- The version of `qwen-omega` affected (`python qwen-omega.py --version`).
- Any proof-of-concept code or output.

### What to expect

- **Acknowledgement** within 48 hours.
- **Status update** within 7 days.
- A **fix and advisory** published as soon as possible, coordinated with you.

## Scope

| In scope | Out of scope |
|----------|-------------|
| Credential leakage via `settings.json` | API provider outages |
| Path traversal in file writes | Issues with `@qwen-code/qwen-code` itself |
| Code injection via model IDs or URLs | Network-level attacks |
| Insecure TLS (`--insecure` flag misuse) | Social engineering |

## Security design notes

- **No API keys are written to `settings.json`** — only `envKey` references.
- Settings are written **atomically** with `os.replace` and mode `0600`.
- Timestamped **backups** are created before any overwrite.
- The `--insecure` flag explicitly disables TLS verification and is intended **only for local development**.
