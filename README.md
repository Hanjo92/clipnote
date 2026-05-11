# clipnote

[![CI](https://github.com/Hanjo92/clipnote/actions/workflows/ci.yml/badge.svg)](https://github.com/Hanjo92/clipnote/actions/workflows/ci.yml)

Save web pages and papers into structured Markdown notes.

clipnote is a local-first tool for turning URLs into readable notes with:
- cleaned titles
- summary drafts
- tags
- duplicate detection
- weekly recaps
- a Chrome extension for one-click capture

It currently works especially well for an Obsidian vault, but the core idea is broader: **URL → structured Markdown note**.

---

## What it does

### Save pages and papers
- save blog posts, changelog pages, product updates, and arXiv papers
- infer `papers` vs `links`
- generate a Markdown note in date-based folders
- warn on duplicate URL/title matches

### Improve note quality automatically
- clean noisy page titles
- generate summary drafts and key points
- add source-aware tags
- support selected text as a saved excerpt

### Handle papers better
- arXiv metadata enrichment
  - arXiv id
  - published date
  - authors
  - categories
- long author lists are shortened in the header and preserved below

### Keep the vault tidy
- scan duplicates across the vault
- recommend which note to keep
- merge useful excerpts into the kept note
- archive redundant notes

### Review what you saved
- generate weekly recaps
- compare against the previous period
- extract highlights, recurring themes, and source breakdowns

---

## Project structure

- `clipnote.py` — main CLI
- `clipnote_server.py` — local HTTP bridge for the Chrome extension
- `extension/` — Chrome extension MVP
- `CHROME_EXTENSION_PLAN.md` — extension design notes

---

## Quick start

### Install
```bash
cd ~/Projects/clipnote
pipx install .
```

For local development:
```bash
python3 -m pip install -e ".[dev]"
```

To refresh an existing local install from this checkout:
```bash
cd ~/Projects/clipnote
pipx install --force .
```

### 1) Save a paper
```bash
cd ~/Projects/clipnote
python3 clipnote.py save 'https://arxiv.org/abs/2604.11978' --dry-run
python3 clipnote.py save 'https://arxiv.org/abs/2604.11978'
```

### 2) Save a link
```bash
cd ~/Projects/clipnote
python3 clipnote.py save 'https://openai.com/index/gpt-5-5-instant/' --dry-run
python3 clipnote.py save 'https://openai.com/index/gpt-5-5-instant/'
```

### 3) Check duplicates
```bash
cd ~/Projects/clipnote
python3 clipnote.py cleanup --urls-only
```

### 4) Generate a weekly recap
```bash
cd ~/Projects/clipnote
python3 clipnote.py recap --week --compare-previous
```

### 5) Save the recap into the vault
```bash
cd ~/Projects/clipnote
python3 clipnote.py recap --week --compare-previous --save-note
```

### Run tests
```bash
python3 -m unittest discover -s tests
```

---

## Chrome extension

clipnote includes a Chrome extension MVP so you do not have to open a terminal every time.

Quick setup guide:
- [`docs/EXTENSION_QUICKSTART.md`](docs/EXTENSION_QUICKSTART.md)

### Run the local server
```bash
cd ~/Projects/clipnote
python3 clipnote_server.py
```

The server prints an `auth token`. Paste that token into the extension popup before previewing or saving.

Default allowed origin:
- `chrome-extension://dojaomlgohpahfibbdbjjnkkpbdoljnf`

The extension manifest includes a fixed key, so unpacked loads keep the same extension ID.

### Load the extension
Requires Chrome 127 or newer.

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select `~/Projects/clipnote/extension`
5. Reload the extension after changes

Expected extension ID:
- `dojaomlgohpahfibbdbjjnkkpbdoljnf`

Package a release zip:
```bash
python3 scripts/package_extension.py --output dist/clipnote-extension.zip
```

### Current extension flow
- popup auto-loads the current tab URL
- preview before saving
- title override
- kind override
- duplicate visibility
- save and auto-open note
- `Open` / `Open existing` from the popup
- right-click preview/save for page and link targets
- selected text can be saved as `Selected excerpt`

### Context menu actions
- `Preview page in clipnote`
- `Save page to clipnote`
- `Preview link in clipnote`
- `Save link to clipnote`

If you highlight text before saving, clipnote stores it under:

```md
## Selected excerpt
> ...
```

---

## Local HTTP API

The extension talks to a local server.

### Endpoints
- `GET /health`
- `POST /preview`
- `POST /save`
- `POST /open`

### Example
```bash
curl http://127.0.0.1:8765/health

curl -X POST http://127.0.0.1:8765/preview \
  -H 'Content-Type: application/json' \
  -H 'Origin: chrome-extension://dojaomlgohpahfibbdbjjnkkpbdoljnf' \
  -H 'X-Clipnote-Token: <token printed by clipnote_server.py>' \
  -d '{"url":"https://arxiv.org/abs/2604.11978"}'
```

---

## CLI reference

### Save
```bash
python3 clipnote.py save 'https://arxiv.org/abs/2604.11978' --dry-run
python3 clipnote.py save 'https://openai.com/index/gpt-5-5-instant/' --kind links
```

### Dedupe / cleanup
```bash
python3 clipnote.py dedupe
python3 clipnote.py dedupe --urls-only
python3 clipnote.py dedupe --recommend
python3 clipnote.py cleanup --urls-only
python3 clipnote.py cleanup --urls-only --apply
```

### Recap
```bash
python3 clipnote.py recap --week
python3 clipnote.py recap --week --anchor-date 2026-05-07
python3 clipnote.py recap --week --compare-previous
python3 clipnote.py recap --week --save-note
python3 clipnote.py recap --week --save-note --dry-run
```

---

## Notes

Right now this project is still an MVP, but the main workflow is already usable:
- discover something worth keeping
- preview/save it quickly
- clean up duplicates later
- review the week in recap form

---

## Next ideas
- richer body summarization
- source alias/person normalization
- better keyword weighting in recap compare
- optional arXiv affiliation handling
