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
  Date,
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
        self.assertIn('id="aiSummaryLanguage"', html)
        self.assertIn('value="ko"', html)
        self.assertIn('value="original"', html)

    def test_popup_ui_exposes_vault_path_settings(self):
        html = (ROOT / "extension" / "popup.html").read_text(encoding="utf-8")

        self.assertIn('id="vaultPath"', html)
        self.assertIn('id="vaultPathBtn"', html)

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
            elements.vaultPath.value = '/Users/song/Obsidian/AI';

            const payload = payloadFromForm();

            assert.strictEqual(payload.summaryOverride, 'on-device summary');
            assert.strictEqual(Object.hasOwn(payload, 'vaultPath'), false);
            console.log(JSON.stringify(payload));
            """
        )

        payload = json.loads(output)
        self.assertEqual(payload["summaryOverride"], "on-device summary")
        self.assertNotIn("vaultPath", payload)

    def test_load_current_tab_populates_selected_text_from_active_tab_selection(self):
        output = run_popup_script(
            """
            fetch = async () => ({
              ok: true,
              status: 200,
              async text() {
                return JSON.stringify({
                  ok: true,
                  preview: {
                    title: 'Example',
                    kind: 'links',
                    source: 'example.com',
                    path: 'Links/Example.md',
                    relativePath: 'Links/Example.md',
                    tags: [],
                    summary: 'Summary',
                    duplicateUrls: [],
                    duplicateTitles: [],
                  },
                });
              },
            });
            chrome.scripting.executeScript = async (options) => {
              assert.strictEqual(options.target.tabId, 7);
              return [{ result: ' selected text from page ' }];
            };

            await loadCurrentTab();

            assert.strictEqual(elements.selectedText.value, 'selected text from page');
            console.log(elements.selectedText.value);
            """
        )

        self.assertEqual(output, "selected text from page")

    def test_load_current_tab_does_not_auto_preview_active_tab(self):
        output = run_popup_script(
            """
            let fetchCalls = 0;
            fetch = async () => {
              fetchCalls += 1;
              throw new Error('preview should wait for explicit click');
            };
            chrome.scripting.executeScript = async () => [{ result: ' selected text from page ' }];

            await loadCurrentTab();

            assert.strictEqual(elements.url.value, 'https://example.com/article');
            assert.strictEqual(elements.selectedText.value, 'selected text from page');
            assert.strictEqual(fetchCalls, 0);
            console.log('loaded');
            """
        )

        self.assertEqual(output, "loaded")

    def test_pending_preview_loads_fields_without_auto_preview(self):
        output = run_popup_script(
            """
            const pending = {
              url: 'https://example.com/from-menu',
              selectedText: 'selected from context menu',
              at: Date.now(),
            };
            let fetchCalls = 0;
            let removedKey = '';
            fetch = async () => {
              fetchCalls += 1;
              throw new Error('preview should wait for explicit click');
            };
            chrome.storage.local.get = async (keys) => {
              if (Array.isArray(keys) && keys.includes('aiNotePendingPreview')) {
                return { aiNotePendingPreview: pending };
              }
              return {};
            };
            chrome.storage.local.remove = async (keys) => {
              removedKey = Array.isArray(keys) ? keys.join(',') : String(keys);
            };

            await loadCurrentTab();

            assert.strictEqual(elements.url.value, 'https://example.com/from-menu');
            assert.strictEqual(elements.selectedText.value, 'selected from context menu');
            assert.strictEqual(fetchCalls, 0);
            assert.strictEqual(removedKey, 'aiNotePendingPreview');
            console.log('pending loaded');
            """
        )

        self.assertEqual(output, "pending loaded")

    def test_stale_pending_preview_is_discarded_without_reusing_selected_text(self):
        output = run_popup_script(
            """
            const stalePending = {
              url: 'https://old.example/private',
              selectedText: 'stale selected secret',
              at: Date.now() - 10 * 60 * 1000,
            };
            let removedKey = '';
            chrome.storage.local.get = async (keys) => {
              if (Array.isArray(keys) && keys.includes('aiNotePendingPreview')) {
                return { aiNotePendingPreview: stalePending };
              }
              return {};
            };
            chrome.storage.local.remove = async (keys) => {
              removedKey = Array.isArray(keys) ? keys.join(',') : String(keys);
            };
            chrome.scripting.executeScript = async () => [{ result: ' fresh selected text ' }];

            await loadCurrentTab();

            assert.strictEqual(elements.url.value, 'https://example.com/article');
            assert.strictEqual(elements.selectedText.value, 'fresh selected text');
            assert.strictEqual(removedKey, 'aiNotePendingPreview');
            console.log(elements.selectedText.value);
            """
        )

        self.assertEqual(output, "fresh selected text")

    def test_save_vault_path_settings_posts_to_settings_endpoint(self):
        output = run_popup_script(
            """
            elements.serverUrl.value = 'http://127.0.0.1:8765';
            elements.authToken.value = 'secret';
            elements.vaultPath.value = ' /Users/song/Obsidian/AI ';
            fetch = async (url, options) => {
              assert.strictEqual(url, 'http://127.0.0.1:8765/settings');
              assert.strictEqual(options.headers['X-Clipnote-Token'], 'secret');
              assert.strictEqual(JSON.parse(options.body).vaultPath, '/Users/song/Obsidian/AI');
              return {
                ok: true,
                status: 200,
                async text() {
                  return JSON.stringify({ ok: true, vaultPath: '/Users/song/Obsidian/AI' });
                },
              };
            };

            await saveVaultPathSettings();

            assert.strictEqual(elements.vaultPath.value, '/Users/song/Obsidian/AI');
            console.log(elements.vaultPath.value);
            """
        )

        self.assertEqual(output, "/Users/song/Obsidian/AI")

    def test_clear_auth_token_removes_stored_token(self):
        output = run_popup_script(
            """
            let removedKey = '';
            chrome.storage.local.remove = async (keys) => {
              removedKey = Array.isArray(keys) ? keys.join(',') : String(keys);
            };
            elements.authToken.value = 'secret';

            await clearAuthToken();

            assert.strictEqual(elements.authToken.value, '');
            assert.strictEqual(removedKey, 'aiNoteAuthToken');
            console.log('cleared');
            """
        )

        self.assertEqual(output, "cleared")

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

    def test_original_summary_language_does_not_call_translator(self):
        output = run_popup_script(
            """
            elements.aiSummaryLanguage.value = 'original';
            elements.selectedText.value = 'Original page text';
            Translator = {
              async create() {
                throw new Error('translator should not be created for original summaries');
              },
            };
            Summarizer = {
              async availability() {
                return 'available';
              },
              async create() {
                return {
                  async summarize() {
                    return 'English summary';
                  },
                  destroy() {},
                };
              },
            };

            await runAiSummary();

            assert.strictEqual(elements.aiSummary.value, 'English summary');
            console.log(elements.aiSummary.value);
            """
        )

        self.assertEqual(output, "English summary")

    def test_korean_summary_language_translates_summary(self):
        output = run_popup_script(
            """
            const order = [];
            elements.aiSummaryLanguage.value = 'ko';
            elements.selectedText.value = 'Original page text';
            Summarizer = {
              async availability() {
                order.push('summarizerAvailability');
                return 'available';
              },
              async create() {
                order.push('summarizerCreate');
                return {
                  async summarize() {
                    order.push('summarize');
                    return 'English summary';
                  },
                  destroy() {},
                };
              },
            };
            Translator = {
              async availability(options) {
                order.push(options.sourceLanguage + ':' + options.targetLanguage + ':availability');
                return 'available';
              },
              async create(options) {
                order.push(options.sourceLanguage + ':' + options.targetLanguage + ':create');
                return {
                  async translate(text) {
                    order.push('translate:' + text);
                    return '한국어 요약';
                  },
                  destroy() {},
                };
              },
            };

            await runAiSummary();

            assert.strictEqual(elements.aiSummary.value, '한국어 요약');
            assert.deepStrictEqual(order, [
              'en:ko:availability',
              'en:ko:create',
              'summarizerAvailability',
              'summarizerCreate',
              'summarize',
              'translate:English summary',
            ]);
            console.log(elements.aiSummary.value);
            """
        )

        self.assertEqual(output, "한국어 요약")

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
