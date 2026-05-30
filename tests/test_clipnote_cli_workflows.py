from __future__ import annotations

import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import clipnote
import clipnote_server
from tests.test_clipnote_server_security import post_json, running_server


def save_args(vault_path: Path, **overrides):
    values = {
        "url": "https://example.com/article",
        "title": None,
        "kind": "links",
        "date": "2026-05-11",
        "vault_name": "AI",
        "vault_path": str(vault_path),
        "dry_run": False,
        "force": False,
        "duplicate_lookback_days": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class ClipnoteCliWorkflowTest(unittest.TestCase):
    def test_save_writes_note_with_mocked_fetch(self):
        html = """
        <html>
          <head>
            <title>Example Article</title>
            <meta name="description" content="A compact article summary for later reference." />
          </head>
          <body><p>This paragraph is long enough to become a key point in the saved note output.</p></body>
        </html>
        """
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            with mock.patch.object(clipnote, "fetch_html", return_value=html):
                with redirect_stdout(io.StringIO()):
                    result = clipnote.cmd_save(save_args(vault_path))

            note_path = vault_path / "Links" / "2026-05-11" / "Example Article.md"
            self.assertEqual(result, 0)
            self.assertTrue(note_path.exists())
            content = note_path.read_text(encoding="utf-8")
            self.assertIn("# Example Article", content)
            self.assertIn("- Link: https://example.com/article", content)

    def test_save_existing_target_returns_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            note_path = vault_path / "Links" / "2026-05-11" / "Example.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text("# existing\n", encoding="utf-8")
            meta = clipnote.NoteMeta(
                source="example.com",
                title="Example",
                link="https://example.com/article",
                kind="links",
                note_date="2026-05-11",
                folder=note_path.parent,
                path=note_path,
                duplicate_urls=[],
                duplicate_titles=[],
            )
            with mock.patch.object(clipnote, "prepare_note", return_value=meta):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result = clipnote.cmd_save(save_args(vault_path))

            self.assertEqual(result, 2)
            self.assertEqual(note_path.read_text(encoding="utf-8"), "# existing\n")

    def test_save_rejects_invalid_url_before_fetching(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            with mock.patch.object(clipnote, "fetch_html") as fetch_html:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result = clipnote.cmd_save(save_args(vault_path, url="not-a-url"))

        self.assertEqual(result, 2)
        fetch_html.assert_not_called()

    def test_save_rejects_invalid_date_before_fetching(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            with mock.patch.object(clipnote, "fetch_html") as fetch_html:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result = clipnote.cmd_save(save_args(vault_path, date="../escape"))

        self.assertEqual(result, 2)
        fetch_html.assert_not_called()

    def test_parser_rejects_invalid_kind(self):
        parser = clipnote.build_parser()

        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["save", "https://example.com/article", "--kind", "bad"])

    def test_duplicate_detection_groups_url_and_title_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            first = vault_path / "Links" / "2026-05-10" / "Same Title.md"
            second = vault_path / "Links" / "2026-05-11" / "Same Title.md"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_text("# Same Title\n\n- Link: https://example.com/dup\n", encoding="utf-8")
            second.write_text("# Same Title\n\n- Link: https://example.com/dup\n", encoding="utf-8")

            by_url, by_title = clipnote.collect_duplicate_groups(vault_path)

        self.assertEqual(len(by_url["https://example.com/dup"]), 2)
        self.assertTrue(any(len(paths) == 2 for paths in by_title.values()))

    def test_prepare_note_default_duplicate_scan_covers_whole_vault(self):
        html = "<html><head><title>Example Article</title></head><body></body></html>"
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            old_note = vault_path / "Links" / "2026-05-01" / "Old.md"
            old_note.parent.mkdir(parents=True)
            old_note.write_text("# Old\n\n- Link: https://example.com/article\n", encoding="utf-8")

            with mock.patch.object(clipnote, "fetch_html", return_value=html):
                meta = clipnote.prepare_note(
                    "https://example.com/article",
                    vault_path,
                    "2026-05-11",
                    "links",
                    None,
                )

        self.assertEqual(meta.duplicate_urls, [old_note])

    def test_prepare_note_duplicate_lookback_limits_old_date_folders(self):
        html = "<html><head><title>Example Article</title></head><body></body></html>"
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            old_note = vault_path / "Links" / "2026-05-01" / "Old.md"
            recent_note = vault_path / "Links" / "2026-05-10" / "Recent.md"
            old_note.parent.mkdir(parents=True)
            recent_note.parent.mkdir(parents=True)
            for note in (old_note, recent_note):
                note.write_text("# Note\n\n- Link: https://example.com/article\n", encoding="utf-8")

            with mock.patch.object(clipnote, "fetch_html", return_value=html):
                meta = clipnote.prepare_note(
                    "https://example.com/article",
                    vault_path,
                    "2026-05-11",
                    "links",
                    None,
                    duplicate_lookback_days=3,
                )

        self.assertEqual(meta.duplicate_urls, [recent_note])

    def test_prepare_note_rejects_non_positive_duplicate_lookback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "duplicate lookback"):
                clipnote.prepare_note(
                    "https://example.com/article",
                    Path(tmp),
                    "2026-05-11",
                    "links",
                    None,
                    duplicate_lookback_days=0,
                )

    def test_cleanup_dry_run_and_apply_archive_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            short = vault_path / "Links" / "2026-05-10" / "Duplicate Short.md"
            long = vault_path / "Links" / "2026-05-11" / "Duplicate Long.md"
            short.parent.mkdir(parents=True)
            long.parent.mkdir(parents=True)
            short.write_text("# Duplicate Short\n\n- Link: https://example.com/dup\n", encoding="utf-8")
            long.write_text(
                "# Duplicate Long\n\n- Link: https://example.com/dup\n\n## Notes\n"
                + "\n".join(f"- useful point {idx}" for idx in range(8))
                + "\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(vault_name="AI", vault_path=str(vault_path), urls_only=True, titles_only=False, apply=False)
            with redirect_stdout(io.StringIO()):
                dry_result = clipnote.cmd_cleanup(args)

            self.assertEqual(dry_result, 0)
            self.assertTrue(short.exists())
            self.assertTrue(long.exists())

            args = argparse.Namespace(vault_name="AI", vault_path=str(vault_path), urls_only=True, titles_only=False, apply=True)
            with redirect_stdout(io.StringIO()):
                apply_result = clipnote.cmd_cleanup(args)

            self.assertEqual(apply_result, 0)
            self.assertTrue(long.exists())
            self.assertFalse(short.exists())
            self.assertTrue((vault_path / "Archive" / short.relative_to(vault_path)).exists())

    def test_recap_generates_weekly_summary_from_temp_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp)
            link_note = vault_path / "Links" / "2026-05-11" / "Tool Update.md"
            paper_note = vault_path / "Papers" / "2026-05-12" / "Research Paper.md"
            link_note.parent.mkdir(parents=True)
            paper_note.parent.mkdir(parents=True)
            link_note.write_text(
                "# Tool Update\n\n- Source: example.com\n- Date: 2026-05-11\n- Link: https://example.com/tool\n\n"
                "## One-line summary\n- Tooling update summary.\n",
                encoding="utf-8",
            )
            paper_note.write_text(
                "# Research Paper\n\n- Source: arXiv\n- Date: 2026-05-12\n- Link: https://arxiv.org/abs/2605.00001\n\n"
                "## TL;DR\n- Research summary.\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            args = argparse.Namespace(
                week=True,
                anchor_date="2026-05-13",
                vault_name="AI",
                vault_path=str(vault_path),
                output=None,
                save_note=False,
                dry_run=False,
                force=False,
                compare_previous=False,
            )
            with redirect_stdout(output):
                result = clipnote.cmd_recap(args)

        recap = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("- total: 2", recap)
        self.assertIn("- papers: 1", recap)
        self.assertIn("- links: 1", recap)
        self.assertIn("Tool Update", recap)
        self.assertIn("Research Paper", recap)

    def test_server_bad_request_for_missing_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            with running_server(Path(tmp)) as server:
                status, data = post_json(
                    server,
                    "/preview",
                    {},
                    origin=clipnote_server.DEFAULT_ORIGIN,
                    token="secret",
                )

        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "bad_request")

    def test_server_preview_applies_ai_summary_override(self):
        html = """
        <html>
          <head>
            <title>Example Article</title>
            <meta name="description" content="Original server-side summary." />
          </head>
          <body><p>Page body that should not become the preview summary.</p></body>
        </html>
        """
        with tempfile.TemporaryDirectory() as tmp:
            with running_server(Path(tmp)) as server:
                with mock.patch.object(clipnote, "fetch_html", return_value=html):
                    status, data = post_json(
                        server,
                        "/preview",
                        {
                            "url": "https://example.com/article",
                            "summaryOverride": " On-device Gemini Nano summary. ",
                        },
                        origin=clipnote_server.DEFAULT_ORIGIN,
                        token="secret",
                    )

        self.assertEqual(status, 200)
        self.assertEqual(data["preview"]["summary"], "On-device Gemini Nano summary.")


if __name__ == "__main__":
    unittest.main()
