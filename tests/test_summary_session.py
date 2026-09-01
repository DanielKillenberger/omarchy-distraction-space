#!/usr/bin/env python3
"""Service composition, capture, and session start (fn-3.2)."""

from __future__ import annotations

import fcntl
import io
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
distractions = SourceFileLoader("distractions_session", str(ROOT / "distractions")).load_module()
FILTER = ROOT / "NotificationFilter.qml"
CAPTURE = ROOT / "PingCapture.qml"
MANIFEST = ROOT / "manifest.json"


class SessionHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / "state"
        self.runtime = root / "run"
        self.state.mkdir()
        self.runtime.mkdir()
        self.cfg = root / "focus.json"
        self.cfg.write_text(json.dumps({"agent_summaries": True, "summary_agent": "claude"}) + "\n")
        self.patches = [
            mock.patch.object(distractions, "STATE_DIR", self.state),
            mock.patch.object(distractions, "FOCUS", self.state / "distractions.focus"),
            mock.patch.object(distractions, "CONFIG_PATH", self.cfg),
            mock.patch.object(distractions, "SUMMARY_STATE_LOCK", self.runtime / "summary-state.lock"),
            mock.patch.object(distractions, "SUMMARIZE_SESSION_LOCK", self.runtime / "summarize-session.lock"),
            mock.patch.object(distractions, "FOCUS_CONFIG_LOCK", self.runtime / "focus.json.lock"),
            mock.patch.object(distractions, "notify", lambda *args, **kwargs: True),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        distractions.set_focus(True)

    def ready_session(self, **overrides) -> dict:
        control = distractions.default_summary_control()
        control["session_id"] = "sess-1"
        control["session_ready"] = True
        control.update(overrides)
        distractions.write_summary_control(control)
        return control

    def record(self, **fields) -> dict:
        payload = {
            "app": "Telegram Desktop",
            "title": "hi",
            "body": "ping",
            "at": "2026-09-01T00:00:00Z",
        }
        payload.update(fields)
        return payload


class LockSeparationTests(SessionHarness):
    def test_capture_appends_while_parser_lifetime_guard_is_held(self):
        self.ready_session()
        guard = distractions.try_summarize_session_lock()
        self.addCleanup(guard.close)
        written = distractions.capture_ping(self.record())
        self.assertEqual(written["seq"], 1)
        self.assertEqual(distractions.read_ping_records()[0]["seq"], 1)
        self.assertEqual(distractions.read_counts(), {})

    def test_state_and_lifetime_locks_are_distinct_files(self):
        self.assertNotEqual(distractions.SUMMARY_STATE_LOCK, distractions.SUMMARIZE_SESSION_LOCK)
        self.assertNotEqual(distractions.SUMMARY_STATE_LOCK, distractions.LISTEN_LOCK)


class CaptureLockTests(SessionHarness):
    def test_lock_timeout_is_append_failure_near_250ms(self):
        self.ready_session()
        holder = open(distractions.SUMMARY_STATE_LOCK, "w")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        self.addCleanup(holder.close)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            distractions.capture_ping(self.record())
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.2)
        self.assertLess(elapsed, 1.0)
        self.assertEqual(distractions.read_ping_records(), [])

    def test_locked_append_is_monotonic_and_trims_oldest_without_renumber(self):
        self.ready_session()
        distractions.PING_JSONL_MAX_BYTES = 180
        first = distractions.capture_ping(self.record(title="one", body="x" * 40))
        second = distractions.capture_ping(self.record(title="two", body="y" * 40))
        third = distractions.capture_ping(self.record(title="three", body="z" * 40))
        seqs = [row["seq"] for row in distractions.read_ping_records()]
        self.assertEqual(first["seq"], 1)
        self.assertEqual(second["seq"], 2)
        self.assertEqual(third["seq"], 3)
        self.assertNotIn(1, seqs)
        self.assertEqual(seqs, list(range(seqs[0], seqs[0] + len(seqs))))
        self.assertLessEqual(distractions.ping_text_path().stat().st_size, 180)
        self.assertEqual(oct(distractions.ping_text_path().stat().st_mode & 0o777), "0o600")

    def test_stale_or_unfocused_capture_is_rejected(self):
        self.ready_session(session_ready=False)
        with self.assertRaises(ValueError):
            distractions.capture_ping(self.record())
        self.ready_session()
        distractions.set_focus(False)
        with self.assertRaises(ValueError):
            distractions.capture_ping(self.record())
        distractions.set_focus(True)
        self.ready_session(finish_requested=True)
        with self.assertRaises(ValueError):
            distractions.capture_ping(self.record())
        self.assertEqual(distractions.read_ping_records(), [])

    def test_identity_map_miss_does_not_write_ping_text(self):
        self.ready_session()
        self.assertIsNone(distractions.match_banner("firefox", "", "https://example.com"))
        if distractions.match_banner("firefox", "", "plain"):
            self.fail("identity miss must skip capture")
        self.assertEqual(distractions.read_ping_records(), [])
        self.assertIn("memberLabelFor(row)", FILTER.read_text())
        observed = FILTER.read_text()
        gate = observed[observed.find("function onRowObserved") : observed.find("function enqueueCount")]
        self.assertLess(gate.find("!memberLabelFor(row)"), gate.find("enqueueMemberToast"))


class FocusOnOrderTests(SessionHarness):
    def test_prepare_before_flag_ready_after_mute_binds_new_session(self):
        order: list[str] = []
        previous = distractions.default_summary_control()
        previous["session_id"] = "old-session"
        previous["next_seq"] = 9
        distractions.write_summary_control(previous)

        real_prepare = distractions.prepare_summary_session

        def track_prepare():
            order.append("prepare")
            return real_prepare()

        def track_set(value):
            order.append("flag")
            self.assertTrue(distractions.read_summary_control().get("session_id"))
            self.assertFalse(distractions.read_summary_control().get("session_ready"))
            return real_set(value)

        def track_mute():
            order.append("mute")
            return True

        def track_ready():
            order.append("ready")
            return real_ready()

        real_set = distractions.set_focus
        real_ready = distractions.mark_summary_session_ready
        with mock.patch.object(distractions, "prepare_summary_session", track_prepare):
            with mock.patch.object(distractions, "set_focus", track_set):
                with mock.patch.object(distractions, "apply_network_block"):
                    with mock.patch.object(distractions, "on_distractions", return_value=False):
                        with mock.patch.object(distractions, "apply_notification_block", track_mute):
                            with mock.patch.object(distractions, "mark_summary_session_ready", track_ready):
                                distractions.enable_focus()
        self.assertEqual(order, ["prepare", "flag", "mute", "ready"])
        control = distractions.read_summary_control()
        self.assertNotEqual(control["session_id"], "old-session")
        self.assertTrue(control["session_ready"])
        self.assertEqual(control["next_seq"], 1)
        first = distractions.capture_ping(self.record())
        self.assertEqual(first["seq"], 1)

    def test_pending_catchup_does_not_reset_session(self):
        self.ready_session(session_id="kept", next_seq=4, lift_fail_pending=True)
        ping = distractions.ping_text_path()
        ping.write_text(json.dumps({"seq": 3, "app": "X", "title": "t", "body": "b", "at": "t"}) + "\n")
        control = distractions.prepare_summary_session()
        self.assertEqual(control["session_id"], "kept")
        self.assertEqual(control["next_seq"], 4)
        self.assertTrue(ping.exists())
        self.assertFalse(control["session_ready"])

    def test_mute_failure_does_not_publish_ready(self):
        with mock.patch.object(distractions, "apply_network_block"):
            with mock.patch.object(distractions, "on_distractions", return_value=False):
                with mock.patch.object(distractions, "apply_notification_block", return_value=False):
                    distractions.enable_focus()
        control = distractions.read_summary_control()
        self.assertTrue(control["session_id"])
        self.assertFalse(control["session_ready"])


class RestartBudgetTests(SessionHarness):
    def test_restart_counter_and_mocked_backoff_then_cap(self):
        self.ready_session()
        sleeps: list[float] = []
        with mock.patch.object(distractions.time, "sleep", side_effect=lambda s: sleeps.append(s)):
            first = distractions.apply_parser_restart()
            second = distractions.apply_parser_restart()
            refused = distractions.apply_parser_restart()
        self.assertEqual(first["parser_restarts"], 1)
        self.assertEqual(second["parser_restarts"], 2)
        self.assertIsNone(refused)
        self.assertEqual(sleeps, [1.0, 4.0])
        closed = distractions.read_summary_control()
        self.assertEqual(closed["parser_restarts"], 2)
        self.assertTrue(closed["parser_closed"])
        self.assertFalse(closed["session_ready"])
        self.assertFalse(closed["parser_active"])

    def test_quickshell_restart_cannot_reset_or_double_count(self):
        self.ready_session(parser_restarts=1, parser_active=True)
        with mock.patch.object(distractions.time, "sleep"):
            again = distractions.apply_parser_restart()
        self.assertEqual(again["parser_restarts"], 2)
        qml = CAPTURE.read_text()
        self.assertIn("--restart", qml)
        self.assertIn("--session", qml)
        self.assertNotIn("parser_restarts +", qml)
        self.assertNotIn("parser_restarts +=", qml)

    def test_clean_finish_and_disable_do_not_restart(self):
        self.ready_session(parser_active=True)
        distractions.request_summary_finish()
        control = distractions.read_summary_control()
        self.assertTrue(control["finish_requested"])
        self.assertFalse(control["session_ready"])
        self.assertFalse(control["parser_active"])
        self.assertTrue(distractions.should_stop_parser(control))
        self.cfg.write_text(json.dumps({"agent_summaries": False}) + "\n")
        self.assertTrue(distractions.should_stop_parser())

    def test_mid_session_disable_discards_unread_and_stops_capture(self):
        self.ready_session(agent_pid=None)
        distractions.capture_ping(self.record())
        distractions.update_focus_config(agent_summaries=False)
        distractions.request_summary_finish()
        with self.assertRaises(ValueError):
            distractions.capture_ping(self.record(title="late"))
        self.assertEqual(len(distractions.read_ping_records()), 1)
        self.assertTrue(distractions.should_stop_parser())
        self.assertEqual(distractions.read_counts(), {})


class ParserObserveTests(SessionHarness):
    def test_first_record_visible_without_kick_and_singleton_blocks_second(self):
        self.ready_session()
        distractions.capture_ping(self.record(title="first"))
        seen = distractions.observe_ping_records(0)
        self.assertEqual([row["title"] for row in seen], ["first"])
        first = distractions.try_summarize_session_lock()
        self.assertIsNotNone(first)
        self.addCleanup(first.close)
        self.assertIsNone(distractions.try_summarize_session_lock())
        with mock.patch.object(distractions.time, "sleep"):
            self.assertEqual(distractions.run_summarize_session(once=True), 2)
        self.assertFalse(distractions.read_summary_control()["parser_active"])

    def test_files_are_0600_and_session_bound(self):
        self.ready_session()
        distractions.capture_ping(self.record())
        self.assertEqual(oct(distractions.summary_control_path().stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(distractions.ping_text_path().stat().st_mode & 0o777), "0o600")


class CliSilenceTests(SessionHarness):
    def test_no_cli_dumps_ping_or_result_while_focused(self):
        self.ready_session()
        distractions.capture_ping(self.record(title="SECRET-PING", body="SECRET-BODY"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            stdin = io.StringIO(json.dumps(self.record(title="more")) + "\n")
            with mock.patch.object(distractions.sys, "stdin", stdin):
                try:
                    distractions.cmd_capture_ping()
                except SystemExit:
                    pass
            distractions.cmd_summarize_session = distractions.cmd_summarize_session
            with mock.patch.object(distractions, "run_summarize_session", return_value=0):
                distractions.cmd_summarize_session()
        text = buf.getvalue()
        self.assertNotIn("SECRET-PING", text)
        self.assertNotIn("SECRET-BODY", text)
        self.assertNotIn("sess-1", text)

    def test_unknown_dump_commands_do_not_exist(self):
        source = Path(ROOT / "distractions").read_text()
        main = source[source.find("def main()") :]
        for name in ('"dump-pings"', '"show-summary"', '"ping-text"', '"print-result"'):
            self.assertNotIn(name, main)


class ReviewFixTests(SessionHarness):
    def test_mid_session_enable_republishes_ready(self):
        self.ready_session(finish_requested=True, session_ready=False)
        self.cfg.write_text(json.dumps({"agent_summaries": False}) + "\n")
        with mock.patch.object(distractions, "menu_select", return_value="On"):
            with mock.patch.object(distractions, "apply_notification_block", return_value=True):
                distractions.cmd_agent_summaries()
        control = distractions.read_summary_control()
        self.assertTrue(control["session_ready"])
        self.assertFalse(control["finish_requested"])
        self.assertEqual(control["session_id"], "sess-1")
        written = distractions.capture_ping(self.record(title="after-on"))
        self.assertEqual(written["seq"], 1)

    def test_restart_rejects_foreign_session_and_busy_lock(self):
        self.ready_session(session_id="keep")
        with mock.patch.object(distractions.time, "sleep"):
            self.assertIsNone(distractions.apply_parser_restart("other"))
        self.assertEqual(distractions.read_summary_control()["parser_restarts"], 0)
        with mock.patch.object(distractions.time, "sleep"):
            self.assertIsNotNone(distractions.apply_parser_restart("keep"))
        self.assertEqual(distractions.read_summary_control()["parser_restarts"], 1)
        guard = distractions.try_summarize_session_lock()
        self.addCleanup(guard.close)
        self.assertEqual(distractions.run_summarize_session(restart=True, expected_session="keep"), 2)
        self.assertEqual(distractions.read_summary_control()["parser_restarts"], 1)

    def test_seq_is_reserved_before_jsonl_publish(self):
        self.ready_session()
        with mock.patch.object(distractions, "write_ping_jsonl", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                distractions.capture_ping(self.record())
        self.assertEqual(distractions.read_summary_control()["next_seq"], 2)
        self.assertEqual(distractions.read_ping_records(), [])
        written = distractions.capture_ping(self.record(title="gap"))
        self.assertEqual(written["seq"], 2)

    def test_disabled_summaries_reject_capture(self):
        self.ready_session()
        self.cfg.write_text(json.dumps({"agent_summaries": False}) + "\n")
        with self.assertRaises(ValueError):
            distractions.capture_ping(self.record())

    def test_config_path_follows_xdg_config_home(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/xdg-config"}):
            self.assertEqual(distractions.config_home(), Path("/tmp/xdg-config"))

    def test_enable_requires_mute_and_disable_requires_write(self):
        self.ready_session(finish_requested=True, session_ready=False)
        self.cfg.write_text(json.dumps({"agent_summaries": False}) + "\n")
        with mock.patch.object(distractions, "menu_select", return_value="On"):
            with mock.patch.object(distractions, "apply_notification_block", return_value=False):
                distractions.cmd_agent_summaries()
        self.assertFalse(distractions.read_summary_control()["session_ready"])
        self.ready_session()
        with mock.patch.object(distractions, "menu_select", return_value="Off"):
            with mock.patch.object(distractions, "update_focus_config", return_value=False):
                distractions.cmd_agent_summaries()
        self.assertTrue(distractions.read_summary_control()["session_ready"])
        self.assertFalse(distractions.read_summary_control()["finish_requested"])

    def test_stale_parser_start_does_not_clear_finish(self):
        self.ready_session(finish_requested=True, session_ready=False)
        with self.assertRaises(ValueError):
            distractions.mark_parser_active("sess-1")
        self.assertTrue(distractions.read_summary_control()["finish_requested"])
        self.assertFalse(distractions.read_summary_control()["parser_active"])

    def test_disable_flips_focus_before_finish(self):
        self.ready_session()
        order: list[str] = []
        real_set = distractions.set_focus
        real_finish = distractions.request_summary_finish

        def track_set(value):
            order.append("flag")
            return real_set(value)

        def track_finish():
            order.append("finish")
            self.assertFalse(distractions.is_focus())
            return real_finish()

        with mock.patch.object(distractions, "set_focus", track_set):
            with mock.patch.object(distractions, "request_summary_finish", track_finish):
                with mock.patch.object(distractions, "log_path", return_value=self.state / "log"):
                    with mock.patch.object(distractions, "on_distractions", return_value=False):
                        with mock.patch.object(distractions, "lift_network_block"):
                            with mock.patch.object(distractions, "lift_notification_block", return_value=True):
                                distractions.disable_focus("x" * 50)
        self.assertEqual(order, ["flag", "finish"])
        self.assertFalse(distractions.arm_summary_after_mute(resume=True)["session_ready"])

    def test_ready_requires_focus_and_capture_requires_session(self):
        self.ready_session(session_ready=False, finish_requested=True)
        distractions.set_focus(False)
        control = distractions.arm_summary_after_mute(resume=True)
        self.assertFalse(control["session_ready"])
        distractions.set_focus(True)
        control = distractions.arm_summary_after_mute(resume=True)
        self.assertTrue(control["session_ready"])
        with self.assertRaises(ValueError):
            distractions.capture_ping({**self.record(), "session": "other"})
        written = distractions.capture_ping({**self.record(), "session": "sess-1"})
        self.assertEqual(written["seq"], 1)

    def test_clear_parser_running_ignores_foreign_session(self):
        self.ready_session(parser_active=True)
        distractions.clear_parser_running("other")
        self.assertTrue(distractions.read_summary_control()["parser_active"])
        distractions.clear_parser_running("sess-1")
        self.assertFalse(distractions.read_summary_control()["parser_active"])

    def test_capture_stdin_is_bounded(self):
        self.ready_session()
        huge = json.dumps(self.record(body="x" * (distractions.CAPTURE_STDIN_MAX + 8)))
        with mock.patch.object(distractions.sys, "stdin", io.StringIO(huge)):
            with self.assertRaises(SystemExit):
                distractions.cmd_capture_ping()
        self.assertEqual(distractions.read_ping_records(), [])


class ServiceCompositionTests(unittest.TestCase):
    def test_manifest_keeps_one_notification_filter_service(self):
        data = json.loads(MANIFEST.read_text())
        self.assertEqual(data["entryPoints"]["service"], "NotificationFilter.qml")
        self.assertNotEqual(data["entryPoints"]["service"], "PingCapture.qml")
        self.assertIn("service", data["kinds"])

    def test_filter_instantiates_capture_child_before_dismiss(self):
        text = FILTER.read_text()
        self.assertIn("PingCapture", text)
        self.assertIn("enqueueMemberToast", text)
        observed = text[text.find("function onRowObserved") : text.find("function enqueueCount")]
        self.assertLess(observed.find("enqueueMemberToast"), observed.find("suppressLive"))
        self.assertLess(observed.find("enqueueMemberToast"), observed.find("restoredQueue"))

    def test_capture_qml_starts_parser_from_ready_timer_not_focus_flag(self):
        text = CAPTURE.read_text()
        self.assertIn("interval: 250", text)
        self.assertIn("summarize-session", text)
        self.assertIn("--session", text)
        self.assertIn("captureQueueLimit", text)
        self.assertIn("stopCaptureWork", text)
        self.assertIn("launchedSession", text)
        self.assertIn("session:", text)
        self.assertIn("sessionReady", text)
        self.assertNotIn("is_focus", text)
        self.assertNotIn("focus-status", text)
        self.assertIn("StdioCollector", text)
        self.assertNotIn("IpcHandler", text)
        self.assertNotIn("focus-summary.jsonl", text)


if __name__ == "__main__":
    unittest.main()
