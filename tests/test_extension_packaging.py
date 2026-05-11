from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class ExtensionPackagingTest(unittest.TestCase):
    def test_manifest_declares_icons_and_action_icons(self):
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))

        for size in ("16", "32", "48", "128"):
            self.assertEqual(manifest["icons"][size], f"icon-{size}.png")
            self.assertEqual(manifest["action"]["default_icon"][size], f"icon-{size}.png")

    def test_required_icon_assets_exist(self):
        for size in (16, 32, 48, 128):
            self.assertTrue((ROOT / "extension" / f"icon-{size}.png").exists())

    def test_package_extension_script_creates_zip(self):
        output = Path(tempfile.gettempdir()) / "clipnote-extension-test.zip"
        if output.exists():
            output.unlink()

        subprocess.run(
            ["python3", str(ROOT / "scripts" / "package_extension.py"), "--output", str(output)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        with zipfile.ZipFile(output) as archive:
            names = set(archive.namelist())

        self.assertIn("manifest.json", names)
        self.assertIn("background.js", names)
        self.assertIn("popup.js", names)
        self.assertIn("icon-16.png", names)
        self.assertIn("icon-32.png", names)
        self.assertIn("icon-48.png", names)
        self.assertIn("icon-128.png", names)

    def test_chrome_extension_release_doc_exists(self):
        self.assertTrue((ROOT / "docs" / "CHROME_EXTENSION_RELEASE.md").exists())


if __name__ == "__main__":
    unittest.main()
