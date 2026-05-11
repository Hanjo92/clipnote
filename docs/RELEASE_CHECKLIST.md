# Release Checklist

Use this checklist for every production release.

## Version

- Update `clipnote.__version__` in `clipnote.py`.
- Match `pyproject.toml` project version to `clipnote.__version__`.
- Match `extension/manifest.json` version to `clipnote.__version__`, or document why the extension ships separately.
- Add release notes to `CHANGELOG.md`.

## Verify

```bash
python3 -m unittest discover -s tests
python3 -m py_compile clipnote.py clipnote_server.py
python3 -m json.tool extension/manifest.json >/dev/null
node --check extension/background.js
node --check extension/popup.js
python3 -m pip wheel . -w /tmp/clipnote-wheel --no-deps
python3 scripts/package_extension.py --output /tmp/clipnote-extension.zip
```

## Package

- Build the Python wheel.
- Package the Chrome extension release zip.
- Confirm required extension assets are present.

## Publish

- Tag the release as `vX.Y.Z`.
- Attach Python and extension artifacts.
- Confirm install or refresh with `pipx install .` or `pipx install --force .`.
