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
            mock.patch.object(distractions, "FOCUS_TRANSITION_LOCK", self.runtime / "focus-transition.lock"),
            mock.patch.object(distractions, "PARSE_DEBOUNCE_S", 0.0),
            mock.patch.object(distractions, "PARSER_POLL_S", 0.02),
            mock.patch.object(distractions, "FINISH_WAIT_S", 0.4),
            mock.patch.object(
                distractions,
                "prompt_focus_close",
                return_value={"action": "dismiss", "eval": "", "note": ""},
            ),
            mock.patch.object(distractions, "collect_summary_feedback"),
            mock.patch.object(distractions, "menu_select", return_value=""),
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
        with mock.patch.object(distractions, "invoke_summary_agent", return_value="ok"):
            for seq in range(1, 4):
                rows = [
                    {
                        "seq": seq,
                        "app": "Telegram",
                        "title": f"n{seq}",
                        "body": "b",
                        "at": "2026-09-01T00:00:00Z",
                    }
                ]
                self.assertTrue(distractions.run_one_parse(rows, "sess-1"))
            self.assertEqual(
                distractions.run_one_parse(
                    [
                        {
                            "seq": 4,
                            "app": "Telegram",
                            "title": "n4",
                            "body": "b",
                            "at": "2026-09-01T00:00:00Z",
                        }
                    ],
                    "sess-1",
                ),
                "",
            )
        self.assertEqual(distractions.read_summary_control()["invocations"], 3)

    def test_grok_proof_and_parse_each_consume_durable_budget(self):
        self.ready_session()
        first = self.write_records("one")
        second = [
            {
                "seq": 2,
                "app": "Telegram",
                "title": "two",
                "body": "body-two",
                "at": "2026-09-01T00:00:00Z",
            }
        ]
        with mock.patch.object(distractions, "resolve_summary_agent", return_value="grok"):
            with mock.patch.object(distractions, "prove_grok", return_value="UNAVAILABLE") as proof:
                with mock.patch.object(
                    distractions,
                    "invoke_summary_agent",
                    return_value="summary",
                ) as invoke:
                    self.assertEqual(distractions.run_one_parse(first, "sess-1"), "summary")
                    after_first = distractions.read_summary_control()
                    self.assertEqual(after_first["invocations"], 2)
                    self.assertTrue(after_first["grok_proven"])

                    with mock.patch.object(distractions.time, "sleep"):
                        restarted = distractions.apply_parser_restart("sess-1")
                    self.assertTrue(restarted["grok_proven"])

                    self.assertEqual(distractions.run_one_parse(second, "sess-1"), "summary")

        self.assertEqual(distractions.read_summary_control()["invocations"], 3)
        proof.assert_called_once_with()
        self.assertEqual(invoke.call_count, 2)
        self.assertTrue(all(call.kwargs == {"grok_proven": True} for call in invoke.call_args_list))

    def test_grok_spawns_neither_proof_nor_parse_without_two_free_slots(self):
        self.ready_session(invocations=2, grok_proven=False)
        rows = self.write_records("one")
        with mock.patch.object(distractions, "resolve_summary_agent", return_value="grok"):
            with mock.patch.object(distractions, "prove_grok") as proof:
                with mock.patch.object(distractions, "invoke_summary_agent") as invoke:
                    self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "")
        proof.assert_not_called()
        invoke.assert_not_called()
        control = distractions.read_summary_control()
        self.assertEqual(control["invocations"], 2)
        self.assertEqual(control["last_consumed_seq"], 0)

    def test_reserve_rejects_already_consumed_records(self):
        self.ready_session(last_consumed_seq=2, invocations=1)
        rows = self.write_records("one", "two")
        with mock.patch.object(distractions, "invoke_summary_agent") as invoke:
            self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "")
            invoke.assert_not_called()
        self.assertEqual(distractions.read_summary_control()["invocations"], 1)

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

    def test_agent_spawn_fails_closed_when_pid_cannot_be_published(self):
        self.ready_session()
        proc = mock.Mock()
        proc.pid = 99
        proc.wait.return_value = 0
        distractions._agent_invocation.session_id = "sess-1"
        try:
            with mock.patch.object(subprocess, "Popen", return_value=proc):
                with mock.patch.object(distractions, "_record_agent_pid", return_value=False):
                    with mock.patch.object(distractions, "_kill_process_group") as kill:
                        with self.assertRaises(distractions.SummaryAgentError):
                            distractions._run_agent(["true"], cwd=Path(self.tmp.name), env={})
            kill.assert_called_with(proc)
        finally:
            delattr(distractions._agent_invocation, "session_id")

    def test_pid_publication_and_clear_are_session_and_pid_bound(self):
        self.ready_session(session_id="new", mute_applied_session="new")
        with mock.patch.object(distractions, "_pid_starttime", return_value="10"):
            self.assertFalse(distractions._record_agent_pid(99, "old"))
            self.assertTrue(distractions._record_agent_pid(99, "new"))
        self.assertEqual(distractions.read_summary_control()["agent_pid"], 99)

        control = distractions.read_summary_control()
        control["agent_pid"] = 100
        control["agent_starttime"] = "11"
        distractions.write_summary_control(control)
        self.assertFalse(
            distractions._record_agent_pid(None, "new", expected_pid=99)
        )
        self.assertEqual(distractions.read_summary_control()["agent_pid"], 100)

    def test_grok_config_cap_rejection_is_parse_failure(self):
        self.ready_session()
        rows = self.write_records("cap")
        with mock.patch.object(distractions, "resolve_summary_agent", return_value="grok"):
            with mock.patch.object(distractions, "grok_bounds_honored", return_value=False):
                self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "")
        self.assertFalse(distractions.summary_result_path().exists())
        self.assertEqual(distractions.read_summary_control()["invocations"], 2)

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

    def test_stdout_over_limit_is_rejected(self):
        huge = "x" * (distractions.PARSE_STDOUT_MAX + 50)

        def fake_popen(*args, **kwargs):
            proc = mock.Mock()
            proc.pid = 7
            proc.returncode = 0
            proc.communicate.return_value = (huge, "")
            return proc

        with mock.patch.object(subprocess, "Popen", fake_popen):
            with self.assertRaises(distractions.SummaryAgentError):
                distractions._run_agent(["true"], cwd=Path(self.tmp.name), env={})


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

    def test_finish_signals_without_immediate_reap(self):
        self.ready_session()
        reaps: list[str] = []

        def track_reap(control=None):
            reaps.append("reap")

        with mock.patch.object(distractions, "reap_summary_children", track_reap):
            with mock.patch.object(distractions, "invoke_summary_agent") as invoke:
                distractions.summarize_finish("sess-1")
                invoke.assert_not_called()
        self.assertEqual(reaps, ["reap"])
        first = distractions.request_summary_finish("sess-1", reap=False)
        self.assertTrue(first["finish_requested"])

    def test_stale_finish_does_not_stop_current_session(self):
        self.ready_session(session_id="live")
        control = distractions.summarize_finish("old")
        self.assertEqual(control["session_id"], "live")
        self.assertFalse(control["finish_requested"])
        self.assertTrue(control["session_ready"])

    def test_parse_failure_notifies_before_grouped(self):
        self.ready_session(parse_failed=True)
        self.seed_counts({"Telegram": 1})
        notices: list[str] = []

        def fake_notify(title, body="", timeout_ms=4000):
            notices.append(title)
            return True

        with mock.patch.object(distractions, "notify", fake_notify):
            self.assertEqual(distractions.apply_summary_xor(), "grouped")
        self.assertEqual(notices[0], "Focus mode")
        self.assertIn("While you were focused", notices)

    def test_parse_failed_stale_text_does_not_publish_summary(self):
        self.ready_session(parse_failed=True)
        self.seed_result("stale from an earlier parse")
        self.seed_counts({"Telegram": 1})
        notices: list[tuple[str, str]] = []

        def fake_notify(title, body="", timeout_ms=4000):
            notices.append((title, body))
            return True

        with mock.patch.object(distractions, "notify", fake_notify):
            self.assertEqual(distractions.apply_summary_xor(), "grouped")
        self.assertTrue(any("Could not summarize" in body for _, body in notices))
        self.assertFalse(any(title == "Focus summary" for title, _ in notices))
        self.assertIn("While you were focused", [title for title, _ in notices])

    def test_summaries_off_after_lift_fail_uses_xor_cleanup(self):
        self.cfg.write_text(json.dumps({"agent_summaries": False}) + "\n")
        self.ready_session(lift_fail_pending=True, session_ready=False)
        self.seed_result("obsolete")
        order: list[str] = []

        def track_lift(*, catchup=True):
            order.append(f"lift:{catchup}")
            return True

        def track_xor():
            order.append("xor")
            return "grouped"

        with mock.patch.object(distractions, "log_path", return_value=self.state / "log"):
            with mock.patch.object(distractions, "lift_network_block"):
                with mock.patch.object(distractions, "lift_notification_block", track_lift):
                    with mock.patch.object(distractions, "apply_summary_xor", track_xor):
                        with mock.patch.object(distractions, "notify", return_value=True):
                            distractions.disable_focus("x" * 50)
        self.assertEqual(order, ["lift:False", "xor"])

    def test_rlimit_failure_fails_closed(self):
        with mock.patch.object(resource, "setrlimit", side_effect=OSError("denied")):
            with self.assertRaises(OSError):
                distractions._apply_parse_rlimits()

    def test_oversized_record_is_skipped_not_prompted(self):
        self.ready_session()
        huge = "h" * (distractions.PARSE_MAX_PROMPT_BYTES + 8)
        rows = [
            {
                "seq": 1,
                "app": "Telegram",
                "title": huge,
                "body": "x",
                "at": "2026-09-01T00:00:00Z",
            },
            {
                "seq": 2,
                "app": "Telegram",
                "title": "ok",
                "body": "small",
                "at": "2026-09-01T00:00:01Z",
            },
        ]
        prompts: list[str] = []

        def fake_invoke(agent, prompt):
            prompts.append(prompt)
            return "ok"

        with mock.patch.object(distractions, "invoke_summary_agent", fake_invoke):
            self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "ok")
        self.assertTrue(prompts)
        self.assertNotIn(huge, prompts[0])
        self.assertIn("ok", prompts[0])
        self.assertEqual(distractions.read_summary_control()["last_consumed_seq"], 2)

    def test_no_agent_does_not_reserve_or_mark_failure(self):
        self.ready_session()
        rows = self.write_records("later")
        with mock.patch.object(distractions, "resolve_summary_agent", return_value=""):
            self.assertEqual(distractions.run_one_parse(rows, "sess-1"), "")
        control = distractions.read_summary_control()
        self.assertEqual(control["invocations"], 0)
        self.assertEqual(control["last_consumed_seq"], 0)
        self.assertFalse(control.get("parse_failed"))

    def test_finish_without_lock_skips_final_parse(self):
        self.ready_session()
        self.write_records("left")
        with mock.patch.object(distractions, "try_summarize_session_lock", return_value=None):
            with mock.patch.object(distractions, "invoke_summary_agent") as invoke:
                distractions.summarize_finish("sess-1")
                invoke.assert_not_called()

    def test_restart_reaps_orphan_agent(self):
        self.ready_session(agent_pid=4242, agent_starttime="99")
        reaped: list[tuple] = []

        def track_kill(pid, starttime=None):
            reaped.append((pid, starttime))

        with mock.patch.object(distractions, "_kill_pid", track_kill):
            with mock.patch.object(distractions.time, "sleep"):
                distractions.apply_parser_restart("sess-1")
        self.assertEqual(reaped, [(4242, "99")])

    def test_notify_timeout_tries_fallback(self):
        calls: list[str] = []

        def fake_check_call(cmd, **kwargs):
            calls.append(cmd[0])
            raise subprocess.TimeoutExpired(cmd, 1)

        def fake_call(cmd, **kwargs):
            calls.append(cmd[0])
            return 0

        with mock.patch.object(subprocess, "check_call", fake_check_call):
            with mock.patch.object(subprocess, "call", fake_call):
                self.assertTrue(distractions.notify("Focus summary", "body"))
        self.assertEqual(calls, ["omarchy-notification-send", "notify-send"])

    def test_kill_requires_matching_starttime_then_escalates(self):
        import signal

        signals: list[tuple[int, int]] = []
        alive = {"ok": True}
        clock = [0.0]

        def fake_starttime(pid):
            return "77" if alive["ok"] else ""

        def fake_kill(pid, sig):
            signals.append((pid, sig))
            if sig == signal.SIGKILL:
                alive["ok"] = False

        def fake_mono():
            return clock[0]

        def fake_sleep(seconds):
            clock[0] += seconds

        with mock.patch.object(distractions, "_pid_starttime", fake_starttime):
            with mock.patch.object(distractions.time, "monotonic", fake_mono):
                with mock.patch.object(distractions.time, "sleep", fake_sleep):
                    with mock.patch.object(os, "kill", fake_kill):
                        with mock.patch.object(os, "killpg", fake_kill):
                            distractions._kill_pid(4242, "")
                            self.assertEqual(signals, [])
                            distractions._kill_pid(4242, "77")
        self.assertIn((4242, signal.SIGTERM), signals)
        self.assertIn((4242, signal.SIGKILL), signals)

    def test_stale_parse_failure_does_not_mark_new_session(self):
        self.ready_session(session_id="new")
        control = distractions._mark_parse_failed("old")
        self.assertFalse(control.get("parse_failed"))
        self.assertFalse(distractions.read_summary_control().get("parse_failed"))

    def test_enable_waits_for_disable_transition_lock(self):
        self.ready_session()
        order: list[str] = []
        release = threading.Event()

        def slow_finish(session=None):
            order.append("finish")
            release.wait(2)
            return {}

        def track_enable_prepare():
            order.append("enable")
            return distractions.read_summary_control()

        with mock.patch.object(distractions, "log_path", return_value=self.state / "log"):
            with mock.patch.object(distractions, "summarize_finish", slow_finish):
                with mock.patch.object(distractions, "lift_notification_block", return_value=True):
                    with mock.patch.object(distractions, "apply_summary_xor", return_value="grouped"):
                        with mock.patch.object(distractions, "lift_network_block"):
                            with mock.patch.object(distractions, "notify", return_value=True):
                                worker = threading.Thread(
                                    target=distractions.disable_focus,
                                    args=("x" * 50,),
                                )
                                worker.start()
                                deadline = time.monotonic() + 2
                                while time.monotonic() < deadline and "finish" not in order:
                                    time.sleep(0.01)
                                with mock.patch.object(
                                    distractions, "prepare_summary_session", track_enable_prepare
                                ):
                                    with mock.patch.object(distractions, "apply_network_block"):
                                        with mock.patch.object(distractions, "on_distractions", return_value=False):
                                            with mock.patch.object(
                                                distractions, "apply_notification_block", return_value=True
                                            ):
                                                starter = threading.Thread(target=distractions.enable_focus)
                                                starter.start()
                                                time.sleep(0.1)
                                                self.assertEqual(order, ["finish"])
                                                release.set()
                                                worker.join(timeout=2)
                                                starter.join(timeout=2)
        self.assertEqual(order, ["finish", "enable"])

    def test_disable_aborts_when_session_rotates(self):
        self.ready_session(session_id="leave-me")
        xor_calls: list[str] = []

        def rotate(_session=None):
            control = distractions.read_summary_control()
            control["session_id"] = "newer"
            distractions.write_summary_control(control)
            distractions.set_focus(True)
            return control

        with mock.patch.object(distractions, "log_path", return_value=self.state / "log"):
            with mock.patch.object(distractions, "summarize_finish", rotate):
                with mock.patch.object(distractions, "apply_summary_xor", lambda: xor_calls.append("xor")):
                    with mock.patch.object(distractions, "lift_notification_block") as lift:
                        with mock.patch.object(distractions, "lift_network_block"):
                            distractions.disable_focus("x" * 50)
                    lift.assert_not_called()
        self.assertEqual(xor_calls, [])
        self.assertTrue(distractions.is_focus())


class CloseWindowHarness(ParseHarness):
    def setUp(self):
        super().setUp()
        self.log = self.state / "disable.log"
        self.dialog_calls: list[dict] = []
        extra = [
            mock.patch.object(distractions, "log_path", lambda: self.log),
            mock.patch.object(distractions, "lift_network_block"),
            mock.patch.object(distractions, "on_distractions", return_value=False),
            mock.patch.object(distractions, "summarize_finish", return_value={}),
            mock.patch.object(distractions, "lift_notification_block", return_value=True),
        ]
        for patch in extra:
            patch.start()
            self.addCleanup(patch.stop)

    def seed_recap(self, purpose: str = "write docs", session_id: str = "sess-1") -> None:
        distractions.write_private_atomic(
            distractions.session_recap_path(),
            json.dumps({"purpose": purpose, "session_id": session_id}) + "\n",
        )

    def inject_close(self, result):
        def fake(*, purpose="", summary="", ask_eval=True, ask_feedback=True):
            self.dialog_calls.append(
                {
                    "purpose": purpose,
                    "summary": summary,
                    "ask_eval": ask_eval,
                    "ask_feedback": ask_feedback,
                }
            )
            return result

        return mock.patch.object(distractions, "prompt_focus_close", fake)

    def disable(self) -> None:
        distractions.disable_focus("x" * 50)


class HostedXorTests(CloseWindowHarness):
    def test_hosted_nonempty_skips_notify_feedback_and_grouped(self):
        self.ready_session()
        self.seed_recap()
        self.seed_result("important ping")
        self.seed_counts({"Telegram": 1})
        notices: list[str] = []
        grouped: list[str] = []
        feedback: list[str] = []

        def fake_notify(title, body="", timeout_ms=4000):
            notices.append(title)
            return True

        with self.inject_close({"action": "helpful", "eval": "", "note": "ok"}):
            with mock.patch.object(distractions, "notify", fake_notify):
                with mock.patch.object(
                    distractions, "show_grouped_notice", lambda: grouped.append("g") or True
                ):
                    with mock.patch.object(
                        distractions, "collect_summary_feedback", lambda: feedback.append("f")
                    ):
                        self.disable()
        self.assertEqual(self.dialog_calls[0]["summary"], "Here's what you missed\nimportant ping")
        self.assertEqual(self.dialog_calls[0]["purpose"], "write docs")
        self.assertTrue(self.dialog_calls[0]["ask_eval"])
        self.assertTrue(self.dialog_calls[0]["ask_feedback"])
        self.assertNotIn("Focus summary", notices)
        self.assertEqual(grouped, [])
        self.assertEqual(feedback, [])
        self.assertFalse(distractions.is_focus())
        row = json.loads(distractions.summary_ledger_path().read_text().splitlines()[-1])
        self.assertEqual(row["helpful"], True)
        self.assertEqual(row["note"], "ok")

    def test_hosted_copy_survives_post_xor_state_change(self):
        self.ready_session()
        self.seed_recap()
        self.seed_result("stable")
        original = distractions.apply_summary_xor

        def xor_then_corrupt():
            arm = original()
            control = distractions.read_summary_control()
            control["parse_failed"] = True
            distractions.write_summary_control(control)
            self.cfg.write_text(
                json.dumps(
                    {
                        "agent_summaries": True,
                        "summary_agent": "claude",
                        "session_close_ui": False,
                    }
                )
                + "\n"
            )
            return arm

        with self.inject_close({"action": "dismiss", "eval": "", "note": ""}):
            with mock.patch.object(distractions, "apply_summary_xor", xor_then_corrupt):
                self.disable()
        self.assertEqual(self.dialog_calls[0]["summary"], "Here's what you missed\nstable")

    def test_close_dialog_scrolls_long_summary(self):
        source = Path(ROOT / "distractions").read_text()
        close = source[source.find("def prompt_focus_close") : source.find("def run_session_close_window")]
        self.assertIn("Gtk.ScrolledWindow", close)
        self.assertIn("set_max_content_height", close)
        self.assertIn("_scroll_text(purpose_value", close)
        self.assertIn("_scroll_text(summary_value", close)

    def test_hosted_copy_empty_vs_parse_failed(self):
        cases = (
            ("note", False, "Here's what you missed\nnote"),
            ("", False, "You didn't miss anything"),
            ("", True, None),
        )
        for text, parse_failed, expected in cases:
            with self.subTest(text=text, parse_failed=parse_failed):
                self.dialog_calls.clear()
                self.ready_session(parse_failed=parse_failed)
                self.seed_recap()
                self.seed_result(text)
                notices: list[tuple[str, str]] = []

                def fake_notify(title, body="", timeout_ms=4000):
                    notices.append((title, body))
                    return True

                with self.inject_close({"action": "dismiss", "eval": "", "note": ""}):
                    with mock.patch.object(distractions, "notify", fake_notify):
                        self.assertEqual(
                            distractions.apply_summary_xor(),
                            "hosted" if expected else "grouped",
                        )
                        if expected:
                            distractions.run_session_close_window(
                                hosted_copy=expected, xor_skipped=False
                            )
                if expected:
                    self.assertEqual(self.dialog_calls[0]["summary"], expected)
                    self.assertFalse(any(title == "Focus summary" for title, _ in notices))
                    self.assertFalse(
                        any("Could not summarize" in body for _, body in notices)
                    )
                else:
                    self.assertEqual(self.dialog_calls, [])
                    self.assertTrue(
                        any("Could not summarize" in body for _, body in notices)
                    )
                    self.assertNotEqual(
                        distractions.hosted_summary_copy(
                            distractions.read_summary_control(),
                            distractions.read_summary_result(),
                            distractions.read_session_recap(),
                        ),
                        "You didn't miss anything",
                    )

    def test_hosted_dismiss_clears_counts_and_result_once(self):
        self.ready_session()
        self.seed_recap()
        self.seed_result("shown")
        self.seed_counts({"Telegram": 2})
        with self.inject_close({"action": "dismiss", "eval": "", "note": ""}):
            self.disable()
        self.assertEqual(distractions.read_counts(), {})
        self.assertFalse(distractions.summary_result_path().exists())
        self.assertIsNone(distractions.read_session_recap())
        self.dialog_calls.clear()
        with self.inject_close({"action": "dismiss", "eval": "", "note": ""}):
            distractions.run_session_close_window(
                hosted_copy="Here's what you missed\nshown", xor_skipped=False
            )
        self.assertEqual(self.dialog_calls, [])
        self.assertEqual(distractions.read_counts(), {})

    def test_close_ui_off_uses_today_notify_and_feedback(self):
        self.cfg.write_text(
            json.dumps(
                {
                    "agent_summaries": True,
                    "summary_agent": "claude",
                    "session_close_ui": False,
                }
            )
            + "\n"
        )
        self.ready_session()
        self.seed_recap()
        self.seed_result("shown")
        asked: list[str] = []
        notices: list[str] = []
        with self.inject_close({"action": "helpful", "eval": "", "note": ""}):
            with mock.patch.object(
                distractions, "notify", lambda title, body="", **k: notices.append(title) or True
            ):
                with mock.patch.object(
                    distractions, "collect_summary_feedback", lambda: asked.append("ask")
                ):
                    self.assertEqual(distractions.apply_summary_xor(), "summary")
        self.assertEqual(notices, ["Focus summary"])
        self.assertEqual(asked, ["ask"])
        self.assertEqual(self.dialog_calls, [])

    def test_purpose_eval_off_still_hosts_summary(self):
        self.cfg.write_text(
            json.dumps(
                {
                    "agent_summaries": True,
                    "summary_agent": "claude",
                    "session_close_purpose": False,
                    "session_close_eval": False,
                }
            )
            + "\n"
        )
        self.ready_session()
        self.seed_recap()
        self.seed_result("kept")
        with self.inject_close({"action": "dismiss", "eval": "", "note": ""}):
            self.disable()
        self.assertEqual(self.dialog_calls[0]["purpose"], "")
        self.assertFalse(self.dialog_calls[0]["ask_eval"])
        self.assertEqual(self.dialog_calls[0]["summary"], "Here's what you missed\nkept")

    def test_result_and_ledger_schema_have_no_importance_field(self):
        payload = distractions.publish_summary_result("x", "sess-1")
        self.assertEqual(set(payload), {"session_id", "text"})
        self.assertTrue(distractions.append_ledger_entry(True, "n"))
        row = json.loads(distractions.summary_ledger_path().read_text().splitlines()[-1])
        self.assertEqual(set(row), {"at", "helpful", "note"})

    def test_summaries_off_still_grouped(self):
        self.cfg.write_text("{}\n")
        self.seed_recap()
        lifts: list[bool] = []

        def track_lift(*, catchup=True):
            lifts.append(catchup)
            return True

        with self.inject_close({"action": "dismiss", "eval": "", "note": ""}):
            with mock.patch.object(distractions, "lift_notification_block", track_lift):
                self.disable()
        self.assertEqual(lifts, [True])
        self.assertEqual(self.dialog_calls[0]["purpose"], "write docs")
        self.assertEqual(self.dialog_calls[0]["summary"], "")


class LiftFailCloseTests(CloseWindowHarness):
    def test_lift_fail_purpose_eval_keeps_counts_and_result(self):
        self.ready_session()
        self.seed_recap("deep work")
        self.seed_result("keep-me")
        self.seed_counts({"Telegram": 3})
        with self.inject_close({"action": "dismiss", "eval": "ok-ish", "note": ""}):
            with mock.patch.object(distractions, "lift_notification_block", return_value=False):
                self.disable()
        self.assertEqual(self.dialog_calls[0]["summary"], "")
        self.assertEqual(self.dialog_calls[0]["purpose"], "deep work")
        self.assertTrue(self.dialog_calls[0]["ask_eval"])
        self.assertFalse(self.dialog_calls[0]["ask_feedback"])
        self.assertEqual(distractions.read_counts(), {"Telegram": 3})
        self.assertEqual(distractions.read_summary_result()["text"], "keep-me")
        self.assertIsNone(distractions.read_session_recap())
        self.assertFalse(distractions.is_focus())
        self.assertNotIn("ok-ish", self.log.read_text())

    def test_consumed_recap_blocks_second_window_retry_uses_notify(self):
        self.ready_session()
        self.seed_recap()
        self.seed_result("later")
        self.seed_counts({"X": 1})
        with self.inject_close({"action": "dismiss", "eval": "", "note": ""}):
            with mock.patch.object(distractions, "lift_notification_block", return_value=False):
                self.disable()
        self.assertIsNone(distractions.read_session_recap())
        self.dialog_calls.clear()
        notices: list[str] = []
        with mock.patch.object(
            distractions, "notify", lambda title, body="", **k: notices.append(title) or True
        ):
            with mock.patch.object(distractions, "collect_summary_feedback", return_value=None):
                self.assertEqual(distractions.apply_summary_xor(), "summary")
        self.assertEqual(notices, ["Focus summary"])
        self.assertEqual(self.dialog_calls, [])

    def test_self_eval_skip_and_dismiss_leave_focus_off(self):
        self.ready_session()
        self.seed_recap()
        self.seed_result("shown")
        with self.inject_close({"action": "dismiss", "eval": "   ", "note": "ignored"}):
            self.disable()
        self.assertFalse(distractions.is_focus())
        self.assertNotIn("ignored", self.log.read_text())
        self.assertIsNone(distractions.read_session_recap())

    def test_dismiss_skips_nonempty_eval_and_helpful(self):
        self.ready_session()
        self.seed_recap()
        self.seed_result("shown")
        with self.inject_close({"action": "dismiss", "eval": "typed eval", "note": "typed note"}):
            self.disable()
        self.assertFalse(distractions.is_focus())
        self.assertNotIn("typed eval", self.log.read_text())
        self.assertNotIn("typed note", self.log.read_text())
        self.assertFalse(distractions.summary_ledger_path().exists())

    def test_helpful_persists_self_eval(self):
        self.ready_session()
        self.seed_recap()
        self.seed_result("shown")
        with self.inject_close({"action": "helpful", "eval": "hit the purpose", "note": "good"}):
            self.disable()
        self.assertIn("hit the purpose", self.log.read_text())
        row = json.loads(distractions.summary_ledger_path().read_text().splitlines()[-1])
        self.assertEqual(row["helpful"], True)
        self.assertEqual(row["note"], "good")


if __name__ == "__main__":
    unittest.main()
