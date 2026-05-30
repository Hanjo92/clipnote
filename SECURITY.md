# Security Policy

## Supported Versions

Security fixes are provided for the latest release and the current `main` branch.
Older releases are not actively maintained.

## Reporting a Vulnerability

Please do not report security vulnerabilities in public issues.

Use GitHub private vulnerability reporting:

https://github.com/Hanjo92/clipnote/security/advisories/new

If private reporting is unavailable, open a public issue that only asks for a
private contact channel. Do not include exploit details, auth tokens, vault
paths, selected text, private page URLs, local file paths, logs with secrets, or
screenshots containing sensitive notes.

Useful private report details include:

- affected clipnote version or commit
- affected area: CLI, local server, Chrome extension, packaging, or docs
- operating system and browser version
- concise reproduction steps
- expected impact

## Scope

Security reports are most useful when they affect clipnote's local HTTP bridge,
browser extension permissions, auth token handling, URL fetching, redirect
handling, file writes, packaging, or release process.

Expected response scope for this small project:

- acknowledge actionable private reports when maintainers are available
- investigate reproducible reports that affect supported versions
- publish a fix and release note when a vulnerability is confirmed
- close reports that require a compromised local machine, unsafe local
  configuration outside clipnote, or behavior already documented as trusted
  local operation
