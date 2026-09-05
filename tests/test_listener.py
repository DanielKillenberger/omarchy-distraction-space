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
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox
from test_cgroup import SESSION_PATH, SLICE_PATH, FakeProc
from test_hypr import OPEN

sys.path.insert(0, str(ROOT))
from ds import feedback, hypr, listener, setup
from ds.catalog import expand_entry
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
# A refusal from the wrapper, toggled by a file so a test can flip it mid-run.
if os.path.exists(os.environ.get("DS_NFT_FAIL_FILE", "")):
    sys.stderr.write("refused: slice cgroup missing\n")
    sys.exit(1)
if "check" in args:
    print('{"dev":1,"ino":2}')
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

# Quiet stand-ins so no listener test reaches the real shell IPC, bus monitor, or PulseAudio.
SHELL_STUB = r"""
import sys
args = sys.argv[1:]
if args[:2] == ["notifications", "silencedSenders"]:
    print("[]")
elif args[:2] in (["notifications", "silence"], ["notifications", "unsilence"]) and len(args) == 3:
    print("[]")
else:
    print("Function not found.")
    sys.exit(1)
"""

QUIET_STUB = r"""
import os, sys, time
args = sys.argv[1:]
if args == ["-f", "json", "list", "sink-inputs"]:
    print("[]")
elif args[:1] == ["set-sink-input-mute"]:
    pass
else:
    while os.getppid() != 1:
        time.sleep(0.5)
"""

# The listener starts the slice before every wrapper call; the real user manager stays out of it.
SYSTEMCTL = r"""
import os, sys
from pathlib import Path
Path(os.environ["DS_SYSTEMCTL_LOG"]).open("a").write(" ".join(sys.argv[1:]) + "\n")
"""

# The default browser is one file the test rewrites between ticks. Never the real xdg-settings.
XDG_SETTINGS = r"""
import os, sys
from pathlib import Path
args = sys.argv[1:]
Path(os.environ["DS_XDG_LOG"]).open("a").write(" ".join(args) + "\n")
if args == ["get", "default-web-browser"]:
    print(Path(os.environ["DS_XDG_DEFAULT"]).read_text().strip())
    sys.exit(0)
sys.exit(1)
"""

# The entry sync refreshes the desktop cache after a write; the real tool stays out of the sandbox.
UPDATE_DESKTOP_DATABASE = r"""
import os, sys
from pathlib import Path
Path(os.environ["DS_UDD_LOG"]).open("a").write(" ".join(sys.argv[1:]) + "\n")
"""

OMARCHY_BASECAMP = (
    "[Desktop Entry]\nVersion=1.0\nName=Basecamp\nExec=omarchy-launch-webapp https://launchpad.37signals.com\n"
    "Terminal=false\nType=Application\nIcon=basecamp\nStartupNotify=true\n"
)

_ENV_KEYS = (
    "DS_HYPR_LOG", "DS_NOTIFY_LOG", "DS_NFT_LOG", "GETENT_LOG", "DS_HOOK_LOG",
    "DS_HYPR_STATE", "DS_SOCKET2", "GETENT_MAP", "GETENT_GATE", "DS_HYPR_FAIL",
    "DS_FEEDBACK_HTTP_PORT", "DS_FEEDBACK_TLS_PORT", "DS_SYSTEMCTL_LOG",
    "XDG_DATA_HOME", "XDG_DATA_DIRS", "DS_XDG_DEFAULT", "DS_XDG_LOG", "DS_UDD_LOG",
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
        self.systemctl_log = self.box.runtime / "systemctl.log"
        self.sock2_path = self.box.runtime / "socket2.sock"
        self.gate = self.box.runtime / "getent.gate"
        # The harness pins XDG_DATA_HOME to the sandbox's data directory for the listener
        # process; the entries manifest and the files the entry sync writes live under it.
        self.apps = self.box.data / "applications"
        self.xdg_default = self.box.runtime / "xdg-default"
        self.xdg_default.write_text("google-chrome.desktop\n", encoding="utf-8")
        self.xdg_log = self.box.runtime / "xdg.log"
        self.udd_log = self.box.runtime / "udd.log"
        self._orig_env = {k: os.environ.get(k) for k in _ENV_KEYS}
        os.environ.update({
            # No system desktop files either: the browser pick must not find the
            # developer's real Chrome under /usr/share.
            "XDG_DATA_DIRS": str(self.box.runtime / "share"),
            "DS_XDG_DEFAULT": str(self.xdg_default),
            "DS_XDG_LOG": str(self.xdg_log),
            "DS_UDD_LOG": str(self.udd_log),
            "DS_HYPR_LOG": str(self.hypr_log),
            "DS_NOTIFY_LOG": str(self.notify_log),
            "DS_NFT_LOG": str(self.nft_log),
            "GETENT_LOG": str(self.getent_log),
            "DS_HOOK_LOG": str(self.hook_log),
            "DS_HYPR_STATE": str(self.hypr_state),
            "DS_SYSTEMCTL_LOG": str(self.systemctl_log),
            "DS_NFT_FAIL_FILE": str(self.box.runtime / "nft.fail"),
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
        self.box.fake_bin("omarchy-shell", SHELL_STUB)
        self.box.fake_bin("busctl", QUIET_STUB)
        self.box.fake_bin("pactl", QUIET_STUB)
        self.box.fake_bin("systemctl", SYSTEMCTL)
        self.box.fake_bin("xdg-settings", XDG_SETTINGS)
        self.box.fake_bin("update-desktop-database", UPDATE_DESKTOP_DATABASE)
        self.hook_py = self.box.bin / "ds-hook.py"
        self.hook_py.write_text("#!/usr/bin/env python3\n" + HOOK, encoding="utf-8")
        self.hook_py.chmod(0o755)
        self._workspace("1", 1)
        self.proc = None
        self.sock2 = None
        self.conn = None
        self.fired = []

    def tearDown(self):
        self._stop()
        for sock in self.fired:
            try:
                sock.close()
            except OSError:
                pass
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

    def _workspace(self, name, wid=1, clients=None, active=None):
        write_json(self.hypr_state, {
            "activeworkspace": {"id": wid, "name": name},
            "activewindow": active or {},
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

    def _fire(self, verb):
        """Send a verb and leave the reply unread: the request lands, the caller does not wait."""
        sock = self._reload_sock()
        sock.sendall((verb + "\n").encode())
        self.fired.append(sock)

    def _period_env(self, seconds):
        site = self.box.runtime / "pysite"
        site.mkdir(exist_ok=True)
        (site / "sitecustomize.py").write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "from ds import listener\n"
            f"listener.PERIOD = {float(seconds)!r}\n",
            encoding="utf-8",
        )
        return {"PYTHONPATH": str(site)}

    def _systemctl_lines(self):
        if not self.systemctl_log.exists():
            return []
        return [ln for ln in self.systemctl_log.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _register_handler(self):
        """What `distractions setup` leaves behind: the handler file, its manifest line, and the default set to it."""
        handler = self.apps / setup.HANDLER_ID
        handler.parent.mkdir(parents=True, exist_ok=True)
        handler.write_text(setup._render_handler(), encoding="utf-8")
        write_json(self.box.state_dir / "entries.json", {
            "files": [{"path": str(handler), "backup": None}],
            "previous_handler": "google-chrome.desktop",
        })
        self.xdg_default.write_text(setup.HANDLER_ID + "\n", encoding="utf-8")

    def _xdg_sets(self):
        return [ln for ln in self._xdg_lines() if ln.startswith("set ")]

    def _assert_links_never_asks(self):
        """The browser pick reads the default once per start; the link check must add nothing per tick."""
        self.assertTrue(_wait(lambda: "links" in (self._state() or {}).get("observed_at", {})))
        n = len(self._xdg_lines())
        time.sleep(2.2)
        self.assertEqual(len(self._xdg_lines()), n)
        self.assertEqual(self._xdg_sets(), [])

    def _xdg_lines(self):
        if not self.xdg_log.exists():
            return []
        return [ln for ln in self.xdg_log.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _udd_lines(self):
        if not self.udd_log.exists():
            return []
        return [ln for ln in self.udd_log.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _entries(self):
        path = self.box.state_dir / "entries.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _notices(self, needle):
        if not self.notify_log.exists():
            return []
        return [ln for ln in self.notify_log.read_text(encoding="utf-8").splitlines() if needle in ln]

    def _links(self):
        st = self._state()
        return st.get("links") if st else None

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
        """The wrapper verbs in call order: `replace ds` / `check ds` / `flush ds`."""
        cmds = []
        for block in self._nft().split("\n--\n"):
            line = block.strip().splitlines()
            if line:
                cmds.append(" ".join(line[0].split()[-2:]))
        return cmds

    def _hooks(self):
        if not self.hook_log.exists():
            return []
        return [ln for ln in self.hook_log.read_text(encoding="utf-8").splitlines() if ln]

    def _dispatches(self):
        if not self.hypr_log.exists():
            return []
        out = []
        for line in self.hypr_log.read_text(encoding="utf-8").splitlines():
            argv = json.loads(line) if line.strip() else []
            if argv[:1] == ["dispatch"]:
                out.append(argv[1])
        return out

    def _released(self):
        return (self._state() or {}).get("released")

    def _getent_hosts(self):
        if not self.getent_log.exists():
            return []
        return [ln for ln in self.getent_log.read_text(encoding="utf-8").splitlines() if ln]

    def _wait_nft(self, needle, timeout=6.0):
        self.assertTrue(_wait(lambda: needle in self._nft(), timeout), f"missing {needle!r} in {self._nft()!r}")

    def _assert_reconciliation_stall(self, tool, body):
        self._cfg(list=["x.com", "Telegram"])
        self._register_handler()
        self._start()
        self._wait_nft("replace ds")
        self.assertTrue(_wait(lambda: len((self._state() or {}).get("observed_at", {})) == 3))
        self.assertTrue(self._state()["hold"], "hold starts active before the stalled transition")
        started = self.box.runtime / "side-effect.started"
        gate = self.box.runtime / "side-effect.gate"
        self.box.fake_bin(tool, f"""
import os, time
from pathlib import Path
with Path({str(started)!r}).open("a") as log:
    print(os.getpid(), file=log)
while not Path({str(gate)!r}).exists():
    time.sleep(0.02)
""" + body)
        # A changed owned entry ensures refresh reaches the desktop cache.
        (self.apps / "Telegram.desktop").write_text("[Desktop Entry]\nName=drift\n")
        self._fire("refresh")
        self.assertTrue(_wait(started.exists), "worker command did not start")
        self._fire("refresh")
        self._fire("refresh")
        write_json(self.box.state_dir / "lock.json", {
            "locked": True, "since": _iso(-120), "until": _iso(-1), "purpose": "deadline",
        })
        client = {"address": "0xabc", "class": "org.telegram.desktop", "pid": 999999,
                  "workspace": {"id": 1, "name": "1"}}
        self._workspace("distraction", 5, clients=[client])
        self._send("workspacev2>>5,distraction")
        self._send("openwindow>>abc,1,org.telegram.desktop,Telegram")
        try:
            self.assertEqual(self._reload("ping", timeout=1), b"ok")
            self.assertTrue(_wait(lambda: any("0xabc" in d for d in self._dispatches()), 2))
            self.assertTrue(_wait(lambda: self._hooks().count("unlock") == 1, 2))
            self.assertFalse(self._state()["hold"])
            self.assertFalse(self._state()["locked"])
            self.assertEqual(len(started.read_text().splitlines()), 1)
            self.fired[-1].settimeout(0.1)
            with self.assertRaises(TimeoutError):
                self.fired[-1].recv(64)
        finally:
            gate.touch()
        for sock in self.fired:
            sock.settimeout(8)
            self.assertEqual(sock.recv(64), b"ok\n")
        if tool == "sudo":
            self.assertEqual(len(started.read_text().splitlines()), 3)
        else:
            self.assertLessEqual(len(started.read_text().splitlines()), 2)
        self.assertEqual(set(self._state()["observed_at"]),
                         {"site_block", "notification_hold", "links"})

    def test_stalled_firewall_keeps_events_hold_and_deadline_live(self):
        self._assert_reconciliation_stall("sudo", SUDO)

    def test_stalled_slice_keeps_events_hold_and_deadline_live(self):
        self._assert_reconciliation_stall("systemctl", SYSTEMCTL)

    def test_stalled_cache_keeps_events_hold_and_deadline_live(self):
        self._assert_reconciliation_stall("update-desktop-database", UPDATE_DESKTOP_DATABASE)

    def test_stalled_link_check_keeps_events_hold_and_deadline_live(self):
        self._assert_reconciliation_stall("xdg-settings", XDG_SETTINGS)

    def test_disable_during_apply_orders_flush_and_rejects_obsolete_success(self):
        os.environ["GETENT_MAP"] = json.dumps({"x.com": ["203.0.113.10"],
            "www.x.com": ["203.0.113.10"], "youtube.com": ["203.0.113.20"],
            "www.youtube.com": ["203.0.113.20"]})
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on"))
        started, gate = self.box.runtime / "apply.started", self.box.runtime / "apply.gate"
        self.box.fake_bin("sudo", f"""
import sys, time
from pathlib import Path
if "replace" in sys.argv:
    Path({str(started)!r}).touch()
    while not Path({str(gate)!r}).exists():
        time.sleep(0.02)
""" + SUDO)
        self._cfg(list=["youtube.com"])
        self._fire("reload")
        self.assertTrue(_wait(started.exists))
        self._cfg(site_block={"enabled": False})
        self._fire("reload")
        self.assertEqual(self._reload("ping", timeout=1), b"ok")
        for sock in self.fired:
            sock.settimeout(0.1)
            with self.assertRaises(TimeoutError):
                sock.recv(64)
        gate.touch()
        for sock in self.fired:
            sock.settimeout(8)
            self.assertEqual(sock.recv(64), b"ok\n")
        self.assertEqual(self._nft_cmds()[-2:], ["replace ds", "flush ds"])
        self.assertEqual(self._state()["site_block"], "off")
        self.assertEqual(self._getent_hosts().count("x.com"), 1)
        self.assertEqual(self._getent_hosts().count("youtube.com"), 1)

    def test_equal_refresh_checks_and_advances_observation_without_replace(self):
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on"))
        observed = self._state()["observed_at"]["site_block"]
        for cycle in (2, 3):
            self.assertTrue(_wait(lambda: listener.state.now_iso() > observed, 2))
            self.assertEqual(self.box.run("refresh", timeout=16).returncode, 0)
            self.assertEqual(self._nft_cmds(), ["replace ds"] + ["check ds"] * cycle)
            latest = self._state()["observed_at"]["site_block"]
            self.assertGreater(latest, observed)
            observed = latest

    def test_disable_during_check_never_repairs_or_acknowledges_stale_policy(self):
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on"))
        started, gate = self.box.runtime / "check.started", self.box.runtime / "check.gate"
        self.box.fake_bin("sudo", f"""
import sys, time
from pathlib import Path
if "check" in sys.argv:
    Path({str(started)!r}).touch()
    while not Path({str(gate)!r}).exists():
        time.sleep(0.02)
""" + SUDO)
        self._fire("refresh")
        self.assertTrue(_wait(started.exists))
        self._cfg(site_block={"enabled": False})
        self._fire("reload")
        self.assertEqual(self._reload("ping", timeout=1), b"ok")
        for sock in self.fired:
            sock.settimeout(0.1)
            with self.assertRaises(TimeoutError):
                sock.recv(64)
        gate.touch()
        for sock in self.fired:
            sock.settimeout(8)
            self.assertEqual(sock.recv(64), b"ok\n")
        self.assertEqual(self._nft_cmds(), ["replace ds", "check ds", "check ds", "flush ds"])
        self.assertEqual(self._state()["site_block"], "off")

    def test_unverifiable_check_reports_error_then_replaces_on_recovery(self):
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on"))
        bad = self.box.runtime / "bad.check"
        bad.touch()
        self.box.fake_bin("sudo", f"""
import sys
from pathlib import Path
if "check" in sys.argv and Path({str(bad)!r}).exists():
    print("old wrapper output")
    sys.exit(0)
""" + SUDO)
        self.assertEqual(self.box.run("refresh", timeout=16).returncode, 1)
        self.assertEqual(self._state()["site_block"], "unavailable")
        self.assertEqual(self._nft_cmds().count("replace ds"), 2)
        bad.unlink()
        self.assertEqual(self.box.run("refresh", timeout=16).returncode, 0)
        self.assertEqual(self._state()["site_block"], "on")
        self.assertEqual(self._nft_cmds()[-2:], ["replace ds", "check ds"])
        self.assertEqual(self._nft_cmds().count("replace ds"), 3)

    def _assert_shutdown_stall(self, tool):
        self._cfg()
        started = self.box.runtime / "apply.pid"
        self.box.fake_bin(tool, f"""
import os, time
from pathlib import Path
Path({str(started)!r}).write_text(str(os.getpid()))
time.sleep(3600)
""")
        self._start()
        self.assertTrue(_wait(started.exists))
        pid = int(started.read_text())
        self.addCleanup(lambda: os.kill(pid, signal.SIGKILL) if Path(f"/proc/{pid}").exists() else None)
        self.proc.send_signal(signal.SIGTERM)
        self.assertEqual(self.proc.wait(timeout=4), 0)
        self.assertFalse(Path(f"/proc/{pid}").exists())

    def test_shutdown_cancels_and_reaps_stalled_side_effect(self):
        self._assert_shutdown_stall("sudo")

    def test_shutdown_cancels_and_reaps_browser_lookup(self):
        self._assert_shutdown_stall("xdg-settings")

    def test_entries_lock_defers_without_failure_and_recovers(self):
        self._cfg()
        self._register_handler()
        self._start(extra_env=self._period_env(1))
        self.assertTrue(_wait(lambda: len((self._state() or {}).get("observed_at", {})) == 3))
        with setup._entries_lock(0) as held:
            self.assertTrue(held)
            for _ in range(2):
                self.assertEqual(self._reload("refresh"), b"deferred")
                self.assertEqual(self._state()["launcher_refresh"], "deferred")
            response = self.box.run("refresh", timeout=5)
            self.assertEqual(response.returncode, 1)
            self.assertEqual(self._notices("Refresh failed"), [])
            self.assertEqual(self._notices("Launcher refresh failed"), [])
            self.assertTrue(self._notices("Refresh deferred"))
        self.assertEqual(self._reload("refresh"), b"ok")
        self.assertEqual(self._state()["launcher_refresh"], "ok")

    def test_launcher_failure_notice_once_per_failure_streak(self):
        self._cfg()
        self._register_handler()
        self._start()
        self.assertTrue(_wait(lambda: len((self._state() or {}).get("observed_at", {})) == 3))
        fail = "import sys; sys.exit(1)"
        self.box.fake_bin("update-desktop-database", fail)
        for _ in range(2):
            self.assertEqual(self._reload("refresh"), b"error")
            self.assertEqual(self._state()["launcher_refresh"], "unavailable")
        self.assertEqual(len(self._notices("Launcher refresh failed")), 1)
        self.box.fake_bin("update-desktop-database", UPDATE_DESKTOP_DATABASE)
        self.assertEqual(self._reload("refresh"), b"ok")
        self.box.fake_bin("update-desktop-database", fail)
        (self.apps / "x.com.desktop").write_text("[Desktop Entry]\nName=drift\n")
        self.assertEqual(self._reload("refresh"), b"error")
        self.assertEqual(len(self._notices("Launcher refresh failed")), 2)

    def test_startup_does_not_claim_entry_refresh(self):
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: len((self._state() or {}).get("observed_at", {})) == 3))
        self.assertEqual(self._state()["launcher_refresh"], "off")

    def test_worker_command_timeouts_report_failure_then_recover(self):
        self._cfg()
        self._register_handler()
        env = self._period_env(60)
        site = self.box.runtime / "pysite" / "sitecustomize.py"
        with site.open("a") as out:
            out.write("from ds import net, cgroup, setup\n"
                      "net.COMMAND_TIMEOUT = cgroup.SYSTEMCTL_TIMEOUT = setup.UDD_TIMEOUT = 0.5\n")
        self._start(extra_env=env)
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on"))
        for tool, body in (("sudo", SUDO), ("systemctl", SYSTEMCTL),
                           ("update-desktop-database", UPDATE_DESKTOP_DATABASE)):
            with self.subTest(tool=tool):
                pidfile = self.box.runtime / (tool + ".pid")
                self.box.fake_bin(tool, f"""
import os, time
from pathlib import Path
Path({str(pidfile)!r}).write_text(str(os.getpid()))
time.sleep(3600)
""")
                (self.apps / "x.com.desktop").write_text("[Desktop Entry]\nName=drift\n")
                self.assertEqual(self._reload("refresh", timeout=5), b"error")
                self.assertFalse(Path(f"/proc/{pidfile.read_text()}").exists())
                field = "launcher_refresh" if tool == "update-desktop-database" else "site_block"
                self.assertEqual(self._state()[field], "unavailable")
                self.assertEqual(self._reload("ping", timeout=1), b"ok")
                self.box.fake_bin(tool, body)
                self.assertEqual(self._reload("refresh", timeout=5), b"ok")
                self.assertEqual(self._state()["site_block"], "on")

    def test_periodic_observations_advance_without_policy_changes(self):
        self._cfg()
        self._start(extra_env=self._period_env(1))
        self.assertTrue(_wait(lambda: len((self._state() or {}).get("observed_at", {})) == 3))
        before = self._state()["observed_at"]
        self.assertTrue(_wait(lambda: all(self._state()["observed_at"].get(key, "") > value
                                         for key, value in before.items()), 4))

    def test_links_displaced_on_a_later_tick_with_one_notice(self):
        self._cfg()
        self._register_handler()
        self._start(extra_env=self._period_env(1.0))
        self.assertTrue(_wait(lambda: self._links() == "on"), self._state())
        # Another browser takes the default behind the listener's back.
        self.xdg_default.write_text("google-chrome.desktop\n", encoding="utf-8")
        self.assertTrue(_wait(lambda: self._links() == "displaced", timeout=8.0), self._state())
        self.assertTrue(_wait(lambda: len(self._notices("distractions setup")) == 1))
        # Two more periods: still displaced, still the one notice.
        self.assertTrue(_wait(lambda: len(self._xdg_lines()) >= 4, timeout=8.0), self._xdg_lines())
        self.assertEqual(self._links(), "displaced")
        self.assertEqual(len(self._notices("distractions setup")), 1)

    def test_links_off_without_a_registered_handler_or_with_the_switch_off(self):
        # Nothing registered: the state says off and xdg-settings is never asked.
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: self._links() == "off"), self._state())
        self._assert_links_never_asks()
        self._stop()
        self.conn.close()
        self.sock2.close()
        # Registered, but the switch is off: the same answer, still no call.
        self._register_handler()
        self._cfg(open_links_in_space=False)
        self._start()
        self.assertTrue(_wait(lambda: self._links() == "off"), self._state())
        self._assert_links_never_asks()
        self.assertEqual(self._notices("distractions setup"), [])

    def test_refresh_and_the_tick_rewrite_a_regenerated_web_app_and_never_touch_the_default(self):
        self._cfg()
        basecamp = self.apps / "Basecamp.desktop"
        basecamp.parent.mkdir(parents=True, exist_ok=True)
        basecamp.write_text(OMARCHY_BASECAMP, encoding="utf-8")
        # Before setup has written its manifest the listener owns no entries and writes none.
        self._start(extra_env=self._period_env(1.0))
        time.sleep(2.2)
        self.assertEqual(basecamp.read_text(encoding="utf-8"), OMARCHY_BASECAMP)
        self.assertIsNone(self._entries())
        self.assertEqual(self._udd_lines(), [])
        self._stop()
        self.conn.close()
        self.sock2.close()
        # After setup: `refresh` rewrites the unlisted web app to forward, backs it up, records it.
        self._register_handler()
        self._start(extra_env=self._period_env(1.0))
        self.assertTrue(_wait(lambda: self._links() == "on"), self._state())
        r = self.box.run("refresh", timeout=16)
        self.assertEqual(r.returncode, 0, r.stderr)
        forward = OMARCHY_BASECAMP.replace("omarchy-launch-webapp", f"{ROOT / 'distractions'} open --app")
        self.assertEqual(basecamp.read_text(encoding="utf-8"), forward)
        backup = self.box.state_dir / "entries-backup" / "Basecamp.desktop"
        self.assertEqual(backup.read_text(encoding="utf-8"), OMARCHY_BASECAMP)
        entries = self._entries()
        self.assertIn({"path": str(basecamp), "backup": str(backup)}, entries["files"])
        self.assertIn({"path": str(self.apps / setup.HANDLER_ID), "backup": None}, entries["files"])
        self.assertEqual(entries["previous_handler"], "google-chrome.desktop")
        self.assertEqual(len(self._udd_lines()), 1)
        # Omarchy regenerates the entry: the next period rewrites it from the new file.
        regenerated = OMARCHY_BASECAMP.replace("Icon=basecamp", "Icon=basecamp-new")
        basecamp.write_text(regenerated, encoding="utf-8")
        self.assertTrue(_wait(lambda: basecamp.read_text(encoding="utf-8") == forward.replace("Icon=basecamp", "Icon=basecamp-new"), 6.0), basecamp.read_text(encoding="utf-8"))
        self.assertEqual(backup.read_text(encoding="utf-8"), regenerated)
        self.assertTrue(_wait(lambda: len(self._udd_lines()) == 2), self._udd_lines())
        # Nothing changed since: the following periods write nothing. The default browser is
        # never set from here, and the handler stays as recorded.
        time.sleep(2.2)
        self.assertEqual(len(self._udd_lines()), 2)
        self.assertEqual(self._xdg_sets(), [])
        self.assertEqual(self.xdg_default.read_text(encoding="utf-8").strip(), setup.HANDLER_ID)
        self.assertEqual(self._links(), "on")

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

    def test_enter_and_leave_touch_no_network(self):
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on", 4), self._state())
        st = self._state()
        self.assertFalse(st["on_space"])
        self.assertEqual(st["listener_pid"], self.proc.pid)
        self.assertEqual((st["links"], st["browser"], st["released"]), ("off", None, {}))
        self.assertEqual(self._systemctl_lines(), ["--user start app-distraction.slice"])
        nft_cmds, hosts = self._nft_cmds(), list(self._getent_hosts())
        self.assertEqual(nft_cmds, ["replace ds", "check ds"])
        self._workspace("2", 2)
        self._send("workspacev2>>2,2")
        self._workspace("distraction", 5)
        self._send("workspacev2>>5,distraction")
        self.assertTrue(_wait(lambda: self._hooks().count("enter") == 1, 4), self._hooks())
        self.assertTrue(_wait(lambda: (self._state() or {}).get("on_space") is True, 4), self._state())
        self.assertEqual(self._state()["site_block"], "on")
        self._workspace("1", 1)
        self._send("workspacev2>>1,1")
        self.assertTrue(_wait(lambda: self._hooks().count("leave") == 1, 4), self._hooks())
        time.sleep(1.2)
        self.assertEqual(self._nft_cmds(), nft_cmds)
        self.assertEqual(self._getent_hosts(), hosts)
        self.assertEqual(self._systemctl_lines(), ["--user start app-distraction.slice"])
        st = self._state()
        self.assertFalse(st["on_space"])
        self.assertEqual(st["site_block"], "on")

    def test_periodic_resolve_runs_on_the_space_with_the_slice_started_first(self):
        self._cfg()
        self._start(extra_env=self._period_env(1.0))
        self._wait_nft("replace ds")
        self._workspace("distraction", 5)
        self._send("workspacev2>>5,distraction")
        self.assertTrue(_wait(lambda: self._hooks().count("enter") == 1, 4), self._hooks())
        self.assertTrue(_wait(lambda: self._nft().count("check ds") >= 3, 6), self._nft_cmds())
        self.assertEqual(self._nft().count("replace ds"), 1)
        self.assertNotIn("flush ds", self._nft())
        self.assertTrue((self._state() or {}).get("on_space"))
        self.assertEqual(self._state()["site_block"], "on")
        checks = self._nft_cmds().count("check ds")
        self.assertEqual(self._systemctl_lines()[:checks], ["--user start app-distraction.slice"] * checks)

    def test_refresh_resolves_without_rereading_config(self):
        os.environ["GETENT_MAP"] = json.dumps({
            "x.com": ["203.0.113.10"], "www.x.com": ["203.0.113.10"],
            "youtube.com": ["203.0.113.20"], "www.youtube.com": ["203.0.113.20"],
        })
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        n_replace, n_hosts = self._nft().count("replace ds"), len(self._getent_hosts())
        self._cfg(list=["youtube.com"])
        r = self.box.run("refresh", timeout=16)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._nft().count("replace ds"), n_replace)
        self.assertEqual(self._nft().count("check ds"), 2)
        self.assertEqual(sorted(self._getent_hosts()[n_hosts:]), ["www.x.com", "x.com"])
        self.assertNotIn("203.0.113.20", self._nft())
        r = self.box.run("reload", timeout=16)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._nft().count("replace ds"), n_replace + 1)
        self.assertIn("youtube.com", self._getent_hosts())
        self.assertIn("203.0.113.20", self._nft())

    def test_state_names_the_browser_open_would_pick(self):
        self._cfg(browser=["/usr/bin/brave", "--foo"])
        self._start()
        self.assertTrue(_wait(lambda: (self._state() or {}).get("browser") == "brave", 4), self._state())
        self.assertEqual(json.loads(self.box.run("status", "--json").stdout)["browser"], "brave")
        # Reload follows a config change.
        self._cfg(browser=["chromium"])
        self.assertEqual(self.box.run("reload", timeout=16).returncode, 0)
        self.assertTrue(_wait(lambda: (self._state() or {}).get("browser") == "chromium", 4), self._state())

    def test_site_block_disabled_flushes_each_refresh_and_keeps_hold(self):
        self._cfg(site_block={"enabled": False, "pass_through": True})
        self._start()
        self._wait_nft("flush ds")
        self.assertTrue(_wait(lambda: (self._state() or {}).get("hold") is True, 4), self._state())
        time.sleep(1.2)
        self.assertEqual(self._nft_cmds(), ["flush ds"])
        self.assertEqual(self._getent_hosts(), [])
        self.assertEqual(self._systemctl_lines(), [])  # a flush needs no slice
        st = self._state()
        self.assertEqual(st["site_block"], "off")
        self.assertEqual(st["notification_hold"], "on")
        observed = self._state()["observed_at"]["site_block"]
        r = self.box.run("refresh", timeout=16)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._nft_cmds(), ["flush ds", "flush ds"])
        self.assertGreater(self._state()["observed_at"]["site_block"], observed)
        self.assertEqual(self._getent_hosts(), [])
        r = self.box.run("status", "--json")
        self.assertEqual(json.loads(r.stdout)["site_block"], "off")
        self._cfg()
        r = self.box.run("reload", timeout=16)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._nft_cmds(), ["flush ds", "flush ds", "replace ds", "check ds"])
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on", 4), self._state())

    def test_wrapper_refusal_replies_error_and_reports_unavailable(self):
        fail = self.box.runtime / "nft.fail"
        fail.write_text("1", encoding="utf-8")
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "unavailable", 4), self._state())
        # The wrapper refused, so the person asking hears error, not ok.
        r = self.box.run("refresh", timeout=16)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        r = self.box.run("reload", timeout=16)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        fail.unlink()
        r = self.box.run("refresh", timeout=16)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on", 4), self._state())

    def test_site_block_disabled_reports_a_refused_flush_and_retries_on_refresh(self):
        fail = self.box.runtime / "nft.fail"
        fail.write_text("1", encoding="utf-8")
        self._cfg(site_block={"enabled": False, "pass_through": True})
        self._start()
        self._wait_nft("flush ds")
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "unavailable", 4), self._state())
        r = self.box.run("reload", timeout=16)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        r = self.box.run("refresh", timeout=16)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        fail.unlink()
        r = self.box.run("refresh", timeout=16)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "off", 4), self._state())
        self.assertEqual(self._getent_hosts(), [])
        # Every off observation performs a fresh flush.
        n = self._nft_cmds().count("flush ds")
        self.assertEqual(self.box.run("refresh", timeout=16).returncode, 0)
        self.assertEqual(self._nft_cmds().count("flush ds"), n + 1)

    def test_stale_generation_dropped(self):
        os.environ["GETENT_GATE"] = str(self.gate)
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: bool(self._getent_hosts()), 4))
        first = list(self._getent_hosts())
        self._fire("refresh")
        time.sleep(0.15)
        self.gate.write_text("1", encoding="utf-8")
        self.assertTrue(_wait(lambda: len(self._getent_hosts()) >= len(first) * 2, 6))
        self.assertTrue(_wait(lambda: "replace ds" in self._nft(), 6))
        self.assertEqual(self._nft().count("replace ds"), 1)

    def test_entering_the_space_mid_batch_still_applies(self):
        os.environ["GETENT_GATE"] = str(self.gate)
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: bool(self._getent_hosts()), 4))
        self._workspace("distraction", 5)
        self._send("workspacev2>>5,distraction")
        self.assertTrue(_wait(lambda: self._hooks().count("enter") == 1, 4), self._hooks())
        self.gate.write_text("1", encoding="utf-8")
        self._wait_nft("replace ds")
        self.assertNotIn("flush ds", self._nft())
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on", 4), self._state())
        self.assertTrue(self._state()["on_space"])

    def test_overlapping_requests_coalesce(self):
        os.environ["GETENT_GATE"] = str(self.gate)
        self._cfg()
        self._start()
        self.assertTrue(_wait(lambda: bool(self._getent_hosts()), 4))
        n0 = len(self._getent_hosts())
        self._fire("refresh")
        time.sleep(0.05)
        self._fire("refresh")
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
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on"))
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
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on"))
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
        self.assertEqual(self._nft().count("replace ds"), n_before)
        self.assertGreaterEqual(self._nft().count("check ds"), 2)

    def test_resolve_exception_keeps_enforcement(self):
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on"))
        nft_before = self._nft()
        addrs = self.box.state_dir / "addrs.json"
        addrs.unlink()
        addrs.mkdir()
        r = self.box.run("refresh", timeout=16)
        self.assertEqual(r.returncode, 1, r.stderr)
        text = self.notify_log.read_text(encoding="utf-8")
        self.assertEqual(text.count("Network update failed"), 1)
        self.assertIn("Refresh failed", text)
        self.assertEqual(self._nft(), nft_before)
        self.assertNotIn("flush ds", nft_before)
        r = self.box.run("refresh", timeout=16)
        self.assertEqual(r.returncode, 1, r.stderr)
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

    def test_release_exempts_the_focused_window_until_it_closes_or_expires(self):
        telegram = {"address": "0xaaa", "class": "org.telegram.desktop", "workspace": {"id": 1, "name": "1"}}
        move = hypr.move_window_lua("0xaaa")
        self._cfg(list=["Telegram", "x.com"])
        self._workspace("1", 1, clients=[telegram], active=telegram)
        self._start()
        self._wait_nft("replace ds")
        self.assertTrue(_wait(lambda: self._dispatches() == [move], 4), "the boot scan moved it")
        r = self.box.run("release", "5", timeout=16)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(list(self._released()), ["0xaaa"], self._state())
        until = self._released()["0xaaa"]
        self.assertGreater(datetime.fromisoformat(until), datetime.now(timezone.utc) + timedelta(minutes=4))
        self.assertEqual(json.loads(self.box.run("status", "--json").stdout)["released"], {"0xaaa": until})
        # Dragged off the space, reopened, and rescanned: the exemption holds through all three.
        self._send("movewindow>>0xaaa,1")
        self._send("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
        self._send("configreloaded>>")
        self._workspace("distraction", 5, clients=[telegram], active=telegram)
        self._send("workspacev2>>5,distraction")
        self.assertTrue(_wait(lambda: self._hooks().count("enter") == 1, 4), "the events before it were handled")
        self.assertEqual(self._dispatches(), [move])
        # Closed: pruned.
        self._send("closewindow>>0xaaa")
        self.assertTrue(_wait(lambda: self._released() == {}, 4), self._state())
        # Expired with snap_back on (the default): moved back once.
        until = _iso(2)
        self.assertEqual(self._reload(f"release 0xaaa {until}"), b"ok")
        self.assertEqual(self._released(), {"0xaaa": until})
        self.assertTrue(_wait(lambda: self._dispatches() == [move, move], 6), self._dispatches())
        self.assertEqual(self._released(), {})
        time.sleep(1.2)
        self.assertEqual(self._dispatches(), [move, move])
        # A deadline already past, or unreadable, is refused and records nothing.
        self.assertEqual(self._reload(f"release 0xaaa {_iso(-1)}"), b"error")
        self.assertEqual(self._reload("release 0xaaa soon"), b"error")
        self.assertEqual(self._reload("release 0xaaa"), b"error")
        # A window Hyprland no longer lists is refused too: nothing would ever prune it.
        self.assertEqual(self._reload(f"release 0xdead {_iso(5)}"), b"error")
        self.assertEqual(self._released(), {})

    def test_snap_back_off_ignores_moves_and_release_reports_its_errors(self):
        telegram = {"address": "0xaaa", "class": "org.telegram.desktop", "workspace": {"id": 1, "name": "1"}}
        self._workspace("1", 1, clients=[telegram], active=telegram)
        r = self.box.run("release", "0", timeout=3)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("not a positive integer", r.stderr)
        # An unbounded duration would overflow the deadline: refused at the parser.
        r = self.box.run("release", "99999999999", timeout=3)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("minute limit", r.stderr)
        r = self.box.run("release", timeout=3)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(len(self._notices("No listener running")), 1)
        self._cfg(list=["Telegram", "x.com"], containment={"snap_back": False})
        self._workspace("1", 1, clients=[telegram])
        self._start()
        self._wait_nft("replace ds")
        r = self.box.run("release", timeout=16)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(len(self._notices("No window to release")), 1)
        self.assertEqual(self._released(), {})
        # A manual move stands; a fresh window is still placed.
        self.hypr_log.write_text("", encoding="utf-8")
        self._send("movewindow>>0xaaa,1")
        self._send("movewindowv2>>0xaaa,1,1")
        self._send("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
        move = hypr.move_window_lua("0xaaa")
        self.assertTrue(_wait(lambda: move in self._dispatches(), 4), self._dispatches())
        self.assertEqual(self._dispatches(), [move])

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
        self.assertTrue(_wait(lambda: (self._state() or {}).get("on_space") is True, 3), self._state())
        self.assertEqual(self._state()["site_block"], "on")
        self.assertFalse((self._state() or {}).get("locked"))
        r = self.box.run("lock", "25", "deep", "work")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(_wait(lambda: (self._state() or {}).get("locked") is True, 3), self._state())
        st = self._state()
        self.assertEqual(st["purpose"], "deep work")
        self.assertTrue(st["on_space"])
        self.assertEqual(st["site_block"], "on")

    def test_coalesced_reload_waiters_complete_together(self):
        os.environ["GETENT_GATE"] = str(self.gate)
        self.gate.write_text("1", encoding="utf-8")
        self._cfg()
        self._start()
        self._wait_nft("replace ds")
        self.assertTrue(_wait(lambda: (self._state() or {}).get("site_block") == "on"))
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
        self.assertEqual(self._nft().count("replace ds"), n_before + 1)
        self.assertGreaterEqual(self._nft().count("check ds"), 2)

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
        self._fire("refresh")
        t.join(timeout=2 * bd + 8)
        self.assertFalse(t.is_alive())
        self.assertEqual(got, [b"ok"])


class ExpansionTests(unittest.TestCase):
    def test_version_2_expansion_reads_with_desktop_null_and_the_block_on(self):
        entry = {"name": "X", "classes": ["^chrome-x\\.com__.*$"], "hosts": ["x.com"], "senders": [], "audio": {}}
        exp = listener._as_exp({"list": [entry], "keep_reachable": [], "nudges": {"app_banner": True}})
        self.assertEqual(exp["list"], [{**entry, "desktop": None}])
        self.assertEqual(exp["site_block"], {"enabled": True})
        kept = {**entry, "desktop": "org.telegram.desktop"}
        exp = listener._as_exp({"list": [kept], "site_block": {"enabled": False}})
        self.assertEqual(exp["list"], [kept])
        self.assertEqual(exp["site_block"], {"enabled": False})
        self.assertEqual(listener._as_exp(None)["site_block"], {"enabled": True})


class HoldRetryTests(unittest.TestCase):
    def test_unavailable_retries_once_per_period_with_one_notice(self):
        clock = [1000.0]
        push = mock.Mock(side_effect=["unavailable", "unavailable", "on"])
        notify = mock.Mock()
        with mock.patch.object(listener.hold, "push", push), \
             mock.patch.object(listener.hold, "effective_hold", return_value=True), \
             mock.patch.object(listener.lock, "is_locked", return_value=False), \
             mock.patch.object(listener.ui, "notify", notify), \
             mock.patch.object(listener.time, "monotonic", side_effect=lambda: clock[0]):
            ctx = listener._Ctx()
            ctx.exp = {"list": []}
            ctx.mute.sync = mock.Mock()
            ctx.sync_hold(force=True)
            self.assertEqual(push.call_count, 1)
            self.assertEqual(notify.call_count, 1)
            self.assertEqual(ctx.hold_ipc, "unavailable")
            clock[0] = 1000.0 + 1.0
            ctx.sync_hold()
            self.assertEqual(push.call_count, 1)
            clock[0] = 1000.0 + listener.PERIOD
            ctx.sync_hold()
            self.assertEqual(push.call_count, 2)
            self.assertEqual(ctx.hold_ipc, "unavailable")
            self.assertEqual(notify.call_count, 1)
            clock[0] = 1000.0 + 2 * listener.PERIOD
            ctx.sync_hold()
            self.assertEqual(push.call_count, 3)
            self.assertEqual(ctx.hold_ipc, "on")
            clock[0] = 1000.0 + 3 * listener.PERIOD
            ctx.sync_hold()
            self.assertEqual(push.call_count, 3)


class ScanTests(unittest.TestCase):
    """`_scan` on start and reload runs the three containment layers over every existing client."""

    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.hypr_log = self.box.runtime / "hypr.log"
        self.hypr_state = self.box.runtime / "hypr-state.json"
        self.notify_log = self.box.runtime / "notify.log"
        self.open_log = self.box.runtime / "open.log"
        proc = self.box.runtime / "proc"
        proc.mkdir()
        self.proc = FakeProc(proc)
        os.environ.update({
            "DS_HYPR_LOG": str(self.hypr_log),
            "DS_HYPR_STATE": str(self.hypr_state),
            "DS_NOTIFY_LOG": str(self.notify_log),
            "DS_OPEN_LOG": str(self.open_log),
            "DS_PROC_ROOT": str(proc),
        })
        self.addCleanup(os.environ.pop, "DS_PROC_ROOT", None)
        for key in ("DS_HYPR_FAIL", "DS_OPEN_FAIL"):
            os.environ.pop(key, None)
        self.box.fake_bin("hyprctl", HYPRCTL)
        self.box.fake_bin("omarchy-notification-send", NOTIFY)
        cli = self.box.fake_bin("distractions", OPEN)
        patcher = mock.patch.object(hypr, "CLI", str(cli))
        patcher.start()
        self.addCleanup(patcher.stop)
        hypr._reset_for_tests()
        feedback.start({"nudges": {"block_page": False}, "site_block": {"pass_through": False}}, False)
        self.addCleanup(feedback.stop)

    @staticmethod
    def _client(address, klass, workspace, pid):
        return {"address": address, "class": klass, "pid": pid,
                "workspace": {"id": 5 if workspace == hypr.SPACE else 1, "name": workspace}}

    def _dispatches(self):
        out = []
        for line in self.hypr_log.read_text(encoding="utf-8").splitlines():
            argv = json.loads(line)
            if argv[:1] == ["dispatch"]:
                out.append(argv[1])
        return out

    def test_scan_applies_all_three_layers_to_existing_clients(self):
        hypr.apply_rules({"list": [expand_entry(n) for n in ("Telegram", "WhatsApp", "X")]})
        self.proc.add(100, 1, f"{SLICE_PATH}/run-1.scope")
        self.proc.add(300, 1, SESSION_PATH)
        write_json(self.hypr_state, {"activeworkspace": {"id": 1, "name": "1"}, "clients": [
            self._client("0xa", "org.telegram.desktop", "1", 300),
            self._client("0xb", "google-chrome", "1", 100),
            self._client("0xc", "chrome-web.whatsapp.com__-Default", "1", 300),
            self._client("0xd", "chrome-x.com__-Distraction", hypr.SPACE, 100),
            self._client("0xe", "firefox", "1", 300),
        ]})
        self.hypr_log.write_text("", encoding="utf-8")
        listener._scan()
        self.assertEqual(self._dispatches(), [
            hypr.move_window_lua("0xa"), hypr.move_window_lua("0xb"), hypr.move_window_lua("0xc"),
        ])
        self.assertFalse(self.open_log.exists(), "discovery never launches a replacement")
        notices = self.notify_log.read_text(encoding="utf-8")
        self.assertIn("Telegram opened in the distraction space", notices)
        self.assertIn("WhatsApp opened in the distraction space", notices)
        self.assertNotIn("X opened", notices, "a window already on the space did not land")


if __name__ == "__main__":
    unittest.main()
