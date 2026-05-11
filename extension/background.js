const DEFAULT_SERVER_URL = 'http://127.0.0.1:8765';
const REQUEST_TIMEOUT_MS = 15000;
const ALLOWED_SERVER_HOSTS = new Set(['127.0.0.1', 'localhost']);
const ALLOWED_SERVER_PORT = '8765';
const MENU_PREVIEW_PAGE = 'clipnote-preview-page';
const MENU_PREVIEW_LINK = 'clipnote-preview-link';
const MENU_SAVE_PAGE = 'clipnote-save-page';
const MENU_SAVE_LINK = 'clipnote-save-link';

function createMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_PREVIEW_PAGE,
      title: 'Preview page in clipnote',
      contexts: ['page', 'selection']
    });
    chrome.contextMenus.create({
      id: MENU_SAVE_PAGE,
      title: 'Save page to clipnote',
      contexts: ['page', 'selection']
    });
    chrome.contextMenus.create({
      id: MENU_PREVIEW_LINK,
      title: 'Preview link in clipnote',
      contexts: ['link']
    });
    chrome.contextMenus.create({
      id: MENU_SAVE_LINK,
      title: 'Save link to clipnote',
      contexts: ['link']
    });
  });
}

async function openPopupPreview(url, selectedText = '') {
  await chrome.storage.local.set({
    aiNotePendingPreview: {
      url,
      selectedText,
      at: Date.now(),
    },
  });
  await chrome.action.openPopup();
}

async function getServerUrl() {
  const stored = await chrome.storage.local.get(['aiNoteServerUrl']);
  const raw = stored.aiNoteServerUrl || DEFAULT_SERVER_URL;
  return normalizeServerUrl(raw);
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

async function getAuthHeaders() {
  const stored = await chrome.storage.local.get(['aiNoteAuthToken']);
  const token = String(stored.aiNoteAuthToken || '').trim();
  const headers = { 'Content-Type': 'application/json' };
  if (token) {
    headers['X-Clipnote-Token'] = token;
  }
  return headers;
}

async function notify(title, message) {
  await chrome.notifications.create({
    type: 'basic',
    iconUrl: 'icon-128.png',
    title,
    message,
  });
}

async function saveUrl(url, kind = 'auto', selectedText = '') {
  const base = await getServerUrl();
  const { response, data } = await postJson(`${base}/save`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify({ url, kind, selectedText }),
  });
  return { ok: response.ok && !!data.ok, status: response.status, data };
}

async function openSavedPath(path) {
  const base = await getServerUrl();
  const { response, data } = await postJson(`${base}/open`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify({ path }),
  });
  return { ok: response.ok && !!data.ok, status: response.status, data };
}

async function postJson(url, options) {
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

chrome.runtime.onInstalled.addListener(() => {
  createMenus();
});

chrome.runtime.onStartup.addListener(() => {
  createMenus();
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  const isLink = info.menuItemId === MENU_SAVE_LINK || info.menuItemId === MENU_PREVIEW_LINK;
  const isPreview = info.menuItemId === MENU_PREVIEW_PAGE || info.menuItemId === MENU_PREVIEW_LINK;
  const url = isLink ? info.linkUrl : info.pageUrl;
  const selectedText = info.selectionText || '';
  if (!url) {
    await notify('clipnote', 'No URL found for this menu action.');
    return;
  }
  if (isPreview) {
    try {
      await openPopupPreview(url, selectedText);
    } catch (error) {
      await notify('clipnote', error?.message || 'Could not open preview popup');
    }
    return;
  }
  try {
    const { ok, status, data } = await saveUrl(url, 'auto', selectedText);
    if (ok) {
      const suffix = selectedText ? ' (with selection)' : '';
      const opened = await openSavedPath(data.path).catch(() => ({ ok: false }));
      const openSuffix = opened.ok ? ' and opened note' : '';
      await notify('clipnote', `Saved: ${data.relativePath}${suffix}${openSuffix}`);
      return;
    }
    if (status === 409) {
      await notify('clipnote', 'A note already exists for that save path.');
      return;
    }
    await notify('clipnote', data.message || data.error || 'Save failed');
  } catch (error) {
    await notify('clipnote', error?.message || 'Could not reach local clipnote server');
  }
});
