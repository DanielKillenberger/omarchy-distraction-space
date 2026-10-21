#!/usr/bin/env python3
"""State files are readable only by their owner, whatever the umask.

held.jsonl carries notification titles and bodies and the log records what the plugin
did, so neither may come out 0644 under the usual umask 022 (marketplace review on
omarchy-plugin-marketplace#12365).
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import hold, hypr, lock, net, state, summary


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


class PrivateStateTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.addCleanup(self.box.restore_env)
        old = os.umask(0o022)
        self.addCleanup(os.umask, old)

    def test_a_new_state_dir_is_owner_only(self):
        shutil.rmtree(self.box.state_dir, ignore_errors=True)
        self.assertEqual(_mode(state.state_dir()), 0o700)

    def test_an_older_wider_state_dir_is_tightened(self):
        os.chmod(self.box.state_dir, 0o755)
        state.state_dir()
        self.assertEqual(_mode(self.box.state_dir), 0o700)

    def test_held_notifications_are_owner_only(self):
        self.assertTrue(hold.append_held("Telegram", "title", "body"))
        self.assertEqual(_mode(hold.held_path()), 0o600)

    def test_an_older_wider_held_file_is_tightened_on_the_next_append(self):
        hold.held_path().write_text("", encoding="utf-8")
        os.chmod(hold.held_path(), 0o644)
        self.assertTrue(hold.append_held("Telegram", "title", "body"))
        self.assertEqual(_mode(hold.held_path()), 0o600)

    def test_the_trimmed_held_file_stays_owner_only(self):
        for i in range(60):
            self.assertTrue(hold.append_held("Telegram", str(i), "y" * 2000))
        self.assertLessEqual(hold.held_path().stat().st_size, hold.FILE_CAP)
        self.assertEqual(_mode(hold.held_path()), 0o600)

    def test_every_log_writer_creates_the_log_owner_only(self):
        writers = (
            ("hypr", lambda: hypr._log("x"), state.state_path("log")),
            ("hold", lambda: hold._log("x"), state.state_path("log")),
            ("summary", lambda: summary._log("x"), state.state_path("log")),
            ("lock", lambda: lock._append_log("x"), lock._log_path()),
            ("net", lambda: net._append_log("x"), net._log_path()),
        )
        for name, write, log in writers:
            with self.subTest(writer=name, log=str(log)):
                log.unlink(missing_ok=True)
                write()
                self.assertEqual(_mode(log), 0o600)

    def test_json_state_stays_owner_only(self):
        state.write_json(state.state_path("state.json"), {"a": 1})
        self.assertEqual(_mode(state.state_path("state.json")), 0o600)

    def test_a_mode_change_that_fails_stops_nothing(self):
        os.chmod(self.box.state_dir, 0o755)
        with mock.patch("os.chmod", side_effect=PermissionError):
            self.assertEqual(state.state_dir(), self.box.state_dir)
        hold.held_path().write_text("", encoding="utf-8")
        os.chmod(hold.held_path(), 0o644)
        with mock.patch("os.fchmod", side_effect=PermissionError):
            self.assertTrue(hold.append_held("Telegram", "title", "body"))
        self.assertIn("title", hold.held_path().read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
