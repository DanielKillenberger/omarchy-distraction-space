#!/usr/bin/env python3
"""Bounded parse, XOR, and lift-fail retain (fn-3.3)."""

from __future__ import annotations

import json
import os
import resource
import subprocess
import tempfile
import threading
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
distractions = SourceFileLoader("distractions_parse", str(ROOT / "distractions")).load_module()


class ParseHarness(unittest.TestCase):
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
            mock.patch.object(distractions, "SUMMARY_RESULT_LOCK", self.runtime / "summary-result.lock"),
            mock.patch.object(distractions, "SUMMARY_LEDGER_LOCK", self.runtime / "summary-ledger.lock"),
            mock.patch.object(distractions, "FOCUS_CONFIG_LOCK", self.runtime / "focus.json.lock"),
            mock.patch.object(distractions, "PARSE_DEBOUNCE_S", 0.0),
            mock.patch.object(distractions, "PARSER_POLL_S", 0.02),
            mock.patch.object(distractions, "FINISH_WAIT_S", 0.4),
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
        control["mute_applied_session"] = "sess-1"
        control.update(overrides)
        distractions.write_summary_control(control)
        return control

    def write_records(self, *titles: str) -> list[dict]:
        rows = []
        for index, title in enumerate(titles, start=1):
            rows.append(
                {
                    "seq": index,
                    "app": "Telegram",
                    "title": title,
                    "body": f"body-{title}",
                    "at": "2026-09-01T00:00:00Z",
                }
            )
        lines = [json.dumps(row, separators=(",", ":")) + "\n" for row in rows]
        distractions.write_ping_jsonl(lines)
        control = distractions.read_summary_control()
        control["next_seq"] = len(rows) + 1
        distractions.write_summary_control(control)
        return rows

    def seed_counts(self, payload: dict[str, int]) -> None:
        distractions.write_counts_atomic(payload)

    def seed_result(self, text: str, session_id: str = "sess-1") -> None:
        distractions.publish_summary_result(text, session_id)


class ReservationAndBoundsTests(ParseHarness):
    def test_reserve_is_atomic_and_crash_does_not_replay(self):
        self.ready_session()
        rows = self.write_records("one", "two")
        with mock.patch.object(
            distractions, "invoke_summary_agent", side_effect=OSError("crashed")
        ) as invoke:
            self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "")
            invoke.assert_called_once()
        control = distractions.read_summary_control()
        self.assertEqual(control["invocations"], 1)
        self.assertEqual(control["last_consumed_seq"], 2)
        self.assertEqual(distractions.observe_ping_records(control["last_consumed_seq"]), [])
        with mock.patch.object(distractions.time, "sleep"):
            restarted = distractions.apply_parser_restart("sess-1")
        self.assertIsNotNone(restarted)
        self.assertEqual(restarted["invocations"], 1)
        self.assertEqual(restarted["last_consumed_seq"], 2)
        self.assertEqual(distractions.observe_ping_records(restarted["last_consumed_seq"]), [])

    def test_invocation_budget_is_three(self):
        self.ready_session()
        rows = self.write_records("a")
        with mock.patch.object(distractions, "invoke_summary_agent", return_value="ok"):
            for _ in range(3):
                self.assertTrue(distractions.run_one_parse(rows, "sess-1"))
            self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "")
        self.assertEqual(distractions.read_summary_control()["invocations"], 3)

    def test_stale_session_does_not_reserve_or_publish(self):
        self.ready_session()
        rows = self.write_records("stale")
        with mock.patch.object(distractions, "invoke_summary_agent") as invoke:
            self.assertEqual(distractions.run_one_parse(rows, "other"), "")
            invoke.assert_not_called()
        self.assertEqual(distractions.read_summary_control()["invocations"], 0)
        self.assertFalse(distractions.summary_result_path().exists())

    def test_stale_session_after_invoke_drops_result(self):
        self.ready_session()
        rows = self.write_records("late")

        def rotate(_agent, _prompt):
            control = distractions.read_summary_control()
            control["session_id"] = "sess-2"
            distractions.write_summary_control(control)
            return "should-not-publish"

        with mock.patch.object(distractions, "invoke_summary_agent", side_effect=rotate):
            self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "")
        self.assertFalse(distractions.summary_result_path().exists())

    def test_claude_and_grok_closed_bounds_and_rlimits(self):
        claude = distractions.claude_argv()
        self.assertIn("--max-turns", claude)
        self.assertEqual(claude[claude.index("--max-turns") + 1], "1")
        self.assertIn("--max-budget-usd", claude)
        self.assertEqual(claude[claude.index("--max-budget-usd") + 1], "0.25")
        grok = distractions.grok_argv("PROMPT", "/empty")
        self.assertEqual(grok[-2:], ["-p", "PROMPT"])
        self.assertIn("--max-turns", grok)
        self.assertEqual(grok[grok.index("--max-turns") + 1], "1")
        captured = {}

        def fake_popen(*args, **kwargs):
            captured["preexec"] = kwargs.get("preexec_fn")
            proc = mock.Mock()
            proc.pid = 99
            proc.returncode = 0
            proc.communicate.return_value = ("ok\n", "")
            return proc

        with mock.patch.object(subprocess, "Popen", fake_popen):
            distractions._run_agent(["true"], cwd=Path(self.tmp.name), env={})
        self.assertTrue(callable(captured.get("preexec")))
        self.assertEqual(distractions.PARSE_RLIMIT_AS, 512 * 1024 * 1024)
        self.assertEqual(distractions.PARSE_RLIMIT_FSIZE, 1024 * 1024)
        self.assertEqual(distractions.PARSE_RLIMIT_NPROC, 16)
        self.assertEqual(resource.RLIMIT_AS, resource.RLIMIT_AS)

    def test_grok_config_cap_rejection_is_parse_failure(self):
        self.ready_session()
        rows = self.write_records("cap")
        with mock.patch.object(distractions, "resolve_summary_agent", return_value="grok"):
            with mock.patch.object(distractions, "grok_bounds_honored", return_value=False):
                with mock.patch.object(distractions, "ensure_grok_proven"):
                    self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "")
        self.assertFalse(distractions.summary_result_path().exists())
        self.assertEqual(distractions.read_summary_control()["invocations"], 1)

    def test_timeout_empty_and_overlimit_do_not_publish(self):
        self.ready_session()
        rows = self.write_records("t")
        with mock.patch.object(
            distractions,
            "invoke_summary_agent",
            side_effect=subprocess.TimeoutExpired(["claude"], 1),
        ):
            self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "")
        with mock.patch.object(distractions, "invoke_summary_agent", return_value=""):
            self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "")
        self.assertFalse(distractions.summary_result_path().exists())

    def test_stdout_is_capped_at_8kib(self):
        huge = "x" * (distractions.PARSE_STDOUT_MAX + 50)

        def fake_popen(*args, **kwargs):
            proc = mock.Mock()
            proc.pid = 7
            proc.returncode = 0
            proc.communicate.return_value = (huge, "")
            return proc

        with mock.patch.object(subprocess, "Popen", fake_popen):
            result = distractions._run_agent(["true"], cwd=Path(self.tmp.name), env={})
        self.assertEqual(len(result.stdout), distractions.PARSE_STDOUT_MAX)


class SessionSpawnTests(ParseHarness):
    def test_first_unseen_starts_one_shot_once_does_not(self):
        self.ready_session()
        self.write_records("first")
        calls: list[str] = []

        def fake_invoke(agent, prompt):
            calls.append(agent)
            return "summary-one"

        with mock.patch.object(distractions, "invoke_summary_agent", fake_invoke):
            self.assertEqual(distractions.run_summarize_session(once=True), 0)
            self.assertEqual(calls, [])
            thread = threading.Thread(
                target=distractions.run_summarize_session,
                kwargs={"expected_session": "sess-1"},
            )
            thread.start()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not distractions.summary_result_path().exists():
                time.sleep(0.02)
            distractions.request_summary_finish()
            thread.join(timeout=2)
        self.assertTrue(thread.is_alive() is False)
        self.assertEqual(calls, ["claude"])
        self.assertEqual(distractions.read_summary_result()["text"], "summary-one")
        self.assertEqual(oct(distractions.summary_result_path().stat().st_mode & 0o777), "0o600")

    def test_replacement_waits_for_child_and_debounce(self):
        self.ready_session()
        self.write_records("one")
        release = threading.Event()
        calls: list[str] = []

        def fake_invoke(agent, prompt):
            calls.append(prompt)
            if len(calls) == 1:
                release.wait(2)
            return f"pass-{len(calls)}"

        with mock.patch.object(distractions, "PARSE_DEBOUNCE_S", 0.25):
            with mock.patch.object(distractions, "invoke_summary_agent", fake_invoke):
                thread = threading.Thread(
                    target=distractions.run_summarize_session,
                    kwargs={"expected_session": "sess-1"},
                )
                thread.start()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and len(calls) < 1:
                    time.sleep(0.02)
                extra = {
                    "seq": 2,
                    "app": "Telegram",
                    "title": "two",
                    "body": "body-two",
                    "at": "2026-09-01T00:00:01Z",
                }
                lines = [
                    json.dumps(row, separators=(",", ":")) + "\n"
                    for row in distractions.read_ping_records() + [extra]
                ]
                distractions.write_ping_jsonl(lines)
                time.sleep(0.08)
                self.assertEqual(len(calls), 1)
                release.set()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and len(calls) < 2:
                    time.sleep(0.02)
                distractions.request_summary_finish()
                thread.join(timeout=2)
        self.assertEqual(len(calls), 2)

    def test_finish_skips_final_parse_after_restart_budget(self):
        self.ready_session(invocations=1, parser_restarts=2, last_consumed_seq=0)
        self.write_records("left")
        with mock.patch.object(distractions, "invoke_summary_agent") as invoke:
            distractions.summarize_finish("sess-1")
            invoke.assert_not_called()
        self.ready_session(invocations=1, parser_restarts=0, last_consumed_seq=0, session_ready=True)
        self.write_records("left")
        with mock.patch.object(distractions, "invoke_summary_agent", return_value="final"):
            distractions.summarize_finish("sess-1")
        self.assertEqual(distractions.read_summary_result()["text"], "final")


class XorAndLiftTests(ParseHarness):
    def test_successful_summary_clears_counts_once(self):
        self.ready_session()
        self.seed_counts({"Telegram": 2})
        self.seed_result("important ping")
        notices: list[tuple] = []

        def fake_notify(title, body="", timeout_ms=4000):
            notices.append((title, body, timeout_ms))
            return True

        with mock.patch.object(distractions, "notify", fake_notify):
            self.assertEqual(distractions.apply_summary_xor(), "summary")
        self.assertEqual(notices, [("Focus summary", "important ping", 12000)])
        self.assertEqual(distractions.read_counts(), {})
        self.assertFalse(distractions.summary_result_path().exists())

    def test_empty_or_off_or_no_agent_uses_grouped_notice(self):
        self.ready_session()
        self.seed_counts({"Telegram": 1})
        grouped: list[str] = []

        def fake_grouped():
            grouped.append("grouped")
            return True

        with mock.patch.object(distractions, "show_grouped_notice", fake_grouped):
            self.assertEqual(distractions.apply_summary_xor(), "grouped")
            self.cfg.write_text(json.dumps({"agent_summaries": False, "summary_agent": "claude"}) + "\n")
            self.seed_result("text")
            self.assertEqual(distractions.apply_summary_xor(), "grouped")
            self.cfg.write_text(json.dumps({"agent_summaries": True, "summary_agent": "claude"}) + "\n")
            with mock.patch.object(distractions, "resolve_summary_agent", return_value=""):
                self.assertEqual(distractions.apply_summary_xor(), "grouped")
        self.assertEqual(grouped, ["grouped", "grouped", "grouped"])
        self.assertEqual(distractions.read_counts(), {"Telegram": 1})

    def test_display_failure_falls_back_to_grouped(self):
        self.ready_session()
        self.seed_counts({"X": 1})
        self.seed_result("shown?")
        with mock.patch.object(distractions, "notify", return_value=False):
            with mock.patch.object(distractions, "show_grouped_notice", return_value=True) as grouped:
                self.assertEqual(distractions.apply_summary_xor(), "grouped")
                grouped.assert_called_once()
        self.assertEqual(distractions.read_counts(), {"X": 1})

    def test_notify_primary_fail_fallback_ok_is_success(self):
        calls: list[list[str]] = []

        def fake_check_call(cmd, **kwargs):
            calls.append(list(cmd))
            raise FileNotFoundError("no omarchy-notification-send")

        def fake_call(cmd, **kwargs):
            calls.append(list(cmd))
            return 0

        with mock.patch.object(subprocess, "check_call", fake_check_call):
            with mock.patch.object(subprocess, "call", fake_call):
                self.assertTrue(distractions.notify("Focus summary", "body", timeout_ms=12000))
        self.assertEqual(calls[0][0], "omarchy-notification-send")
        self.assertEqual(calls[1][0], "notify-send")

    def test_lift_fail_retains_and_next_success_retries_xor(self):
        self.ready_session()
        self.seed_counts({"Telegram": 3})
        self.seed_result("keep-me")
        self.write_records("kept")
        xor_calls: list[str] = []

        def track_xor():
            xor_calls.append("xor")
            return "summary"

        with mock.patch.object(distractions, "log_path", return_value=self.state / "log"):
            with mock.patch.object(distractions, "lift_network_block"):
                with mock.patch.object(distractions, "lift_notification_block", return_value=False) as lift:
                    with mock.patch.object(distractions, "apply_summary_xor", track_xor):
                        with mock.patch.object(distractions, "summarize_finish", return_value={}):
                            distractions.disable_focus("x" * 50)
                    lift.assert_called_once_with(catchup=False)
        self.assertEqual(xor_calls, [])
        self.assertEqual(distractions.read_counts(), {"Telegram": 3})
        self.assertEqual(distractions.read_summary_result()["text"], "keep-me")
        self.assertTrue(distractions.read_summary_control()["lift_fail_pending"])
        self.assertEqual(distractions.read_ping_records()[0]["title"], "kept")
        kept = distractions.prepare_summary_session()
        self.assertEqual(kept["session_id"], "sess-1")
        self.assertEqual(distractions.read_summary_result()["text"], "keep-me")
        with mock.patch.object(distractions, "notify", return_value=True):
            self.assertEqual(distractions.apply_summary_xor(), "summary")
        self.assertEqual(distractions.read_counts(), {})

    def test_summaries_off_keeps_lift_then_notice(self):
        self.cfg.write_text(json.dumps({"agent_summaries": False}) + "\n")
        order: list[str] = []

        def track_lift(*, catchup=True):
            order.append(f"lift:{catchup}")
            return True

        def track_xor():
            order.append("xor")
            return "grouped"

        def track_network():
            order.append("network")

        with mock.patch.object(distractions, "log_path", return_value=self.state / "log"):
            with mock.patch.object(distractions, "lift_network_block", track_network):
                with mock.patch.object(distractions, "lift_notification_block", track_lift):
                    with mock.patch.object(distractions, "apply_summary_xor", track_xor):
                        with mock.patch.object(distractions, "notify", return_value=True):
                            distractions.disable_focus("x" * 50)
        self.assertEqual(order, ["network", "lift:True"])

    def test_summaries_on_finish_then_lift_xor_then_network(self):
        self.ready_session()
        order: list[str] = []

        def track_finish(expected_session=None):
            order.append("finish")
            return {}

        def track_lift(*, catchup=True):
            order.append(f"lift:{catchup}")
            return True

        def track_xor():
            order.append("xor")
            return "summary"

        def track_network():
            order.append("network")

        with mock.patch.object(distractions, "log_path", return_value=self.state / "log"):
            with mock.patch.object(distractions, "summarize_finish", track_finish):
                with mock.patch.object(distractions, "lift_notification_block", track_lift):
                    with mock.patch.object(distractions, "apply_summary_xor", track_xor):
                        with mock.patch.object(distractions, "lift_network_block", track_network):
                            with mock.patch.object(distractions, "notify", return_value=True):
                                distractions.disable_focus("x" * 50)
        self.assertEqual(order, ["finish", "lift:False", "xor", "network"])

    def test_summarize_finish_is_a_main_command(self):
        source = Path(ROOT / "distractions").read_text()
        main = source[source.find("def main()") :]
        self.assertIn('"summarize-finish"', main)


if __name__ == "__main__":
    unittest.main()
