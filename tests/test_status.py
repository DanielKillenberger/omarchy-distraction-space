#!/usr/bin/env python3
"""status --json shape and stubbed command exit codes."""

from __future__ import annotations

import inspect
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import feedback, hypr, listener, lock, net, setup, ui

STUBS = (
    "enter",
    "leave",
    "toggle",
    "next",
    "prev",
    "lock",
    "unlock",
    "menu",
    "listen",
    "reload",
    "setup",
)
STATUS_KEYS = {
    "locked",
    "until",
    "purpose",
    "on_space",
    "site_block",
    "listener_pid",
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
                    "updated": _iso(-1),
                }
            ),
            encoding="utf-8",
        )
        data = json.loads(box.run("status", "--json").stdout)
        self.assertEqual(data["site_block"], "on")
        self.assertIsNone(data["listener_pid"])

    def test_stubbed_commands_exit_2_not_yet(self):
        box = self._box()
        for cmd in STUBS:
            with self.subTest(cmd=cmd):
                r = box.run(cmd)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("not yet", r.stderr)
        r = box.run("setup", "--remove")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("not yet", r.stderr)
        r = box.run("lock", "25", "deep", "work")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("not yet", r.stderr)
        r = box.run("unlock", "x" * 50)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("not yet", r.stderr)

    def test_no_command_exits_2(self):
        box = self._box()
        r = box.run()
        self.assertEqual(r.returncode, 2)


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
        self.assertEqual(inspect.signature(ui.confirm_enter).parameters["timeout"].default, 30)
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
