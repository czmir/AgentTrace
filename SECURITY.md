# Security Policy

## Reporting

Email the maintainer via GitHub issues **without** pasting secrets, or open a private security advisory on https://github.com/czmir/AgentTrace/security.

## What AgentTrace stores

Traces may include prompts, tool arguments, and tool results. The SDK redacts common API key / auth patterns and sensitive field names before SQLite persist. **Do not** treat redaction as a complete DLP product.

## Running locally

- Default CORS is localhost only (`AGENTTRACE_CORS`).
- Do not expose `:8765` / `:4321` to the public internet without an auth proxy.
- Keep `.env` out of git (see `.gitignore`).
- Replay `mode=reexecute` is in-process only; the HTTP API refuses it so the UI cannot trigger side effects.

## Supply chain

Runtime dependencies are bounded in `pyproject.toml`. GitHub Dependabot is enabled for pip and GitHub Actions. Pin CI action major versions; review Dependabot PRs before merge.
