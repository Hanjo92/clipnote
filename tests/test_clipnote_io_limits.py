from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import clipnote
import clipnote_server
from tests.test_clipnote_server_security import post_json, running_server


class FakeHeaders:
    def get_content_charset(self):
        return "utf-8"


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.offset = 0
        self.headers = FakeHeaders()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


def note_meta(vault_path: Path, note_path: Path) -> clipnote.NoteMeta:
    return clipnote.NoteMeta(
        source="example.com",
        title="Example",
        link="https://example.com/article",
        kind="links",
        note_date="2026-05-11",
        folder=note_path.parent,
        path=note_path,
        duplicate_urls=[],
        duplicate_titles=[],
        summary="summary",
        why_save="- useful",
        key_points=["point"],
        tags=["#ai", "#link"],
    )


class ClipnoteIOLimitsTest(unittest.TestCase):
    def test_oversized_json_body_is_rejected_before_route_handler_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with running_server(Path(tmp)) as server:
                server.max_json_body_bytes = 32
                with mock.patch.object(clipnote_server, "prepare_preview", return_value={"ok": True}) as prepare:
                    status, data = post_json(
                        server,
                        "/preview",
                        {"url": "https://example.com/" + ("x" * 80)},
                        origin=clipnote_server.DEFAULT_ORIGIN,
                        token="secret",
                    )

        self.assertEqual(status, 413)
        self.assertEqual(data["error"], "request_too_large")
        prepare.assert_not_called()

    def test_fetch_html_rejects_oversized_response(self):
        with mock.patch.object(clipnote, "MAX_FETCH_BYTES", 8, create=True):
            with mock.patch.object(clipnote, "urlopen", return_value=FakeResponse(b"012345678")):
                with self.assertRaisesRegex(ValueError, "too large"):
                    clipnote.fetch_html("https://example.com/large")

    def test_preview_timeout_returns_timeout_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with running_server(Path(tmp)) as server:
                with mock.patch.object(clipnote_server, "prepare_preview", side_effect=TimeoutError("timed out")):
                    status, data = post_json(
                        server,
                        "/preview",
                        {"url": "https://example.com/article"},
                        origin=clipnote_server.DEFAULT_ORIGIN,
                        token="secret",
                    )

        self.assertEqual(status, 504)
        self.assertEqual(data["error"], "timeout")

    def test_concurrent_non_force_saves_allow_only_one_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            target = vault_path / "Links" / "2026-05-11" / "Example.md"
            meta = note_meta(vault_path, target)
            barrier = threading.Barrier(2)
            original_exists = Path.exists

            def racing_exists(path: Path) -> bool:
                if path == target:
                    barrier.wait(timeout=5)
                    return False
                return original_exists(path)

            with mock.patch.object(clipnote, "prepare_note", return_value=meta):
                with mock.patch.object(clipnote, "build_note", return_value="# Example\n"):
                    with mock.patch.object(Path, "exists", racing_exists):
                        results = []
                        threads = [
                            threading.Thread(
                                target=lambda: results.append(
                                    clipnote_server.save_note(
                                        {
                                            "url": "https://example.com/article",
                                            "date": "2026-05-11",
                                            "vaultPath": str(vault_path),
                                        }
                                    )
                                )
                            )
                            for _ in range(2)
                        ]
                        for thread in threads:
                            thread.start()
                        for thread in threads:
                            thread.join(timeout=5)

            self.assertEqual(len(results), 2)
            self.assertEqual(sum(1 for result in results if result.get("ok")), 1)
            self.assertEqual(sum(1 for result in results if result.get("error") == "exists"), 1)
            self.assertTrue(target.exists())

    def test_force_save_uses_atomic_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            target = vault_path / "Links" / "2026-05-11" / "Example.md"
            target.parent.mkdir(parents=True)
            target.write_text("# old\n", encoding="utf-8")
            meta = note_meta(vault_path, target)
            with mock.patch.object(clipnote, "prepare_note", return_value=meta):
                with mock.patch.object(clipnote, "build_note", return_value="# new\n"):
                    with mock.patch.object(clipnote_server.os, "replace", wraps=os.replace) as replace:
                        result = clipnote_server.save_note(
                            {
                                "url": "https://example.com/article",
                                "date": "2026-05-11",
                                "vaultPath": str(vault_path),
                                "force": True,
                            }
                        )

            self.assertTrue(result["ok"])
            self.assertEqual(target.read_text(encoding="utf-8"), "# new\n")
            replace.assert_called_once()


if __name__ == "__main__":
    unittest.main()
