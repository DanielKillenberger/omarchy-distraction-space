#!/usr/bin/env python3
"""Notification hold: sender keys, shell push, bus capture into held.jsonl, listener wiring."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox
from test_listener import GETENT, HYPRCTL, NOTIFY, SUDO, _wait

sys.path.insert(0, str(ROOT))
from ds import catalog, hold
from ds.config import DEFAULTS
from ds.state import write_json

SHELL = r"""
import json, os, sys
from pathlib import Path
Path(os.environ["DS_SHELL_LOG"]).open("a").write(" ".join(sys.argv[1:]) + "\n")
args = sys.argv[1:]
if args[:1] != ["notifications"]:
    print("Target not found.")
    sys.exit(1)
if os.environ.get("DS_SHELL_MISSING"):
    print("Function not found.")
    sys.exit(1)
path = Path(os.environ["DS_SHELL_STATE"])
current = json.loads(path.read_text()) if path.exists() else []
if args[1:2] == ["silencedSenders"]:
    print(json.dumps(current))
elif args[1:2] == ["setSilencedSenders"]:
    # Real `qs ipc call` splits a "[...]" argument into separate arguments, so
    # the JSON setter is unreachable from the CLI; mimic that failure.
    print("Too many arguments provided (1 required but 2 were provided.)")
    sys.exit(1)
elif args[1:2] in (["silence"], ["unsilence"]) and len(args) == 3:
    def norm(item):
        key = item.strip().lower()
        return key[4:] if key.startswith("www.") else key
    out = [norm(i) for i in current if isinstance(i, str) and norm(i)]
    out = list(dict.fromkeys(out))
    key = norm(args[2])
    if args[1] == "silence":
        if key and key not in out:
            out.append(key)
    else:
        out = [k for k in out if k != key]
    path.write_text(json.dumps(out))
    print(json.dumps(out))
else:
    print("Function not found.")
    sys.exit(1)
"""

BUSCTL = r"""
import os, sys, time
from pathlib import Path
Path(os.environ["DS_BUS_LOG"]).open("a").write(f"{time.monotonic():.3f} {' '.join(sys.argv[1:])}\n")
if Path(os.environ.get("DS_BUS_EXIT", "/nonexistent")).exists():
    sys.exit(3)
lines = Path(os.environ["DS_BUS_LINES"])
seen = 0
while True:
    text = lines.read_text(encoding="utf-8") if lines.exists() else ""
    rows = text.splitlines()
    for row in rows[seen:]:
        sys.stdout.write(row + "\n")
        sys.stdout.flush()
    seen = len(rows)
    time.sleep(0.05)
"""

_ENV_KEYS = ("DS_SHELL_LOG", "DS_SHELL_STATE", "DS_SHELL_MISSING", "DS_BUS_LOG", "DS_BUS_LINES",
             "DS_BUS_EXIT", "DS_HYPR_LOG", "DS_HYPR_STATE", "DS_NOTIFY_LOG", "DS_NFT_LOG", "DS_SOCKET2",
             "GETENT_MAP", "DS_FEEDBACK_HTTP_PORT", "DS_FEEDBACK_TLS_PORT")
LIST = ["Telegram", "Discord", "example.com"]
KEYS = ["telegram desktop", "org.telegram.desktop", "web.telegram.org", "discord.com", "example.com"]


def notify_line(app, icon, summary, body):
    return json.dumps({
        "type": "method_call", "sender": ":1.5", "destination": "org.freedesktop.Notifications",
        "path": "/org/freedesktop/Notifications", "interface": "org.freedesktop.Notifications",
        "member": "Notify", "signature": "susssasa{sv}i",
        "payload": {"type": "susssasa{sv}i",
                    "data": [app, 0, icon, summary, body, [], {"urgency": {"type": "y", "data": 1}}, -1]},
    })


class HoldUnitTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.shell_log = self.box.runtime / "shell.log"
        self.shell_state = self.box.runtime / "shell-state.json"
        self._orig = {k: os.environ.get(k) for k in _ENV_KEYS}
        os.environ.update(DS_SHELL_LOG=str(self.shell_log), DS_SHELL_STATE=str(self.shell_state))
        os.environ.pop("DS_SHELL_MISSING", None)
        self.box.fake_bin("omarchy-shell", SHELL)

    def tearDown(self):
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _silenced(self):
        return json.loads(self.shell_state.read_text()) if self.shell_state.exists() else []

    def _calls(self):
        return self.shell_log.read_text().splitlines() if self.shell_log.exists() else []

    def test_sender_keys_cover_senders_pwa_hosts_and_plain_hosts(self):
        expanded = catalog.expand({"list": [*LIST, {"name": "Foo", "hosts": ["www.foo.org"], "senders": ["Foo App"]}]})
        self.assertEqual(hold.sender_keys(expanded), [*KEYS, "foo app", "foo.org"])
        table = hold.key_table(expanded)
        self.assertEqual(table["web.telegram.org"], "Telegram")
        self.assertEqual(table["example.com"], "example.com")
        self.assertEqual(table["foo.org"], "Foo")
        self.assertEqual(hold.sender_keys(catalog.expand({"list": ["X", "Facebook"]})), ["x.com", "facebook.com"])

    def test_effective_hold_table(self):
        cases = [
            ("off-space", False, False, True), ("off-space", True, False, False), ("off-space", None, True, False),
            ("locked", False, True, True), ("locked", False, False, False), ("locked", True, True, True),
            ("never", False, True, False),
        ]
        for mode, on_space, locked, want in cases:
            with self.subTest(mode=mode, on_space=on_space, locked=locked):
                self.assertIs(hold.effective_hold({"hold_notifications": mode}, on_space, locked), want)
        self.assertIs(hold.effective_hold(None, False, False), True)

    def test_push_adds_and_removes_only_plugin_keys(self):
        # "example.com" is on the plugin list AND was silenced by hand beforehand.
        self.shell_state.write_text(json.dumps(["hand added", "WWW.Example.COM"]))
        self.assertEqual(hold.push(KEYS, True), "on")
        self.assertEqual(self._silenced(), ["hand added", "example.com", *KEYS[:4]])
        self.assertEqual(hold.push(KEYS, True), "on")
        mutations = [c for c in self._calls() if c.split()[1] in ("silence", "unsilence")]
        self.assertEqual(len(mutations), len(self._silenced()) - 2, "one call per added key, none on the no-op push")
        self.assertFalse(any("setSilencedSenders" in c for c in self._calls()), "the JSON setter is unreachable through qs ipc")
        self.assertEqual(hold.push(KEYS[1:], True, retire=[KEYS[0]]), "on")
        self.assertEqual(self._silenced(), ["hand added", "example.com", *KEYS[1:4]])
        self.assertEqual(hold.push(KEYS[1:], False), "off")
        self.assertEqual(self._silenced(), ["hand added", "example.com"], "a hand-silenced key survives hold off")
        self.assertFalse(hold.owned_path().exists())

    def test_owned_keys_persist_across_a_restart(self):
        self.shell_state.write_text(json.dumps(["hand added"]))
        self.assertEqual(hold.push(KEYS, True), "on")
        self.assertEqual(sorted(json.loads(hold.owned_path().read_text())), sorted(KEYS))
        # A fresh process knows what it owns without having pushed anything this run.
        self.assertEqual(hold.push(KEYS, False), "off")
        self.assertEqual(self._silenced(), ["hand added"])
        # A key the person removed by hand while owned is simply not there any more.
        self.assertEqual(hold.push(KEYS, True), "on")
        self.shell_state.write_text(json.dumps(["hand added", *KEYS[1:]]))
        self.assertEqual(hold.push(KEYS, False), "off")
        self.assertEqual(self._silenced(), ["hand added"])
        self.assertFalse(hold.owned_path().exists())

    def test_push_missing_method_is_unavailable_without_a_set_call(self):
        os.environ["DS_SHELL_MISSING"] = "1"
        self.assertEqual(hold.push(KEYS, True), "unavailable")
        self.assertEqual(self._calls(), ["notifications silencedSenders"])
        with mock.patch.object(hold.subprocess, "run", side_effect=PermissionError("denied")):
            self.assertEqual(hold.push(KEYS, True), "unavailable")

    def test_capture_start_failure_backs_off_instead_of_raising(self):
        cap = hold.Capture()
        with mock.patch.object(hold.subprocess, "Popen", side_effect=PermissionError("denied")):
            cap.tick(now=100.0)
            self.assertIsNone(cap.proc)
            self.assertFalse(cap.missing)
            self.assertEqual(cap.next_start, 101.0)
            cap.tick(now=100.5)
            cap.tick(now=101.0)
        self.assertIsNone(cap.proc)
        self.assertEqual(cap.next_start, 105.0)

    def test_attribute_native_chromium_and_unmatched(self):
        table = hold.key_table(catalog.expand({"list": LIST}))
        cases = [
            (["Telegram Desktop", 0, "telegram", "Alice", "hi", [], {}, -1], "Telegram"),
            (["Google Chrome", 0, "google-chrome", "Bob", "discord.com\nBob: hey", [], {}, -1], "Discord"),
            (["chromium", 0, "", "Bob", '<a href="https://www.example.com/x">www.example.com</a> ping', [], {}, -1],
             "example.com"),
            (["Slack", 0, "slack", "Bob", "discord.com\nnot chromium", [], {}, -1], None),
            (["Google Chrome", 0, "google-chrome", "Bob", "no origin here", [], {}, -1], None),
            (["Telegram Desktop"], None),
        ]
        for data, want in cases:
            with self.subTest(app=data[0], body=data[4] if len(data) > 4 else None):
                self.assertEqual(hold.attribute(data, table), want)

    def test_held_clipping_cap_and_counts(self):
        self.assertTrue(hold.append_held("Telegram", "t", "x" * 5000))
        self.assertTrue(hold.append_held("Discord", "é" * 3000, ""))
        recs = [json.loads(ln) for ln in hold.held_path().read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(recs[0]["body"].encode()), hold.FIELD_CAP)
        self.assertEqual(len(recs[1]["title"].encode()), hold.FIELD_CAP)
        self.assertEqual(set(recs[0]), {"at", "app", "title", "body"})
        for i in range(60):
            self.assertTrue(hold.append_held("Telegram", str(i), "y" * 2000))
        size = hold.held_path().stat().st_size
        self.assertLessEqual(size, hold.FILE_CAP)
        self.assertGreater(size, hold.FILE_CAP - 2200)
        lines = hold.held_path().read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(lines[-1])["title"], "59")
        self.assertEqual(hold.held_counts(), {"Telegram": len(lines)})
        hold.held_path().unlink()
        os.chmod(self.box.state_dir, 0o500)
        try:
            self.assertFalse(hold.append_held("Telegram", "t", "b"))
        finally:
            os.chmod(self.box.state_dir, 0o700)
        self.assertEqual(hold.held_counts(), {})

    def test_senders_command_prints_keys(self):
        cfg = json.loads(json.dumps(DEFAULTS))
        cfg["list"] = LIST
        self.box.config_file.write_text(json.dumps(cfg), encoding="utf-8")
        r = self.box.run("senders", timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), KEYS)


class HoldListenerTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        rt = self.box.runtime
        self.shell_log, self.shell_state = rt / "shell.log", rt / "shell-state.json"
        self.bus_log, self.bus_lines, self.bus_exit = rt / "bus.log", rt / "bus.lines", rt / "bus.exit"
        self.notify_log, self.hypr_state, self.sock2_path = rt / "notify.log", rt / "hypr-state.json", rt / "s2.sock"
        self._orig = {k: os.environ.get(k) for k in _ENV_KEYS}
        os.environ.update({
            "DS_SHELL_LOG": str(self.shell_log), "DS_SHELL_STATE": str(self.shell_state),
            "DS_BUS_LOG": str(self.bus_log), "DS_BUS_LINES": str(self.bus_lines), "DS_BUS_EXIT": str(self.bus_exit),
            "DS_HYPR_LOG": str(rt / "hypr.log"), "DS_HYPR_STATE": str(self.hypr_state),
            "DS_NOTIFY_LOG": str(self.notify_log), "DS_NFT_LOG": str(rt / "nft.log"), "DS_SOCKET2": str(self.sock2_path),
            "GETENT_MAP": json.dumps({"example.com": ["203.0.113.10"], "www.example.com": ["203.0.113.10"]}),
            "DS_FEEDBACK_HTTP_PORT": "0", "DS_FEEDBACK_TLS_PORT": "0",
        })
        os.environ.pop("DS_SHELL_MISSING", None)
        for name, src in (("omarchy-shell", SHELL), ("busctl", BUSCTL), ("hyprctl", HYPRCTL),
                          ("getent", GETENT), ("sudo", SUDO), ("omarchy-notification-send", NOTIFY)):
            self.box.fake_bin(name, src)
        cfg = json.loads(json.dumps(DEFAULTS))
        cfg["list"], cfg["nudges"] = LIST, {"app_banner": False, "block_page": False}
        cfg["summary"]["command"] = "off"  # the summary is test_summary's; `auto` would reach a real agent CLI
        self.box.config_file.write_text(json.dumps(cfg), encoding="utf-8")
        self._workspace("1", 1)
        self.proc = None

    def tearDown(self):
        self._stop()
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

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

    def _stop(self):
        """SIGTERM the listener and return its stderr."""
        if self.proc is None:
            return ""
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
        try:
            _, err = self.proc.communicate(timeout=6)
        except Exception:
            self.proc.kill()
            _, err = self.proc.communicate(timeout=2)
        self.proc = None
        return err or ""

    def _state(self):
        path = self.box.state_dir / "state.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _silenced(self):
        return json.loads(self.shell_state.read_text()) if self.shell_state.exists() else []

    def _held(self):
        path = self.box.state_dir / "held.jsonl"
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def _emit(self, *lines):
        with self.bus_lines.open("a", encoding="utf-8") as f:
            f.write("".join(ln + "\n" for ln in lines))

    def _go(self, name, wid):
        self._workspace(name, wid)
        self.conn.sendall(f"workspacev2>>{wid},{name}\n".encode())

    def _notices(self):
        text = self.notify_log.read_text(encoding="utf-8") if self.notify_log.exists() else ""
        return [ln for ln in text.splitlines() if "Notification hold unavailable" in ln]

    def test_hold_pushes_captures_releases_and_removes_on_exit(self):
        self.shell_state.write_text(json.dumps(["hand added"]))
        self._start()
        self.assertTrue(_wait(lambda: self._silenced() == ["hand added", *KEYS], 5), self._silenced())
        self.assertTrue(_wait(lambda: self._state().get("hold") is True, 3), self._state())
        self.assertEqual(self._state().get("notification_hold"), "on")
        self.assertTrue(_wait(lambda: self.bus_log.exists(), 3))
        self._emit(notify_line("Telegram Desktop", "telegram", "Alice", "hi"),
                   notify_line("Google Chrome", "google-chrome", "Bob", "www.discord.com\nBob: hey"),
                   notify_line("Slack", "slack", "Carol", "meeting"))
        self.assertTrue(_wait(lambda: len(self._held()) == 2, 5), self._held())
        self.assertEqual([r["app"] for r in self._held()], ["Telegram", "Discord"])
        self.assertEqual(self._held()[1]["body"], "www.discord.com\nBob: hey")
        self.assertTrue(_wait(lambda: self._state().get("held") == {"Telegram": 1, "Discord": 1}, 3), self._state())
        self._go("distraction", 5)
        self.assertTrue(_wait(lambda: self._silenced() == ["hand added"], 5), self._silenced())
        self.assertTrue(_wait(lambda: self._state().get("hold") is False, 3), self._state())
        self.assertEqual(self._state().get("notification_hold"), "off")
        # Entering the space hands the two records to the summary; a ping on the space is not recorded.
        self.assertTrue(_wait(lambda: self._state().get("held") == {}, 3), self._state())
        self._emit(notify_line("Telegram Desktop", "telegram", "Alice", "on space"))
        time.sleep(0.4)
        self.assertEqual(len(self._held()), 0)
        self._go("2", 2)
        self.assertTrue(_wait(lambda: self._silenced() == ["hand added", *KEYS], 5), self._silenced())
        self._stop()
        self.assertEqual(self._silenced(), ["hand added"])
        self.assertEqual(self._notices(), [])

    def test_missing_method_is_unavailable_once_and_capture_continues(self):
        os.environ["DS_SHELL_MISSING"] = "1"
        self._start()
        self.assertTrue(_wait(lambda: self._state().get("notification_hold") == "unavailable", 5), self._state())
        self.assertTrue(self._state().get("hold"))
        self.assertTrue(_wait(lambda: self.bus_log.exists(), 3))
        self._emit(notify_line("Telegram Desktop", "telegram", "Alice", "hi"))
        self.assertTrue(_wait(lambda: len(self._held()) == 1, 5), self._held())
        self._go("distraction", 5)
        self.assertTrue(_wait(lambda: self._state().get("hold") is False, 3), self._state())
        self._go("2", 2)
        self.assertTrue(_wait(lambda: self._state().get("hold") is True, 3), self._state())
        self.assertEqual(self._state().get("notification_hold"), "unavailable")
        self.assertEqual(len(self._notices()), 1)
        self.assertGreaterEqual(self.shell_log.read_text().count("silencedSenders"), 3)

    def test_busctl_exit_restarts_with_backoff(self):
        self.bus_exit.write_text("1")
        self._start()
        starts = lambda: [float(ln.split()[0]) for ln in self.bus_log.read_text().splitlines()] \
            if self.bus_log.exists() else []
        self.assertTrue(_wait(lambda: len(starts()) >= 3, 9), starts())
        t = starts()
        self.assertGreaterEqual(t[1] - t[0], 0.9, t)
        self.assertGreaterEqual(t[2] - t[1], 3.9, t)
        self.assertLess(t[2] - t[1], 8.0, t)
        err = self._stop()
        self.assertIn("busctl exited with 3; restarting in 1s", err)
        self.assertIn("restarting in 4s", err)


if __name__ == "__main__":
    unittest.main()
