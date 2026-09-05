#!/usr/bin/env python3
"""Resolver batch, last-good, apply/flush, hanging getent, batch log."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import net, setup, state

GETENT = r"""
import json, os, sys, time
host = sys.argv[-1]
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
args = sys.argv[1:]
if args[:1] == ["-n"]:
    args = args[1:]
log = os.environ["DS_NFT_LOG"]
body = sys.stdin.read()
with open(log, "a", encoding="utf-8") as f:
    f.write(" ".join(args) + "\n")
    f.write(body)
    f.write("\n--\n")
if os.environ.get("DS_NFT_FAIL"):
    sys.exit(1)
if args[:1] == ["install"] or args[:1] == ["rm"]:
    sys.exit(0)
sys.exit(0)
"""

NOTIFY = r"""
import os, sys
path = os.environ["DS_NOTIFY_LOG"]
with open(path, "a", encoding="utf-8") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
"""


def _children():
    me = os.getpid()
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
        if ppid != me:
            continue
        try:
            cmd = Path(f"/proc/{name}/cmdline").read_bytes().replace(b"\x00", b" ").decode()
        except OSError:
            cmd = ""
        kids.append((int(name), cmd))
    return kids


def _getent_children():
    return [k for k in _children() if "getent" in k[1]]


class NetTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.nft_log = self.box.runtime / "nft.log"
        self.notify_log = self.box.runtime / "notify.log"
        os.environ["DS_NFT_LOG"] = str(self.nft_log)
        os.environ["DS_NOTIFY_LOG"] = str(self.notify_log)
        os.environ.pop("DS_NFT_FAIL", None)
        os.environ.pop("GETENT_MAP", None)
        self.box.fake_bin("getent", GETENT)
        self.box.fake_bin("sudo", SUDO)
        self.box.fake_bin("omarchy-notification-send", NOTIFY)
        self.addCleanup(net.shutdown)

    def _map(self, table):
        os.environ["GETENT_MAP"] = json.dumps(table)

    def _log_text(self):
        path = state.state_path("log")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _resolve(self, hosts, generation, reason, keep_reachable=()):
        addrs, batch = net.resolve_batch(hosts, generation, reason, keep_reachable)
        return addrs, batch

    def test_unresolvable_keeps_last_good(self):
        state.write_json(state.state_path("addrs.json"), {"gone.example": ["203.0.113.9"]})
        self._map({"gone.example": None, "live.example": ["198.51.100.7"]})
        addrs, _ = self._resolve(["gone.example", "live.example"], 1, "start")
        self.assertIn("203.0.113.9", addrs)
        self.assertIn("198.51.100.7", addrs)
        cache = state.read_json(state.state_path("addrs.json"), {})
        self.assertEqual(cache["gone.example"], ["203.0.113.9"])
        self.assertEqual(cache["live.example"], ["198.51.100.7"])

    def test_deadline_pending_uses_last_good(self):
        state.write_json(
            state.state_path("addrs.json"),
            {f"h{i}.example": [f"203.0.113.{i}"] for i in range(1, 21)},
        )
        self._map({f"h{i}.example": "hang" for i in range(1, 21)})
        hosts = [f"h{i}.example" for i in range(1, 21)]
        t0 = time.monotonic()
        with mock.patch.object(net, "BATCH_DEADLINE", 0.3):
            addrs, _ = self._resolve(hosts, 2, "periodic")
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 2.0)
        self.assertIn("203.0.113.1", addrs)
        self.assertIn("203.0.113.20", addrs)

    def test_command_deadline_kills_and_reaps_child(self):
        import subprocess
        pidfile = self.box.runtime / "command.pid"
        script = f"import os,time; open({str(pidfile)!r}, 'w').write(str(os.getpid())); time.sleep(3600)"
        with self.assertRaises(subprocess.TimeoutExpired):
            net.run_command([sys.executable, "-c", script], capture_output=True, timeout=0.2)
        self.assertFalse(Path(f"/proc/{pidfile.read_text()}").exists())
        self.assertEqual(net._children, {})

    def test_apply_launch_errors_and_timeout_are_unavailable_without_publication(self):
        import subprocess
        for error in (PermissionError("denied"), FileNotFoundError("missing"),
                      subprocess.TimeoutExpired("sudo", 1)):
            with self.subTest(error=error), mock.patch.object(net, "run_command", side_effect=error), \
                 mock.patch.object(net, "_notice_unavailable"):
                net.site_block = "off"
                self.assertEqual(net.apply(["203.0.113.10"], publish=False), "unavailable")
                self.assertEqual(net.site_block, "off")

    def test_empty_final_set_sends_flush_not_empty_replace(self):
        self._map({})
        addrs, _ = self._resolve(["missing.example"], 3, "reload")
        self.assertEqual(addrs, [])
        result = net.apply(addrs)
        self.assertEqual(result, "off")
        text = self.nft_log.read_text(encoding="utf-8")
        self.assertIn(f"{setup.wrapper_dest()} flush ds", text)
        self.assertNotIn("replace ds", text)
        self.assertEqual(net.site_block, "off")

    def test_flush_does_not_inherit_an_open_stdin(self):
        # The wrapper reads stdin to EOF on flush. With an inherited stdin that never
        # closes (a socket, a pipe held by the launcher), apply([]) would block forever.
        r, w = os.pipe()
        saved = os.dup(0)
        result = {}
        worker = threading.Thread(target=lambda: result.setdefault("value", net.apply([])), daemon=True)
        try:
            os.dup2(r, 0)
            worker.start()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive(), "flush blocked on the inherited stdin")
        finally:
            os.dup2(saved, 0)
            os.close(saved)
            os.close(w)
            os.close(r)
            worker.join(timeout=5)
        self.assertEqual(result.get("value"), "off")
        self.assertIn(f"{setup.wrapper_dest()} flush ds", self.nft_log.read_text(encoding="utf-8"))

    def test_keep_reachable_subtracted(self):
        self._map({
            "blocked.example": ["203.0.113.10", "198.51.100.10"],
            "ok.example": ["198.51.100.10"],
        })
        addrs, _ = self._resolve(["blocked.example"], 4, "start", keep_reachable=["ok.example"])
        self.assertIn("203.0.113.10", addrs)
        self.assertNotIn("198.51.100.10", addrs)

    def test_keep_reachable_from_snapshot_not_config(self):
        self.box.config_file.write_text(
            json.dumps({"keep_reachable": ["other.example"]}),
            encoding="utf-8",
        )
        state.write_json(
            state.state_path("addrs.json"),
            {
                "blocked.example": ["203.0.113.10", "198.51.100.10"],
                "cdn.example": ["198.51.100.10"],
                "other.example": ["192.0.2.1"],
            },
        )
        self._map({})
        addrs, _ = self._resolve(
            ["blocked.example"], 5, "reload", keep_reachable=["cdn.example"],
        )
        self.assertIn("203.0.113.10", addrs)
        self.assertNotIn("198.51.100.10", addrs)
        self.assertNotIn("192.0.2.1", addrs)

    def test_hanging_getent_three_batches_then_shutdown(self):
        state.write_json(state.state_path("addrs.json"), {"slow.example": ["192.0.2.8"]})
        self._map({"slow.example": "hang", "also.example": "hang"})
        threads_after = []
        for gen in (10, 11, 12):
            t0 = time.monotonic()
            addrs, _ = self._resolve(["slow.example", "also.example"], gen, "periodic")
            elapsed = time.monotonic() - t0
            self.assertLess(elapsed, 6.0)
            self.assertIn("192.0.2.8", addrs)
            self.assertEqual(_getent_children(), [])
            threads_after.append(threading.active_count())
        self.assertEqual(threads_after[0], threads_after[1])
        self.assertEqual(threads_after[1], threads_after[2])
        barrier = threading.Event()

        def in_flight():
            barrier.set()
            net.resolve_batch(["slow.example"], 99, "refresh")

        worker = threading.Thread(target=in_flight)
        worker.start()
        self.assertTrue(barrier.wait(timeout=2))
        until = time.monotonic() + 2
        while time.monotonic() < until and not _getent_children():
            time.sleep(0.01)
        t0 = time.monotonic()
        net.shutdown()
        shutdown_ms = time.monotonic() - t0
        self.assertLess(shutdown_ms, 3.0)
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(_getent_children(), [])

    def test_batch_writes_one_log_line(self):
        self._map({"a.example": ["203.0.113.1"], "b.example": None})
        state.write_json(state.state_path("addrs.json"), {"b.example": ["198.51.100.2"]})
        addrs, batch = self._resolve(["a.example", "b.example"], 7, "workspace")
        net.apply(addrs)
        net.finish_batch(batch, "applied")
        lines = [ln for ln in self._log_text().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertIn("gen=7", line)
        self.assertIn("reason=workspace", line)
        self.assertIn("hosts=2", line)
        self.assertIn("resolved=1", line)
        self.assertIn("failed=1", line)
        self.assertIn("apply=", line)
        self.assertIn("elapsed_ms=", line)
        self.assertRegex(line, r"marker=\S+")

    def test_apply_replace_and_unavailable_notice_once(self):
        self._map({"a.example": ["203.0.113.4"]})
        addrs, _ = self._resolve(["a.example"], 8, "start")
        self.assertEqual(net.apply(addrs), "on")
        self.assertEqual(net.site_block, "on")
        text = self.nft_log.read_text(encoding="utf-8")
        self.assertIn(f"{setup.wrapper_dest()} replace ds", text)
        self.assertTrue(str(setup.wrapper_dest()).startswith("/"))
        self.assertIn("203.0.113.4", text)
        os.environ["DS_NFT_FAIL"] = "1"
        self.assertEqual(net.apply(["203.0.113.4"]), "unavailable")
        self.assertEqual(net.site_block, "unavailable")
        self.assertTrue(self.notify_log.exists())
        first = self.notify_log.read_text(encoding="utf-8")
        self.assertTrue(first.strip())
        net.apply(["203.0.113.4"])
        self.assertEqual(self.notify_log.read_text(encoding="utf-8"), first)

    def test_finish_batch_stale_coalesced_without_apply(self):
        self._map({"a.example": ["203.0.113.1"]})
        _, batch = self._resolve(["a.example"], 9, "workspace")
        self.assertFalse(self.nft_log.exists())
        net.finish_batch(batch, "stale")
        net.finish_batch(batch, "coalesced")
        self.assertFalse(self.nft_log.exists())
        lines = [ln for ln in self._log_text().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 2)
        self.assertIn("marker=stale", lines[0])
        self.assertIn("apply=stale", lines[0])
        self.assertIn("gen=9", lines[0])
        self.assertIn("marker=coalesced", lines[1])
        self.assertIn("apply=coalesced", lines[1])
        self.assertIn("elapsed_ms=", lines[0])
        self.assertIn("elapsed_ms=", lines[1])

    def test_apply_survives_unwritable_log(self):
        blocked = self.box.runtime / "nolog"
        blocked.mkdir()
        os.chmod(blocked, 0o555)
        bad_log = blocked / "log"
        self.box.config_file.write_text(json.dumps({"log": str(bad_log)}), encoding="utf-8")
        self._map({"a.example": ["203.0.113.4"]})
        addrs, batch = self._resolve(["a.example"], 8, "start")
        try:
            self.assertEqual(net.apply(addrs), "on")
            net.finish_batch(batch, "applied")
        finally:
            os.chmod(blocked, 0o755)
        self.assertFalse(bad_log.exists())
        text = self._log_text()
        self.assertIn("gen=8", text)
        self.assertIn("apply=applied", text)


if __name__ == "__main__":
    unittest.main()
