#!/usr/bin/env python3
"""Summary: command resolution, prompt on stdin, count fallback, record clearing, DS_HELD, listener wiring."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox
from test_hold import BUSCTL, LIST, SHELL, notify_line
from test_listener import GETENT, HYPRCTL, NOTIFY, QUIET_STUB, SUDO, _wait
from test_lock import HOOK_SCRIPT

sys.path.insert(0, str(ROOT))
from ds import hold, lock, summary
from ds.config import DEFAULTS
from ds.state import write_json

# A stand-in agent CLI: records argv and the prompt it got on stdin, then answers per the environment.
AGENT = r"""
import json, os, sys, time
from pathlib import Path
text = sys.stdin.read()
Path(os.environ["DS_AGENT_LOG"]).open("a", encoding="utf-8").write(json.dumps({"argv": sys.argv, "stdin": text}) + "\n")
time.sleep(float(os.environ.get("DS_AGENT_SLEEP", "0")))
if os.environ.get("DS_AGENT_FLOOD"):
    try:
        for _ in range(400):
            sys.stdout.write("x" * 65536)
            sys.stdout.flush()
    except BrokenPipeError:
        os._exit(0)
    os._exit(0)
sys.stdout.write(os.environ.get("DS_AGENT_REPLY", "You missed nothing that needs you."))
sys.exit(int(os.environ.get("DS_AGENT_RC", "0")))
"""

HOOK_ENV = r"""
import json, os
from pathlib import Path
with Path(os.environ["DS_HOOK_LOG"]).open("a", encoding="utf-8") as f:
    f.write(json.dumps({"event": os.environ.get("DS_EVENT"), "held": json.loads(os.environ.get("DS_HELD", "{}"))}) + "\n")
"""

RECORDS = [
    {"at": "2026-09-02T10:00:00+00:00", "app": "Telegram", "title": "Alice", "body": "lunch?"},
    {"at": "2026-09-02T10:00:05+00:00", "app": "Discord", "title": "Bob", "body": "hey"},
    {"at": "2026-09-02T10:00:09+00:00", "app": "Telegram", "title": "Alice", "body": "or coffee"},
]
GROUPED = "Telegram 2 · Discord 1"
_ENV_KEYS = ("DS_AGENT_LOG", "DS_AGENT_REPLY", "DS_AGENT_RC", "DS_AGENT_SLEEP", "DS_AGENT_FLOOD", "DS_HOOK_OUT", "DS_HOOK_LOG",
             "DS_SHELL_LOG", "DS_SHELL_STATE", "DS_SHELL_MISSING", "DS_BUS_LOG", "DS_BUS_LINES", "DS_BUS_EXIT",
             "DS_HYPR_LOG", "DS_HYPR_STATE", "DS_NOTIFY_LOG", "DS_NFT_LOG", "DS_SOCKET2", "GETENT_MAP",
             "DS_FEEDBACK_HTTP_PORT", "DS_FEEDBACK_TLS_PORT")


def _cfg(**summary_over):
    cfg = json.loads(json.dumps(DEFAULTS))
    cfg["summary"].update(summary_over)
    return cfg


def _iso(delta_s: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_s)).replace(microsecond=0).isoformat()


class _Env(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self._orig = {k: os.environ.get(k) for k in _ENV_KEYS}
        for k in _ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class SummaryUnitTests(_Env):
    def setUp(self):
        super().setUp()
        self.agent_log = self.box.runtime / "agent.log"
        os.environ["DS_AGENT_LOG"] = str(self.agent_log)
        # Only the sandbox's fakes resolve: /usr/bin carries python3 for their shebang and no agent CLI.
        os.environ["PATH"] = f"{self.box.bin}{os.pathsep}/usr/bin"
        for name in ("claude", "grok"):
            self.box.fake_bin(name, AGENT)

    def _asked(self):
        return [json.loads(ln) for ln in self.agent_log.read_text(encoding="utf-8").splitlines()] \
            if self.agent_log.exists() else []

    def _log_text(self):
        p = self.box.state_dir / "log"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def test_resolve_auto_prefers_claude_then_grok_then_count(self):
        self.assertEqual(summary.resolve_command(_cfg()), ["claude", "-p", "--output-format", "text"])
        (self.box.bin / "claude").unlink()
        self.assertEqual(summary.resolve_command(_cfg()), ["grok", "-p"])
        (self.box.bin / "grok").unlink()
        self.assertIsNone(summary.resolve_command(_cfg()))
        self.box.fake_bin("claude", AGENT)
        self.assertIsNone(summary.resolve_command(_cfg(command="off")))
        self.assertEqual(summary.resolve_command(_cfg(command=["agent", "--x"])), ["agent", "--x"])
        self.assertEqual(summary.resolve_command(None), ["claude", "-p", "--output-format", "text"])

    def test_body_sends_prompt_on_stdin_and_clips_the_reply(self):
        os.environ["DS_AGENT_REPLY"] = "Alice asked about lunch,\n  twice.  \n"
        self.assertEqual(summary.body(RECORDS, _cfg()), "Alice asked about lunch, twice.")
        asked = self._asked()
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0]["argv"][1:], ["-p", "--output-format", "text"])
        self.assertTrue(asked[0]["stdin"].startswith(summary.PROMPT))
        self.assertIn("second person", asked[0]["stdin"])
        self.assertEqual([json.loads(ln) for ln in asked[0]["stdin"][len(summary.PROMPT):].splitlines()], RECORDS)
        custom = [sys.executable, str(self.box.bin / "grok"), "--flag"]
        os.environ["DS_AGENT_REPLY"] = "é" * 500
        reply = summary.body(RECORDS, _cfg(command=custom))
        self.assertEqual(len(reply.encode("utf-8")), summary.CLIP)
        self.assertEqual(reply, "é" * (summary.CLIP // 2))
        self.assertEqual(self._asked()[-1]["argv"][1:], ["--flag"])
        # A reply that fills the read cap exactly is still a reply, clipped; only what fits the cap is read.
        os.environ["DS_AGENT_REPLY"] = "y" * summary.READ_CAP
        self.assertEqual(summary.body(RECORDS, _cfg()), "y" * summary.CLIP)

    def test_a_flooding_agent_is_cut_off_at_the_read_cap(self):
        os.environ["DS_AGENT_FLOOD"] = "1"
        t0 = time.monotonic()
        with mock.patch.object(summary, "READ_CAP", 8192):
            # Twenty-six megabytes are offered; the pipe closes at the cap and the fake exits 0 on the broken pipe.
            self.assertEqual(summary.ask(["claude", "-p"], "prompt", 10), "x" * summary.CLIP)
        self.assertLess(time.monotonic() - t0, 5.0)
        self.assertEqual(summary.body(RECORDS, _cfg(timeout_seconds=10)), "x" * summary.CLIP)

    def test_failure_timeout_empty_off_and_missing_fall_back_to_the_grouped_count(self):
        cases = [
            ("exit 1", {"DS_AGENT_RC": "1"}, _cfg(), "summary: claude exited 1"),
            ("timeout", {"DS_AGENT_SLEEP": "5"}, _cfg(timeout_seconds=1), "summary: claude timed out after 1s"),
            ("empty", {"DS_AGENT_REPLY": " \n"}, _cfg(), None),
            ("off", {}, _cfg(command="off"), None),
            ("missing", {}, _cfg(command=[str(self.box.bin / "no-such-agent")]), "no-such-agent"),
        ]
        for name, env, cfg, log_bit in cases:
            with self.subTest(case=name):
                with mock.patch.dict(os.environ, env):
                    before = self._log_text()
                    t0 = time.monotonic()
                    self.assertEqual(summary.body(RECORDS, cfg), GROUPED)
                    self.assertLess(time.monotonic() - t0, 4.0)
                    tail = self._log_text()[len(before):]
                    if log_bit is None:
                        self.assertEqual(tail, "")
                    else:
                        self.assertIn("summary: ", tail)
                        self.assertIn(log_bit, tail)
        self.assertEqual(summary.grouped({"A": 1, "B": 3, "C": 1}), "B 3 · A 1 · C 1")

    def test_take_consumes_records_and_zero_records_show_nothing(self):
        for rec in RECORDS:
            self.assertTrue(hold.append_held(rec["app"], rec["title"], rec["body"]))
        with hold.held_path().open("a", encoding="utf-8") as f:
            f.write("not json\n" + json.dumps({"app": ""}) + "\n")
        self.assertEqual(hold.held_counts(), {"Telegram": 2, "Discord": 1})
        records = summary.take()
        self.assertEqual([(r["app"], r["title"], r["body"]) for r in records],
                         [(r["app"], r["title"], r["body"]) for r in RECORDS])
        self.assertFalse(hold.held_path().exists())
        self.assertEqual(hold.held_counts(), {})
        self.assertEqual(summary.take(), [])
        self.assertEqual([p.name for p in self.box.state_dir.iterdir() if "taken" in p.name], [])
        # A claim that cannot be made (the state dir is read-only) takes nothing and leaves the file for later.
        self.assertTrue(hold.append_held("Telegram", "t", "b"))
        os.chmod(self.box.state_dir, 0o500)
        try:
            self.assertEqual(summary.take(), [])
        finally:
            os.chmod(self.box.state_dir, 0o700)
        self.assertEqual(hold.held_counts(), {"Telegram": 1})
        self.assertEqual(len(summary.take()), 1)
        with mock.patch.object(summary.ui, "notify") as notify:
            self.assertFalse(summary.notice([], _cfg(command="off")))
            self.assertIsNone(summary.start([], _cfg(command="off")))
            notify.assert_not_called()
            self.assertTrue(summary.notice(records, _cfg(command="off")))
            notify.assert_called_once_with(summary.TITLE, GROUPED)

    def test_unlock_command_claims_the_records_for_its_hook_and_its_notice(self):
        hook_out = self.box.runtime / "hook-out.json"
        os.environ["DS_HOOK_OUT"] = str(hook_out)
        hook_py = self.box.bin / "ds-hook.py"
        hook_py.write_text(HOOK_SCRIPT, encoding="utf-8")
        cfg = _cfg(command="off")
        cfg["hooks"]["unlock"] = [[sys.executable, str(hook_py)]]
        self.box.config_file.write_text(json.dumps(cfg), encoding="utf-8")
        def hook_payload():
            self.assertTrue(_wait(lambda: hook_out.exists() and hook_out.stat().st_size, 3))
            payload = json.loads(hook_out.read_text(encoding="utf-8"))
            hook_out.unlink()
            self.assertEqual(payload["DS_EVENT"], "unlock")
            return json.loads(payload["DS_HELD"])

        with mock.patch.object(lock, "_notify"), mock.patch.object(summary.ui, "notify") as notify:
            self.assertEqual(lock.lock(25, "write"), 0)
            for rec in RECORDS:
                hold.append_held(rec["app"], rec["title"], rec["body"])
            self.assertEqual(lock.unlock("x" * 50), 0)
            notify.assert_called_once_with(summary.TITLE, GROUPED)
            self.assertEqual(hook_payload(), {"Telegram": 2, "Discord": 1})
            self.assertFalse(hold.held_path().exists())
            # Nothing held, nothing shown; the hook still runs.
            self.assertEqual(lock.lock(25, "again"), 0)
            self.assertEqual(lock.unlock("y" * 50), 0)
            notify.assert_called_once()
            self.assertEqual(hook_payload(), {})


class SummaryListenerTests(_Env):
    def setUp(self):
        super().setUp()
        rt = self.box.runtime
        self.agent_log, self.hook_log, self.notify_log = rt / "agent.log", rt / "hook.log", rt / "notify.log"
        self.bus_lines, self.hypr_state, self.sock2_path = rt / "bus.lines", rt / "hypr-state.json", rt / "s2.sock"
        os.environ.update({
            "DS_AGENT_LOG": str(self.agent_log), "DS_HOOK_LOG": str(self.hook_log),
            "DS_SHELL_LOG": str(rt / "shell.log"), "DS_SHELL_STATE": str(rt / "shell-state.json"),
            "DS_BUS_LOG": str(rt / "bus.log"), "DS_BUS_LINES": str(self.bus_lines), "DS_BUS_EXIT": str(rt / "bus.exit"),
            "DS_HYPR_LOG": str(rt / "hypr.log"), "DS_HYPR_STATE": str(self.hypr_state),
            "DS_NOTIFY_LOG": str(self.notify_log), "DS_NFT_LOG": str(rt / "nft.log"), "DS_SOCKET2": str(self.sock2_path),
            "GETENT_MAP": json.dumps({"example.com": ["203.0.113.10"], "www.example.com": ["203.0.113.10"]}),
            "DS_FEEDBACK_HTTP_PORT": "0", "DS_FEEDBACK_TLS_PORT": "0",
        })
        for name, src in (("omarchy-shell", SHELL), ("busctl", BUSCTL), ("hyprctl", HYPRCTL), ("getent", GETENT),
                          ("sudo", SUDO), ("omarchy-notification-send", NOTIFY), ("pactl", QUIET_STUB),
                          ("claude", AGENT)):
            self.box.fake_bin(name, src)
        self.hook_py = self.box.bin / "ds-hook.py"
        self.hook_py.write_text("#!/usr/bin/env python3\n" + HOOK_ENV, encoding="utf-8")
        self.hook_py.chmod(0o755)
        self._workspace("1", 1)
        self.proc = None

    def tearDown(self):
        self._stop()
        super().tearDown()

    def _write_cfg(self, **summary_over):
        cfg = _cfg(**summary_over)
        cfg["list"], cfg["nudges"] = LIST, {"app_banner": False, "block_page": False}
        hook = [sys.executable, str(self.hook_py)]
        cfg["hooks"] = {"lock": [], "unlock": [hook], "enter": [hook], "leave": []}
        self.box.config_file.write_text(json.dumps(cfg), encoding="utf-8")

    def _workspace(self, name, wid):
        write_json(self.hypr_state, {"activeworkspace": {"id": wid, "name": name}, "clients": [],
                                     "workspaces": [{"id": 1, "name": "1"}, {"id": 5, "name": "distraction"}]})

    def _start(self):
        import socket
        self.sock2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock2.bind(str(self.sock2_path))
        self.sock2.listen(1)
        self.sock2.settimeout(5)
        self.addCleanup(self.sock2.close)
        self.proc = self.box.popen("listen")
        self.conn, _ = self.sock2.accept()
        self.addCleanup(self.conn.close)
        self.box.wait_file(self.box.runtime / "distraction-space.sock", timeout=5)
        self.assertIsNone(self.proc.poll(), "listener exited early")
        self.assertTrue(_wait(lambda: (self.box.runtime / "bus.log").exists(), 3))

    def _stop(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.communicate(timeout=6)
        except Exception:
            self.proc.kill()
            self.proc.communicate(timeout=2)
        self.proc = None

    def _state(self):
        path = self.box.state_dir / "state.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _held_file(self):
        return self.box.state_dir / "held.jsonl"

    def _emit(self, *lines):
        with self.bus_lines.open("a", encoding="utf-8") as f:
            f.write("".join(ln + "\n" for ln in lines))

    def _go(self, name, wid):
        self._workspace(name, wid)
        self.conn.sendall(f"workspacev2>>{wid},{name}\n".encode())

    def _notices(self):
        text = self.notify_log.read_text(encoding="utf-8") if self.notify_log.exists() else ""
        return [ln for ln in text.splitlines() if ln.startswith(summary.TITLE)]

    def _hooks(self):
        return [json.loads(ln) for ln in self.hook_log.read_text(encoding="utf-8").splitlines()] \
            if self.hook_log.exists() else []

    def _hold(self, held):
        self._emit(notify_line("Telegram Desktop", "telegram", "Alice", "hi"),
                   notify_line("Telegram Desktop", "telegram", "Alice", "again"),
                   notify_line("Google Chrome", "google-chrome", "Bob", "discord.com\nBob: hey"))
        self.assertTrue(_wait(lambda: self._state().get("held") == held, 5), self._state())

    def test_entering_the_space_shows_the_agent_line_once_hands_counts_to_the_hook_and_clears(self):
        os.environ["DS_AGENT_REPLY"] = "Alice asked twice; nothing urgent."
        self._write_cfg()
        self._start()
        self._hold({"Telegram": 2, "Discord": 1})
        self._go("distraction", 5)
        self.assertTrue(_wait(lambda: self._notices() == [f"{summary.TITLE} Alice asked twice; nothing urgent."], 6),
                        self._notices())
        self.assertTrue(_wait(lambda: len(self._hooks()) == 1, 3), self._hooks())
        self.assertEqual(self._hooks()[0], {"event": "enter", "held": {"Telegram": 2, "Discord": 1}})
        self.assertFalse(self._held_file().exists())
        self.assertTrue(_wait(lambda: self._state().get("held") == {}, 3), self._state())
        asked = json.loads(self.agent_log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(asked["argv"][1:], ["-p", "--output-format", "text"])
        self.assertEqual([json.loads(ln)["app"] for ln in asked["stdin"][len(summary.PROMPT):].splitlines()],
                         ["Telegram", "Telegram", "Discord"])
        self._go("2", 2)
        self.assertTrue(_wait(lambda: self._state().get("on_space") is False, 3), self._state())
        self._go("distraction", 5)
        self.assertTrue(_wait(lambda: len(self._hooks()) == 2, 3), self._hooks())
        self.assertEqual(self._hooks()[1], {"event": "enter", "held": {}})
        time.sleep(0.5)
        self.assertEqual(len(self._notices()), 1)

    def test_manual_unlock_and_expiry_each_summarize_once_with_the_count_fallback(self):
        self._write_cfg(command="off")
        write_json(self.box.state_dir / "lock.json",
                   {"locked": True, "since": _iso(-60), "until": _iso(3600), "purpose": "deep work"})
        self._start()
        self._hold({"Telegram": 2, "Discord": 1})
        r = self.box.run("unlock", *(["done"] * 20), timeout=15)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(_wait(lambda: self._notices() == [f"{summary.TITLE} {GROUPED}"], 6), self._notices())
        self.assertTrue(_wait(lambda: len(self._hooks()) == 1, 3), self._hooks())
        self.assertEqual(self._hooks()[0], {"event": "unlock", "held": {"Telegram": 2, "Discord": 1}})
        self.assertTrue(_wait(lambda: self._state().get("held") == {}, 3), self._state())
        self.assertFalse(self._held_file().exists())
        self.assertFalse(self.agent_log.exists())
        write_json(self.box.state_dir / "lock.json",
                   {"locked": True, "since": _iso(-60), "until": _iso(2), "purpose": "one more"})
        self.assertTrue(_wait(lambda: self._state().get("locked") is True, 3), self._state())
        self._emit(notify_line("Telegram Desktop", "telegram", "Alice", "third"))
        self.assertTrue(_wait(lambda: self._state().get("held") == {"Telegram": 1}, 5), self._state())
        self.assertTrue(_wait(lambda: len(self._notices()) == 2, 8), self._notices())
        self.assertEqual(self._notices()[1], f"{summary.TITLE} Telegram 1")
        self.assertIn("Lock ended one more", self.notify_log.read_text(encoding="utf-8"))
        self.assertTrue(_wait(lambda: len(self._hooks()) == 2, 3), self._hooks())
        self.assertEqual(self._hooks()[1], {"event": "unlock", "held": {"Telegram": 1}})
        self.assertFalse(self._held_file().exists())


if __name__ == "__main__":
    unittest.main()
