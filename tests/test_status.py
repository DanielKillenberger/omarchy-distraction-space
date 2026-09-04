#!/usr/bin/env python3
"""status --json shape and stubbed command exit codes."""

from __future__ import annotations

import inspect
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import feedback, hypr, listener, lock, net, setup, state, ui

STUBS = ()
STATUS_KEYS = {
    "locked",
    "until",
    "purpose",
    "on_space",
    "site_block",
    "listener_pid",
    "hold",
    "held",
    "notification_hold",
    "pass_through",
    "updated",
}

HYPRCTL_ON = """
import json, sys
if sys.argv[1:3] == ["-j", "activeworkspace"]:
    print(json.dumps({"id": 5, "name": "distraction"}))
else:
    sys.exit(1)
"""
HYPRCTL_OFF = """
import json, sys
if sys.argv[1:3] == ["-j", "activeworkspace"]:
    print(json.dumps({"id": 1, "name": "1"}))
else:
    sys.exit(1)
"""


def _iso(delta_hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=delta_hours)).replace(
        microsecond=0
    ).isoformat()


class StatusTests(unittest.TestCase):
    def _box(self, isolate_path=False) -> Sandbox:
        box = Sandbox(isolate_path=isolate_path)
        self.addCleanup(box.cleanup)
        return box

    def test_status_json_on_space_without_listener(self):
        box = self._box()
        box.fake_bin("hyprctl", HYPRCTL_ON)
        r = box.run("status", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(set(data), STATUS_KEYS)
        self.assertTrue(data["on_space"])
        self.assertFalse(data["locked"])
        self.assertIsNone(data["until"])
        self.assertEqual(data["purpose"], "")
        self.assertEqual(data["site_block"], "off")
        self.assertIsNone(data["listener_pid"])
        self.assertFalse(data["hold"])
        self.assertEqual(data["held"], {})
        self.assertEqual(data["notification_hold"], "off")
        self.assertEqual(data["pass_through"], "off")

    def test_status_json_off_space(self):
        box = self._box()
        box.fake_bin("hyprctl", HYPRCTL_OFF)
        data = json.loads(box.run("status", "--json").stdout)
        self.assertFalse(data["on_space"])

    def test_status_json_hyprctl_absent(self):
        box = self._box(isolate_path=True)
        r = box.run("status", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertIsNone(data["on_space"])

    def test_status_json_ignores_missing_and_malformed_config(self):
        box = self._box()
        self.assertFalse(box.config_file.exists())
        r = box.run("status", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(set(data), STATUS_KEYS)
        self.assertFalse(box.config_file.exists())
        box.config_file.write_text("{not json", encoding="utf-8")
        r = box.run("status", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(set(data), STATUS_KEYS)
        self.assertEqual(box.config_file.read_text(encoding="utf-8"), "{not json")
        box.config_file.write_text(json.dumps({"list": 1}) + "\n", encoding="utf-8")
        before = box.config_file.read_bytes()
        r = box.run("status", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(set(data), STATUS_KEYS)
        self.assertEqual(box.config_file.read_bytes(), before)

    def test_expired_lock_reads_unlocked(self):
        box = self._box()
        box.fake_bin("hyprctl", HYPRCTL_OFF)
        (box.state_dir / "lock.json").write_text(
            json.dumps(
                {
                    "locked": True,
                    "since": _iso(-2),
                    "until": _iso(-1),
                    "purpose": "old",
                }
            ),
            encoding="utf-8",
        )
        data = json.loads(box.run("status", "--json").stdout)
        self.assertFalse(data["locked"])

    def test_future_lock_is_locked_with_purpose(self):
        box = self._box()
        box.fake_bin("hyprctl", HYPRCTL_OFF)
        until = _iso(2)
        (box.state_dir / "lock.json").write_text(
            json.dumps(
                {
                    "locked": True,
                    "since": _iso(0),
                    "until": until,
                    "purpose": "deep work",
                }
            ),
            encoding="utf-8",
        )
        data = json.loads(box.run("status", "--json").stdout)
        self.assertTrue(data["locked"])
        self.assertEqual(data["purpose"], "deep work")
        self.assertEqual(data["until"], until)

    def test_stale_state_site_block_dead_listener(self):
        box = self._box()
        box.fake_bin("hyprctl", HYPRCTL_OFF)
        (box.state_dir / "state.json").write_text(
            json.dumps(
                {
                    "locked": False,
                    "until": None,
                    "purpose": "",
                    "on_space": False,
                    "site_block": "on",
                    "listener_pid": 2147483647,
                    "hold": True,
                    "held": {"Telegram": 3, "Discord": "many", "X": True},
                    "notification_hold": "unavailable",
                    "pass_through": "on",
                    "updated": _iso(-1),
                }
            ),
            encoding="utf-8",
        )
        r = box.run("status", "--json")
        data = json.loads(r.stdout)
        self.assertEqual(set(data), STATUS_KEYS)
        self.assertEqual(data["site_block"], "on")
        self.assertIsNone(data["listener_pid"])
        self.assertTrue(data["hold"])
        self.assertEqual(data["held"], {"Telegram": 3})
        self.assertEqual(data["notification_hold"], "unavailable")
        self.assertEqual(data["pass_through"], "on")
        r = box.run("status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("hold=on held=3 notification_hold=unavailable", r.stdout)
        self.assertIn("pass_through=on", r.stdout)

    def test_stubbed_commands_exit_2_not_yet(self):
        box = self._box()
        for cmd in STUBS:
            with self.subTest(cmd=cmd):
                r = box.run(cmd)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("not yet", r.stderr)

    def test_no_command_exits_2(self):
        box = self._box()
        r = box.run()
        self.assertEqual(r.returncode, 2)


class BoundedReadTests(unittest.TestCase):
    """What a reader materializes from a state path someone else can replace."""

    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.path = Path(self.box.state) / "probe.json"

    def test_reads_a_normal_state_file_whole(self):
        self.path.write_text(json.dumps({"locked": True}), encoding="utf-8")
        self.assertEqual(state.read_json(self.path), {"locked": True})

    def test_reads_exactly_the_cap_and_refuses_one_byte_more(self):
        self.path.write_bytes(b"x" * state.READ_CAP)
        self.assertEqual(len(state.read_bounded(self.path)), state.READ_CAP)
        self.path.write_bytes(b"x" * (state.READ_CAP + 1))
        self.assertIsNone(state.read_bounded(self.path))

    def test_refuses_oversized_json_instead_of_truncating_it(self):
        # Valid JSON followed by padding: truncation at the cap would leave bytes
        # that still parse, so the caller would believe a file it never read whole.
        body = json.dumps({"locked": True}).encode("utf-8")
        self.path.write_bytes(body + b" " * (state.READ_CAP + 1 - len(body)))
        self.assertIsNone(state.read_bounded(self.path))
        self.assertEqual(state.read_json(self.path, {}), {})

    def test_refuses_a_path_that_is_not_a_regular_file(self):
        fifo = Path(self.box.state) / "fifo.json"
        os.mkfifo(fifo)
        self.assertIsNone(state.read_bounded(fifo))
        self.assertEqual(state.read_json(fifo, {}), {})
        self.assertIsNone(state.read_bounded(Path(self.box.state)))
        self.assertIsNone(state.read_bounded(Path(self.box.state) / "gone.json"))

    def test_refuses_a_symlink_even_to_a_readable_file(self):
        target = Path(self.box.state) / "target.json"
        target.write_text(json.dumps({"locked": True}), encoding="utf-8")
        link = Path(self.box.state) / "link.json"
        link.symlink_to(target)
        self.assertIsNone(state.read_bounded(link))
        self.assertEqual(state.read_json(link, {}), {})

    def test_state_reads_come_through_the_bound(self):
        os.mkfifo(state.state_path("state.json"))
        os.mkfifo(state.state_path("lock.json"))
        # Neither call blocks on the fifo; both fall back to their empty answer.
        self.assertIsNone(state.read_state())
        self.assertFalse(state.read_lock()["locked"])


def _params(fn):
    return list(inspect.signature(fn).parameters)


class StubContractTests(unittest.TestCase):
    def test_ui_contract(self):
        self.assertTrue(issubclass(ui.Unavailable, Exception))
        self.assertEqual(_params(ui.select), ["prompt", "rows", "timeout"])
        self.assertIsNone(inspect.signature(ui.select).parameters["timeout"].default)
        self.assertEqual(_params(ui.input), ["prompt", "timeout"])
        self.assertIsNone(inspect.signature(ui.input).parameters["timeout"].default)
        notify = inspect.signature(ui.notify)
        self.assertEqual(list(notify.parameters), ["title", "body", "glyph", "action", "urgent"])
        self.assertEqual(notify.parameters["glyph"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(notify.parameters["action"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(notify.parameters["urgent"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(notify.parameters["glyph"].default)
        self.assertIsNone(notify.parameters["action"].default)
        self.assertIs(notify.parameters["urgent"].default, False)
        self.assertFalse(hasattr(ui, "confirm_enter"))
        self.assertEqual(_params(ui.prompt_lock), ["cfg"])
        self.assertEqual(_params(ui.prompt_reason), ["min_chars"])
        self.assertEqual(_params(ui.menu), [])
        self.assertEqual(_params(ui.cmd_menu), ["args"])

    def test_lock_contract(self):
        self.assertEqual(_params(lock.is_locked), [])
        self.assertEqual(_params(lock.lock), ["minutes", "purpose"])
        self.assertEqual(_params(lock.unlock), ["reason"])
        self.assertEqual(_params(lock.expire_if_due), [])
        self.assertEqual(_params(lock.run_hook), ["name", "env"])
        self.assertEqual(_params(lock.enter), [])
        self.assertEqual(_params(lock.leave), [])
        self.assertEqual(_params(lock.toggle), [])
        for fn in (lock.cmd_lock, lock.cmd_unlock, lock.cmd_enter, lock.cmd_leave, lock.cmd_toggle):
            self.assertEqual(_params(fn), ["args"])

    def test_hypr_contract(self):
        self.assertEqual(_params(hypr.hyprctl_json), ["args"])
        self.assertEqual(_params(hypr.active_workspace), [])
        self.assertEqual(_params(hypr.on_space), [])
        self.assertEqual(_params(hypr.apply_rules), ["expanded"])
        self.assertEqual(_params(hypr.handle_event), ["line"])
        self.assertEqual(_params(hypr.move_to_space), ["address"])
        self.assertEqual(_params(hypr.cycle), ["direction"])
        self.assertEqual(_params(hypr.cmd_next), ["args"])
        self.assertEqual(_params(hypr.cmd_prev), ["args"])

    def test_net_feedback_listener_setup_contract(self):
        self.assertEqual(_params(net.resolve_batch), ["hosts", "generation", "reason"])
        self.assertEqual(_params(net.shutdown), [])
        self.assertEqual(_params(net.apply), ["addresses"])
        self.assertEqual(_params(feedback.start), ["config", "is_locked"])
        self.assertEqual(_params(feedback.stop), [])
        self.assertEqual(_params(listener.run), [])
        self.assertEqual(_params(listener.cmd_listen), ["args"])
        self.assertEqual(_params(listener.cmd_reload), ["args"])
        self.assertEqual(_params(setup.cmd_setup), ["args"])


if __name__ == "__main__":
    unittest.main()
