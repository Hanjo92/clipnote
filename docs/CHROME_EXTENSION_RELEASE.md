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
- `scripting` for selected-text capture and on-device AI page-body extraction after user action
- `storage` for server URL and auth token settings

Host permissions are limited to:
- `http://127.0.0.1:8765/*`
- `http://localhost:8765/*`

## Data Flow

- Preview/save sends the page URL, note kind, selected text, title override, and optional generated summary override to the local clipnote server.
- Opening the popup loads the current tab details locally; the local server is contacted only after an explicit **Preview** or **Save** action.
- **Selected text** is sent to the local server when previewing or saving so it can be written under `## Selected excerpt`.
- **AI page-body fallback** runs only after the user clicks **AI Summary**. The page body is read in Chrome for on-device summarization and is not sent to the local server.
- **AI summary override** is sent to the local server only after the user clicks **Preview** or **Save**.
- The trusted vault path is updated through the authenticated local `/settings` route; preview/save payloads do not choose arbitrary vault paths.

## Security Notes

- Keep the auth token private. With the token, a local client can preview/save notes and update the trusted vault path.
- The server rejects loopback, localhost, private-network, link-local, multicast, reserved, and unresolved redirect targets before fetching user-provided URLs.
- The trusted vault path setting accepts existing directories. For broader public distribution, consider requiring an Obsidian vault marker such as `.obsidian`.

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
10. Click **AI Summary** with **Korean** selected and confirm only the generated summary is used as the note summary override.
11. Update **Vault path** in the popup and confirm preview/save writes under that trusted path.
