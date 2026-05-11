from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ExtensionContextMenuTest(unittest.TestCase):
    def test_page_preview_and_save_are_available_for_selection_context(self):
        script = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")

        self.assertIn("contexts: ['page', 'selection']", script)
        self.assertIn("const selectedText = info.selectionText || '';", script)

    def test_link_actions_remain_link_targeted(self):
        script = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")

        self.assertIn("contexts: ['link']", script)
        self.assertIn("const url = isLink ? info.linkUrl : info.pageUrl;", script)


if __name__ == "__main__":
    unittest.main()
