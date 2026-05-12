from __future__ import annotations

import json
from pathlib import Path
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


def run_popup_script(script_body: str) -> str:
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const elements = {};
function makeElement(id) {
  return {
    id,
    value: '',
    textContent: '',
    className: '',
    innerHTML: '',
    disabled: false,
    style: {},
    dataset: {},
    classList: {
      add() {},
      remove() {},
      toggle() {},
    },
    appendChild() {},
    addEventListener() {},
  };
}

function element(id) {
  if (!elements[id]) {
    elements[id] = makeElement(id);
  }
  return elements[id];
}

const context = {
  AbortController,
  Error,
  JSON,
  Promise,
  Set,
  URL,
  assert,
  clearTimeout,
  console,
  elements,
  process,
  fetch: async () => {
    throw new Error('fetch should not be called in these popup unit tests');
  },
  navigator: { userActivation: { isActive: true } },
  setTimeout,
  document: {
    getElementById: element,
    createElement: makeElement,
    addEventListener() {},
  },
  chrome: {
    storage: {
      local: {
        async get() { return {}; },
        async set() {},
        async remove() {},
      },
    },
    tabs: {
      async query() { return [{ id: 7, url: 'https://example.com/article' }]; },
    },
    scripting: {
      async executeScript() {
        return [{ result: 'Visible page body from the active tab.' }];
      },
    },
  },
};
context.globalThis = context;

vm.createContext(context);
vm.runInContext(fs.readFileSync('extension/popup.js', 'utf8'), context);
vm.runInContext(`
(async () => {
${script_body}
})().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
`, context);
"""
    script = harness.replace("${script_body}", textwrap.dedent(script_body))
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


class ExtensionAiSummaryTest(unittest.TestCase):
    def test_popup_ui_exposes_ai_summary_controls(self):
        html = (ROOT / "extension" / "popup.html").read_text(encoding="utf-8")

        self.assertIn('id="aiSummary"', html)
        self.assertIn('id="aiSummaryBtn"', html)

    def test_manifest_uses_scripting_permission_for_page_body_fallback(self):
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))

        self.assertIn("scripting", manifest["permissions"])

    def test_payload_includes_ai_summary_override(self):
        output = run_popup_script(
            """
            elements.url.value = ' https://example.com/article ';
            elements.kind.value = 'links';
            elements.titleOverride.value = ' Optional title ';
            elements.selectedText.value = ' selected excerpt ';
            elements.aiSummary.value = ' on-device summary ';

            const payload = payloadFromForm();

            assert.strictEqual(payload.summaryOverride, 'on-device summary');
            console.log(JSON.stringify(payload));
            """
        )

        payload = json.loads(output)
        self.assertEqual(payload["summaryOverride"], "on-device summary")

    def test_ai_summary_source_prefers_selected_text(self):
        output = run_popup_script(
            """
            elements.selectedText.value = ' selected excerpt ';
            chrome.scripting.executeScript = async () => {
              throw new Error('page body should not be read when selected text exists');
            };

            const source = await getAiSummarySource();

            assert.deepStrictEqual(source, { text: 'selected excerpt', label: 'selected text' });
            console.log(source.label);
            """
        )

        self.assertEqual(output, "selected text")

    def test_ai_summary_source_falls_back_to_active_tab_body(self):
        output = run_popup_script(
            """
            elements.selectedText.value = '';
            let targetTabId = null;
            chrome.scripting.executeScript = async (options) => {
              targetTabId = options.target.tabId;
              return [{ result: ' Visible page body from the active tab. ' }];
            };

            const source = await getAiSummarySource();

            assert.strictEqual(targetTabId, 7);
            assert.deepStrictEqual(source, {
              text: 'Visible page body from the active tab.',
              label: 'page body',
            });
            console.log(source.label);
            """
        )

        self.assertEqual(output, "page body")

    def test_gemini_summary_rejects_when_summarizer_api_is_missing(self):
        output = run_popup_script(
            """
            Summarizer = undefined;
            try {
              await createGeminiNanoSummary('content');
            } catch (error) {
              assert.match(error.message, /Chrome built-in Summarizer API is not available/);
              console.log('missing');
            }
            """
        )

        self.assertEqual(output, "missing")

    def test_gemini_summary_invokes_chrome_summarizer(self):
        output = run_popup_script(
            """
            let availabilityCalled = false;
            let destroyCalled = false;
            let summarizedText = null;
            Summarizer = {
              async availability() {
                availabilityCalled = true;
                return 'available';
              },
              async create(options) {
                assert.strictEqual(options.type, 'tldr');
                assert.strictEqual(options.format, 'plain-text');
                assert.strictEqual(options.length, 'medium');
                return {
                  async summarize(text) {
                    summarizedText = text;
                    return 'On-device summary';
                  },
                  destroy() {
                    destroyCalled = true;
                  },
                };
              },
            };

            const summary = await createGeminiNanoSummary('Original page text');

            assert.strictEqual(availabilityCalled, true);
            assert.strictEqual(summarizedText, 'Original page text');
            assert.strictEqual(summary, 'On-device summary');
            assert.strictEqual(destroyCalled, true);
            console.log(summary);
            """
        )

        self.assertEqual(output, "On-device summary")

    def test_ai_summary_button_creates_summarizer_before_body_fallback(self):
        output = run_popup_script(
            """
            const order = [];
            elements.selectedText.value = '';
            chrome.scripting.executeScript = async () => {
              order.push('executeScript');
              return [{ result: { text: 'Visible page body.', label: 'page body' } }];
            };
            Summarizer = {
              async availability() {
                order.push('availability');
                return 'available';
              },
              async create() {
                order.push('create');
                return {
                  async summarize() {
                    order.push('summarize');
                    return 'On-device summary';
                  },
                  destroy() {},
                };
              },
            };

            await runAiSummary();

            assert.deepStrictEqual(order, ['availability', 'create', 'executeScript', 'summarize']);
            assert.strictEqual(elements.aiSummary.value, 'On-device summary');
            console.log(order.join(','));
            """
        )

        self.assertEqual(output, "availability,create,executeScript,summarize")


if __name__ == "__main__":
    unittest.main()
