#!/usr/bin/env python3
"""Lock state, lazy expiry, reason log, hooks, and lock/unlock CLI prompts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import config, lock, state
from ds.config import DEFAULTS
from ds.ui import Unavailable

HYPRCTL_ON = """
import json, sys
if sys.argv[1:3] == ["-j", "activeworkspace"]:
    print(json.dumps({"id": 5, "name": "distraction"}))
else:
    sys.exit(1)
"""


def _iso(delta_minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_minutes)).replace(
        microsecond=0
    ).isoformat()


HOOK_SCRIPT = r"""
import json, os, sys, time
from pathlib import Path
out = Path(os.environ["DS_HOOK_OUT"])
delay = float(os.environ.get("DS_HOOK_SLEEP", "0"))
if delay:
    time.sleep(delay)
payload = {k: os.environ.get(k, "") for k in (
    "DS_EVENT", "DS_PURPOSE", "DS_MINUTES", "DS_REASON", "DS_HELD",
)}
payload["pgrp"] = os.getpgrp()
payload["pid"] = os.getpid()
if os.environ.get("DS_HOOK_FAIL"):
    out.write_text(json.dumps(payload), encoding="utf-8")
    sys.exit(1)
out.write_text(json.dumps(payload), encoding="utf-8")
"""


class LockTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.notices: list[tuple[str, str]] = []
        self.hook_out = self.box.runtime / "hook-out.json"
        os.environ["DS_HOOK_OUT"] = str(self.hook_out)
        os.environ.pop("DS_HOOK_SLEEP", None)
        os.environ.pop("DS_HOOK_FAIL", None)
        self.hook_py = self.box.bin / "ds-hook.py"
        self.hook_py.write_text(HOOK_SCRIPT, encoding="utf-8")
        self.notify_patch = patch("ds.ui.notify", self._notify)
        self.notify_patch.start()
        self.addCleanup(self.notify_patch.stop)
        lock._cfg_warned = False

    def _notify(self, title, body, *, glyph=None, action=None, urgent=False):
        self.notices.append((title, body))

    def _cfg(self, **over):
        cfg = json.loads(json.dumps(DEFAULTS))
        for key, value in over.items():
            if key == "lock" and isinstance(value, dict):
                cfg["lock"] = {**cfg["lock"], **value}
            elif key == "hooks" and isinstance(value, dict):
                cfg["hooks"] = {**cfg["hooks"], **value}
            else:
                cfg[key] = value
        config.save(cfg)
        return cfg

    def _hook_argv(self):
        return [sys.executable, str(self.hook_py)]

    def _wait_hook(self, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.hook_out.exists() and self.hook_out.stat().st_size:
                return json.loads(self.hook_out.read_text(encoding="utf-8"))
            time.sleep(0.02)
        self.fail("hook did not write output")

    def _raw_lock(self):
        return json.loads((self.box.state_dir / "lock.json").read_text(encoding="utf-8"))

    def test_past_until_reads_unlocked_everywhere(self):
        state.write_json(
            state.state_path("lock.json"),
            {
                "locked": True,
                "since": _iso(-30),
                "until": _iso(-1),
                "purpose": "old",
            },
        )
        self.assertFalse(lock.is_locked())
        self.assertFalse(state.read_lock()["locked"])
        self.assertEqual(lock.unlock("x" * 50), 0)
        raw = json.loads((self.box.state_dir / "lock.json").read_text(encoding="utf-8"))
        self.assertTrue(raw["locked"])
        self.assertFalse(lock.is_locked())

    def test_expire_if_due_true_once_per_transition(self):
        state.write_json(
            state.state_path("lock.json"),
            {
                "locked": True,
                "since": _iso(-30),
                "until": _iso(-1),
                "purpose": "old",
            },
        )
        self._cfg(hooks={"unlock": [self._hook_argv()]})
        self.assertFalse(lock.is_locked())
        self.assertTrue(lock.expire_if_due())
        self.assertFalse(lock.expire_if_due())
        self.assertFalse(lock.expire_if_due())
        raw = self._raw_lock()
        self.assertFalse(raw["locked"])
        time.sleep(0.15)
        self.assertFalse(self.hook_out.exists())

    def test_future_lock_does_not_expire(self):
        self.assertEqual(lock.lock(40, "deep work"), 0)
        self.assertTrue(lock.is_locked())
        self.assertFalse(lock.expire_if_due())
        raw = self._raw_lock()
        self.assertTrue(raw["locked"])
        self.assertEqual(raw["purpose"], "deep work")
        self.assertIsNotNone(raw["until"])

    def test_lock_runs_lock_hook_once_unlock_runs_unlock_hook_once(self):
        self._cfg(hooks={"lock": [self._hook_argv()], "unlock": [self._hook_argv()]})
        self.assertEqual(lock.lock(25, "write"), 0)
        payload = self._wait_hook()
        self.assertEqual(payload["DS_EVENT"], "lock")
        self.assertEqual(payload["DS_PURPOSE"], "write")
        self.assertEqual(payload["DS_MINUTES"], "25")
        self.assertEqual(payload["DS_REASON"], "")
        self.assertEqual(json.loads(payload["DS_HELD"]), {})
        self.hook_out.unlink()
        self.assertEqual(lock.unlock("x" * 50), 0)
        payload = self._wait_hook()
        self.assertEqual(payload["DS_EVENT"], "unlock")
        self.assertEqual(payload["DS_PURPOSE"], "write")
        self.assertEqual(payload["DS_REASON"], "x" * 50)
        self.assertEqual(json.loads(payload["DS_HELD"]), {})

    def test_already_locked_is_noop_without_second_hook(self):
        self._cfg(hooks={"lock": [self._hook_argv()]})
        self.assertEqual(lock.lock(10, "one"), 0)
        self._wait_hook()
        self.hook_out.unlink()
        self.assertEqual(lock.lock(90, "two"), 0)
        time.sleep(0.2)
        self.assertFalse(self.hook_out.exists())
        self.assertEqual(self._raw_lock()["purpose"], "one")

    def test_short_reason_refuses_and_keeps_the_lock(self):
        self._cfg(lock={"reason_min_chars": 50}, hooks={"unlock": [self._hook_argv()]})
        self.assertEqual(lock.lock(25, "stay locked"), 0)
        rc = lock.unlock("too short")
        self.assertEqual(rc, 1)
        self.assertTrue(lock.is_locked())
        self.assertEqual(self._raw_lock()["purpose"], "stay locked")
        self.assertTrue(self.notices)
        self.assertTrue(any("50" in (t + b) for t, b in self.notices))
        time.sleep(0.15)
        self.assertFalse(self.hook_out.exists())
        log = state.state_path("log")
        if log.exists():
            self.assertNotIn("too short", log.read_text(encoding="utf-8"))

    def test_reason_min_chars_zero_unlocks_without_prompt(self):
        self._cfg(lock={"reason_min_chars": 0})
        self.assertEqual(lock.lock(25, "any"), 0)
        with patch("ds.ui.prompt_reason", side_effect=AssertionError("prompt must not run")):
            rc = lock._cli_unlock(Namespace(reason=[]))
        self.assertEqual(rc, 0)
        self.assertFalse(lock.is_locked())
        text = (self.box.state_dir / "log").read_text(encoding="utf-8")
        self.assertIn("any", text)
        self.assertTrue(any(tok in text.lower() for tok in ("unlock", "reason")))

    def test_unlock_appends_timestamp_purpose_and_reason(self):
        self._cfg(lock={"reason_min_chars": 8})
        self.assertEqual(lock.lock(None, "deep work"), 0)
        reason = "enough reason text"
        self.assertEqual(lock.unlock(reason), 0)
        text = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("deep work", text)
        self.assertIn(reason, text)
        self.assertRegex(text, r"\d{4}-\d{2}-\d{2}T")

    def test_expired_unlock_is_noop(self):
        state.write_json(
            state.state_path("lock.json"),
            {"locked": True, "since": _iso(-30), "until": _iso(-1), "purpose": "old"},
        )
        self.assertEqual(lock.unlock("x" * 50), 0)
        raw = self._raw_lock()
        self.assertTrue(raw["locked"])

    def test_hooks_detached_documented_env_failure_ignored(self):
        os.environ["DS_HOOK_SLEEP"] = "1.2"
        self._cfg(hooks={"lock": [self._hook_argv()]})
        t0 = time.monotonic()
        self.assertEqual(lock.lock(15, "detach me"), 0)
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.6)
        payload = self._wait_hook(timeout=3)
        self.assertEqual(payload["DS_EVENT"], "lock")
        self.assertEqual(payload["DS_PURPOSE"], "detach me")
        self.assertEqual(payload["DS_MINUTES"], "15")
        self.assertNotEqual(payload["pgrp"], os.getpgrp())

        self.hook_out.unlink()
        os.environ.pop("DS_HOOK_SLEEP", None)
        os.environ["DS_HOOK_FAIL"] = "1"
        self._cfg(hooks={"unlock": [self._hook_argv()]})
        self.assertEqual(lock.unlock("y" * 50), 0)
        self.assertFalse(lock.is_locked())
        self._wait_hook()

        self.assertEqual(lock.lock(5, "missing bin"), 0)
        self._cfg(hooks={"unlock": [["/no/such/hook-binary-ds"]]})
        self.assertEqual(lock.unlock("z" * 50), 0)
        self.assertFalse(lock.is_locked())

    def test_cmd_lock_no_args_uses_prompt_lock(self):
        self._cfg()
        with patch("ds.ui.prompt_lock", return_value=(40, "from menu")) as prompt:
            rc = lock._cli_lock(Namespace(duration=None, purpose=[]))
        self.assertEqual(rc, 0)
        prompt.assert_called_once()
        cfg = prompt.call_args[0][0]
        self.assertEqual(cfg["lock"]["default_minutes"], 25)
        self.assertTrue(lock.is_locked())
        self.assertEqual(self._raw_lock()["purpose"], "from menu")

    def test_cmd_lock_prompt_cancel_locks_nothing(self):
        self._cfg()
        with patch("ds.ui.prompt_lock", return_value=None):
            rc = lock._cli_lock(Namespace(duration=None, purpose=[]))
        self.assertEqual(rc, 0)
        self.assertFalse(lock.is_locked())
        self.assertFalse((self.box.state_dir / "lock.json").exists() or lock.is_locked())

    def test_cmd_lock_unavailable_requires_argument_form(self):
        self._cfg()
        with patch("ds.ui.prompt_lock", side_effect=Unavailable):
            rc = lock._cli_lock(Namespace(duration=None, purpose=[]))
        self.assertEqual(rc, 1)
        self.assertFalse(lock.is_locked())
        self.assertTrue(self.notices)
        self.assertTrue(
            any("argument" in (t + b).lower() or "prompt" in (t + b).lower() for t, b in self.notices)
        )

    def test_cmd_unlock_unavailable_requires_argument_form(self):
        self._cfg()
        self.assertEqual(lock.lock(20, "need reason"), 0)
        with patch("ds.ui.prompt_reason", side_effect=Unavailable):
            rc = lock._cli_unlock(Namespace(reason=[]))
        self.assertEqual(rc, 1)
        self.assertTrue(lock.is_locked())
        self.assertTrue(self.notices)

    def test_cmd_lock_forever_and_minutes_args(self):
        self._cfg()
        with patch("ds.ui.prompt_lock", side_effect=AssertionError("no prompt")):
            rc = lock._cli_lock(Namespace(duration="forever", purpose=["until", "I", "unlock"]))
        self.assertEqual(rc, 0)
        raw = self._raw_lock()
        self.assertTrue(raw["locked"])
        self.assertIsNone(raw["until"])
        self.assertEqual(raw["purpose"], "until I unlock")
        self.assertEqual(lock.unlock("w" * 50), 0)
        rc = lock._cli_lock(Namespace(duration="25", purpose=["cli"]))
        self.assertEqual(rc, 0)
        self.assertTrue(lock.is_locked())
        self.assertEqual(self._raw_lock()["purpose"], "cli")

    def test_cli_lock_unlock_enter(self):
        self.box.fake_bin("hyprctl", HYPRCTL_ON)
        r = self.box.run("lock", "25", "deep", "work")
        self.assertEqual(r.returncode, 0, r.stderr)
        raw = self._raw_lock()
        self.assertTrue(raw["locked"])
        self.assertEqual(raw["purpose"], "deep work")
        self.assertIsNotNone(raw["until"])
        reason = "x" * 50
        r = self.box.run("unlock", reason)
        self.assertEqual(r.returncode, 0, r.stderr)
        raw = self._raw_lock()
        self.assertFalse(raw["locked"])
        r = self.box.run("enter")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_expire_race_does_not_drop_new_lock(self):
        self._cfg()
        script = r"""
import os, sys, time
from pathlib import Path
sys.path.insert(0, os.environ["DS_ROOT"])
from ds import lock
go = Path(os.environ["DS_GO"])
out = Path(os.environ["DS_OUT"])
Path(os.environ["DS_READY"]).write_text("1")
deadline = time.monotonic() + 5
while not go.exists() and time.monotonic() < deadline:
    time.sleep(0.001)
if sys.argv[1] == "expire":
    out.write_text("true" if lock.expire_if_due() else "false")
else:
    lock.lock(40, "racer")
    out.write_text("done")
"""
        env = self.box.env()
        env["DS_ROOT"] = str(ROOT)
        for i in range(12):
            go = self.box.runtime / f"race-go-{i}"
            if go.exists():
                go.unlink()
            state.write_json(
                state.state_path("lock.json"),
                {
                    "locked": True,
                    "since": _iso(-30),
                    "until": _iso(-1),
                    "purpose": "old",
                },
            )
            expire_out = self.box.runtime / f"race-eout-{i}"
            lock_out = self.box.runtime / f"race-lout-{i}"
            expire_ready = self.box.runtime / f"race-eready-{i}"
            lock_ready = self.box.runtime / f"race-lready-{i}"
            pe = subprocess.Popen(
                [sys.executable, "-c", script, "expire"],
                env={**env, "DS_GO": str(go), "DS_OUT": str(expire_out), "DS_READY": str(expire_ready)},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            pl = subprocess.Popen(
                [sys.executable, "-c", script, "lock"],
                env={**env, "DS_GO": str(go), "DS_OUT": str(lock_out), "DS_READY": str(lock_ready)},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not (
                    expire_ready.exists() and lock_ready.exists()
                ):
                    time.sleep(0.005)
                self.assertTrue(
                    expire_ready.exists() and lock_ready.exists(),
                    f"racers did not start on round {i}",
                )
                go.write_text("1", encoding="utf-8")
                try:
                    erc = pe.wait(timeout=5)
                    lrc = pl.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pe.kill()
                    pl.kill()
                    pe.wait(timeout=2)
                    pl.wait(timeout=2)
                    self.fail(f"racer timed out on round {i}")
                if erc != 0:
                    self.fail(f"expire racer failed round {i}: {pe.stderr.read()}")
                if lrc != 0:
                    self.fail(f"lock racer failed round {i}: {pl.stderr.read()}")
            finally:
                for proc in (pe, pl):
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=2)
                    if proc.stderr:
                        proc.stderr.close()
            raw = self._raw_lock()
            self.assertTrue(raw["locked"], i)
            self.assertEqual(raw["purpose"], "racer", i)
            self.assertTrue(lock.is_locked(), i)

    def test_config_load_merges_partial_and_rejects_invalid(self):
        self.box.config_file.write_text(
            json.dumps({"lock": {"default_minutes": 40}}), encoding="utf-8"
        )
        with patch("ds.ui.prompt_lock", return_value=None) as prompt:
            rc = lock._cli_lock(Namespace(duration=None, purpose=[]))
        self.assertEqual(rc, 0)
        prompt.assert_called_once()
        cfg = prompt.call_args[0][0]
        self.assertEqual(cfg["lock"]["default_minutes"], 40)
        self.assertEqual(cfg["lock"]["reason_min_chars"], 50)
        self.assertIn("list", cfg)
        self.assertIn("nudges", cfg)

        lock._cfg_warned = False
        self.notices.clear()
        self.box.config_file.write_text(
            json.dumps({"lock": {"reason_min_chars": -1, "default_minutes": 25, "ask_purpose": True}}),
            encoding="utf-8",
        )
        self.assertEqual(lock._reason_min(), 50)
        self.assertEqual(lock._reason_min(), 50)
        cfg_notices = [
            (t, b) for t, b in self.notices
            if "config" in (t + b).lower() or "default" in (t + b).lower()
        ]
        self.assertEqual(len(cfg_notices), 1)
        self.assertEqual(lock.lock(10, "stay locked"), 0)
        rc = lock.unlock("short")
        self.assertEqual(rc, 1)
        self.assertTrue(lock.is_locked())
        self.assertEqual(self._raw_lock()["purpose"], "stay locked")

    def test_unlock_log_failure_keeps_lock(self):
        log_as_dir = self.box.state_dir / "not-a-log-file"
        log_as_dir.mkdir()
        self._cfg(log=str(log_as_dir), hooks={"unlock": [self._hook_argv()]})
        self.assertEqual(lock.lock(25, "stay"), 0)
        self.notices.clear()
        rc = lock.unlock("x" * 50)
        self.assertEqual(rc, 1)
        self.assertTrue(lock.is_locked())
        self.assertEqual(self._raw_lock()["purpose"], "stay")
        self.assertTrue(self.notices)
        time.sleep(0.15)
        self.assertFalse(self.hook_out.exists())


if __name__ == "__main__":
    unittest.main()
