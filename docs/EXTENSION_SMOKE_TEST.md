# Chrome Extension Manual Smoke Test

Run this checklist before publishing an extension release. CI covers syntax,
manifest validity, assets, and packaging; this checklist covers browser behavior
that requires Chrome APIs.

## Setup

- Start the local server and keep the terminal open:

```bash
clipnote-server
```

- Copy the current server auth token.
- Open an `http` or `https` test page with selectable body text and at least one
  normal link.
- Open `chrome://extensions`, enable **Developer mode**, choose **Load
  unpacked**, and select the repository `extension/` directory.
- Confirm the clipnote toolbar icon renders and the extension details page shows
  no load errors.

## Popup Flow

- Open the popup from the toolbar on the test page.
- Confirm **URL** is filled with the current tab URL.
- Select text on the page, reopen the popup, and confirm **Selected text** is
  filled.
- Enter `http://127.0.0.1:8765` as **Server**.
- Paste the current server auth token.
- Set **Vault path** to the test Obsidian vault or test notes directory.
- Click **Preview** and confirm the preview result shows title, kind, path,
  summary, tags, and duplicate sections.
- Click **Save** and confirm a saved-path success notice appears.
- Click **Open** and confirm the saved note opens in Obsidian or the default app.
- Save the same page again and confirm the existing-note conflict path is shown
  without overwriting the note.

## Context Menu Flow

- Right-click the page and choose **Preview page in clipnote**.
- Confirm the popup opens with the page URL and any selected text.
- Right-click the page and choose **Save page to clipnote**.
- Confirm a Chrome notification reports the save result.
- Right-click a normal link and choose **Preview link in clipnote**.
- Confirm the popup opens with the link URL, not the current page URL.
- Right-click a normal link and choose **Save link to clipnote**.
- Confirm a Chrome notification reports the save result.

## Pending Preview TTL

Context-menu preview data should only be used briefly.

- Trigger **Preview page in clipnote** from the context menu and confirm the
  fresh pending preview is loaded.
- In the extension DevTools console, seed a stale pending preview:

```js
chrome.storage.local.set({
  aiNotePendingPreview: {
    url: "https://example.com/stale-preview",
    selectedText: "stale text",
    at: Date.now() - 3 * 60 * 1000,
  },
});
```

- Open the popup on a different current tab.
- Confirm the stale URL and stale selected text are ignored, and the current tab
  is loaded instead.

## AI Summary Flow

Run the states that are available on the test Chrome profile.

- **Unavailable:** In a profile/browser where `Summarizer` or `Translator` is not
  available, click **AI Summary** and confirm a clear unavailable message is
  shown.
- **Downloadable/downloading:** In a profile where Gemini Nano or the Korean
  translator is downloadable but not ready, click **AI Summary** and confirm the
  popup shows preparing/downloading progress and remains usable.
- **Ready, original language:** Choose **Original**, click **AI Summary**, and
  confirm the generated text fills **AI summary**.
- **Ready, Korean:** Choose **Korean**, click **AI Summary**, and confirm the
  generated Korean text fills **AI summary**.
- After a ready summary, click **Preview** or **Save** and confirm the note uses
  the AI summary override.
