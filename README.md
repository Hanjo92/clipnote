# clipnote

[![CI](https://github.com/Hanjo92/clipnote/actions/workflows/ci.yml/badge.svg)](https://github.com/Hanjo92/clipnote/actions/workflows/ci.yml)

Local-first CLI and Chrome extension for saving web pages and papers as
structured Markdown notes.

clipnote turns a URL into a useful note: cleaned title, summary draft, tags,
source metadata, duplicate warnings, and optional selected-text excerpts. It is
especially useful with Obsidian vaults, but the output is plain Markdown.

## Highlights

- Save blog posts, product updates, changelog pages, and arXiv papers.
- Infer `papers` vs `links` and write notes into date-based folders.
- Enrich arXiv notes with id, publication date, authors, and categories.
- Preview before saving, including duplicate URL/title matches.
- Capture from Chrome with popup and context-menu actions.
- Use selected page text as a saved excerpt.
- Optionally use Chrome built-in AI APIs for summary overrides.
- Generate weekly recap notes and clean up duplicates later.

## Quick Start

Clone and install:

```bash
git clone https://github.com/Hanjo92/clipnote.git
cd clipnote
pipx install .
```

For local development:

```bash
python3 -m pip install -e ".[dev]"
```

Save a paper:

```bash
clipnote save 'https://arxiv.org/abs/2604.11978' --dry-run
clipnote save 'https://arxiv.org/abs/2604.11978'
```

Save a link:

```bash
clipnote save 'https://example.com/article' --kind links
```

Check duplicates:

```bash
clipnote cleanup --urls-only
```

Generate a weekly recap:

```bash
clipnote recap --week --compare-previous
clipnote recap --week --compare-previous --save-note
```

## Chrome Extension

The Chrome extension lets you preview, save, and open notes without switching to
the terminal.

Requires Chrome 127 or newer.

Full setup guide:

- [Extension quickstart](docs/EXTENSION_QUICKSTART.md)

Short version:

1. Start the local bridge:

   ```bash
   clipnote-server
   ```

2. Copy the printed `auth token`.
3. Open `chrome://extensions`.
4. Enable **Developer mode**.
5. Click **Load unpacked** and select the repository `extension/` directory.
6. Paste the token into the extension popup.
7. Set **Vault path** to your Obsidian vault or notes directory.

Expected unpacked extension ID:

```text
dojaomlgohpahfibbdbjjnkkpbdoljnf
```

The manifest includes a fixed public key so local unpacked installs keep the
same extension ID for the server allowlist. This is not a private signing key.

Extension actions:

- Popup preview/save for the current tab
- `Open` and `Open existing` from the popup
- Context-menu preview/save for pages and links
- Selected-text capture into `## Selected excerpt`
- Optional AI Summary override using Chrome built-in AI APIs

Package the extension:

```bash
python3 scripts/package_extension.py --output dist/clipnote-extension.zip
```

## CLI Reference

Save:

```bash
clipnote save 'https://arxiv.org/abs/2604.11978' --dry-run
clipnote save 'https://example.com/article' --kind links
clipnote save 'https://example.com/article' --duplicate-lookback-days 7
```

Dedupe and cleanup:

`dedupe` reports or recommends duplicate handling. `cleanup` can archive
redundant notes when run with `--apply`.

```bash
clipnote dedupe
clipnote dedupe --urls-only
clipnote dedupe --recommend
clipnote cleanup --urls-only
clipnote cleanup --urls-only --apply
```

Recap:

```bash
clipnote recap --week
clipnote recap --week --anchor-date 2026-05-07
clipnote recap --week --compare-previous
clipnote recap --week --save-note
clipnote recap --week --save-note --dry-run
```

## Local HTTP API

The extension talks to the local server at `http://127.0.0.1:8765`.

Endpoints:

- `GET /health`
- `POST /settings`
- `POST /preview`
- `POST /save`
- `POST /open`

Example:

```bash
curl http://127.0.0.1:8765/health

curl -X POST http://127.0.0.1:8765/preview \
  -H 'Content-Type: application/json' \
  -H 'Origin: chrome-extension://dojaomlgohpahfibbdbjjnkkpbdoljnf' \
  -H 'X-Clipnote-Token: <token printed by clipnote-server>' \
  -d '{"url":"https://arxiv.org/abs/2604.11978"}'
```

## Project Layout

- `clipnote.py` - main CLI and note generation logic
- `clipnote_server.py` - authenticated local HTTP bridge
- `extension/` - Chrome extension source
- `scripts/package_extension.py` - extension packaging helper
- `tests/` - CLI, server, extension, and packaging tests
- `docs/` - extension setup and release checklists

## Documentation

- [Extension quickstart](docs/EXTENSION_QUICKSTART.md)
- [Chrome extension release notes](docs/CHROME_EXTENSION_RELEASE.md)
- [Extension manual smoke test](docs/EXTENSION_SMOKE_TEST.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## Development

Run tests:

```bash
python3 -m unittest discover -s tests
```

Run syntax and packaging checks:

```bash
python3 -m py_compile clipnote.py clipnote_server.py scripts/package_extension.py
python3 -m json.tool extension/manifest.json >/dev/null
node --check extension/background.js
node --check extension/popup.js
python3 scripts/package_extension.py --output /tmp/clipnote-extension.zip
```

## Security

Please report vulnerabilities through the [security policy](SECURITY.md). Do not
post auth tokens, vault paths, selected text, private page URLs, or logs with
secrets in public issues.

## Status

clipnote is an MVP, but the main workflow is usable:

1. discover something worth keeping
2. preview or save it quickly
3. clean up duplicates later
4. review the week in recap form

## License

MIT License. See [LICENSE](LICENSE).
