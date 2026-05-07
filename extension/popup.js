const statusEl = document.getElementById('status');
const noticeEl = document.getElementById('notice');
const serverUrlEl = document.getElementById('serverUrl');
const urlEl = document.getElementById('url');
const selectedTextEl = document.getElementById('selectedText');
const titleOverrideEl = document.getElementById('titleOverride');
const kindEl = document.getElementById('kind');
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
  return raw.trim().replace(/\/$/, '');
}

async function getStoredServerUrl() {
  const stored = await chrome.storage.local.get(['aiNoteServerUrl']);
  return stored.aiNoteServerUrl || 'http://127.0.0.1:8765';
}

async function setStoredServerUrl(value) {
  await chrome.storage.local.set({ aiNoteServerUrl: value.trim() });
}

function payloadFromForm() {
  return {
    url: urlEl.value.trim(),
    kind: kindEl.value,
    titleOverride: titleOverrideEl.value.trim() || null,
    selectedText: selectedTextEl.value.trim() || '',
  };
}

async function postJson(path, payload) {
  const base = normalizeServerUrl(serverUrlEl.value || 'http://127.0.0.1:8765');
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  return { ok: response.ok && !!data.ok, status: response.status, data };
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

async function loadCurrentTab() {
  try {
    const stored = await chrome.storage.local.get(['aiNotePendingPreview']);
    const pending = stored.aiNotePendingPreview;
    if (pending?.url) {
      urlEl.value = pending.url;
      selectedTextEl.value = pending.selectedText || '';
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
    titleOverrideEl.value = '';
    setStatus('Current tab loaded');
    await runPreview();
  } catch (error) {
    setStatus(error.message || 'Failed to load current tab', true);
  }
}

serverUrlEl.addEventListener('change', async () => {
  await setStoredServerUrl(serverUrlEl.value);
});

previewBtn.addEventListener('click', runPreview);
saveBtn.addEventListener('click', runSave);
openBtn.addEventListener('click', runOpen);

document.addEventListener('DOMContentLoaded', async () => {
  const savedServerUrl = await getStoredServerUrl();
  if (savedServerUrl) {
    serverUrlEl.value = savedServerUrl;
  }
  loadCurrentTab();
});
