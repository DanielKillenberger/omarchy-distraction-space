#!/usr/bin/env python3
"""Start dialog gate and session UI flags (fn-6.1)."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
distractions = SourceFileLoader("distractions_start", str(ROOT / "distractions")).load_module()


class StartHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / "state"
        self.runtime = root / "run"
        self.state.mkdir()
        self.runtime.mkdir()
        self.cfg = root / "focus.json"
        self.cfg.write_text("{}\n")
        self.dialog_calls: list[dict] = []
        self.patches = [
            mock.patch.object(distractions, "STATE_DIR", self.state),
            mock.patch.object(distractions, "FOCUS", self.state / "distractions.focus"),
            mock.patch.object(distractions, "CONFIG_PATH", self.cfg),
            mock.patch.object(distractions, "SUMMARY_STATE_LOCK", self.runtime / "summary-state.lock"),
            mock.patch.object(distractions, "FOCUS_CONFIG_LOCK", self.runtime / "focus.json.lock"),
            mock.patch.object(distractions, "FOCUS_TRANSITION_LOCK", self.runtime / "focus-transition.lock"),
            mock.patch.object(distractions, "notify", lambda *args, **kwargs: True),
            mock.patch.object(distractions, "apply_network_block"),
            mock.patch.object(distractions, "on_distractions", return_value=False),
            mock.patch.object(distractions, "apply_notification_block", return_value=True),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        distractions.set_focus(False)

    def inject_dialog(self, result):
        def fake(*, ask_purpose=True):
            self.dialog_calls.append({"ask_purpose": ask_purpose})
            return result

        return mock.patch.object(distractions, "prompt_focus_start", fake)

    def parse_deadline(self, text: str) -> datetime:
        return datetime.fromisoformat(text)


class ConfirmStartTests(StartHarness):
    def test_confirm_enables_and_stores_active_and_recap(self):
        with self.inject_dialog(("write the docs", 25)):
            distractions.request_focus_on()
        self.assertTrue(distractions.is_focus())
        active = distractions.read_session_active()
        recap = distractions.read_session_recap()
        control = distractions.read_summary_control()
        self.assertEqual(active["purpose"], "write the docs")
        self.assertEqual(active["session_id"], control["session_id"])
        self.assertTrue(control["session_id"])
        deadline = self.parse_deadline(active["deadline"])
        expected = datetime.now(timezone.utc).astimezone() + timedelta(minutes=25)
        self.assertLess(abs((deadline - expected).total_seconds()), 5)
        self.assertEqual(recap["purpose"], "write the docs")
        self.assertEqual(recap["session_id"], control["session_id"])
        self.assertEqual(oct(distractions.session_active_path().stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(distractions.session_recap_path().stat().st_mode & 0o777), "0o600")

    def test_focus_and_focus_on_argv_use_the_gate(self):
        with self.inject_dialog(("from argv", 25)):
            with mock.patch.object(sys, "argv", ["distractions", "focus-on"]):
                distractions.main()
        self.assertTrue(distractions.is_focus())
        self.assertEqual(distractions.read_session_active()["purpose"], "from argv")
        distractions.set_focus(False)
        self.dialog_calls.clear()
        with self.inject_dialog(("from toggle", 30)):
            with mock.patch.object(sys, "argv", ["distractions", "focus"]):
                distractions.main()
        self.assertEqual(distractions.read_session_active()["purpose"], "from toggle")
        self.assertEqual(len(self.dialog_calls), 1)

    def test_reuse_session_id_updates_active_keeps_recap(self):
        with self.inject_dialog(("first purpose", 25)):
            distractions.request_focus_on()
        first_active = dict(distractions.read_session_active())
        first_recap = dict(distractions.read_session_recap())
        control = distractions.read_summary_control()
        control["lift_fail_pending"] = True
        distractions.write_summary_control(control)
        distractions.set_focus(False)
        with self.inject_dialog(("second purpose", 40)):
            distractions.request_focus_on()
        active = distractions.read_session_active()
        recap = distractions.read_session_recap()
        self.assertEqual(active["purpose"], "second purpose")
        self.assertEqual(active["session_id"], first_active["session_id"])
        self.assertNotEqual(active["deadline"], first_active["deadline"])
        self.assertEqual(recap, first_recap)

    def test_minutes_default_and_bounds(self):
        self.assertEqual(distractions.SESSION_MINUTES_DEFAULT, 25)
        for minutes in (1, 240):
            with self.subTest(minutes=minutes):
                distractions.set_focus(False)
                with self.inject_dialog(("bounded", minutes)):
                    distractions.request_focus_on()
                deadline = self.parse_deadline(distractions.read_session_active()["deadline"])
                expected = datetime.now(timezone.utc).astimezone() + timedelta(minutes=minutes)
                self.assertLess(abs((deadline - expected).total_seconds()), 5)


class RefuseStartTests(StartHarness):
    def test_dismiss_whitespace_and_out_of_range_leave_focus_off(self):
        cases = (
            None,
            ("   \t  ", 25),
            ("keep going", 0),
            ("keep going", 241),
        )
        for result in cases:
            with self.subTest(result=result):
                distractions.set_focus(False)
                with self.inject_dialog(result):
                    distractions.request_focus_on()
                self.assertFalse(distractions.is_focus())
                self.assertIsNone(distractions.read_session_active())
                self.assertIsNone(distractions.read_session_recap())

    def test_already_on_focus_on_skips_dialog(self):
        distractions.set_focus(True)
        with self.inject_dialog(("should not run", 25)):
            distractions.request_focus_on()
            with mock.patch.object(sys, "argv", ["distractions", "focus-on"]):
                distractions.main()
        self.assertEqual(self.dialog_calls, [])
        self.assertIsNone(distractions.read_session_active())


class StartFlagTests(StartHarness):
    def test_start_ui_off_skips_dialog_and_uses_25(self):
        self.assertTrue(distractions.update_focus_config(session_start_ui=False))
        with self.inject_dialog(("unused", 99)):
            distractions.request_focus_on()
        self.assertEqual(self.dialog_calls, [])
        self.assertTrue(distractions.is_focus())
        active = distractions.read_session_active()
        self.assertEqual(active["purpose"], "")
        deadline = self.parse_deadline(active["deadline"])
        expected = datetime.now(timezone.utc).astimezone() + timedelta(minutes=25)
        self.assertLess(abs((deadline - expected).total_seconds()), 5)

    def test_start_purpose_off_collects_minutes_only(self):
        self.assertTrue(distractions.update_focus_config(session_start_purpose=False))
        with self.inject_dialog(("ignored purpose", 12)):
            distractions.request_focus_on()
        self.assertEqual(self.dialog_calls, [{"ask_purpose": False}])
        self.assertTrue(distractions.is_focus())
        self.assertEqual(distractions.read_session_active()["purpose"], "")
        deadline = self.parse_deadline(distractions.read_session_active()["deadline"])
        expected = datetime.now(timezone.utc).astimezone() + timedelta(minutes=12)
        self.assertLess(abs((deadline - expected).total_seconds()), 5)

    def test_truncated_active_is_absent(self):
        path = distractions.session_active_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"purpose": "x", "deadline":')
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        self.assertIsNone(distractions.read_session_active())

    def test_malformed_session_records_are_absent(self):
        active = distractions.session_active_path()
        recap = distractions.session_recap_path()
        active.parent.mkdir(parents=True, exist_ok=True)
        cases = (
            (active, {"purpose": 1, "deadline": "2026-09-01T12:00:00+00:00", "session_id": "s1"}),
            (active, {"purpose": "ok", "deadline": ["not", "iso"], "session_id": "s1"}),
            (active, {"purpose": "ok", "deadline": "not-iso", "session_id": "s1"}),
            (recap, {"purpose": 12, "session_id": "s1"}),
        )
        for path, payload in cases:
            with self.subTest(payload=payload):
                path.write_text(json.dumps(payload))
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
                if path == active:
                    self.assertIsNone(distractions.read_session_active())
                else:
                    self.assertIsNone(distractions.read_session_recap())

    def test_invalid_utf8_active_is_absent(self):
        path = distractions.session_active_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'{"purpose": "\xff", "deadline": "2026-09-01T12:00:00+00:00", "session_id": "s1"}')
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        self.assertIsNone(distractions.read_session_active())


class StaleStartTests(StartHarness):
    def test_stale_dialog_confirm_does_not_replace_active(self):
        with self.inject_dialog(("first purpose", 25)):
            distractions.request_focus_on()
        first = dict(distractions.read_session_active())
        first_recap = dict(distractions.read_session_recap())
        real_is_focus = distractions.is_focus
        checks = {"n": 0}

        def already_on_after_collect():
            checks["n"] += 1
            if checks["n"] == 1:
                return False
            return real_is_focus()

        with mock.patch.object(distractions, "is_focus", side_effect=already_on_after_collect):
            with self.inject_dialog(("stale purpose", 40)):
                distractions.request_focus_on()
        self.assertEqual(distractions.read_session_active(), first)
        self.assertEqual(distractions.read_session_recap(), first_recap)
        self.assertEqual(len(self.dialog_calls), 2)
