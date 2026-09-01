#!/usr/bin/env python3
"""Session timer auto-disable (fn-6.2)."""

from __future__ import annotations

import inspect
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
distractions = SourceFileLoader("distractions_timer", str(ROOT / "distractions")).load_module()
BAR = ROOT / "BarWidget.qml"


class TimerHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / "state"
        self.runtime = root / "run"
        self.state.mkdir()
        self.runtime.mkdir()
        self.cfg = root / "focus.json"
        self.cfg.write_text("{}\n")
        self.log = self.state / "disable.log"
        self.notices: list[tuple[str, str]] = []
        self.patches = [
            mock.patch.object(distractions, "STATE_DIR", self.state),
            mock.patch.object(distractions, "FOCUS", self.state / "distractions.focus"),
            mock.patch.object(distractions, "CONFIG_PATH", self.cfg),
            mock.patch.object(distractions, "SUMMARY_STATE_LOCK", self.runtime / "summary-state.lock"),
            mock.patch.object(distractions, "FOCUS_CONFIG_LOCK", self.runtime / "focus.json.lock"),
            mock.patch.object(distractions, "FOCUS_TRANSITION_LOCK", self.runtime / "focus-transition.lock"),
            mock.patch.object(distractions, "log_path", lambda: self.log),
            mock.patch.object(distractions, "notify", self._notify),
            mock.patch.object(distractions, "apply_network_block"),
            mock.patch.object(distractions, "lift_network_block"),
            mock.patch.object(distractions, "on_distractions", return_value=False),
            mock.patch.object(distractions, "apply_notification_block", return_value=True),
            mock.patch.object(distractions, "lift_notification_block", return_value=True),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        distractions._timer_off_launched_for = None
        distractions.set_focus(True)

    def _notify(self, title, body="", **_kwargs):
        self.notices.append((title, body))
        return True

    def wall_now(self) -> datetime:
        return datetime.now(timezone.utc).astimezone()

    def write_active(
        self,
        purpose: str,
        deadline,
        session_id: str = "sess-1",
        activation: str | None = None,
    ) -> None:
        if isinstance(deadline, datetime):
            deadline = deadline.isoformat(timespec="seconds")
        payload = {"purpose": purpose, "deadline": deadline, "session_id": session_id}
        if activation is not None:
            payload["activation"] = activation
        distractions.write_private_atomic(
            distractions.session_active_path(),
            json.dumps(payload) + "\n",
        )

    def write_recap(self, purpose: str, session_id: str = "sess-1") -> None:
        distractions.write_private_atomic(
            distractions.session_recap_path(),
            json.dumps({"purpose": purpose, "session_id": session_id}) + "\n",
        )

    def seed_session(self, purpose: str = "write the docs", *, past: bool = True) -> None:
        delta = timedelta(minutes=-5) if past else timedelta(minutes=25)
        self.write_active(purpose, self.wall_now() + delta)
        self.write_recap(purpose)

    def log_text(self) -> str:
        if not self.log.exists():
            return ""
        return self.log.read_text(encoding="utf-8")


class TimerDisableTests(TimerHarness):
    def test_elapsed_deadline_turns_focus_off_without_min_reason(self):
        self.seed_session("ship the timer")
        distractions.disable_focus_timer()
        self.assertFalse(distractions.is_focus())
        self.assertLess(len("ship the timer"), distractions.MIN_REASON)

    def test_timer_log_includes_purpose_and_timer_marker(self):
        self.seed_session("deep work block")
        distractions.disable_focus_timer()
        text = self.log_text()
        self.assertIn("deep work block", text)
        self.assertIn("timer", text)

    def test_handoff_disable_appends_active_purpose(self):
        self.seed_session("keep the purpose")
        reason = "x" * distractions.MIN_REASON
        distractions.disable_focus(reason)
        text = self.log_text()
        self.assertIn(reason, text)
        self.assertIn("keep the purpose", text)
        self.assertNotIn("timer", text)

    def test_handoff_still_requires_min_reason(self):
        self.seed_session()
        with self.assertRaises(SystemExit) as raised:
            distractions.disable_focus("too short")
        self.assertIn(str(distractions.MIN_REASON), str(raised.exception))
        self.assertTrue(distractions.is_focus())
        self.assertEqual(self.log_text(), "")

    def test_timer_disable_keeps_recap_pending(self):
        self.seed_session("keep recap")
        recap = dict(distractions.read_session_recap())
        distractions.disable_focus_timer()
        self.assertEqual(distractions.read_session_recap(), recap)
        self.assertIsNone(distractions.read_session_active())

    def test_already_off_timer_confirm_is_noop(self):
        self.seed_session()
        distractions.set_focus(False)
        distractions.disable_focus_timer()
        distractions.disable_focus("x" * distractions.MIN_REASON)
        self.assertEqual(self.log_text(), "")
        self.assertEqual(self.notices, [])
        self.assertFalse(distractions.is_focus())
        self.assertIsNotNone(distractions.read_session_active())

    def test_late_short_handoff_after_timer_is_noop(self):
        self.seed_session("timer won")
        distractions.disable_focus_timer()
        self.assertFalse(distractions.is_focus())
        distractions.disable_focus("too short")
        self.assertIn("timer", self.log_text())
        self.assertEqual(self.log_text().count("\n"), 1)
        self.assertFalse(distractions.is_focus())

    def test_timer_off_before_deadline_is_noop(self):
        self.seed_session("not yet", past=False)
        self.write_active("far future", datetime(2999, 1, 1, tzinfo=timezone.utc), "sess-2999")
        distractions.disable_focus_timer()
        self.assertTrue(distractions.is_focus())
        self.assertEqual(self.log_text(), "")
        self.assertIsNotNone(distractions.read_session_active())

    def test_stale_handoff_does_not_disable_new_session(self):
        self.write_active("session a", self.wall_now() - timedelta(minutes=5), "sess-a")
        self.write_recap("session a", "sess-a")

        def confirm_after_new_session():
            distractions.disable_focus_timer()
            distractions.set_focus(True)
            self.write_active("session b", self.wall_now() + timedelta(minutes=25), "sess-b")
            self.write_recap("session b", "sess-b")
            return "x" * distractions.MIN_REASON

        with mock.patch.object(distractions, "prompt_reason", confirm_after_new_session):
            distractions.request_focus_toggle()
        self.assertTrue(distractions.is_focus())
        self.assertEqual(distractions.read_session_active()["session_id"], "sess-b")
        self.assertIn("timer", self.log_text())
        self.assertNotIn("x" * distractions.MIN_REASON, self.log_text())

    def test_stale_handoff_reused_id_same_deadline_is_noop(self):
        deadline = self.wall_now() - timedelta(minutes=5)
        self.write_active("session a", deadline, "sess-reuse", activation="act-a")
        self.write_recap("session a", "sess-reuse")

        def confirm_reused_identity():
            distractions.disable_focus_timer()
            distractions.set_focus(True)
            self.write_active("session b", deadline, "sess-reuse", activation="act-b")
            self.write_recap("session b", "sess-reuse")
            return "x" * distractions.MIN_REASON

        with mock.patch.object(distractions, "prompt_reason", confirm_reused_identity):
            distractions.request_focus_toggle()
        self.assertTrue(distractions.is_focus())
        active = distractions.read_session_active()
        self.assertEqual(active["session_id"], "sess-reuse")
        self.assertEqual(active["activation"], "act-b")
        self.assertEqual(active["purpose"], "session b")
        self.assertIn("timer", self.log_text())
        self.assertNotIn("x" * distractions.MIN_REASON, self.log_text())

    def test_short_reason_timer_win_before_validate_is_noop(self):
        self.seed_session("race")
        real_lock = distractions._lock_focus_transition

        def lock_after_timer():
            if distractions.is_focus():
                with mock.patch.object(distractions, "_lock_focus_transition", real_lock):
                    distractions.disable_focus_timer()
            return real_lock()

        with mock.patch.object(distractions, "_lock_focus_transition", lock_after_timer):
            distractions.disable_focus("too short")
        self.assertFalse(distractions.is_focus())
        self.assertIn("timer", self.log_text())
        self.assertEqual(self.log_text().count("\n"), 1)


class TimerFireTests(TimerHarness):
    def test_listener_restart_future_deadline_does_not_fire_past_does(self):
        src = inspect.getsource(distractions.listen)
        bootstrap, loop = src.split("while True:", 1)
        self.assertNotIn("maybe_fire_session_timer", bootstrap)
        self.assertIn("maybe_fire_session_timer", loop)
        self.assertLess(loop.find("select.select"), loop.find("maybe_fire_session_timer"))
        spawned: list[str] = []

        def fake_spawn():
            spawned.append("timer-off")

        with mock.patch.object(distractions, "spawn_focus_timer_off", fake_spawn):
            self.seed_session("later", past=False)
            distractions.maybe_fire_session_timer()
            self.assertEqual(spawned, [])
            self.assertTrue(distractions.is_focus())
            distractions._timer_off_launched_for = None
            self.seed_session("overdue", past=True)
            distractions.maybe_fire_session_timer()
        self.assertEqual(spawned, ["timer-off"])
        self.assertTrue(distractions.is_focus())

    def test_consecutive_due_sessions_each_fire_timer(self):
        spawned: list[str] = []

        def fake_spawn():
            spawned.append("timer-off")

        with mock.patch.object(distractions, "spawn_focus_timer_off", fake_spawn):
            self.write_active("first", self.wall_now() - timedelta(minutes=5), "sess-a")
            distractions.maybe_fire_session_timer()
            self.assertEqual(spawned, ["timer-off"])
            distractions.set_focus(False)
            distractions.maybe_fire_session_timer()
            distractions.set_focus(True)
            self.write_active("second", self.wall_now() - timedelta(minutes=1), "sess-b")
            distractions.maybe_fire_session_timer()
        self.assertEqual(spawned, ["timer-off", "timer-off"])
        self.assertTrue(distractions.is_focus())

    def test_missing_corrupt_truncated_does_not_timer_disable(self):
        cases = (
            "missing",
            "truncated",
            "corrupt",
            "naive",
            "no-deadline",
        )
        path = distractions.session_active_path()
        for case in cases:
            with self.subTest(case=case):
                distractions.set_focus(True)
                distractions._timer_off_launched_for = None
                if path.exists():
                    path.unlink()
                if case == "truncated":
                    path.write_text('{"purpose": "x", "deadline":')
                    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
                elif case == "corrupt":
                    path.write_text("{not-json")
                    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
                elif case == "naive":
                    self.write_active("x", "2020-01-01T00:00:00")
                elif case == "no-deadline":
                    distractions.write_private_atomic(
                        path,
                        json.dumps({"purpose": "x", "session_id": "sess-1"}) + "\n",
                    )
                spawned = []
                with mock.patch.object(
                    distractions, "spawn_focus_timer_off", lambda: spawned.append("x")
                ):
                    distractions.maybe_fire_session_timer()
                    distractions.disable_focus_timer()
                self.assertEqual(spawned, [])
                self.assertTrue(distractions.is_focus())
                self.assertEqual(self.log_text(), "")

    def test_timer_off_spawns_detached_helper(self):
        self.seed_session("detach me")
        calls: list[dict] = []

        def fake_popen(argv, **kwargs):
            calls.append({"argv": list(argv), **kwargs})
            return mock.Mock()

        with mock.patch.object(distractions.subprocess, "Popen", fake_popen):
            with mock.patch.object(distractions, "_disable_focus_locked") as locked:
                distractions.maybe_fire_session_timer()
                locked.assert_not_called()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["argv"][-1], "focus-timer-off")
        self.assertTrue(calls[0]["start_new_session"])
        with mock.patch.object(sys, "argv", ["distractions", "focus-timer-off"]):
            distractions.main()
        self.assertFalse(distractions.is_focus())

    def test_eye_icon_unchanged(self):
        text = BAR.read_text()
        self.assertIn('text: "󰈈"', text)
        self.assertIn("interval: 2000", text)
        self.assertNotIn("focus-timer-off", text)


if __name__ == "__main__":
    unittest.main()
