#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
distractions = SourceFileLoader("distractions", str(ROOT / "distractions")).load_module()
QML = ROOT / "NotificationFilter.qml"
README = ROOT / "README.md"
MANIFEST = ROOT / "manifest.json"


class CountStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(distractions, "STATE_DIR", self.state),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_is_zero(self):
        self.assertEqual(distractions.read_counts(), {})

    def test_increment_merges_under_lock(self):
        distractions.increment_count("Telegram")
        distractions.increment_count("Telegram")
        distractions.increment_count("Discord")
        self.assertEqual(distractions.read_counts(), {"Telegram": 2, "Discord": 1})

    def test_increment_fsyncs_temp_then_renames(self):
        calls: list[str] = []
        real_fsync = os.fsync
        real_replace = os.replace

        def fsync(fd):
            calls.append("fsync")
            return real_fsync(fd)

        def replace(src, dst):
            self.assertIn("fsync", calls)
            calls.append("replace")
            return real_replace(src, dst)

        with mock.patch.object(os, "fsync", fsync):
            with mock.patch.object(os, "replace", replace):
                distractions.increment_count("Signal")
        self.assertEqual(calls, ["fsync", "replace"])
        self.assertTrue(distractions.count_path().exists())

    def test_concurrent_increments_share_flock(self):
        errors: list[BaseException] = []

        def bump():
            try:
                distractions.increment_count("X")
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=bump) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(distractions.read_counts(), {"X": 8})

    def test_empty_label_does_not_write(self):
        with self.assertRaises(SystemExit):
            distractions.increment_count("  ")
        self.assertFalse(distractions.count_path().exists())


class NotifyTimeoutTests(unittest.TestCase):
    def test_notify_helper_times_out_and_returns_false(self):
        with mock.patch.object(
            subprocess,
            "check_call",
            side_effect=subprocess.TimeoutExpired(cmd="omarchy-notification-send", timeout=1),
        ):
            self.assertFalse(distractions.notify("While you were focused", "Telegram 1"))


class CatchupNoticeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / "state"
        self.runtime = root / "run"
        self.state.mkdir()
        self.runtime.mkdir()
        self.calls: list[tuple[str, ...]] = []
        self.disarm_out = "drained"
        self.drain_out = "drained"
        self.drain_code = 0
        self.notice_ok = True
        self.notices: list[tuple] = []
        self.patches = [
            mock.patch.object(distractions, "STATE_DIR", self.state),
            mock.patch.object(distractions, "FOCUS", self.state / "distractions.focus"),
            mock.patch.object(distractions, "MUTED_PATH", self.state / "distractions.muted.json"),
            mock.patch.object(distractions, "NOTIFY_LOCK", self.runtime / "notify.lock"),
            mock.patch.object(distractions, "WATCHER_REQUEST", self.runtime / "request.json"),
            mock.patch.object(distractions, "WATCHER_STATUS", self.runtime / "status.json"),
            mock.patch.object(distractions, "APPLY_WAIT_S", 0.35),
            mock.patch.object(distractions, "shell_ipc", self.fake_shell),
            mock.patch.object(distractions, "which_cmd", lambda _name: True),
            mock.patch.object(distractions, "notify", self.fake_notify),
            mock.patch.object(distractions, "wait_watcher_ack", self.fake_ack),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        distractions.FOCUS.write_text("on\n")

    def tearDown(self):
        self.tmp.cleanup()

    def fake_shell(self, *args, timeout=4.0):
        self.calls.append(args)
        if args[:2] == (distractions.PLUGIN_IPC, "disarm"):
            return 0, self.disarm_out
        if args[:2] == (distractions.PLUGIN_IPC, "drainState"):
            return self.drain_code, self.drain_out
        return 1, "unknown"

    def fake_ack(self, generation, want_armed, timeout=8.0):
        return True, ""

    def fake_notify(self, title, body="", timeout_ms=4000):
        self.notices.append((title, body, timeout_ms))
        if title == "While you were focused":
            return self.notice_ok
        return True

    def seed_counts(self, payload: dict[str, int]) -> None:
        distractions.write_counts_atomic(payload)

    def test_grouped_notice_lists_per_app_counts(self):
        title, body = distractions.format_grouped_notice({"Discord": 1, "Telegram": 3})
        self.assertEqual(title, "While you were focused")
        self.assertEqual(body, "Discord 1\nTelegram 3")

    def test_successful_lift_with_counts_sends_one_grouped_notice_and_clears(self):
        self.seed_counts({"Telegram": 2, "Signal": 1})
        self.assertTrue(distractions.lift_notification_block())
        grouped = [item for item in self.notices if item[0] == "While you were focused"]
        self.assertEqual(len(grouped), 1)
        self.assertIn("Telegram 2", grouped[0][1])
        self.assertIn("Signal 1", grouped[0][1])
        self.assertEqual(distractions.read_counts(), {})
        self.assertFalse(distractions.count_path().exists())

    def test_successful_lift_with_zero_counts_sends_no_grouped_notice(self):
        self.assertTrue(distractions.lift_notification_block())
        self.assertEqual(self.notices, [])
        self.assertFalse(distractions.count_path().exists())

    def test_drain_error_is_lift_failure_and_preserves_counts(self):
        self.seed_counts({"Telegram": 1})
        self.disarm_out = "error"
        self.drain_out = "error"
        self.assertFalse(distractions.lift_notification_block())
        self.assertEqual(distractions.read_counts(), {"Telegram": 1})
        self.assertFalse(any(item[0] == "While you were focused" for item in self.notices))

    def test_drain_timeout_is_lift_failure_and_preserves_counts(self):
        self.seed_counts({"WhatsApp": 4})
        self.disarm_out = "draining"
        self.drain_out = "busy"
        self.assertFalse(distractions.lift_notification_block())
        self.assertEqual(distractions.read_counts(), {"WhatsApp": 4})
        self.assertTrue(any(item[0] == "Focus mode" for item in self.notices))
        self.assertFalse(any(item[0] == "While you were focused" for item in self.notices))

    def test_notice_failure_preserves_counts(self):
        self.seed_counts({"X": 2})
        self.notice_ok = False
        self.assertTrue(distractions.lift_notification_block())
        self.assertEqual(distractions.read_counts(), {"X": 2})

    def test_watcher_ack_failure_preserves_counts(self):
        self.seed_counts({"Messages": 1})

        def fail_ack(generation, want_armed, timeout=8.0):
            return False, "watcher acknowledgement timed out"

        with mock.patch.object(distractions, "wait_watcher_ack", fail_ack):
            self.assertFalse(distractions.lift_notification_block())
        self.assertEqual(distractions.read_counts(), {"Messages": 1})
        self.assertFalse(any(item[0] == "While you were focused" for item in self.notices))

    def test_disable_focus_keeps_mode_off_toast(self):
        self.seed_counts({"Telegram": 1})
        reason = "x" * 50
        with mock.patch.object(distractions, "log_path", return_value=self.state / "log"):
            with mock.patch.object(distractions, "on_distractions", return_value=False):
                distractions.disable_focus(reason)
        titles = [item[0] for item in self.notices]
        self.assertIn("While you were focused", titles)
        self.assertIn("Focus mode off", titles)
        self.assertEqual(titles[-1], "Focus mode off")


class QmlCountContractTests(unittest.TestCase):
    def setUp(self):
        self.text = QML.read_text()

    def test_serializes_increments_through_one_helper_queue(self):
        self.assertIn("count-increment", self.text)
        self.assertIn("enqueueCount", self.text)
        self.assertIn("pumpCount", self.text)
        self.assertIn("id: countProc", self.text)
        self.assertEqual(self.text.count("id: countProc"), 1)
        live = self.text[self.text.find("function suppressLive") : self.text.find("function pumpRestored")]
        self.assertLess(live.find("deletePopupFileFor(row)"), live.find("enqueueCount(label)"))

    def test_count_queue_holds_drain_until_helper_exits(self):
        self.assertIn("countQueue", self.text)
        self.assertIn("pendingOps", self.text)
        self.assertIn("countBusy", self.text)
        self.assertIn("countFailed", self.text)
        self.assertIn("exitCode !== 0", self.text)
        self.assertIn('return "error"', self.text)

    def test_failed_increment_is_kept_until_persisted(self):
        exited = self.text[self.text.find("id: countProc") : self.text.find("id: focusStatus")]
        fail_return = exited.find("root.countFailed = true")
        pending_drop = exited.find("pendingOps")
        self.assertGreater(fail_return, 0)
        self.assertGreater(pending_drop, fail_return)
        self.assertIn("return", exited[fail_return:pending_drop])
        armed = self.text[self.text.find("function setArmed") : self.text.find("function tryBind")]
        self.assertNotIn("countFailed = false", armed)
        self.assertIn("countLabel", armed)
        self.assertIn("pumpCount", armed)

    def test_suppressed_rows_bypass_archive_and_history(self):
        self.assertIn("deletePopupFileFor", self.text)
        self.assertNotIn("dismissPopup", self.text)
        self.assertNotIn("removePopup", self.text)
        self.assertNotIn("showHistory", self.text)
        self.assertNotIn("writeSilenced", self.text)

    def test_restored_reconcile_does_not_increment(self):
        restored = self.text[self.text.find("function suppressRestored") :]
        self.assertNotIn("enqueueCount", restored.split("FileView")[0])


class DocsContractTests(unittest.TestCase):
    def test_readme_covers_mute_catchup_and_failures(self):
        text = README.read_text()
        self.assertIn("no banner and no sound", text)
        self.assertIn("grouped notice", text)
        self.assertIn("mute cannot apply", text)
        self.assertIn("restore fails", text)
        self.assertIn("bar layout", text)
        self.assertIn("notification filter service", text)
        self.assertNotIn("count-increment", text)

    def test_commands_section_unchanged_shape(self):
        text = README.read_text()
        commands = text.split("## Commands", 1)[1]
        self.assertIn("distractions toggle", commands)
        self.assertIn("distractions focus", commands)
        self.assertIn("distractions install", commands)
        self.assertNotIn("count-increment", commands)

    def test_manifest_mentions_mute_and_catchup(self):
        data = json.loads(MANIFEST.read_text())
        blob = data["description"] + " " + data["barWidget"]["description"]
        self.assertIn("mute", blob.lower())
        self.assertIn("grouped count", blob.lower())
        self.assertIn("service", data["kinds"])


if __name__ == "__main__":
    unittest.main()
