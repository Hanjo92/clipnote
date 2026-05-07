const DEFAULT_SERVER_URL = 'http://127.0.0.1:8765';
const MENU_PREVIEW_PAGE = 'clipnote-preview-page';
const MENU_PREVIEW_LINK = 'clipnote-preview-link';
const MENU_SAVE_PAGE = 'clipnote-save-page';
const MENU_SAVE_LINK = 'clipnote-save-link';

function createMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_PREVIEW_PAGE,
      title: 'Preview page in clipnote',
      contexts: ['page']
    });
    chrome.contextMenus.create({
      id: MENU_SAVE_PAGE,
      title: 'Save page to clipnote',
      contexts: ['page']
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
  return String(raw).trim().replace(/\/$/, '');
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
  const response = await fetch(`${base}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, kind, selectedText }),
  });
  const data = await response.json();
  return { ok: response.ok && !!data.ok, status: response.status, data };
}

async function openSavedPath(path) {
  const base = await getServerUrl();
  const response = await fetch(`${base}/open`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  const data = await response.json();
  return { ok: response.ok && !!data.ok, status: response.status, data };
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
