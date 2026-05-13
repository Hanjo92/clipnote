#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import sys
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
from typing import Any
from urllib.error import HTTPError, URLError

import clipnote


DEFAULT_ORIGIN = "chrome-extension://dojaomlgohpahfibbdbjjnkkpbdoljnf"
AUTH_HEADER = "X-Clipnote-Token"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_JSON_BODY_BYTES = int(os.environ.get("CLIPNOTE_MAX_JSON_BODY_BYTES", str(256 * 1024)))


class ClientError(Exception):
    def __init__(self, status: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def relative_to_vault(path: Path, vault_path: Path) -> str:
    resolved_vault = vault_path.resolve()
    resolved_path = path.resolve()
    if not is_under(resolved_path, resolved_vault):
        raise ClientError(HTTPStatus.FORBIDDEN, "forbidden_path", "Path is outside the configured vault")
    return str(resolved_path.relative_to(resolved_vault))


def validate_note_date(note_date: str) -> None:
    if not DATE_PATTERN.match(note_date):
        raise ValueError("Date must use YYYY-MM-DD")
    try:
        date.fromisoformat(note_date)
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD") from exc


def prepare_payload(payload: dict[str, Any], vault_path: Path, allow_client_vault_path: bool = False) -> dict[str, Any]:
    if payload.get("vaultPath") and not allow_client_vault_path:
        raise ValueError("Client-supplied vaultPath is not allowed")
    out = dict(payload)
    note_date = out.get("date")
    if note_date:
        if not isinstance(note_date, str):
            raise ValueError("Date must use YYYY-MM-DD")
        validate_note_date(note_date)
    out["vaultPath"] = str(vault_path.resolve())
    out.pop("vaultName", None)
    return out


def resolve_open_path(path_value: str, vault_path: Path) -> Path:
    raw_path = Path(path_value).expanduser()
    note_path = raw_path if raw_path.is_absolute() else vault_path / raw_path
    note_path = note_path.resolve()
    if not is_under(note_path, vault_path):
        raise ClientError(HTTPStatus.FORBIDDEN, "forbidden_path", "Path is outside the configured vault")
    if not note_path.exists():
        raise ClientError(HTTPStatus.NOT_FOUND, "not_found", "Note path does not exist")
    if not note_path.is_file() or note_path.suffix.lower() != ".md":
        raise ClientError(HTTPStatus.BAD_REQUEST, "bad_request", "Open is only supported for Markdown note files")
    return note_path


def note_meta_to_dict(meta: clipnote.NoteMeta, vault_path: Path) -> dict[str, Any]:
    extra_meta = dict(meta.extra_meta or {})
    relative_folder = relative_to_vault(meta.folder, vault_path)
    relative_path = relative_to_vault(meta.path, vault_path)
    return {
        "source": meta.source,
        "title": meta.title,
        "link": meta.link,
        "kind": meta.kind,
        "noteDate": meta.note_date,
        "folder": relative_folder,
        "path": relative_path,
        "relativePath": relative_path,
        "duplicateUrls": [relative_to_vault(path, vault_path) for path in meta.duplicate_urls],
        "duplicateTitles": [relative_to_vault(path, vault_path) for path in meta.duplicate_titles],
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
    selected_text = optional_str(payload, "selectedText")
    summary_override = optional_str(payload, "summaryOverride")
    note_date = payload.get("date") or date.today().isoformat()
    validate_note_date(note_date)
    vault_name = payload.get("vaultName") or "AI"
    vault_path = clipnote.load_vault_path(vault_name, payload.get("vaultPath")).resolve()
    meta = clipnote.prepare_note(url, vault_path, note_date, kind, title_override, selected_text, summary_override)
    return {
        "ok": True,
        "preview": note_meta_to_dict(meta, vault_path),
    }


def save_note(payload: dict[str, Any]) -> dict[str, Any]:
    url = require_str(payload, "url")
    kind = payload.get("kind") or "auto"
    title_override = payload.get("titleOverride") or payload.get("title")
    selected_text = optional_str(payload, "selectedText")
    summary_override = optional_str(payload, "summaryOverride")
    note_date = payload.get("date") or date.today().isoformat()
    validate_note_date(note_date)
    force = bool(payload.get("force", False))
    vault_name = payload.get("vaultName") or "AI"
    vault_path = clipnote.load_vault_path(vault_name, payload.get("vaultPath")).resolve()
    meta = clipnote.prepare_note(url, vault_path, note_date, kind, title_override, selected_text, summary_override)
    relative_to_vault(meta.folder, vault_path)
    relative_to_vault(meta.path, vault_path)
    if meta.path.exists() and not force:
        return {
            "ok": False,
            "error": "exists",
            "message": "Refusing to overwrite existing note",
            "preview": note_meta_to_dict(meta, vault_path),
        }
    if not clipnote.write_note_file(meta.path, clipnote.build_note(meta), force=force):
        return {
            "ok": False,
            "error": "exists",
            "message": "Refusing to overwrite existing note",
            "preview": note_meta_to_dict(meta, vault_path),
        }
    return {
        "ok": True,
        "saved": True,
        "path": relative_to_vault(meta.path, vault_path),
        "relativePath": relative_to_vault(meta.path, vault_path),
        "preview": note_meta_to_dict(meta, vault_path),
    }


def open_note(payload: dict[str, Any], vault_path: Path) -> dict[str, Any]:
    path_value = require_str(payload, "path")
    note_path = resolve_open_path(path_value, vault_path)
    subprocess.run(["open", str(note_path)], check=True)
    return {
        "ok": True,
        "opened": True,
        "path": relative_to_vault(note_path, vault_path),
    }


def require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required string field: {key}")
    return value.strip()


def optional_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key) or ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value.strip()


class AiNoteHandler(BaseHTTPRequestHandler):
    server_version = f"clipnote-server/{clipnote.__version__}"

    def _set_headers(self, status: int = 200, content_type: str = "application/json", content_length: int | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))
        origin = self.headers.get("Origin")
        allowed = getattr(self.server, "allowed_origins", set())
        if origin and origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", f"Content-Type, {AUTH_HEADER}, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:
        origin_error = self.origin_error()
        if origin_error:
            self.respond_error(origin_error)
            return
        self._set_headers(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.respond_json({"ok": True, "service": "clipnote-server"})
            return
        self.respond_json({"ok": False, "error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            trust_error = self.trust_error()
            if trust_error:
                self.discard_request_body()
                self.respond_error(trust_error)
                return
            payload = self.read_json_body()
            vault_path = self.server_vault_path()
            if self.path == "/preview":
                safe_payload = prepare_payload(payload, vault_path, self.allow_client_vault_path())
                self.respond_json(prepare_preview(safe_payload))
                return
            if self.path == "/save":
                safe_payload = prepare_payload(payload, vault_path, self.allow_client_vault_path())
                result = save_note(safe_payload)
                status = HTTPStatus.OK if result.get("ok") else HTTPStatus.CONFLICT
                self.respond_json(result, status=status)
                return
            if self.path == "/open":
                self.respond_json(open_note(payload, vault_path))
                return
            self.respond_json({"ok": False, "error": "not_found"}, status=HTTPStatus.NOT_FOUND)
        except ClientError as exc:
            self.respond_error(exc)
        except ValueError as exc:
            self.respond_json({"ok": False, "error": "bad_request", "message": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except TimeoutError:
            self.respond_json({"ok": False, "error": "timeout", "message": "Timed out while processing request"}, status=HTTPStatus.GATEWAY_TIMEOUT)
        except (URLError, HTTPError):
            self.respond_json({"ok": False, "error": "network_error", "message": "Could not fetch the requested URL"}, status=HTTPStatus.BAD_GATEWAY)
        except Exception as exc:  # noqa: BLE001
            print(f"clipnote server error: {exc}", file=sys.stderr)
            self.respond_json({"ok": False, "error": "server_error", "message": "Internal server error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def server_vault_path(self) -> Path:
        configured = getattr(self.server, "vault_path", None)
        if configured:
            return Path(configured).expanduser().resolve()
        return clipnote.load_vault_path("AI", None).resolve()

    def allow_client_vault_path(self) -> bool:
        return bool(getattr(self.server, "allow_client_vault_path", False))

    def origin_error(self) -> ClientError | None:
        origin = self.headers.get("Origin")
        if not origin:
            if getattr(self.server, "allow_missing_origin", False):
                return None
            return ClientError(HTTPStatus.FORBIDDEN, "forbidden_origin", "Missing Origin header")
        allowed = getattr(self.server, "allowed_origins", set())
        if origin not in allowed:
            return ClientError(HTTPStatus.FORBIDDEN, "forbidden_origin", "Origin is not allowed")
        return None

    def trust_error(self) -> ClientError | None:
        origin_error = self.origin_error()
        if origin_error:
            return origin_error
        expected_token = getattr(self.server, "auth_token", "")
        if not expected_token:
            return None
        provided_token = self.request_token()
        if not provided_token or not hmac.compare_digest(provided_token, expected_token):
            return ClientError(HTTPStatus.UNAUTHORIZED, "unauthorized", "Invalid clipnote auth token")
        return None

    def request_token(self) -> str:
        authorization = self.headers.get("Authorization", "")
        if authorization.casefold().startswith("bearer "):
            return authorization[7:].strip()
        return self.headers.get(AUTH_HEADER, "").strip()

    def respond_error(self, exc: ClientError) -> None:
        self.respond_json({"ok": False, "error": exc.error, "message": exc.message}, status=exc.status)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("Expected JSON request body")
        max_length = int(getattr(self.server, "max_json_body_bytes", MAX_JSON_BODY_BYTES))
        if length > max_length:
            self.close_connection = True
            raise ClientError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large", "JSON request body is too large")
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def discard_request_body(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 0:
            self.rfile.read(length)

    def respond_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._set_headers(status, content_length=len(body))
        self.wfile.write(body)


def parse_origins(raw: str) -> set[str]:
    items = {item.strip() for item in raw.split(",") if item.strip()}
    return items or {DEFAULT_ORIGIN}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local HTTP bridge for clipnote Chrome extension")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--vault-name", default="AI", help="Vault folder name from obsidian.json")
    parser.add_argument("--vault-path", help="Explicit trusted vault path for this server")
    parser.add_argument(
        "--auth-token",
        default=os.environ.get("CLIPNOTE_AUTH_TOKEN"),
        help="Shared token required in X-Clipnote-Token or Authorization: Bearer",
    )
    parser.add_argument(
        "--allow-origin",
        default=DEFAULT_ORIGIN,
        help="Comma-separated CORS allowlist for extension origins",
    )
    parser.add_argument(
        "--allow-missing-origin",
        action="store_true",
        help="Allow POST requests without an Origin header for local CLI testing",
    )
    parser.add_argument(
        "--allow-client-vault-path",
        action="store_true",
        help="Allow request payloads to choose vaultPath; keep disabled for production use",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    vault_path = clipnote.load_vault_path(args.vault_name, args.vault_path).resolve()
    auth_token = args.auth_token or secrets.token_urlsafe(24)
    httpd = ThreadingHTTPServer((args.host, args.port), AiNoteHandler)
    httpd.allowed_origins = parse_origins(args.allow_origin)
    httpd.allow_missing_origin = args.allow_missing_origin
    httpd.allow_client_vault_path = args.allow_client_vault_path
    httpd.vault_path = vault_path
    httpd.auth_token = auth_token
    print(f"clipnote server listening on http://{args.host}:{args.port}")
    print(f"vault: {vault_path}")
    if args.auth_token:
        print("auth token: configured")
    else:
        print(f"auth token: {auth_token}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
