from __future__ import annotations

import http.client
import io
import json
import tempfile
import threading
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path
from unittest import mock

import clipnote_server


@contextmanager
def running_server(vault_path: Path, *, origins: set[str] | None = None, auth_token: str = "secret"):
    httpd = clipnote_server.ThreadingHTTPServer(("127.0.0.1", 0), clipnote_server.AiNoteHandler)
    httpd.allowed_origins = origins if origins is not None else {clipnote_server.DEFAULT_ORIGIN}
    httpd.auth_token = auth_token
    httpd.vault_path = vault_path.resolve()
    httpd.allow_client_vault_path = False
    thread = threading.Thread(target=httpd.serve_forever)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def post_json(server, path: str, payload: dict, *, origin: str | None = None, token: str | None = None):
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if origin is not None:
        headers["Origin"] = origin
    if token is not None:
        headers["X-Clipnote-Token"] = token
    conn = http.client.HTTPConnection(server.server_address[0], server.server_address[1], timeout=5)
    try:
        conn.request("POST", path, body=body, headers=headers)
        response = conn.getresponse()
        response_body = response.read().decode("utf-8")
    finally:
        conn.close()
    return response.status, json.loads(response_body)


class ClipnoteServerSecurityTest(unittest.TestCase):
    def test_missing_origin_is_rejected_before_route_handler_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with running_server(Path(tmp)) as server:
                with mock.patch.object(clipnote_server, "prepare_preview", return_value={"ok": True}) as prepare:
                    status, data = post_json(
                        server,
                        "/preview",
                        {"url": "https://example.com/article"},
                        token="secret",
                    )

        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "forbidden_origin")
        prepare.assert_not_called()

    def test_missing_auth_token_is_rejected_before_route_handler_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with running_server(Path(tmp)) as server:
                with mock.patch.object(clipnote_server, "prepare_preview", return_value={"ok": True}) as prepare:
                    status, data = post_json(
                        server,
                        "/preview",
                        {"url": "https://example.com/article"},
                        origin=clipnote_server.DEFAULT_ORIGIN,
                    )

        self.assertEqual(status, 401)
        self.assertEqual(data["error"], "unauthorized")
        prepare.assert_not_called()

    def test_client_supplied_vault_path_is_rejected_before_save_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with running_server(Path(tmp)) as server:
                with mock.patch.object(clipnote_server, "save_note", return_value={"ok": True}) as save:
                    status, data = post_json(
                        server,
                        "/save",
                        {"url": "https://example.com/article", "vaultPath": "/tmp/not-the-server-vault"},
                        origin=clipnote_server.DEFAULT_ORIGIN,
                        token="secret",
                    )

        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "bad_request")
        save.assert_not_called()

    def test_traversal_date_is_rejected_before_save_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with running_server(Path(tmp)) as server:
                with mock.patch.object(clipnote_server, "save_note", return_value={"ok": True}) as save:
                    status, data = post_json(
                        server,
                        "/save",
                        {"url": "https://example.com/article", "date": "../escape"},
                        origin=clipnote_server.DEFAULT_ORIGIN,
                        token="secret",
                    )

        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "bad_request")
        save.assert_not_called()

    def test_open_rejects_paths_outside_server_vault(self):
        with tempfile.TemporaryDirectory() as vault_tmp, tempfile.TemporaryDirectory() as outside_tmp:
            outside_note = Path(outside_tmp) / "outside.md"
            outside_note.write_text("# outside\n", encoding="utf-8")
            with running_server(Path(vault_tmp)) as server:
                with mock.patch.object(clipnote_server.subprocess, "run") as run:
                    status, data = post_json(
                        server,
                        "/open",
                        {"path": str(outside_note)},
                        origin=clipnote_server.DEFAULT_ORIGIN,
                        token="secret",
                    )

        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "forbidden_path")
        run.assert_not_called()

    def test_open_rejects_symlink_escape_from_server_vault(self):
        with tempfile.TemporaryDirectory() as vault_tmp, tempfile.TemporaryDirectory() as outside_tmp:
            outside_note = Path(outside_tmp) / "outside.md"
            outside_note.write_text("# outside\n", encoding="utf-8")
            symlink_note = Path(vault_tmp) / "Links" / "outside.md"
            symlink_note.parent.mkdir(parents=True)
            symlink_note.symlink_to(outside_note)
            with running_server(Path(vault_tmp)) as server:
                with mock.patch.object(clipnote_server.subprocess, "run") as run:
                    status, data = post_json(
                        server,
                        "/open",
                        {"path": "Links/outside.md"},
                        origin=clipnote_server.DEFAULT_ORIGIN,
                        token="secret",
                    )

        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "forbidden_path")
        run.assert_not_called()

    def test_open_allows_existing_note_under_server_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            note = vault_path / "Links" / "2026-05-11" / "note.md"
            note.parent.mkdir(parents=True)
            note.write_text("# note\n", encoding="utf-8")
            with running_server(vault_path) as server:
                with mock.patch.object(clipnote_server.subprocess, "run") as run:
                    status, data = post_json(
                        server,
                        "/open",
                        {"path": str(note)},
                        origin=clipnote_server.DEFAULT_ORIGIN,
                        token="secret",
                    )

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        run.assert_called_once()

    def test_internal_exception_details_are_not_returned_to_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret_path = str(Path(tmp) / "secret.md")
            with running_server(Path(tmp)) as server:
                with mock.patch.object(clipnote_server, "prepare_preview", side_effect=RuntimeError(f"boom {secret_path}")):
                    with redirect_stderr(io.StringIO()):
                        status, data = post_json(
                            server,
                            "/preview",
                            {"url": "https://example.com/article"},
                            origin=clipnote_server.DEFAULT_ORIGIN,
                            token="secret",
                        )

        self.assertEqual(status, 500)
        self.assertEqual(data["error"], "server_error")
        self.assertNotIn(secret_path, data.get("message", ""))
        self.assertNotIn("boom", data.get("message", ""))


if __name__ == "__main__":
    unittest.main()
