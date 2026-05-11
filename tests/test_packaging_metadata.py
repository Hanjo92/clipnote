from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PackagingMetadataTest(unittest.TestCase):
    def test_pyproject_declares_project_and_entry_points(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('name = "clipnote"', pyproject)
        self.assertIn('requires-python = ">=3.9"', pyproject)
        self.assertIn("clipnote = \"clipnote:main\"", pyproject)
        self.assertIn("clipnote-server = \"clipnote_server:main\"", pyproject)
        self.assertIn("[project.optional-dependencies]", pyproject)
        self.assertIn("dev =", pyproject)

    def test_versions_are_documented_and_aligned(self):
        clipnote_source = (ROOT / "clipnote.py").read_text(encoding="utf-8")
        server_source = (ROOT / "clipnote_server.py").read_text(encoding="utf-8")
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        version = re.search(r'__version__ = "([^"]+)"', clipnote_source).group(1)
        self.assertEqual(version, manifest["version"])
        self.assertIn(f'version = "{version}"', pyproject)
        self.assertIn("clipnote.__version__", server_source)
        self.assertIn("USER_AGENT = f\"clipnote/{__version__}", clipnote_source)

    def test_release_docs_exist(self):
        self.assertTrue((ROOT / "CHANGELOG.md").exists())
        self.assertTrue((ROOT / "docs" / "RELEASE_CHECKLIST.md").exists())


if __name__ == "__main__":
    unittest.main()
