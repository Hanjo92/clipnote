from __future__ import annotations

from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ExtensionAuthTokenTest(unittest.TestCase):
    def test_manifest_uses_active_tab_without_tabs_permission(self):
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))

        self.assertIn("activeTab", manifest["permissions"])
        self.assertNotIn("tabs", manifest["permissions"])

    def test_manifest_declares_open_popup_minimum_chrome_version(self):
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))

        self.assertGreaterEqual(int(manifest["minimum_chrome_version"]), 127)

    def test_popup_exposes_auth_token_field(self):
        html = (ROOT / "extension" / "popup.html").read_text(encoding="utf-8")

        self.assertIn('id="authToken"', html)

    def test_popup_exposes_auth_token_clear_control(self):
        html = (ROOT / "extension" / "popup.html").read_text(encoding="utf-8")

        self.assertIn('id="authTokenClearBtn"', html)

    def test_popup_sends_clipnote_auth_header(self):
        script = (ROOT / "extension" / "popup.js").read_text(encoding="utf-8")

        self.assertIn("aiNoteAuthToken", script)
        self.assertIn("X-Clipnote-Token", script)

    def test_background_sends_clipnote_auth_header(self):
        script = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")

        self.assertIn("aiNoteAuthToken", script)
        self.assertIn("X-Clipnote-Token", script)


if __name__ == "__main__":
    unittest.main()
