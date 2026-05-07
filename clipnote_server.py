#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
from typing import Any
from urllib.error import HTTPError, URLError

import clipnote


DEFAULT_ORIGIN = "chrome-extension://dojaomlgohpahfibbdbjjnkkpbdoljnf"


def note_meta_to_dict(meta: clipnote.NoteMeta, vault_path: Path) -> dict[str, Any]:
    extra_meta = dict(meta.extra_meta or {})
    return {
        "source": meta.source,
        "title": meta.title,
        "link": meta.link,
        "kind": meta.kind,
        "noteDate": meta.note_date,
        "folder": str(meta.folder),
        "path": str(meta.path),
        "relativePath": str(meta.path.relative_to(vault_path)),
        "duplicateUrls": [str(path.relative_to(vault_path)) for path in meta.duplicate_urls],
        "duplicateTitles": [str(path.relative_to(vault_path)) for path in meta.duplicate_titles],
        "summary": meta.summary,
        "whySave": meta.why_save,
        "keyPoints": meta.key_points or [],
        "tags": meta.tags or [],
        "selectedText": meta.selected_text,
        "extraMeta": extra_meta,
    }


def prepare_preview(payload: dict[str, Any]) -> dict[str, Any]:
    url = require_str(payload, "url")
    kind = payload.get("kind") or "auto"
    title_override = payload.get("titleOverride") or payload.get("title")
    selected_text = payload.get("selectedText") or ""
    note_date = payload.get("date") or date.today().isoformat()
    vault_name = payload.get("vaultName") or "AI"
    vault_path = clipnote.load_vault_path(vault_name, payload.get("vaultPath"))
    meta = clipnote.prepare_note(url, vault_path, note_date, kind, title_override, selected_text)
    return {
        "ok": True,
        "vaultPath": str(vault_path),
        "preview": note_meta_to_dict(meta, vault_path),
    }


def save_note(payload: dict[str, Any]) -> dict[str, Any]:
    url = require_str(payload, "url")
    kind = payload.get("kind") or "auto"
    title_override = payload.get("titleOverride") or payload.get("title")
    selected_text = payload.get("selectedText") or ""
    note_date = payload.get("date") or date.today().isoformat()
    force = bool(payload.get("force", False))
    vault_name = payload.get("vaultName") or "AI"
    vault_path = clipnote.load_vault_path(vault_name, payload.get("vaultPath"))
    meta = clipnote.prepare_note(url, vault_path, note_date, kind, title_override, selected_text)
    if meta.path.exists() and not force:
        return {
            "ok": False,
            "error": "exists",
            "message": f"Refusing to overwrite existing note: {meta.path}",
            "preview": note_meta_to_dict(meta, vault_path),
        }
    meta.folder.mkdir(parents=True, exist_ok=True)
    meta.path.write_text(clipnote.build_note(meta), encoding="utf-8")
    return {
        "ok": True,
        "saved": True,
        "vaultPath": str(vault_path),
        "path": str(meta.path),
        "relativePath": str(meta.path.relative_to(vault_path)),
        "preview": note_meta_to_dict(meta, vault_path),
    }


def open_note(payload: dict[str, Any]) -> dict[str, Any]:
    path_value = require_str(payload, "path")
    note_path = Path(path_value).expanduser().resolve()
    if not note_path.exists():
        return {
            "ok": False,
            "error": "not_found",
            "message": f"Note path does not exist: {note_path}",
        }
    subprocess.run(["open", str(note_path)], check=True)
    return {
        "ok": True,
        "opened": True,
        "path": str(note_path),
    }


def require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required string field: {key}")
    return value.strip()


class AiNoteHandler(BaseHTTPRequestHandler):
    server_version = "clipnote-server/0.1"

    def _set_headers(self, status: int = 200, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        allowed = getattr(self.server, "allowed_origins", set())
        if origin and ("*" in allowed or origin in allowed):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:
        self._set_headers(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.respond_json({"ok": True, "service": "clipnote-server"})
            return
        self.respond_json({"ok": False, "error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            payload = self.read_json_body()
            if self.path == "/preview":
                self.respond_json(prepare_preview(payload))
                return
            if self.path == "/save":
                result = save_note(payload)
                status = HTTPStatus.OK if result.get("ok") else HTTPStatus.CONFLICT
                self.respond_json(result, status=status)
                return
            if self.path == "/open":
                result = open_note(payload)
                status = HTTPStatus.OK if result.get("ok") else HTTPStatus.NOT_FOUND
                self.respond_json(result, status=status)
                return
            self.respond_json({"ok": False, "error": "not_found"}, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.respond_json({"ok": False, "error": "bad_request", "message": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except (URLError, HTTPError) as exc:
            self.respond_json({"ok": False, "error": "network_error", "message": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        except Exception as exc:  # noqa: BLE001
            self.respond_json({"ok": False, "error": "server_error", "message": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("Expected JSON request body")
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def respond_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        self._set_headers(status)
        self.wfile.write(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def parse_origins(raw: str) -> set[str]:
    items = {item.strip() for item in raw.split(",") if item.strip()}
    return items or {DEFAULT_ORIGIN}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local HTTP bridge for clipnote Chrome extension")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--allow-origin",
        default=DEFAULT_ORIGIN,
        help="Comma-separated CORS allowlist for extension origins",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), AiNoteHandler)
    httpd.allowed_origins = parse_origins(args.allow_origin)
    print(f"clipnote server listening on http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
