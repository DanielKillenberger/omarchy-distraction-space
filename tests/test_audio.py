#!/usr/bin/env python3
"""Sound mute: stream attribution, mute/unmute by identity, muted.json, missing pactl, listener wiring."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox
from test_hold import BUSCTL, LIST, SHELL
from test_listener import GETENT, HYPRCTL, NOTIFY, SUDO, _wait

sys.path.insert(0, str(ROOT))
from ds import catalog, hold
from ds.config import DEFAULTS
from ds.state import write_json

PACTL = r"""
import json, os, sys, time
from pathlib import Path
Path(os.environ["DS_PACTL_LOG"]).open("a").write(" ".join(sys.argv[1:]) + "\n")
if Path(os.environ.get("DS_PACTL_FAIL", "/nonexistent")).exists():
    print("Connection failure: Connection refused", file=sys.stderr)
    sys.exit(1)
streams = Path(os.environ["DS_PACTL_STREAMS"])
args = sys.argv[1:]
if args == ["-f", "json", "list", "sink-inputs"]:
    print(streams.read_text() if streams.exists() else "[]")
elif args[:1] == ["set-sink-input-mute"] and len(args) == 3:
    if args[1] in os.environ.get("DS_PACTL_STUCK", "").split(","):
        print("Failure: No such entity", file=sys.stderr)
        sys.exit(1)
    items = json.loads(streams.read_text()) if streams.exists() else []
    for item in items:
        if str(item["index"]) == args[1]:
            item["mute"] = args[2] == "1"
    streams.write_text(json.dumps(items))
elif args == ["subscribe"]:
    events, seen = Path(os.environ["DS_PACTL_EVENTS"]), 0
    while True:
        rows = events.read_text(encoding="utf-8").splitlines() if events.exists() else []
        for row in rows[seen:]:
            sys.stdout.write(row + "\n")
            sys.stdout.flush()
        seen = len(rows)
        time.sleep(0.05)
else:
    sys.exit(1)
"""

_ENV_KEYS = ("DS_PACTL_LOG", "DS_PACTL_STREAMS", "DS_PACTL_EVENTS", "DS_PACTL_FAIL", "DS_PACTL_STUCK", "DS_SHELL_LOG", "DS_SHELL_STATE",
             "DS_SHELL_MISSING", "DS_BUS_LOG", "DS_BUS_LINES", "DS_BUS_EXIT", "DS_HYPR_LOG", "DS_HYPR_STATE",
             "DS_NOTIFY_LOG", "DS_NFT_LOG", "DS_SOCKET2", "GETENT_MAP", "DS_FEEDBACK_HTTP_PORT", "DS_FEEDBACK_TLS_PORT")
CUSTOM = {"name": "Foo", "hosts": ["foo.org"], "audio": {"name": ["Chromium"], "binary": ["chrome"]}}
START = "4242"


def stream(index, name, binary, pid, muted=False):
    props = {"application.name": name, "application.process.binary": binary, "media.name": "Playback"}
    if pid is not None:
        props["application.process.id"] = str(pid)
    return {"index": index, "sink": 1, "corked": False, "mute": muted, "properties": props}


def fake_proc(root: Path, table):
    """`table` maps pid to (ppid, argv); every process gets starttime START."""
    for pid, (ppid, argv) in table.items():
        d = root / str(pid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "stat").write_text(f"{pid} (a b) S {ppid} " + " ".join(["0"] * 17) + f" {START} 0 0\n")
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    return root


class _Env(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        rt = self.box.runtime
        self.pactl_log, self.streams, self.events = rt / "pactl.log", rt / "streams.json", rt / "pactl.events"
        self._orig = {k: os.environ.get(k) for k in _ENV_KEYS}
        os.environ.update(DS_PACTL_LOG=str(self.pactl_log), DS_PACTL_STREAMS=str(self.streams),
                          DS_PACTL_EVENTS=str(self.events), DS_PACTL_FAIL=str(rt / "pactl.fail"))
        os.environ.pop("DS_PACTL_STUCK", None)
        self.box.fake_bin("pactl", PACTL)

    def tearDown(self):
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _streams(self):
        return {str(it["index"]): it["mute"] for it in json.loads(self.streams.read_text())} if self.streams.exists() else {}

    def _calls(self, prefix=""):
        rows = self.pactl_log.read_text().splitlines() if self.pactl_log.exists() else []
        return [r for r in rows if r.startswith(prefix)]

    def _muted(self):
        path = self.box.state_dir / "muted.json"
        return json.loads(path.read_text()) if path.exists() else None


class AudioUnitTests(_Env):
    def setUp(self):
        super().setUp()
        self.table = hold.audio_table(catalog.expand({"list": ["Telegram", "Discord", "example.com", CUSTOM]}))
        chain = {510 + i: (509 + i if i else 1, ["chromium", "--type=renderer"]) for i in range(10)}
        chain[510] = (1, ["chromium", "--app=https://web.telegram.org/"])
        self.proc = fake_proc(self.box.runtime / "proc", {
            100: (1, ["telegram-desktop"]),
            200: (1, ["/usr/lib/chromium/chromium", "--app=https://discord.com/", "--profile-directory=Default"]),
            201: (200, ["/usr/lib/chromium/chromium", "--type=utility", "--utility-sub-type=audio.mojom.AudioService"]),
            300: (1, ["chromium", "--app-id=www.example.com"]),
            400: (1, ["chromium"]),
            **chain,
        })
        self._orig_proc = hold.PROC
        hold.PROC = self.proc
        self.addCleanup(setattr, hold, "PROC", self._orig_proc)

    def test_audio_table_from_catalog_and_custom_entries(self):
        self.assertEqual(self.table["names"], {"telegram desktop": "Telegram", "chromium": "Foo"})
        self.assertEqual(self.table["binaries"], {"telegram-desktop": "Telegram", "telegram": "Telegram", "chrome": "Foo"})
        self.assertEqual(self.table["hosts"], {"web.telegram.org": "Telegram", "discord.com": "Discord",
                                               "example.com": "example.com", "foo.org": "Foo"})
        self.assertEqual(hold.audio_table(catalog.expand({"list": ["X"]}))["hosts"], {"x.com": "X"})
        for cfg, want in (({}, True), ({"mute_sounds": False}, False), (None, True)):
            self.assertIs(hold.mute_on(cfg), want)

    def test_attribute_stream_native_pwa_ancestors_and_bare_browser(self):
        cases = [
            (stream(1, "Telegram Desktop", "telegram-desktop", 100), "Telegram"),
            (stream(1, "Unknown", "/usr/bin/Telegram", 100), "Telegram"),
            (stream(1, "Chromium", "chrome", 201), "Discord"),
            (stream(1, "Chromium", "chrome", 300), "example.com"),
            (stream(1, "Chromium", "chrome", 400), None),
            (stream(1, "Google Chrome", "chrome", None), None),
            (stream(1, "Google Chrome", "chrome", 518), "Telegram"),
            (stream(1, "Google Chrome", "chrome", 519), None),
            (stream(1, "mpv", "mpv", 100), None),
            ({"index": 1}, None),
        ]
        for item, want in cases:
            with self.subTest(item=item.get("properties")):
                self.assertEqual(hold.attribute_stream(item, self.table), want)
        self.assertEqual(hold.identity(100), f"100:{START}")
        self.assertIsNone(hold.identity(999))
        self.assertIsNone(hold.identity(None))

    def test_scan_mutes_attributed_streams_records_identity_and_release_unmutes(self):
        m = hold.Mute()
        m.sync(False, self.table)
        self.assertEqual(self._calls(), [])
        self.streams.write_text(json.dumps([
            stream(3, "Telegram Desktop", "telegram-desktop", 100), stream(4, "Chromium", "chrome", 400),
            stream(5, "Chromium", "chrome", 201), stream(6, "Telegram Desktop", "telegram-desktop", 100, muted=True),
            stream(8, "Telegram Desktop", "telegram-desktop", None),
        ]))
        m.sync(True, self.table)
        self.assertEqual(self._streams(), {"3": True, "4": False, "5": True, "6": True, "8": False})
        self.assertEqual(self._muted(), {"3": f"100:{START}", "5": f"201:{START}"})
        self.assertEqual(self._calls("set-sink-input-mute"), ["set-sink-input-mute 3 1", "set-sink-input-mute 5 1"])
        m.sync(True, self.table)
        self.assertEqual(len(self._calls("set-sink-input-mute")), 2)
        m.sync(False, self.table)
        self.assertEqual(self._streams(), {"3": False, "4": False, "5": False, "6": True, "8": False})
        self.assertIsNone(self._muted())
        self.assertFalse(m.active)
        m.sync(False, self.table)
        self.assertEqual(len(self._calls("-f json list")), 3)

    def test_release_leaves_reused_index_and_user_unmute_alone(self):
        write_json(self.box.state_dir / "muted.json", {"3": f"100:{START}", "7": "555:1", "9": f"201:{START}"})
        self.streams.write_text(json.dumps([
            stream(3, "Telegram Desktop", "telegram-desktop", 100, muted=True),
            stream(7, "Chromium", "chrome", 100, muted=True), stream(9, "Chromium", "chrome", 201),
        ]))
        m = hold.Mute()
        m.sync(False, self.table)
        self.assertEqual(self._streams(), {"3": False, "7": True, "9": False})
        self.assertEqual(self._calls("set-sink-input-mute"), ["set-sink-input-mute 3 0"])
        self.assertIsNone(self._muted())

    def test_pump_rescans_on_new_and_forgets_removed(self):
        self.streams.write_text(json.dumps([stream(3, "Telegram Desktop", "telegram-desktop", 100)]))
        m = hold.Mute()
        m.sync(True, self.table)
        m.tail.stop()
        m.tail.proc = subprocess.Popen(["cat"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.addCleanup(m.tail.stop)
        os.set_blocking(m.tail.proc.stdout.fileno(), False)
        self.streams.write_text(json.dumps([stream(3, "Telegram Desktop", "telegram-desktop", 100, muted=True),
                                            stream(4, "Chromium", "chrome", 201)]))
        m.tail.proc.stdin.write(b"Event 'change' on sink #1\nEvent 'new' on sink-input #4\n")
        m.tail.proc.stdin.flush()
        time.sleep(0.1)
        m.pump()
        self.assertEqual(self._streams(), {"3": True, "4": True})
        self.assertEqual(self._muted(), {"3": f"100:{START}", "4": f"201:{START}"})
        m.tail.proc.stdin.write(b"Event 'remove' on sink-input #3\n")
        m.tail.proc.stdin.close()
        time.sleep(0.1)
        m.pump()
        self.assertEqual(self._muted(), {"4": f"201:{START}"})
        m.release()
        self.assertEqual(self._calls("set-sink-input-mute"), ["set-sink-input-mute 3 1", "set-sink-input-mute 4 1",
                                                              "set-sink-input-mute 4 0"])

    def test_tail_reaps_an_exited_child_on_eof_instead_of_spinning(self):
        m = hold.Mute()
        m.active = True
        m.tail.proc = subprocess.Popen(["cat"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        os.set_blocking(m.tail.proc.stdout.fileno(), False)
        m.tail.proc.stdin.write(b"Event 'remove' on sink-input #1\n")
        m.tail.proc.stdin.close()
        with mock.patch.object(hold, "_log") as log:
            self.assertTrue(_wait(lambda: m.tail.proc.poll() is not None, 2))
            m.pump()
        self.assertIsNone(m.tail.proc)
        self.assertIsNone(m.fileno())
        self.assertGreater(m.tail.next_start, 0.0)
        self.assertEqual(log.call_args_list, [mock.call("pactl exited with 0; restarting in 1s")])
        (self.box.runtime / "pactl.fail").write_text("1")
        with mock.patch.object(hold, "_log"):
            m.scan()
        m.tick(now=m.tail.next_start + 1)
        self.assertIsNone(m.tail.proc, "subscribe must not start while pactl list fails")

    def test_missing_pactl_disables_once(self):
        m = hold.Mute()
        with mock.patch.object(hold.subprocess, "run", side_effect=FileNotFoundError("pactl")), \
                mock.patch.object(hold.subprocess, "Popen", side_effect=FileNotFoundError("pactl")), \
                mock.patch.object(hold, "_log") as log:
            m.sync(True, self.table)
            m.tick(now=1.0)
            m.sync(True, self.table)
            m.sync(False, self.table)
        self.assertTrue(m.missing)
        self.assertEqual(log.call_args_list, [mock.call("pactl missing; sound mute is off")])
        self.assertIsNone(m.tail.proc)
        m2 = hold.Mute()
        m2.active = True
        with mock.patch.object(hold.subprocess, "Popen", side_effect=FileNotFoundError("pactl")), \
                mock.patch.object(hold, "_log") as log:
            m2.tick(now=1.0)
            m2.tick(now=2.0)
        self.assertTrue(m2.missing)
        self.assertEqual(log.call_count, 1)

    def test_failing_pactl_logs_once_and_release_retries_from_tick(self):
        (self.box.runtime / "pactl.fail").write_text("1")
        write_json(self.box.state_dir / "muted.json", {"3": f"100:{START}"})
        self.streams.write_text(json.dumps([stream(3, "Telegram Desktop", "telegram-desktop", 100, muted=True)]))
        m = hold.Mute()
        with mock.patch.object(hold, "_log") as log:
            m.sync(True, self.table)
            m.sync(False, self.table, now=100.0)
            m.tick(now=100.0 + hold.RELEASE_RETRY - 0.5)
        self.assertEqual(log.call_count, 1)
        self.assertFalse(m.missing)
        self.assertEqual(self._muted(), {"3": f"100:{START}"})
        self.assertEqual(self._streams(), {"3": True})
        (self.box.runtime / "pactl.fail").unlink()
        m.tick(now=100.0 + hold.RELEASE_RETRY)
        self.assertEqual(self._streams(), {"3": False})
        self.assertIsNone(self._muted())

    def test_release_keeps_a_record_whose_unmute_failed_until_it_succeeds(self):
        write_json(self.box.state_dir / "muted.json", {"3": f"100:{START}", "5": f"201:{START}"})
        self.streams.write_text(json.dumps([stream(3, "Telegram Desktop", "telegram-desktop", 100, muted=True),
                                            stream(5, "Chromium", "chrome", 201, muted=True)]))
        os.environ["DS_PACTL_STUCK"] = "5"
        m = hold.Mute()
        with mock.patch.object(hold, "_log"):
            m.sync(False, self.table, now=50.0)
        self.assertEqual(self._streams(), {"3": False, "5": True})
        self.assertEqual(self._muted(), {"5": f"201:{START}"})
        os.environ.pop("DS_PACTL_STUCK")
        m.tick(now=50.0 + hold.RELEASE_RETRY)
        self.assertEqual(self._streams(), {"3": False, "5": False})
        self.assertIsNone(self._muted())
        self.assertEqual(self._calls("set-sink-input-mute"),
                         ["set-sink-input-mute 3 0", "set-sink-input-mute 5 0", "set-sink-input-mute 5 0"])


class MuteListenerTests(_Env):
    def setUp(self):
        super().setUp()
        rt = self.box.runtime
        self.hypr_state, self.sock2_path = rt / "hypr-state.json", rt / "s2.sock"
        os.environ.update({
            "DS_SHELL_LOG": str(rt / "shell.log"), "DS_SHELL_STATE": str(rt / "shell-state.json"),
            "DS_BUS_LOG": str(rt / "bus.log"), "DS_BUS_LINES": str(rt / "bus.lines"), "DS_BUS_EXIT": str(rt / "bus.exit"),
            "DS_HYPR_LOG": str(rt / "hypr.log"), "DS_HYPR_STATE": str(self.hypr_state),
            "DS_NOTIFY_LOG": str(rt / "notify.log"), "DS_NFT_LOG": str(rt / "nft.log"), "DS_SOCKET2": str(self.sock2_path),
            "GETENT_MAP": json.dumps({"example.com": ["203.0.113.10"], "www.example.com": ["203.0.113.10"]}),
            "DS_FEEDBACK_HTTP_PORT": "0", "DS_FEEDBACK_TLS_PORT": "0",
        })
        os.environ.pop("DS_SHELL_MISSING", None)
        for name, src in (("omarchy-shell", SHELL), ("busctl", BUSCTL), ("hyprctl", HYPRCTL),
                          ("getent", GETENT), ("sudo", SUDO), ("omarchy-notification-send", NOTIFY)):
            self.box.fake_bin(name, src)
        cfg = json.loads(json.dumps(DEFAULTS))
        cfg["list"], cfg["nudges"] = LIST, {"app_banner": False, "block_page": False}
        self.box.config_file.write_text(json.dumps(cfg), encoding="utf-8")
        self._workspace("1", 1)
        self.proc = None

    def tearDown(self):
        self._stop()
        super().tearDown()

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
        if self.proc is None:
            return ""
        if self.proc.poll() is None:
            self.proc.terminate()
        try:
            _, err = self.proc.communicate(timeout=6)
        except Exception:
            self.proc.kill()
            _, err = self.proc.communicate(timeout=2)
        self.proc = None
        return err or ""

    def _go(self, name, wid):
        self._workspace(name, wid)
        self.conn.sendall(f"workspacev2>>{wid},{name}\n".encode())

    def test_hold_transitions_mute_and_unmute_through_the_listener(self):
        self._start()
        self.assertTrue(_wait(lambda: "subscribe" in self._calls(), 5), self._calls())
        me = hold.identity(self.proc.pid)
        self.assertIsNotNone(me)
        self.streams.write_text(json.dumps([stream(3, "Telegram Desktop", "telegram-desktop", self.proc.pid),
                                            stream(4, "Chromium", "chrome", self.proc.pid)]))
        with self.events.open("a") as f:
            f.write("Event 'new' on sink-input #3\nEvent 'new' on sink-input #4\n")
        self.assertTrue(_wait(lambda: self._streams() == {"3": True, "4": False}, 5), self._streams())
        self.assertEqual(self._muted(), {"3": me})
        self._go("distraction", 5)
        self.assertTrue(_wait(lambda: self._streams() == {"3": False, "4": False}, 5), self._streams())
        self.assertTrue(_wait(lambda: self._muted() is None, 3))
        self.assertTrue(_wait(lambda: self.proc.poll() is None and all(
            (Path(f"/proc/{pid}/cmdline").read_bytes().find(b"subscribe") < 0) for pid in _kids(self.proc.pid)), 3))
        self._go("2", 2)
        self.assertTrue(_wait(lambda: self._streams() == {"3": True, "4": False}, 5), self._streams())
        self.assertEqual(self._muted(), {"3": me})
        err = self._stop()
        self.assertEqual(self._streams(), {"3": False, "4": False}, err)
        self.assertIsNone(self._muted())
        self.assertNotIn("pactl", err)


def _kids(pid):
    out = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            status = Path(f"/proc/{name}/status").read_text()
        except OSError:
            continue
        if f"\nPPid:\t{pid}\n" in status:
            out.append(int(name))
    return out


if __name__ == "__main__":
    unittest.main()
