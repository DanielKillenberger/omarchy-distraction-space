#!/usr/bin/env python3
"""Menus, prompts, notices, and the bar widget."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import catalog, config, state, ui

SELECT = r"""
import json, os, sys, time
from pathlib import Path

log = Path(os.environ["DS_UI_LOG"])
qpath = Path(os.environ["DS_SELECT_Q"])
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps(["select", *sys.argv[1:]]) + "\n")
items = json.loads(qpath.read_text(encoding="utf-8")) if qpath.exists() else []
if not items:
    sys.exit(1)
op = items[0]
qpath.write_text(json.dumps(items[1:]), encoding="utf-8")
kind = op[0] if isinstance(op, list) else op
if kind == "cancel":
    sys.exit(1)
if kind == "sleep":
    time.sleep(float(op[1]))
    sys.exit(1)
if kind == "fail":
    sys.exit(int(op[1]) if len(op) > 1 else 99)
if kind == "index":
    opts = sys.argv[2:]
    raw = opts[int(op[1])]
    parts = raw.split("\t")
    print("\t".join(parts[1:]) if len(parts) > 1 else raw)
    sys.exit(0)
sys.exit(1)
"""

INPUT = r"""
import json, os, sys, time
from pathlib import Path

log = Path(os.environ["DS_UI_LOG"])
qpath = Path(os.environ["DS_INPUT_Q"])
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps(["input", *sys.argv[1:]]) + "\n")
items = json.loads(qpath.read_text(encoding="utf-8")) if qpath.exists() else []
if not items:
    sys.exit(1)
op = items[0]
qpath.write_text(json.dumps(items[1:]), encoding="utf-8")
kind = op[0] if isinstance(op, list) else op
if kind == "cancel":
    sys.exit(1)
if kind == "sleep":
    time.sleep(float(op[1]))
    sys.exit(1)
if kind == "fail":
    sys.exit(int(op[1]) if len(op) > 1 else 99)
if kind == "text":
    print(op[1])
    sys.exit(0)
sys.exit(1)
"""

NOTIFY = r"""
import json, os, sys
from pathlib import Path

p = Path(os.environ["DS_NOTIFY_LOG"])
p.parent.mkdir(parents=True, exist_ok=True)
with p.open("a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
if os.environ.get("DS_NOTIFY_FAIL"):
    sys.exit(1)
"""

CFG = {
    "lock": {"default_minutes": 25, "ask_purpose": True, "reason_min_chars": 50},
}


class UiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.log = self.box.runtime / "ui.log"
        self.notify_log = self.box.runtime / "notify.log"
        self.select_q = self.box.runtime / "select.q"
        self.input_q = self.box.runtime / "input.q"
        os.environ["DS_UI_LOG"] = str(self.log)
        os.environ["DS_NOTIFY_LOG"] = str(self.notify_log)
        os.environ["DS_SELECT_Q"] = str(self.select_q)
        os.environ["DS_INPUT_Q"] = str(self.input_q)
        os.environ.pop("DS_NOTIFY_FAIL", None)
        self.box.fake_bin("omarchy-menu-select", SELECT)
        self.box.fake_bin("omarchy-menu-input", INPUT)
        self.box.fake_bin("omarchy-notification-send", NOTIFY)
        self.updates = []
        self.reloads = []
        real_update = config.update
        real_reload = state.request_reload

        def wrap_update(fn, timeout=None):
            self.updates.append(True)
            return real_update(fn, timeout=timeout)

        def wrap_reload(*a, **k):
            self.reloads.append(True)
            return real_reload(*a, **k)

        pu = patch("ds.config.update", wrap_update)
        pr = patch("ds.state.request_reload", wrap_reload)
        pu.start()
        pr.start()
        self.addCleanup(pu.stop)
        self.addCleanup(pr.stop)

    def _sq(self, *ops):
        self.select_q.write_text(json.dumps(list(ops)), encoding="utf-8")

    def _iq(self, *ops):
        self.input_q.write_text(json.dumps(list(ops)), encoding="utf-8")

    def _cfg(self):
        return json.loads(self.box.config_file.read_text(encoding="utf-8"))

    def _notices(self):
        if not self.notify_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.notify_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _calls(self, kind):
        if not self.log.exists():
            return []
        out = []
        for line in self.log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row and row[0] == kind:
                out.append(row)
        return out

    def test_select_choose_cancel_timeout_and_missing(self):
        rows = ["g\tAlpha\tone", "g\tBeta\ttwo"]
        self._sq(["index", 1])
        self.assertEqual(ui.select("Pick", rows), 1)
        self._sq(["cancel"])
        self.assertIsNone(ui.select("Pick", rows))
        self._sq(["sleep", 2])
        self.assertIsNone(ui.select("Pick", rows, timeout=0.2))
        self._sq(["fail", 99])
        with self.assertRaises(ui.Unavailable):
            ui.select("Pick", rows)
        box = Sandbox(isolate_path=True)
        self.addCleanup(box.cleanup)
        box.apply_env()
        with self.assertRaises(ui.Unavailable):
            ui.select("Pick", rows)

    def test_input_choose_cancel_timeout_and_missing(self):
        self._iq(["text", "hello"])
        self.assertEqual(ui.input("Name"), "hello")
        self._iq(["cancel"])
        self.assertIsNone(ui.input("Name"))
        self._iq(["sleep", 2])
        self.assertIsNone(ui.input("Name", timeout=0.2))
        box = Sandbox(isolate_path=True)
        self.addCleanup(box.cleanup)
        box.apply_env()
        with self.assertRaises(ui.Unavailable):
            ui.input("Name")

    def test_notify_never_raises(self):
        ui.notify("Title", "Body", glyph="x", action="distractions enter", urgent=True)
        self.assertTrue(self._notices())
        os.environ["DS_NOTIFY_FAIL"] = "1"
        ui.notify("Title", "Body")
        box = Sandbox(isolate_path=True)
        self.addCleanup(box.cleanup)
        box.apply_env()
        ui.notify("Title", "Body")

    def test_confirm_enter_choose_cancel_timeout_missing(self):
        self._sq(["index", 0])
        self.assertEqual(ui.confirm_enter(), "enter")
        self._sq(["index", 1])
        self.assertEqual(ui.confirm_enter(), "stay")
        self._sq(["cancel"])
        self.assertEqual(ui.confirm_enter(), "stay")
        self._sq(["sleep", 2])
        self.assertEqual(ui.confirm_enter(timeout=0.2), "stay")
        box = Sandbox(isolate_path=True)
        self.addCleanup(box.cleanup)
        box.apply_env()
        self.assertEqual(ui.confirm_enter(), "unavailable")

    def test_prompt_lock_choose_cancel_timeout_missing(self):
        self._sq(["index", 0])
        self._iq(["text", "deep work"])
        self.assertEqual(ui.prompt_lock(CFG), (25, "deep work"))
        self._sq(["index", 1])
        self._iq(["text", "p"])
        self.assertEqual(ui.prompt_lock(CFG), (50, "p"))
        self._sq(["index", 2])
        self._iq(["text", "p"])
        self.assertEqual(ui.prompt_lock(CFG), (90, "p"))
        self._sq(["index", 3])
        self._iq(["text", "until"])
        self.assertEqual(ui.prompt_lock(CFG), (None, "until"))
        self._sq(["index", 4])
        self._iq(["text", "12"], ["text", "other"])
        self.assertEqual(ui.prompt_lock(CFG), (12, "other"))
        self._sq(["cancel"])
        self.assertIsNone(ui.prompt_lock(CFG))
        cfg_off = {"lock": {"default_minutes": 25, "ask_purpose": False, "reason_min_chars": 50}}
        self._sq(["index", 0])
        self.assertEqual(ui.prompt_lock(cfg_off), (25, ""))
        self._sq(["index", 0])
        self._iq(["cancel"])
        self.assertEqual(ui.prompt_lock(CFG), (25, ""))
        with patch("ds.ui.select", return_value=None):
            self.assertIsNone(ui.prompt_lock(CFG))
        box = Sandbox(isolate_path=True)
        self.addCleanup(box.cleanup)
        box.apply_env()
        with self.assertRaises(ui.Unavailable):
            ui.prompt_lock(CFG)

    def test_prompt_reason_choose_cancel_timeout_missing(self):
        self._iq(["text", "because I need to"])
        self.assertEqual(ui.prompt_reason(5), "because I need to")
        self._iq(["cancel"])
        self.assertIsNone(ui.prompt_reason(5))
        with patch("ds.ui.input", return_value=None):
            self.assertIsNone(ui.prompt_reason(5))
        box = Sandbox(isolate_path=True)
        self.addCleanup(box.cleanup)
        box.apply_env()
        with self.assertRaises(ui.Unavailable):
            ui.prompt_reason(5)

    def test_menu_actions_write_through_update_and_reload(self):
        src = (ROOT / "ds" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("config.update", src)
        self.assertNotIn("config.save", src)
        self.assertNotIn("write_json", src)
        config.load()
        self.updates.clear()
        self.reloads.clear()
        ncat = len(catalog.names())
        self._sq(["index", 2], ["index", 0], ["index", ncat + 1], ["cancel"])
        self.assertEqual(ui.menu(), 0)
        self.assertTrue(self.updates)
        self.assertTrue(self.reloads)
        self.assertNotIn("Telegram", [config.display_name(e) for e in self._cfg()["list"]])

    def test_edit_list_toggle_catalog_and_add_custom(self):
        config.load()
        ncat = len(catalog.names())
        self._sq(
            ["index", 2],
            ["index", 0],
            ["index", ncat],
            ["index", ncat + 1],
            ["index", ncat + 3],
            ["cancel"],
        )
        self._iq(["text", "example.com"], ["text", "class=^Foo$"])
        self.assertEqual(ui.menu(), 0)
        names = [config.display_name(e) for e in self._cfg()["list"]]
        self.assertNotIn("Telegram", names)
        self.assertIn("example.com", names)
        self.assertIn("class=^Foo$", names)

    def test_settings_bools_enums_ints_list_and_readonly(self):
        config.load()
        ncat = len(catalog.names())
        # Settings is root index 3. Row order is documented in ds.ui SETTINGS.
        self._sq(
            ["index", 3],
            *[["index", i] for i in range(5)],
            ["index", 5],
            ["index", 6],
            ["index", 7],
            ["index", 8],
            ["index", 9],
            ["index", 10],
            ["index", ncat + 1],
            ["index", 11],
            ["index", 12],
            ["index", 13],
            ["index", 14],
            ["index", 15],
            ["index", 16],
            ["index", 17],
            ["cancel"],
        )
        self._iq(["text", "40"], ["text", "10"], ["text", "90"])
        self.assertEqual(ui.menu(), 0)
        cfg = self._cfg()
        self.assertFalse(cfg["nudges"]["app_banner"])
        self.assertFalse(cfg["nudges"]["block_page"])
        self.assertFalse(cfg["nudges"]["entry_confirm"])
        self.assertFalse(cfg["mute_sounds"])
        self.assertFalse(cfg["lock"]["ask_purpose"])
        self.assertEqual(cfg["hold_notifications"], "locked")
        self.assertEqual(cfg["summary"]["command"], "off")
        self.assertEqual(cfg["lock"]["default_minutes"], 40)
        self.assertEqual(cfg["lock"]["reason_min_chars"], 10)
        self.assertEqual(cfg["summary"]["timeout_seconds"], 90)
        prompts = [c[1] for c in self._calls("select")]
        self.assertIn("Edit list", prompts)
        self.assertIn("Settings", prompts)
        notices = self._notices()
        joined = " ".join(" ".join(map(str, n)) for n in notices)
        self.assertIn("config set", joined)
        for key in ("keep_reachable", "hooks.lock", "hooks.unlock", "hooks.enter", "hooks.leave", "log"):
            self.assertIn(key, joined, key)

    def test_settings_integer_refuses_invalid_and_command_custom_cycles(self):
        config.load()
        config.update(lambda c: config.set_value(c, "summary.command", ["agent", "--x"]))
        before = self._cfg()["lock"]["default_minutes"]
        self._sq(["index", 3], ["index", 7], ["index", 7], ["index", 6], ["index", 17], ["cancel"])
        self._iq(["text", "-3"], ["text", "nope"])
        self.assertEqual(ui.menu(), 0)
        cfg = self._cfg()
        self.assertEqual(cfg["lock"]["default_minutes"], before)
        self.assertEqual(cfg["summary"]["command"], "auto")
        self.assertTrue(self._notices())

    def test_bar_widget_state_fixture_and_idle_when_missing(self):
        qml = (ROOT / "BarWidget.qml").read_text(encoding="utf-8")
        self.assertIn("FileView", qml)
        self.assertIn("watchChanges", qml)
        self.assertIn("state.json", qml)
        self.assertNotIn("Timer", qml)
        self.assertIn("󰈈", qml)
        self.assertIn("Color.urgent", qml)
        self.assertIn("Qt.LeftButton", qml)
        self.assertIn("Qt.RightButton", qml)
        self.assertIn("Qt.MiddleButton", qml)
        self.assertRegex(qml, r'["\']lock["\']')
        self.assertRegex(qml, r'["\']unlock["\']')
        self.assertRegex(qml, r'["\']menu["\']')
        self.assertRegex(qml, r'["\']toggle["\']')
        self.assertIn("until", qml)
        self.assertIn("purpose", qml)
        fixture = {
            "locked": True,
            "until": "2026-09-01T12:00:00+00:00",
            "purpose": "deep work",
            "on_space": False,
            "site_block": "on",
            "listener_pid": 1,
            "updated": "2026-09-01T11:00:00+00:00",
        }
        path = self.box.state_dir / "state.json"
        path.write_text(json.dumps(fixture), encoding="utf-8")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(data["locked"])
        self.assertIn("until", qml)
        self.assertIn("purpose", qml)
        self.assertIn("property bool locked: false", qml)
        missing = self.box.state_dir / "no-such-state.json"
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
