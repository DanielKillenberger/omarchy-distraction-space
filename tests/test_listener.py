#!/usr/bin/env python3
"""Listener: flock, socket2 loop, net generations, reload, lock tick, hooks."""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds.config import DEFAULTS
from ds.state import write_json

HYPRCTL = r"""
import json, os, sys
from pathlib import Path
fail = os.environ.get("DS_HYPR_FAIL")
if fail and Path(fail).exists():
    sys.exit(1)
log = Path(os.environ["DS_HYPR_LOG"])
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
state_path = Path(os.environ.get("DS_HYPR_STATE", ""))
data = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
args = sys.argv[1:]
if args[:1] == ["-j"] and len(args) >= 2:
    key = args[1]
    print(json.dumps(data.get(key) or ([] if key == "clients" else {"id": 1, "name": "1"})))
    sys.exit(0)
if args[:1] == ["keyword"]:
    print("keyword can't work with non-legacy parsers. Use eval.")
    sys.exit(1)
if args[:1] == ["eval"] and (len(args) < 2 or args[1].startswith("-")):
    sys.stderr.write("usage: hyprctl [flags] <command> [args...|--help]\n")
    sys.exit(1)
if args[:1] in (["eval"], ["dispatch"]):
    sys.exit(0)
sys.exit(1)
"""

GETENT = r"""
import json, os, sys, time
from pathlib import Path
host = sys.argv[-1]
log = os.environ.get("GETENT_LOG")
if log:
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(host + "\n")
gate = os.environ.get("GETENT_GATE")
if gate:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not Path(gate).exists():
        time.sleep(0.02)
table = json.loads(os.environ.get("GETENT_MAP", "{}"))
entry = table.get(host)
if entry == "hang":
    time.sleep(3600)
    sys.exit(2)
if not entry:
    sys.exit(2)
for addr in entry:
    print(f"{addr} STREAM {host}")
"""

SUDO = r"""
import os, sys
from pathlib import Path
args = sys.argv[1:]
if args[:1] == ["-n"]:
    args = args[1:]
log = Path(os.environ["DS_NFT_LOG"])
body = sys.stdin.read()
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as f:
    f.write(" ".join(args) + "\n")
    f.write(body)
    f.write("\n--\n")
sys.exit(0)
"""

NOTIFY = r"""
import os, sys
from pathlib import Path
p = Path(os.environ["DS_NOTIFY_LOG"])
p.parent.mkdir(parents=True, exist_ok=True)
with p.open("a", encoding="utf-8") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
"""

HOOK = r"""
import os
from pathlib import Path
p = Path(os.environ["DS_HOOK_LOG"])
p.parent.mkdir(parents=True, exist_ok=True)
with p.open("a", encoding="utf-8") as f:
    f.write(os.environ.get("DS_EVENT", "") + "\n")
"""

_ENV_KEYS = (
    "DS_HYPR_LOG", "DS_NOTIFY_LOG", "DS_NFT_LOG", "GETENT_LOG", "DS_HOOK_LOG",
    "DS_HYPR_STATE", "DS_SOCKET2", "GETENT_MAP", "GETENT_GATE", "DS_HYPR_FAIL",
    "DS_FEEDBACK_HTTP_PORT", "DS_FEEDBACK_TLS_PORT",
)


def _iso(delta_s: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_s)).replace(
        microsecond=0
    ).isoformat()


def _wait(pred, timeout=6.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return False


def _children(pid):
    kids = []
    try:
        names = os.listdir("/proc")
    except OSError:
        return kids
    for name in names:
        if not name.isdigit():
            continue
        try:
            raw = Path(f"/proc/{name}/status").read_text(encoding="utf-8")
        except OSError:
            continue
        ppid = None
        for line in raw.splitlines():
            if line.startswith("PPid:"):
                ppid = int(line.split()[1])
                break
        if ppid != pid:
            continue
        try:
            cmd = Path(f"/proc/{name}/cmdline").read_bytes().replace(b"\x00", b" ").decode()
        except OSError:
            cmd = ""
        kids.append((int(name), cmd))
    return kids


class ListenerTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.hypr_log = self.box.runtime / "hypr.log"
        self.notify_log = self.box.runtime / "notify.log"
        self.nft_log = self.box.runtime / "nft.log"
        self.getent_log = self.box.runtime / "getent.log"
        self.hook_log = self.box.runtime / "hook.log"
        self.hypr_state = self.box.runtime / "hypr-state.json"
        self.sock2_path = self.box.runtime / "socket2.sock"
        self.gate = self.box.runtime / "getent.gate"
        self._orig_env = {k: os.environ.get(k) for k in _ENV_KEYS}
        os.environ.update({
            "DS_HYPR_LOG": str(self.hypr_log),
            "DS_NOTIFY_LOG": str(self.notify_log),
            "DS_NFT_LOG": str(self.nft_log),
            "GETENT_LOG": str(self.getent_log),
            "DS_HOOK_LOG": str(self.hook_log),
            "DS_HYPR_STATE": str(self.hypr_state),
            "DS_SOCKET2": str(self.sock2_path),
            "GETENT_MAP": json.dumps({"x.com": ["203.0.113.10"], "www.x.com": ["203.0.113.10"]}),
            "DS_FEEDBACK_HTTP_PORT": "0",
            "DS_FEEDBACK_TLS_PORT": "0",
        })
        os.environ.pop("GETENT_GATE", None)
        self.box.fake_bin("hyprctl", HYPRCTL)
        self.box.fake_bin("getent", GETENT)
        self.box.fake_bin("sudo", SUDO)
        self.box.fake_bin("omarchy-notification-send", NOTIFY)
        self.hook_py = self.box.bin / "ds-hook.py"
        self.hook_py.write_text("#!/usr/bin/env python3\n" + HOOK, encoding="utf-8")
        self.hook_py.chmod(0o755)
        self._workspace("1", 1)
        self.proc = None
        self.sock2 = None
        self.conn = None

    def tearDown(self):
        self._stop()
        if self.conn:
            try:
                self.conn.close()
            except OSError:
                pass
        if self.sock2:
            try:
                self.sock2.close()
            except OSError:
                pass
        try:
            self.sock2_path.unlink()
        except OSError:
            pass
        for k, v in self._orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _cfg(self, **over):
        cfg = json.loads(json.dumps(DEFAULTS))
        cfg["nudges"] = {"app_banner": False, "block_page": False}
        cfg["list"] = ["x.com"]
        cfg["hooks"] = {
            "lock": [],
            "unlock": [[sys.executable, str(self.hook_py)]],
            "enter": [[sys.executable, str(self.hook_py)]],
            "leave": [[sys.executable, str(self.hook_py)]],
        }
        for k, v in over.items():
            if k in cfg and isinstance(cfg[k], dict) and isinstance(v, dict):
                cfg[k] = {**cfg[k], **v}
            else:
                cfg[k] = v
        self.box.config_file.write_text(json.dumps(cfg) + "\n", encoding="utf-8")
        return cfg

    def _workspace(self, name, wid=1, clients=None):
        write_json(self.hypr_state, {
            "activeworkspace": {"id": wid, "name": name},
            "clients": clients or [],
            "workspaces": [
                {"id": 1, "name": "1", "windows": 1},
                {"id": 5, "name": "distraction", "windows": 0},
            ],
        })

    def _bind_sock2(self):
        try:
            self.sock2_path.unlink()
        except OSError:
            pass
        self.sock2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock2.bind(str(self.sock2_path))
        self.sock2.listen(1)
        self.sock2.settimeout(5)

    def _start(self, extra_env=None):
        self._bind_sock2()
        self.proc = self.box.popen("listen", extra_env=extra_env)
        self.conn, _ = self.sock2.accept()
        self.box.wait_file(self.box.runtime / "distraction-space.sock", timeout=5)
        self.assertIsNone(self.proc.poll(), self._err())

    def _err(self):
        if self.proc is None:
            return ""
        if self.proc.poll() is None:
            return "listener still running"
        out, err = self.proc.communicate(timeout=2)
        return f"rc={self.proc.returncode} stdout={out!r} stderr={err!r}"

    def _stop(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=4)
            except Exception:
                self.proc.kill()
                self.proc.wait(timeout=2)
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass
        self.proc = None

    def _send(self, line):
        self.conn.sendall((line if line.endswith("\n") else line + "\n").encode())

    def _reload(self, verb="reload", timeout=16):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            sock.connect(str(self.box.runtime / "distraction-space.sock"))
            sock.sendall((verb + "\n").encode())
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(64)
                if not chunk:
                    break
                buf += chunk
            return buf.split(b"\n", 1)[0]
        finally:
            sock.close()

    def _reload_sock(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(str(self.box.runtime / "distraction-space.sock"))
        return sock

    def _state(self):
        path = self.box.state_dir / "state.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _nft(self):
        if not self.nft_log.exists():
            return ""
        return self.nft_log.read_text(encoding="utf-8")

    def _nft_cmds(self):
        text = self._nft()
        cmds = []
        for block in text.split("\n--\n"):
            line = block.strip().splitlines()
            if line:
                cmds.append(line[0])
        return cmds

    def _hooks(self):
        if not self.hook_log.exists():
            return []
        return [ln for ln in self.hook_log.read_text(encoding="utf-8").splitlines() if ln]

    def _getent_hosts(self):
        if not self.getent_log.exists():
            return []
        return [ln for ln in self.getent_log.read_text(encoding="utf-8").splitlines() if ln]

    def _wait_nft(self, needle, timeout=6.0):
        self.assertTrue(_wait(lambda: needle in self._nft(), timeout), f"missing {needle!r} in {self._nft()!r}")

    def test_second_listen_exits_silently(self):
        self._cfg()
        self._start()
        r = self.box.run("listen", timeout=3)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr, "")
        self.assertIsNone(self.proc.poll())

    def test_reload_without_listener_notifies_and_exits_1(self):
        r = self.box.run("reload", timeout=3)
        self.assertEqual(r.returncode, 1, r.stderr)
        text = self.notify_log.read_text(encoding="utf-8") if self.notify_log.exists() else ""
        self.assertIn("No listener running", text)

    def test_workspace_off_space_replace_enter_flush_state(self):
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on", 4), self._state())
        st = self._state()
        self.assertIsNotNone(st)
        self.assertFalse(st["on_space"])
        self.assertEqual(st["site_block"], "on")
        self.assertEqual(st["listener_pid"], self.proc.pid)
        self._workspace("2", 2)
        self._send("workspacev2>>2,2")
        self.assertTrue(_wait(lambda: self._nft().count("replace ds") >= 2, 6))
        self._workspace("distraction", 5)
        self._send("workspacev2>>5,distraction")
        self._wait_nft("flush ds")
        self.assertTrue(_wait(lambda: (self._state() or {}).get("on_space") is True
                              and (self._state() or {}).get("site_block") == "off", 4),
                        self._state())
        st = self._state()
        self.assertEqual(st["site_block"], "off")
        self.assertTrue(st["on_space"])

    def test_stale_generation_dropped(self):
        os.environ["GETENT_GATE"] = str(self.gate)
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: bool(self._getent_hosts()), 4))
        first = list(self._getent_hosts())
        self._workspace("2", 2)
        self._send("workspacev2>>2,2")
        time.sleep(0.15)
        self.gate.write_text("1", encoding="utf-8")
        self.assertTrue(_wait(lambda: len(self._getent_hosts()) >= len(first) * 2, 6))
        self.assertTrue(_wait(lambda: "replace ds" in self._nft(), 6))
        self.assertEqual(self._nft().count("replace ds"), 1)

    def test_entered_space_result_dropped(self):
        os.environ["GETENT_GATE"] = str(self.gate)
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: bool(self._getent_hosts()), 4))
        self._workspace("distraction", 5)
        self._send("workspacev2>>5,distraction")
        self._wait_nft("flush ds")
        self.gate.write_text("1", encoding="utf-8")
        time.sleep(0.8)
        self.assertNotIn("replace ds", self._nft())

    def test_overlapping_requests_coalesce(self):
        os.environ["GETENT_GATE"] = str(self.gate)
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: bool(self._getent_hosts()), 4))
        n0 = len(self._getent_hosts())
        self._workspace("2", 2)
        self._send("workspacev2>>2,2")
        time.sleep(0.05)
        self._workspace("3", 3)
        self._send("workspacev2>>3,3")
        time.sleep(0.1)
        self.gate.write_text("1", encoding="utf-8")
        self.assertTrue(_wait(lambda: len(self._getent_hosts()) >= n0 * 2, 6))
        time.sleep(0.6)
        n = len(self._getent_hosts())
        self.assertEqual(n, n0 * 2, self._getent_hosts())
        self.assertEqual(self._nft().count("replace ds"), 1)

    def test_corrupt_config_uses_expansion_cache(self):
        cached = {
            "list": [{"name": "Cached", "classes": ["^CachedClass$"], "hosts": ["cached.example"],
                      "senders": [], "audio": {}}],
            "keep_reachable": [],
            "nudges": {"app_banner": False, "block_page": False},
        }
        write_json(self.box.state_dir / "expansion.json", cached)
        before = (self.box.state_dir / "expansion.json").read_bytes()
        self.box.config_file.write_text("{not json", encoding="utf-8")
        os.environ["GETENT_MAP"] = json.dumps({"cached.example": ["198.51.100.9"]})
        self._start()
        self.assertTrue(_wait(lambda: self.hypr_log.exists() and "CachedClass" in self.hypr_log.read_text(), 4))
        self.assertEqual((self.box.state_dir / "expansion.json").read_bytes(), before)
        self._wait_nft("replace ds")
        self.assertIn("198.51.100.9", self._nft())

    def test_reload_invalid_config_error_unchanged(self):
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        exp_before = (self.box.state_dir / "expansion.json").read_bytes()
        nft_before = self._nft()
        self.box.config_file.write_text("{not json", encoding="utf-8")
        self.assertEqual(self._reload("reload"), b"error")
        self.assertEqual((self.box.state_dir / "expansion.json").read_bytes(), exp_before)
        time.sleep(0.2)
        self.assertEqual(self._nft(), nft_before)

    def test_successful_load_rewrites_expansion(self):
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: (self.box.state_dir / "expansion.json").exists(), 4))
        first = json.loads((self.box.state_dir / "expansion.json").read_text(encoding="utf-8"))
        self.assertTrue(any("x.com" in (e.get("hosts") or []) for e in first.get("list") or []))
        self._cfg(list=["youtube.com"])
        os.environ["GETENT_MAP"] = json.dumps({
            "youtube.com": ["203.0.113.20"], "www.youtube.com": ["203.0.113.20"],
        })
        self.assertEqual(self._reload("reload"), b"ok")
        self.assertTrue(_wait(lambda: any(
            "youtube.com" in (e.get("hosts") or [])
            for e in json.loads((self.box.state_dir / "expansion.json").read_text()).get("list") or []
        ), 4))

    def test_sigterm_hanging_getent_exits_clean(self):
        os.environ["GETENT_MAP"] = json.dumps({"x.com": "hang", "www.x.com": "hang"})
        self._cfg()
        self._start()
        pid = self.proc.pid
        self.assertTrue(_wait(lambda: any("getent" in c[1] for c in _children(pid)), 4))
        t0 = time.monotonic()
        self.proc.send_signal(signal.SIGTERM)
        rc = self.proc.wait(timeout=3)
        elapsed = time.monotonic() - t0
        try:
            self.proc.stdout.close()
            self.proc.stderr.close()
        except OSError:
            pass
        self.proc = None
        self.assertEqual(rc, 0)
        self.assertLess(elapsed, 3.0)
        time.sleep(0.15)
        fake = str(self.box.bin / "getent")
        left = []
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                cmd = Path(f"/proc/{name}/cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="ignore")
            except OSError:
                continue
            if fake in cmd:
                left.append((name, cmd))
        self.assertEqual(left, [])

    def test_lock_expiry_writes_state_notifies_unlock_hook_once(self):
        self._cfg()
        write_json(self.box.state_dir / "lock.json", {
            "locked": True, "since": _iso(-120), "until": _iso(-1), "purpose": "deep work",
        })
        self._start()
        self.assertTrue(_wait(lambda: (self._state() or {}).get("locked") is False, 3))
        self.assertTrue(_wait(lambda: self.hook_log.exists() and self._hooks().count("unlock") == 1, 3))
        text = self.notify_log.read_text(encoding="utf-8") if self.notify_log.exists() else ""
        self.assertIn("Lock ended", text)
        time.sleep(1.2)
        self.assertEqual(self._hooks().count("unlock"), 1)

    def test_enter_leave_hooks_once(self):
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self._workspace("distraction", 5)
        self._send("workspacev2>>5,distraction")
        self.assertTrue(_wait(lambda: self._hooks().count("enter") == 1, 4), self._hooks())
        self._workspace("1", 1)
        self._send("workspacev2>>1,1")
        self.assertTrue(_wait(lambda: self._hooks().count("leave") == 1, 4), self._hooks())
        time.sleep(1.2)
        self.assertEqual(self._hooks().count("enter"), 1)
        self.assertEqual(self._hooks().count("leave"), 1)

    def test_reload_client_idle_and_overflow_does_not_block(self):
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        idle = self._reload_sock()
        overflow = self._reload_sock()
        try:
            overflow.sendall(b"x" * 300)

            def overflow_closed():
                try:
                    overflow.settimeout(0.2)
                    return overflow.recv(64) == b""
                except TimeoutError:
                    return False
                except (ConnectionResetError, BrokenPipeError, OSError):
                    return True

            self.assertTrue(_wait(overflow_closed, 2), "overflow client stayed open")
            self._workspace("distraction", 5)
            self._send("workspacev2>>5,distraction")
            self.assertTrue(_wait(lambda: self._hooks().count("enter") == 1, 1.8), self._hooks())
            self.assertIsNone(self.proc.poll())
        finally:
            idle.close()
            overflow.close()

    def test_reload_ok_after_apply(self):
        os.environ["GETENT_GATE"] = str(self.gate)
        self.gate.write_text("1", encoding="utf-8")
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        n_before = self._nft().count("replace ds")
        self.gate.unlink()
        got = []

        def go():
            got.append(self._reload("reload", timeout=16))

        t = threading.Thread(target=go, daemon=True)
        t.start()
        time.sleep(0.4)
        self.assertEqual(got, [])
        self.assertEqual(self._nft().count("replace ds"), n_before)
        self.gate.write_text("1", encoding="utf-8")
        t.join(timeout=12)
        self.assertEqual(got, [b"ok"])
        self.assertGreater(self._nft().count("replace ds"), n_before)

    def test_resolve_exception_keeps_enforcement(self):
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        nft_before = self._nft()
        addrs = self.box.state_dir / "addrs.json"
        addrs.unlink()
        addrs.mkdir()
        self._workspace("2", 2)
        self._send("workspacev2>>2,2")
        self.assertTrue(_wait(
            lambda: "Network update failed" in (
                self.notify_log.read_text(encoding="utf-8") if self.notify_log.exists() else ""
            ), 4
        ))
        self.assertEqual(self._nft(), nft_before)
        self.assertNotIn("flush ds", nft_before)
        text = self.notify_log.read_text(encoding="utf-8")
        self.assertEqual(text.count("Network update failed"), 1)
        self._workspace("3", 3)
        self._send("workspacev2>>3,3")
        time.sleep(0.6)
        self.assertEqual(self._nft(), nft_before)
        self.assertEqual(
            self.notify_log.read_text(encoding="utf-8").count("Network update failed"), 1
        )

    def test_batched_workspace_events_ordered(self):
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self.assertEqual(self._hooks(), [])
        self.conn.sendall(b"workspacev2>>5,distraction\nworkspacev2>>1,1\n")
        self.assertTrue(_wait(lambda: self._hooks()[:2] == ["enter", "leave"], 4), self._hooks())
        self.assertEqual(self._hooks().count("enter"), 1)
        self.assertEqual(self._hooks().count("leave"), 1)
        self.assertTrue(_wait(lambda: (self._state() or {}).get("on_space") is False, 3), self._state())

    def _evals(self, marker):
        if not self.hypr_log.exists():
            return []
        out = []
        for line in self.hypr_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            argv = json.loads(line)
            if argv[:1] == ["eval"] and marker in argv[1]:
                out.append(argv[1])
        return out

    def test_configreloaded_reapplies_rules_and_rescans(self):
        self._cfg(list=["Telegram", "x.com"])
        self._start()
        self._wait_nft("replace ds")
        self.assertTrue(_wait(lambda: len(self._evals("omarchy-ds set")) >= 1, 4))
        boot_sets = self._evals("omarchy-ds set")
        self.assertNotIn("keyword", self.hypr_log.read_text(encoding="utf-8"))
        self._workspace("1", 1, clients=[{
            "address": "0xbeef", "class": "org.telegram.desktop",
            "workspace": {"id": 1, "name": "1"},
        }])
        self.hypr_log.write_text("", encoding="utf-8")
        self._send("configreloaded>>")
        self.assertTrue(_wait(lambda: self._evals("omarchy-ds set") == boot_sets, 4), self._evals("omarchy-ds set"))
        self.assertTrue(_wait(lambda: "hl.dsp.window.move" in self.hypr_log.read_text(encoding="utf-8"), 4))
        self.assertIn("0xbeef", self.hypr_log.read_text(encoding="utf-8"))
        self.assertIsNone(self.proc.poll(), self._err())
        self.assertEqual(self._hooks(), [])

    def test_configreloaded_rule_failure_notifies_and_keeps_listener(self):
        fail = self.box.runtime / "hypr.fail"
        os.environ["DS_HYPR_FAIL"] = str(fail)  # the double fails while this file exists
        self._cfg(list=["Telegram", "x.com"])
        self._start()
        self._wait_nft("replace ds")
        self.assertTrue(_wait(lambda: len(self._evals("omarchy-ds set")) >= 1, 4))
        boot_sets = self._evals("omarchy-ds set")
        fail.write_text("", encoding="utf-8")
        self.hypr_log.write_text("", encoding="utf-8")
        self._send("configreloaded>>")
        self.assertTrue(
            _wait(lambda: self.notify_log.exists() and "Window rules could not be updated" in self.notify_log.read_text(encoding="utf-8"), 4),
            self.notify_log.read_text(encoding="utf-8") if self.notify_log.exists() else "",
        )
        self.assertIsNone(self.proc.poll(), self._err())
        fail.unlink()
        self._send("configreloaded>>")
        self.assertTrue(_wait(lambda: self._evals("omarchy-ds set") == boot_sets, 4), self._evals("omarchy-ds set"))
        self.assertIsNone(self.proc.poll(), self._err())

    def test_reload_preserves_transition_baseline(self):
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self.assertEqual(self._hooks(), [])
        self._workspace("distraction", 5)
        self.assertEqual(self._reload("reload"), b"ok")
        self.assertTrue(_wait(lambda: self._hooks().count("enter") == 1, 3), self._hooks())
        self.assertEqual(self._hooks().count("leave"), 0)
        self.assertTrue(_wait(lambda: (self._state() or {}).get("on_space") is True, 3), self._state())

    def test_on_space_none_skips_transition(self):
        fail = self.box.runtime / "hypr.fail"
        os.environ["DS_HYPR_FAIL"] = str(fail)
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self._workspace("distraction", 5)
        self._send("workspacev2>>5,distraction")
        self.assertTrue(_wait(lambda: self._hooks().count("enter") == 1, 4), self._hooks())
        fail.write_text("1", encoding="utf-8")
        self.assertEqual(self._reload("reload"), b"ok")
        time.sleep(0.3)
        self.assertEqual(self._hooks().count("leave"), 0)
        fail.unlink()
        self.assertEqual(self._reload("reload"), b"ok")
        time.sleep(0.3)
        self.assertEqual(self._hooks().count("enter"), 1)
        self.assertEqual(self._hooks().count("leave"), 0)

    def test_stale_socket_and_invalid_config_notices(self):
        path = self.box.runtime / "distraction-space.sock"
        leftover = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        leftover.bind(str(path))
        leftover.close()
        r = self.box.run("reload", timeout=3)
        self.assertEqual(r.returncode, 1, r.stderr)
        text = self.notify_log.read_text(encoding="utf-8") if self.notify_log.exists() else ""
        self.assertIn("No listener running", text)
        try:
            path.unlink()
        except OSError:
            pass
        if self.notify_log.exists():
            self.notify_log.write_text("", encoding="utf-8")
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self.box.config_file.write_text("{not json", encoding="utf-8")
        r = self.box.run("reload", timeout=16)
        self.assertEqual(r.returncode, 1, r.stderr)
        text = self.notify_log.read_text(encoding="utf-8") if self.notify_log.exists() else ""
        self.assertIn("Invalid config", text)
        self.assertEqual(text.count("Invalid config"), 1)
        self.assertIn("Reload failed", text)
        r = self.box.run("reload", timeout=16)
        self.assertEqual(r.returncode, 1, r.stderr)
        text = self.notify_log.read_text(encoding="utf-8")
        self.assertEqual(text.count("Invalid config"), 1)
        self.assertGreaterEqual(text.count("Reload failed"), 2)

    def test_tick_reconciles_lock_and_missed_workspace(self):
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self.assertTrue(_wait(lambda: (self._state() or {}).get("on_space") is False, 4), self._state())
        self.conn.close()
        self.conn = None
        self.sock2.close()
        self.sock2 = None
        try:
            self.sock2_path.unlink()
        except OSError:
            pass
        self._workspace("distraction", 5)
        self.assertTrue(_wait(lambda: self._hooks().count("enter") == 1, 3), self._hooks())
        self.assertTrue(_wait(
            lambda: (self._state() or {}).get("on_space") is True
            and (self._state() or {}).get("site_block") == "off",
            3,
        ), self._state())
        self.assertFalse((self._state() or {}).get("locked"))
        r = self.box.run("lock", "25", "deep", "work")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(_wait(lambda: (self._state() or {}).get("locked") is True, 3), self._state())
        st = self._state()
        self.assertEqual(st["purpose"], "deep work")
        self.assertTrue(st["on_space"])
        self.assertEqual(st["site_block"], "off")

    def test_coalesced_reload_waiters_complete_together(self):
        os.environ["GETENT_GATE"] = str(self.gate)
        self.gate.write_text("1", encoding="utf-8")
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        n_before = self._nft().count("replace ds")
        self.gate.unlink()
        got = []

        def go():
            got.append(self._reload("reload", timeout=16))

        t1 = threading.Thread(target=go, daemon=True)
        t2 = threading.Thread(target=go, daemon=True)
        t1.start()
        time.sleep(0.3)
        t2.start()
        time.sleep(0.4)
        self.assertEqual(got, [])
        self.assertEqual(self._nft().count("replace ds"), n_before)
        self.gate.write_text("1", encoding="utf-8")
        t1.join(timeout=12)
        t2.join(timeout=12)
        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertEqual(sorted(got), [b"ok", b"ok"])
        self.assertGreater(self._nft().count("replace ds"), n_before)

    def test_adopted_waiter_survives_two_deadline_batches(self):
        bd = 0.8
        os.environ["GETENT_GATE"] = str(self.gate)
        self._cfg()
        self._start(extra_env=self.box.batch_deadline_env(bd))
        self.assertTrue(_wait(lambda: bool(self._getent_hosts()), 4))
        got = []

        def go():
            got.append(self._reload("reload", timeout=2 * bd + 6))

        t = threading.Thread(target=go, daemon=True)
        t.start()
        time.sleep(0.15)
        self.assertEqual(got, [])
        self._workspace("2", 2)
        self._send("workspacev2>>2,2")
        t.join(timeout=2 * bd + 8)
        self.assertFalse(t.is_alive())
        self.assertEqual(got, [b"ok"])


if __name__ == "__main__":
    unittest.main()
