# clipnote Chrome Extension Quickstart

This is the fastest way to get the extension working locally.

Requirement:
- Chrome 127 or newer

## 1) Start the local server

```bash
cd ~/Projects/clipnote
python3 clipnote_server.py
```

Leave this terminal running. The server prints an `auth token`; copy it for the extension popup.

---

## 2) Load the extension in Chrome

1. Open `chrome://extensions`
2. Turn on **Developer mode**
3. Click **Load unpacked**
4. Select:

```text
~/Projects/clipnote/extension
```

Expected extension ID:

```text
dojaomlgohpahfibbdbjjnkkpbdoljnf
```

If you change extension files later, click **Reload** on the extension card.

Expected permission shape:
- active tab access after clicking clipnote
- context menus, notifications, scripting, and storage
- localhost/127.0.0.1 access for the local server

---

## 3) First popup test

1. Open any article or paper page
2. Click the clipnote extension icon
3. Paste the server `auth token` into the popup field
4. Click **Preview**
5. Confirm that the popup:
   - loads the current tab URL
   - shows a preview
   - shows duplicates if they exist
6. Click **Save**
7. Confirm the note saves and opens

---

## 4) Context menu test

### Preview a page
- Right-click the page
- Click **Preview page in clipnote**

### Save a page
- Right-click the page
- Click **Save page to clipnote**

### Preview a link
- Right-click a link
- Click **Preview link in clipnote**

### Save a link
- Right-click a link
- Click **Save link to clipnote**

---

## 5) Selected text test

### Page text
1. Highlight a sentence on the page
2. Right-click
3. Click **Preview page in clipnote** or **Save page to clipnote**
4. Confirm the text appears in the note under:

```md
## Selected excerpt
> ...
```

### Link targets
1. Right-click a link without highlighting text
2. Use **Preview link in clipnote** or **Save link to clipnote**
3. If you need selected text, highlight page text and use the page actions above

---

## 6) AI summary test

Chrome built-in AI summaries require a Chrome version/profile where the Summarizer API is available. The model is checked only after you click **AI Summary**.

1. Open an article page
2. Highlight text, or leave nothing highlighted to use the visible page body
3. Click the clipnote extension icon
4. Click **AI Summary**
5. Confirm the generated text appears in **AI summary**
6. Click **Preview** or **Save** to use that summary in the note

The extracted page body stays in Chrome. Only the generated summary override is sent to the local clipnote server when you preview or save.

---

## 7) Conflict test

Try saving the same URL again.

You should see:
- a duplicate/conflict message
- an **Open existing** button in the popup

---

## 8) If something fails

Check these first:

- Is `clipnote_server.py` still running?
- Did you paste the current server `auth token` into the popup?
- Did you reload the extension after changes?
- Is the popup server URL set to `http://127.0.0.1:8765`?
- Server URL accepts only `http://127.0.0.1:8765` or `http://localhost:8765`.
- If preview/save times out or reports a non-JSON response, restart the local server and retry.

You can also verify the server directly:

```bash
curl http://127.0.0.1:8765/health
```
