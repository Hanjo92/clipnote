from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read_script(name: str) -> str:
    return (ROOT / "extension" / name).read_text(encoding="utf-8")


class ExtensionNetworkHardeningTest(unittest.TestCase):
    def test_popup_validates_and_normalizes_local_server_url(self):
        script = read_script("popup.js")

        self.assertIn("normalizeServerUrl", script)
        self.assertIn("new URL", script)
        self.assertIn("127.0.0.1", script)
        self.assertIn("localhost", script)
        self.assertIn("8765", script)
        self.assertIn("Server URL must be", script)

    def test_background_validates_and_normalizes_local_server_url(self):
        script = read_script("background.js")

        self.assertIn("normalizeServerUrl", script)
        self.assertIn("new URL", script)
        self.assertIn("127.0.0.1", script)
        self.assertIn("localhost", script)
        self.assertIn("8765", script)
        self.assertIn("Server URL must be", script)

    def test_popup_fetch_uses_timeout_and_non_json_guard(self):
        script = read_script("popup.js")

        self.assertIn("REQUEST_TIMEOUT_MS", script)
        self.assertIn("AbortController", script)
        self.assertIn("response.text()", script)
        self.assertIn("JSON.parse", script)
        self.assertNotIn("response.json()", script)

    def test_background_fetch_uses_timeout_and_non_json_guard(self):
        script = read_script("background.js")

        self.assertIn("REQUEST_TIMEOUT_MS", script)
        self.assertIn("AbortController", script)
        self.assertIn("response.text()", script)
        self.assertIn("JSON.parse", script)
        self.assertNotIn("response.json()", script)


if __name__ == "__main__":
    unittest.main()
