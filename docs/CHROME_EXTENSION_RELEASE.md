# Chrome Extension Release

## Package

```bash
python3 scripts/package_extension.py --output dist/clipnote-extension.zip
```

The packaging script validates:
- `manifest.json`
- background and popup files
- 16, 32, 48, and 128px icons
- top-level `icons`
- `action.default_icon`

## Permissions

The extension requests:
- `activeTab` for user-invoked current-tab capture
- `contextMenus` for page/link capture actions
- `notifications` for background save feedback
- `storage` for server URL and auth token settings

Host permissions are limited to:
- `http://127.0.0.1:8765/*`
- `http://localhost:8765/*`

## Version

Before packaging, keep these versions aligned unless the extension is intentionally released separately:
- `clipnote.__version__` in `clipnote.py`
- `version` in `pyproject.toml`
- `version` in `extension/manifest.json`

## Smoke Test

1. Start `clipnote-server`.
2. Load the packaged extension or unpacked `extension/` directory.
3. Confirm the toolbar icon renders.
4. Confirm `chrome://extensions` shows the clipnote icon.
5. Paste the current auth token into the popup.
6. Preview and save a normal page.
7. Preview and save a link target.
8. Highlight page text, use the page action, and confirm `## Selected excerpt` is saved.
9. Save the same page twice and confirm the existing-note conflict path.

