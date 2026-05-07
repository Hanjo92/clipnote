# clipnote Chrome Extension Quickstart

This is the fastest way to get the extension working locally.

## 1) Start the local server

```bash
cd ~/Projects/clipnote
python3 clipnote_server.py
```

Leave this terminal running.

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

---

## 3) First popup test

1. Open any article or paper page
2. Click the clipnote extension icon
3. Confirm that the popup:
   - loads the current tab URL
   - shows a preview
   - shows duplicates if they exist
4. Click **Save**
5. Confirm the note saves and opens

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

1. Highlight a sentence on the page
2. Right-click
3. Use preview or save
4. Confirm the text appears in the note under:

```md
## Selected excerpt
> ...
```

---

## 6) Conflict test

Try saving the same URL again.

You should see:
- a duplicate/conflict message
- an **Open existing** button in the popup

---

## 7) If something fails

Check these first:

- Is `clipnote_server.py` still running?
- Did you reload the extension after changes?
- Is the popup server URL set to `http://127.0.0.1:8765`?

You can also verify the server directly:

```bash
curl http://127.0.0.1:8765/health
```
