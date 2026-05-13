const statusEl = document.getElementById('status');
const noticeEl = document.getElementById('notice');
const serverUrlEl = document.getElementById('serverUrl');
const authTokenEl = document.getElementById('authToken');
const urlEl = document.getElementById('url');
const selectedTextEl = document.getElementById('selectedText');
const aiSummaryEl = document.getElementById('aiSummary');
const titleOverrideEl = document.getElementById('titleOverride');
const kindEl = document.getElementById('kind');
const aiSummaryBtn = document.getElementById('aiSummaryBtn');
const previewBtn = document.getElementById('previewBtn');
const saveBtn = document.getElementById('saveBtn');
const openBtn = document.getElementById('openBtn');
const resultEl = document.getElementById('result');
const resultBadgesEl = document.getElementById('resultBadges');
const resultTitleEl = document.getElementById('resultTitle');
const resultKindEl = document.getElementById('resultKind');
const resultSourceEl = document.getElementById('resultSource');
const resultPathEl = document.getElementById('resultPath');
const resultTagsEl = document.getElementById('resultTags');
const resultSummaryEl = document.getElementById('resultSummary');
const resultDuplicateUrlsEl = document.getElementById('resultDuplicateUrls');
const resultDuplicateTitlesEl = document.getElementById('resultDuplicateTitles');
const DEFAULT_SERVER_URL = 'http://127.0.0.1:8765';
const REQUEST_TIMEOUT_MS = 15000;
const AI_SUMMARY_INPUT_LIMIT = 12000;
const ALLOWED_SERVER_HOSTS = new Set(['127.0.0.1', 'localhost']);
const ALLOWED_SERVER_PORT = '8765';
let openButtonMode = 'open';

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? '#fca5a5' : '#9ca3af';
}

function setNotice(message = '', kind = 'info') {
  if (!message) {
    noticeEl.className = 'notice hidden';
    noticeEl.textContent = '';
    return;
  }
  noticeEl.className = `notice ${kind}`;
  noticeEl.textContent = message;
}

function setBusy(isBusy) {
  aiSummaryBtn.disabled = isBusy;
  previewBtn.disabled = isBusy;
  saveBtn.disabled = isBusy;
  openBtn.disabled = isBusy;
  previewBtn.textContent = isBusy ? 'Working…' : 'Preview';
  saveBtn.textContent = isBusy ? 'Working…' : 'Save';
}

function setOpenButton(mode = 'open', visible = true) {
  openButtonMode = mode;
  openBtn.textContent = mode === 'existing' ? 'Open existing' : 'Open';
  openBtn.classList.toggle('hidden', !visible);
}

function normalizeServerUrl(raw) {
  let parsed;
  try {
    parsed = new URL(String(raw || '').trim());
  } catch (error) {
    throw new Error('Server URL must be http://127.0.0.1:8765 or http://localhost:8765');
  }
  if (parsed.protocol !== 'http:' || !ALLOWED_SERVER_HOSTS.has(parsed.hostname) || parsed.port !== ALLOWED_SERVER_PORT) {
    throw new Error('Server URL must be http://127.0.0.1:8765 or http://localhost:8765');
  }
  return parsed.origin;
}

async function getStoredServerUrl() {
  const stored = await chrome.storage.local.get(['aiNoteServerUrl']);
  try {
    return normalizeServerUrl(stored.aiNoteServerUrl || DEFAULT_SERVER_URL);
  } catch (error) {
    return DEFAULT_SERVER_URL;
  }
}

async function setStoredServerUrl(value) {
  const normalized = normalizeServerUrl(value);
  await chrome.storage.local.set({ aiNoteServerUrl: normalized });
  return normalized;
}

async function getStoredAuthToken() {
  const stored = await chrome.storage.local.get(['aiNoteAuthToken']);
  return stored.aiNoteAuthToken || '';
}

async function setStoredAuthToken(value) {
  await chrome.storage.local.set({ aiNoteAuthToken: value.trim() });
}

function payloadFromForm() {
  return {
    url: urlEl.value.trim(),
    kind: kindEl.value,
    titleOverride: titleOverrideEl.value.trim() || null,
    selectedText: selectedTextEl.value.trim() || '',
    summaryOverride: aiSummaryEl.value.trim() || '',
  };
}

function truncateAiSummaryInput(text) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  if (normalized.length <= AI_SUMMARY_INPUT_LIMIT) {
    return normalized;
  }
  return `${normalized.slice(0, AI_SUMMARY_INPUT_LIMIT).trim()}…`;
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) {
    throw new Error('Could not read current tab');
  }
  return tab;
}

async function extractActiveTabText(tabId) {
  const [injection] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const selected = window.getSelection?.()?.toString().trim() || '';
      if (selected) {
        return { text: selected, label: 'selected text' };
      }
      const article = document.querySelector('article, main');
      return { text: (article?.innerText || document.body?.innerText || '').trim(), label: 'page body' };
    },
  });
  const result = injection?.result;
  if (result && typeof result === 'object') {
    return {
      text: String(result.text || '').trim(),
      label: result.label === 'selected text' ? 'selected text' : 'page body',
    };
  }
  return { text: String(result || '').trim(), label: 'page body' };
}

async function getAiSummarySource() {
  const selectedText = selectedTextEl.value.trim();
  if (selectedText) {
    return { text: selectedText, label: 'selected text' };
  }
  const tab = await getActiveTab();
  const source = await extractActiveTabText(tab.id);
  if (!source.text) {
    throw new Error('No selected text or readable page body found');
  }
  return source;
}

async function createGeminiNanoSummary(text, onProgress = () => {}) {
  const summarizer = await createGeminiNanoSummarizer(onProgress);
  try {
    return await summarizeWithGeminiNano(summarizer, text);
  } finally {
    destroySummarizer(summarizer);
  }
}

async function createGeminiNanoSummarizer(onProgress = () => {}) {
  const summarizerApi = globalThis.Summarizer;
  if (!summarizerApi || typeof summarizerApi.availability !== 'function' || typeof summarizerApi.create !== 'function') {
    throw new Error('Chrome built-in Summarizer API is not available in this browser');
  }

  const availability = await summarizerApi.availability();
  if (availability === 'unavailable') {
    throw new Error('Gemini Nano summarization is unavailable on this device or Chrome profile');
  }
  if (availability === 'downloading') {
    onProgress('Downloading Gemini Nano…');
  } else if (availability === 'downloadable') {
    onProgress('Preparing Gemini Nano…');
  }

  return summarizerApi.create({
    type: 'tldr',
    format: 'plain-text',
    length: 'medium',
    monitor(monitor) {
      monitor?.addEventListener?.('downloadprogress', (event) => {
        if (typeof event.loaded === 'number') {
          onProgress(`Downloading Gemini Nano… ${Math.round(event.loaded * 100)}%`);
        }
      });
    },
  });
}

async function summarizeWithGeminiNano(summarizer, text) {
  const summary = await summarizer.summarize(truncateAiSummaryInput(text), {
    context: 'Summarize this web page content for a personal research note.',
  });
  const normalized = String(summary || '').trim();
  if (!normalized) {
    throw new Error('Gemini Nano returned an empty summary');
  }
  return normalized;
}

function destroySummarizer(summarizer) {
  if (summarizer && typeof summarizer.destroy === 'function') {
    summarizer.destroy();
  }
}

async function postJson(path, payload) {
  const base = normalizeServerUrl(serverUrlEl.value || DEFAULT_SERVER_URL);
  const headers = { 'Content-Type': 'application/json' };
  const token = authTokenEl.value.trim();
  if (token) {
    headers['X-Clipnote-Token'] = token;
  }
  const { response, data } = await fetchJson(`${base}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  return { ok: response.ok && !!data.ok, status: response.status, data };
}

async function fetchJson(url, options) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const text = await response.text();
    if (!text.trim()) {
      throw new Error('Local clipnote server returned an empty response');
    }
    let data;
    try {
      data = JSON.parse(text);
    } catch (error) {
      throw new Error('Local clipnote server returned a non-JSON response');
    }
    return { response, data };
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error('Local clipnote server timed out');
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function openSavedPath(path) {
  if (!path) {
    throw new Error('No saved path to open');
  }
  const { ok, data } = await postJson('/open', { path });
  if (!ok) {
    throw new Error(data.message || data.error || 'Open failed');
  }
}

function renderList(listEl, items, emptyText) {
  listEl.innerHTML = '';
  if (!items.length) {
    const li = document.createElement('li');
    li.textContent = emptyText;
    listEl.appendChild(li);
    return;
  }
  items.forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    listEl.appendChild(li);
  });
}

function renderBadges(preview) {
  resultBadgesEl.innerHTML = '';
  const totalDuplicates = (preview.duplicateUrls || []).length + (preview.duplicateTitles || []).length;
  const chips = [];
  chips.push({ label: preview.kind === 'papers' ? 'Paper' : preview.kind === 'links' ? 'Link' : 'Auto', kind: 'ok' });
  chips.push({ label: preview.source || 'Unknown source', kind: 'ok' });
  chips.push({ label: totalDuplicates ? `${totalDuplicates} duplicate${totalDuplicates > 1 ? 's' : ''}` : 'No duplicates', kind: totalDuplicates ? 'warn' : 'ok' });
  chips.forEach((chip) => {
    const span = document.createElement('span');
    span.className = `badge ${chip.kind}`;
    span.textContent = chip.label;
    resultBadgesEl.appendChild(span);
  });
}

function renderPreview(preview) {
  resultEl.classList.remove('hidden');
  setOpenButton('open', !!(preview.path || preview.relativePath));
  renderBadges(preview);
  resultTitleEl.textContent = preview.title || '-';
  resultKindEl.textContent = preview.kind || '-';
  resultSourceEl.textContent = preview.source || '-';
  resultPathEl.textContent = preview.relativePath || preview.path || '-';
  resultPathEl.dataset.fullPath = preview.path || '';
  resultTagsEl.textContent = (preview.tags || []).join(' ') || '-';
  resultSummaryEl.textContent = preview.summary || 'No summary';
  renderList(resultDuplicateUrlsEl, preview.duplicateUrls || [], 'None');
  renderList(resultDuplicateTitlesEl, preview.duplicateTitles || [], 'None');
}

async function runPreview() {
  const payload = payloadFromForm();
  if (!payload.url) {
    setStatus('URL is required', true);
    return;
  }
  setBusy(true);
  setStatus('Generating preview…');
  setNotice('');
  try {
    const { ok, data } = await postJson('/preview', payload);
    if (!ok) {
      throw new Error(data.message || data.error || 'Preview failed');
    }
    renderPreview(data.preview);
    setStatus('Preview ready');
    const duplicateCount = (data.preview.duplicateUrls || []).length + (data.preview.duplicateTitles || []).length;
    if (duplicateCount) {
      setNotice(`Found ${duplicateCount} duplicate candidate${duplicateCount > 1 ? 's' : ''}. Check before saving.`, 'info');
    }
  } catch (error) {
    setStatus(error.message || 'Preview failed', true);
    setNotice(error.message || 'Preview failed', 'error');
  } finally {
    setBusy(false);
  }
}

async function runSave() {
  const payload = payloadFromForm();
  if (!payload.url) {
    setStatus('URL is required', true);
    return;
  }
  setBusy(true);
  setStatus('Saving note…');
  setNotice('');
  try {
    const { ok, status, data } = await postJson('/save', payload);
    if (!ok) {
      if (data.preview) {
        renderPreview(data.preview);
      }
      if (status === 409) {
        setStatus('Note already exists', true);
        setOpenButton('existing', !!(data.preview?.path));
        setNotice('A note already exists at that path. You can open the existing note or change the title override.', 'info');
        return;
      }
      throw new Error(data.message || data.error || 'Save failed');
    }
    renderPreview(data.preview);
    setStatus(`Saved: ${data.relativePath}`);
    setNotice(`Saved successfully to ${data.relativePath}`, 'success');
    try {
      await openSavedPath(data.path);
      setNotice(`Saved and opened ${data.relativePath}`, 'success');
    } catch (openError) {
      setNotice(`Saved, but could not open note automatically: ${openError.message || openError}`, 'info');
    }
  } catch (error) {
    setStatus(error.message || 'Save failed', true);
    setNotice(error.message || 'Save failed', 'error');
  } finally {
    setBusy(false);
  }
}

async function runOpen() {
  const path = resultPathEl.dataset.fullPath || '';
  if (!path) {
    setNotice('Open is only available after preview/save returns a full path.', 'info');
    return;
  }
  setBusy(true);
  setStatus(openButtonMode === 'existing' ? 'Opening existing note…' : 'Opening note…');
  try {
    await openSavedPath(path);
    setStatus(openButtonMode === 'existing' ? 'Existing note opened' : 'Note opened');
    setNotice(openButtonMode === 'existing' ? 'Opened existing note in Obsidian/default app.' : 'Opened note in Obsidian/default app.', 'success');
  } catch (error) {
    setStatus(error.message || 'Open failed', true);
    setNotice(error.message || 'Open failed', 'error');
  } finally {
    setBusy(false);
  }
}

async function runAiSummary() {
  setBusy(true);
  setStatus('Preparing AI summary…');
  setNotice('');
  let summarizer = null;
  try {
    if (navigator.userActivation && !navigator.userActivation.isActive) {
      throw new Error('Click AI Summary to start Gemini Nano');
    }
    summarizer = await createGeminiNanoSummarizer((message) => {
      setStatus(message);
    });
    const source = await getAiSummarySource();
    setStatus(`Summarizing ${source.label}…`);
    const summary = await summarizeWithGeminiNano(summarizer, source.text);
    aiSummaryEl.value = summary;
    setStatus('AI summary ready');
    setNotice('AI summary is ready. Preview or save to use it in the note.', 'success');
  } catch (error) {
    setStatus(error.message || 'AI summary failed', true);
    setNotice(error.message || 'AI summary failed', 'error');
  } finally {
    destroySummarizer(summarizer);
    setBusy(false);
  }
}

async function loadCurrentTab() {
  try {
    const stored = await chrome.storage.local.get(['aiNotePendingPreview']);
    const pending = stored.aiNotePendingPreview;
    if (pending?.url) {
      urlEl.value = pending.url;
      selectedTextEl.value = pending.selectedText || '';
      aiSummaryEl.value = '';
      titleOverrideEl.value = '';
      await chrome.storage.local.remove(['aiNotePendingPreview']);
      setStatus('Loaded from context menu preview');
      await runPreview();
      return;
    }
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url) {
      setStatus('Could not read current tab', true);
      return;
    }
    urlEl.value = tab.url;
    selectedTextEl.value = '';
    aiSummaryEl.value = '';
    titleOverrideEl.value = '';
    setStatus('Current tab loaded');
    await runPreview();
  } catch (error) {
    setStatus(error.message || 'Failed to load current tab', true);
  }
}

serverUrlEl.addEventListener('change', async () => {
  try {
    serverUrlEl.value = await setStoredServerUrl(serverUrlEl.value);
    setNotice('');
  } catch (error) {
    setStatus(error.message || 'Invalid server URL', true);
    setNotice(error.message || 'Invalid server URL', 'error');
  }
});

authTokenEl.addEventListener('change', async () => {
  await setStoredAuthToken(authTokenEl.value);
});

aiSummaryBtn.addEventListener('click', runAiSummary);
previewBtn.addEventListener('click', runPreview);
saveBtn.addEventListener('click', runSave);
openBtn.addEventListener('click', runOpen);

document.addEventListener('DOMContentLoaded', async () => {
  const savedServerUrl = await getStoredServerUrl();
  if (savedServerUrl) {
    serverUrlEl.value = savedServerUrl;
  }
  authTokenEl.value = await getStoredAuthToken();
  loadCurrentTab();
});
