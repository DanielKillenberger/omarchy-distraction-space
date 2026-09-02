#!/usr/bin/env python3
"""Enter without a prompt, leave, toggle, and lock-notice paths."""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import config, hypr, lock, state, ui
from ds.config import DEFAULTS


HYPRCTL = r"""
import json, os, sys
from pathlib import Path

log = Path(os.environ["DS_HYPR_LOG"])
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")

state_path = Path(os.environ.get("DS_HYPR_STATE", ""))
data = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
args = sys.argv[1:]
if args[:1] == ["-j"] and len(args) >= 2:
    key = args[1]
    if key == "activeworkspace":
        print(json.dumps(data.get("activeworkspace") or {"id": 1, "name": "1"}))
        sys.exit(0)
    if key == "workspaces":
        print(json.dumps(data.get("workspaces") or [
            {"id": 1, "name": "1", "windows": 1},
            {"id": 2, "name": "2", "windows": 1},
            {"id": 99, "name": "distraction", "windows": 1},
        ]))
        sys.exit(0)
    sys.exit(1)
if args[:1] in (["keyword"], ["dispatch"]):
    sys.exit(0)
sys.exit(1)
"""

HOOK_SCRIPT = r"""
import json, os
from pathlib import Path
Path(os.environ["DS_HOOK_OUT"]).write_text(
    json.dumps({"event": os.environ.get("DS_EVENT", "")}),
    encoding="utf-8",
)
"""


class EnterTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.notices: list[tuple[str, str]] = []
        self.hypr_log = self.box.runtime / "hypr.log"
        self.hypr_state = self.box.runtime / "hypr-state.json"
        os.environ["DS_HYPR_LOG"] = str(self.hypr_log)
        os.environ["DS_HYPR_STATE"] = str(self.hypr_state)
        self.box.fake_bin("hyprctl", HYPRCTL)
        self.hook_out = self.box.runtime / "hook-out.json"
        os.environ["DS_HOOK_OUT"] = str(self.hook_out)
        self.hook_py = self.box.bin / "ds-enter-hook.py"
        self.hook_py.write_text(HOOK_SCRIPT, encoding="utf-8")
        self.notify_patch = patch("ds.ui.notify", self._notify)
        self.notify_patch.start()
        self.addCleanup(self.notify_patch.stop)
        self.menu_patch = patch("ds.ui.select", side_effect=AssertionError("enter never opens a menu"))
        self.menu_patch.start()
        self.addCleanup(self.menu_patch.stop)
        self._state(name="1")
        self._cfg()

    def _notify(self, title, body, *, glyph=None, action=None, urgent=False):
        self.notices.append((title, body))

    def _cfg(self, **over):
        cfg = json.loads(json.dumps(DEFAULTS))
        for key, value in over.items():
            if key == "nudges" and isinstance(value, dict):
                cfg["nudges"] = {**cfg["nudges"], **value}
            elif key == "hooks" and isinstance(value, dict):
                cfg["hooks"] = {**cfg["hooks"], **value}
            elif key == "lock" and isinstance(value, dict):
                cfg["lock"] = {**cfg["lock"], **value}
            else:
                cfg[key] = value
        config.save(cfg)
        return cfg

    def _state(self, name="1", **kwargs):
        payload = {
            "activeworkspace": {"id": 1 if name != "distraction" else 99, "name": name},
            "workspaces": [
                {"id": 1, "name": "1", "windows": 1},
                {"id": 2, "name": "2", "windows": 1},
                {"id": 99, "name": "distraction", "windows": 1},
            ],
        }
        payload.update(kwargs)
        self.hypr_state.write_text(json.dumps(payload), encoding="utf-8")

    def _hypr_joined(self):
        if not self.hypr_log.exists():
            return []
        return [
            " ".join(json.loads(line))
            for line in self.hypr_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _switched(self):
        return any(
            "hl.dsp.focus" in j and "name:distraction" in j
            for j in self._hypr_joined()
        )

    def _clear_hypr(self):
        self.hypr_log.write_text("", encoding="utf-8")

    def test_enter_switches_without_prompt(self):
        self.assertFalse(hasattr(ui, "confirm_enter"))
        rc = lock.enter()
        self.assertEqual(rc, 0)
        self.assertTrue(self._switched())
        self.assertEqual(self.notices, [])

    def test_expired_lock_does_not_block_enter(self):
        from datetime import datetime, timedelta, timezone

        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0).isoformat()
        state.write_json(
            state.state_path("lock.json"),
            {"locked": True, "since": past, "until": past, "purpose": "old"},
        )
        self.assertFalse(lock.is_locked())
        rc = lock.enter()
        self.assertEqual(rc, 0)
        self.assertTrue(self._switched())
        self.assertFalse(any("locked" in (t + b).lower() for t, b in self.notices))

    def test_locked_enter_shows_notice_and_does_not_switch(self):
        lock.lock(25, "nope")
        self._clear_hypr()
        self.notices.clear()
        rc = lock.enter()
        self.assertEqual(rc, 1)
        self.assertFalse(self._switched())
        self.assertTrue(self.notices)
        blob = " ".join(t + " " + b for t, b in self.notices).lower()
        self.assertIn("lock", blob)

    def test_leave_cycles_off_space(self):
        self._state(name="distraction")
        rc = lock.leave()
        self.assertEqual(rc, 0)
        joined = "\n".join(self._hypr_joined())
        self.assertIn("hl.dsp.focus", joined)
        self.assertNotIn("name:distraction", joined.split("hl.dsp.focus", 1)[-1])

    def test_toggle_on_space_leaves(self):
        self._state(name="distraction")
        rc = lock.toggle()
        self.assertEqual(rc, 0)
        joined = "\n".join(self._hypr_joined())
        self.assertIn("hl.dsp.focus", joined)
        self.assertNotIn("name:distraction", joined.split("hl.dsp.focus", 1)[-1])

    def test_toggle_off_space_enters(self):
        self._state(name="1")
        rc = lock.toggle()
        self.assertEqual(rc, 0)
        self.assertTrue(self._switched())

    def test_toggle_off_space_locked_refuses(self):
        self._state(name="1")
        lock.lock(25, "nope")
        self._clear_hypr()
        self.notices.clear()
        rc = lock.toggle()
        self.assertEqual(rc, 1)
        self.assertFalse(self._switched())
        self.assertTrue(self.notices)

    def test_saved_entry_confirm_key_is_inert(self):
        for value in (True, False):
            with self.subTest(entry_confirm=value):
                self._clear_hypr()
                self._cfg(nudges={"entry_confirm": value})
                rc = lock.enter()
                self.assertEqual(rc, 0)
                self.assertTrue(self._switched())
                self.assertEqual(self.notices, [])

    def test_enter_leave_toggle_run_no_hook(self):
        argv = [sys.executable, str(self.hook_py)]
        self._cfg(hooks={"enter": [argv], "leave": [argv], "lock": [argv], "unlock": [argv]})
        self.assertEqual(lock.enter(), 0)
        time.sleep(0.2)
        self.assertFalse(self.hook_out.exists())
        self._state(name="distraction")
        self._clear_hypr()
        self.assertEqual(lock.leave(), 0)
        time.sleep(0.2)
        self.assertFalse(self.hook_out.exists())
        self._state(name="1")
        self.assertEqual(lock.toggle(), 0)
        time.sleep(0.2)
        self.assertFalse(self.hook_out.exists())

if __name__ == "__main__":
    unittest.main()
