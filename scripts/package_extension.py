#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "extension"
REQUIRED_FILES = [
    "manifest.json",
    "background.js",
    "popup.html",
    "popup.css",
    "popup.js",
    "icon-16.png",
    "icon-32.png",
    "icon-48.png",
    "icon-128.png",
]
ICON_SIZES = ("16", "32", "48", "128")


def load_manifest() -> dict:
    manifest_path = EXTENSION_DIR / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def validate_extension() -> dict:
    missing = [name for name in REQUIRED_FILES if not (EXTENSION_DIR / name).exists()]
    if missing:
        raise SystemExit("Missing extension files: " + ", ".join(missing))

    manifest = load_manifest()
    for size in ICON_SIZES:
        expected = f"icon-{size}.png"
        if manifest.get("icons", {}).get(size) != expected:
            raise SystemExit(f"manifest icons.{size} must be {expected}")
        if manifest.get("action", {}).get("default_icon", {}).get(size) != expected:
            raise SystemExit(f"manifest action.default_icon.{size} must be {expected}")
    return manifest


def package_extension(output: Path) -> Path:
    manifest = validate_extension()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in REQUIRED_FILES:
            archive.write(EXTENSION_DIR / name, arcname=name)
    print(f"packaged clipnote extension {manifest['version']}: {output}")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and package the clipnote Chrome extension")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "clipnote-extension.zip")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    package_extension(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
