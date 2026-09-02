#!/usr/bin/env python3
"""HTTP block page and TLS SNI catcher."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox
from test_hypr import HYPRCTL

sys.path.insert(0, str(ROOT))
from ds import feedback, hypr, state
from ds.catalog import expand_entry

HTTP_PORT = 28080
TLS_PORT = 28443
CFG = {"nudges": {"block_page": True}}


def _free_loopback_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _u16(n: int) -> bytes:
    return bytes([(n >> 8) & 0xFF, n & 0xFF])


def _u24(n: int) -> bytes:
    return bytes([(n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])


def make_client_hello(sni: str | None) -> bytes:
    """Minimal TLS handshake record with an optional SNI host_name."""
    exts = b""
    if sni is not None:
        host = sni.encode("ascii")
        entry = b"\x00" + _u16(len(host)) + host
        sni_data = _u16(len(entry)) + entry
        exts += _u16(0) + _u16(len(sni_data)) + sni_data
    # signature_algorithms so a no-SNI hello still has an extensions block
    sig = b"\x00\x02\x04\x03"
    exts += _u16(13) + _u16(len(sig)) + sig
    body = b"\x03\x03" + b"\x00" * 32 + b"\x00"
    body += _u16(2) + b"\x00\x2f"
    body += b"\x01\x00"
    body += _u16(len(exts)) + exts
    hs = b"\x01" + _u24(len(body)) + body
    return b"\x16\x03\x01" + _u16(len(hs)) + hs


def _exchange(addr: str, port: int, payload: bytes, timeout: float = 2.0) -> bytes:
    family = socket.AF_INET6 if ":" in addr else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect((addr, port))
        try:
            if payload:
                sock.sendall(payload)
        except OSError:
            pass
        chunks = []
        while True:
            try:
                chunk = sock.recv(4096)
            except (socket.timeout, OSError):
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        sock.close()


class _Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def _write_proc(root, tcp_rows=None, tcp6_rows=None, fds=None, ppid=None):
    root = Path(root)
    net = root / "net"
    net.mkdir(parents=True, exist_ok=True)

    def write_table(path, rows):
        lines = [
            "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode"
        ]
        for i, (local_port, inode, uid) in enumerate(rows or []):
            local = f"0100007F:{int(local_port):04X}"
            lines.append(
                f"{i:4d}: {local} 0100007F:01BB 01 00000000:00000000 00:00000000 00000000 "
                f"{int(uid):5d}        0 {int(inode)} 1 0000000000000000 100 0 0 10 0"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    write_table(net / "tcp", tcp_rows)
    write_table(net / "tcp6", tcp6_rows)

    all_pids = set()
    for pid in (fds or {}):
        all_pids.add(int(pid))
    for pid, parent in (ppid or {}).items():
        all_pids.add(int(pid))
        all_pids.add(int(parent))
    for pid in all_pids:
        if pid <= 0:
            continue
        pdir = root / str(pid)
        pdir.mkdir(parents=True, exist_ok=True)
        parent = (ppid or {}).get(pid, 1)
        (pdir / "status").write_text(f"Name:\tx\nPPid:\t{parent}\n", encoding="utf-8")
        fd_dir = pdir / "fd"
        fd_dir.mkdir(exist_ok=True)
        for n, inode in enumerate((fds or {}).get(pid, [])):
            link = fd_dir / str(n)
            try:
                link.unlink()
            except OSError:
                pass
            os.symlink(f"socket:[{inode}]", link)


def _http_get(host: str | None, addr: str = "127.0.0.1") -> bytes:
    if host is None:
        req = b"GET / HTTP/1.1\r\n\r\n"
    else:
        req = f"GET / HTTP/1.1\r\nHost: {host}\r\n\r\n".encode("utf-8")
    return _exchange(addr, HTTP_PORT, req)


class FeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global HTTP_PORT, TLS_PORT
        cls._orig_http_port = HTTP_PORT
        cls._orig_tls_port = TLS_PORT
        HTTP_PORT = _free_loopback_port()
        TLS_PORT = _free_loopback_port()
        cls._env_patch = patch.dict(
            os.environ,
            {
                "DS_FEEDBACK_HTTP_PORT": str(HTTP_PORT),
                "DS_FEEDBACK_TLS_PORT": str(TLS_PORT),
            },
        )
        cls._env_patch.start()

    @classmethod
    def tearDownClass(cls):
        global HTTP_PORT, TLS_PORT
        cls._env_patch.stop()
        HTTP_PORT = cls._orig_http_port
        TLS_PORT = cls._orig_tls_port

    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.notices: list[tuple[str, str]] = []

        def fake_notify(title, body, *, glyph=None, action=None, urgent=False):
            self.notices.append((title, body))

        self._patch = patch("ds.ui.notify", fake_notify)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(feedback.stop)

        self.hypr_log = self.box.runtime / "hypr.log"
        self.hypr_state = self.box.runtime / "hypr-state.json"
        self.proc_root = self.box.runtime / "proc"
        self.proc_root.mkdir()
        os.environ["DS_HYPR_LOG"] = str(self.hypr_log)
        os.environ["DS_HYPR_STATE"] = str(self.hypr_state)
        os.environ["DS_PROC_ROOT"] = str(self.proc_root)
        os.environ.pop("DS_HYPR_FAIL", None)
        self.addCleanup(lambda: os.environ.pop("DS_HYPR_LOG", None))
        self.addCleanup(lambda: os.environ.pop("DS_HYPR_STATE", None))
        self.addCleanup(lambda: os.environ.pop("DS_PROC_ROOT", None))
        self.addCleanup(lambda: os.environ.pop("DS_HYPR_FAIL", None))
        self.hypr_state.write_text("{}", encoding="utf-8")
        self.box.fake_bin("hyprctl", HYPRCTL)
        hypr._reset_for_tests()

    def _clear_banners(self):
        self.notices.clear()
        feedback._banner_at.clear()
        feedback._log_at.clear()

    def _hypr_clients(self, clients):
        payload = {
            "activeworkspace": {"id": 1, "name": "1"},
            "clients": clients,
            "workspaces": [],
        }
        self.hypr_state.write_text(json.dumps(payload), encoding="utf-8")

    def _client(self, address, klass, workspace="1", pid=1):
        return {
            "address": address,
            "class": klass,
            "pid": pid,
            "workspace": {
                "id": 99 if workspace == hypr.SPACE else 1,
                "name": workspace,
            },
        }

    def _banners(self):
        return [n for n in self.notices if n[0] == "Blocked on this workspace"]

    def _start(self, is_locked=None):
        if is_locked is None:
            is_locked = lambda: False
        elif not callable(is_locked):
            flag = bool(is_locked)
            is_locked = lambda: flag
        feedback.start(CFG, is_locked)

    def test_block_page_renders_escaped_host_and_fallback(self):
        locked = False
        self._start(lambda: locked)
        hostile = "<script>alert(1)</script>"
        page = _http_get(hostile)
        self.assertIn(b"200", page.split(b"\r\n", 1)[0])
        self.assertNotIn(b"<script>", page)
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertIn(b"Super+Ctrl+Shift+D", page)
        self.assertNotIn(b"is locked", page)

        fallback = _http_get(None)
        self.assertIn(b"this site", fallback)
        self.assertIn(b"Super+Ctrl+Shift+D", fallback)

        locked = True
        locked_page = _http_get("x.com")
        self.assertIn(b"x.com", locked_page)
        self.assertIn(b"is locked", locked_page)

    def test_non_http_input_closes_without_exception(self):
        self._start()
        junk = _exchange("127.0.0.1", HTTP_PORT, b"x" * 20000, timeout=1.0)
        self.assertEqual(junk, b"")
        page = _http_get("still.example")
        self.assertIn(b"still.example", page)
        self.assertIn(b"Super+Ctrl+Shift+D", page)

    def test_blank_line_terminated_garbage_closes_silently(self):
        self._start()
        junk = _exchange("127.0.0.1", HTTP_PORT, b"garbage\r\n\r\n", timeout=1.0)
        self.assertEqual(junk, b"")
        page = _http_get("still.example")
        self.assertIn(b"still.example", page)
        self.assertIn(b"Super+Ctrl+Shift+D", page)

    def test_sni_parser_valid_clienthello(self):
        data = make_client_hello("www.youtube.com")
        self.assertEqual(feedback.parse_sni(data), "www.youtube.com")

    def test_sni_parser_truncated_at_every_length(self):
        data = make_client_hello("x.com")
        for i in range(len(data)):
            self.assertIsNone(feedback.parse_sni(data[:i]), msg=f"prefix {i}")
        self.assertEqual(feedback.parse_sni(data), "x.com")

    def test_sni_parser_garbage(self):
        for blob in (b"", b"\xff" * 40, b"GET / HTTP/1.1\r\n\r\n", b"\x16\x03\x01\x00\x04XXXX"):
            self.assertIsNone(feedback.parse_sni(blob))

    def test_sni_parser_no_sni(self):
        self.assertIsNone(feedback.parse_sni(make_client_hello(None)))

    def test_first_banner_when_monotonic_below_debounce(self):
        with patch("ds.feedback.time.monotonic", return_value=10.0):
            feedback._maybe_banner("early.example")
        banners = [n for n in self.notices if n[0] == "Blocked on this workspace"]
        self.assertEqual(len(banners), 1)
        self.assertIn("early.example", banners[0][1])
        self.assertIn("Super+Ctrl+Shift+D", banners[0][1])

    def test_concurrent_clienthellos_one_banner_per_host(self):
        self._start()
        hello = make_client_hello("x.com")
        n = 24
        barrier = threading.Barrier(n)
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                body = _exchange("127.0.0.1", TLS_PORT, hello, timeout=2.0)
                if body:
                    errors.append(body)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [])
        banners = [n for n in self.notices if n[0] == "Blocked on this workspace"]
        self.assertEqual(len(banners), 1)
        self.assertIn("x.com", banners[0][1])
        self.assertIn("Super+Ctrl+Shift+D", banners[0][1])

        _exchange("127.0.0.1", TLS_PORT, hello, timeout=2.0)
        banners = [n for n in self.notices if n[0] == "Blocked on this workspace"]
        self.assertEqual(len(banners), 1)

    def test_bind_failure_one_family_other_serves_notifies_once(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(blocker.close)
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("127.0.0.1", HTTP_PORT))
        blocker.listen(1)
        self._start()
        page = _http_get("ipv6.test", addr="::1")
        self.assertIn(b"ipv6.test", page)
        self.assertIn(b"Super+Ctrl+Shift+D", page)
        unavail = [
            n for n in self.notices
            if "unavailable" in n[0].lower() or "unavailable" in n[1].lower()
        ]
        self.assertEqual(len(unavail), 1)

    def test_r1_on_space_helper_walk_no_banner(self):
        uid = os.getuid()
        helper, browser = 2001, 2000
        port, inode = 40000, 9991
        for table in ("tcp", "tcp6"):
            with self.subTest(table=table):
                self._clear_banners()
                hypr._reset_for_tests()
                self._hypr_clients(
                    [self._client("0xaaa", "google-chrome", hypr.SPACE, pid=browser)]
                )
                kwargs = {
                    "fds": {helper: [inode]},
                    "ppid": {helper: browser, browser: 1},
                }
                if table == "tcp":
                    kwargs["tcp_rows"] = [(port, inode, uid)]
                else:
                    kwargs["tcp6_rows"] = [(port, inode, uid)]
                _write_proc(self.proc_root, **kwargs)
                feedback._maybe_banner("api.x.com", peer_port=port)
                self.assertEqual(self._banners(), [])

    def test_r1_off_space_owner_has_window_elsewhere(self):
        uid = os.getuid()
        helper, browser = 2101, 2100
        port, inode = 40010, 9992
        self._hypr_clients([self._client("0xbbb", "google-chrome", "1", pid=browser)])
        _write_proc(
            self.proc_root,
            tcp_rows=[(port, inode, uid)],
            fds={helper: [inode]},
            ppid={helper: browser, browser: 1},
        )
        feedback._maybe_banner("api.x.com", peer_port=port)
        banners = self._banners()
        self.assertEqual(len(banners), 1)
        self.assertIn("Super+Ctrl+Shift+D", banners[0][1])

    def test_r1_unattributed_banner(self):
        uid = os.getuid()
        other_uid = 0 if uid else 1
        cases = ("missing_port", "other_uid", "walk_exhausted")
        for case in cases:
            with self.subTest(case=case):
                self._clear_banners()
                hypr._reset_for_tests()
                port, inode = 40100, 10001
                owner = 2208
                self._hypr_clients(
                    [self._client("0xccc", "google-chrome", hypr.SPACE, pid=owner)]
                )
                if case == "missing_port":
                    _write_proc(
                        self.proc_root,
                        fds={2200: [inode]},
                        ppid={2200: owner, owner: 1},
                    )
                    feedback._maybe_banner("gone.example", peer_port=port)
                elif case == "other_uid":
                    _write_proc(
                        self.proc_root,
                        tcp_rows=[(port, inode, other_uid)],
                        fds={2200: [inode]},
                        ppid={2200: owner, owner: 1},
                    )
                    feedback._maybe_banner("uid.example", peer_port=port)
                else:
                    # owner sits nine PPid hops above the socket holder: one past the walk limit
                    chain = list(range(2210, 2219))
                    leaf = 2219
                    ppid = {chain[i]: chain[i + 1] for i in range(len(chain) - 1)}
                    ppid[chain[-1]] = leaf
                    ppid[leaf] = 1
                    self._hypr_clients(
                        [self._client("0xddd", "google-chrome", hypr.SPACE, pid=leaf)]
                    )
                    _write_proc(
                        self.proc_root,
                        tcp_rows=[(port, inode, uid)],
                        fds={chain[0]: [inode]},
                        ppid=ppid,
                    )
                    feedback._maybe_banner("walk.example", peer_port=port)
                self.assertEqual(len(self._banners()), 1)
        with self.subTest(case="walk_reaches_owner_at_eight_hops"):
            self._clear_banners()
            hypr._reset_for_tests()
            eight = self.box.runtime / "proc8"
            os.environ["DS_PROC_ROOT"] = str(eight)
            _write_proc(eight, tcp_rows=[(port, inode, uid)], fds={chain[1]: [inode]}, ppid=ppid)
            feedback._maybe_banner("walk.example", peer_port=port)
            self.assertEqual(self._banners(), [])

    def test_r1_hyprctl_failure_logs_once_per_minute(self):
        os.environ["DS_HYPR_FAIL"] = "clients"
        clock = _Clock(1000.0)
        with patch("ds.feedback.time.monotonic", clock):
            feedback._maybe_banner("a.example", peer_port=1)
            feedback._maybe_banner("b.example", peer_port=1)
            log = state.state_path("log").read_text(encoding="utf-8")
            self.assertEqual(log.count("hyprctl clients unavailable; banner shown"), 1)
            self.assertEqual(len(self._banners()), 2)
            clock.t = 1061.0
            feedback._maybe_banner("c.example", peer_port=1)
            log = state.state_path("log").read_text(encoding="utf-8")
            self.assertEqual(log.count("hyprctl clients unavailable; banner shown"), 2)
            self.assertEqual(len(self._banners()), 3)

    def test_r1_proc_failure_banner(self):
        with self.subTest("missing_proc_root"):
            os.environ["DS_PROC_ROOT"] = str(self.box.runtime / "no-such-proc")
            feedback._maybe_banner("missing.example", peer_port=40000)
            self.assertEqual(len(self._banners()), 1)
        self._clear_banners()
        os.environ["DS_PROC_ROOT"] = str(self.proc_root)
        with self.subTest("unreadable_status"):
            uid = os.getuid()
            helper, browser = 2301, 2300
            port, inode = 40200, 10002
            self._hypr_clients(
                [self._client("0xeee", "google-chrome", hypr.SPACE, pid=browser)]
            )
            _write_proc(
                self.proc_root,
                tcp_rows=[(port, inode, uid)],
                fds={helper: [inode]},
                ppid={helper: browser, browser: 1},
            )
            status = self.proc_root / str(helper) / "status"
            status.unlink()
            os.symlink("missing-status", status)
            feedback._maybe_banner("status.example", peer_port=port)
            self.assertEqual(len(self._banners()), 1)

    def test_r2_shared_browser_entry_fallback(self):
        hypr.apply_rules([expand_entry("X")])
        uid = os.getuid()
        helper, browser = 3001, 3000
        port, inode = 40300, 11001
        x_class = "chrome-x.com__-Default"
        _write_proc(
            self.proc_root,
            tcp_rows=[(port, inode, uid)],
            fds={helper: [inode]},
            ppid={helper: browser, browser: 1},
        )

        def clients(x_ws):
            return [
                self._client("0xa", x_class, x_ws, pid=browser),
                self._client("0xb", "google-chrome", "1", pid=browser),
            ]

        self._hypr_clients(clients(hypr.SPACE))
        feedback._maybe_banner("api.x.com", peer_port=port)
        self.assertEqual(self._banners(), [])

        feedback._maybe_banner("example.org", peer_port=port)
        self.assertEqual(len(self._banners()), 1)
        self.assertIn("example.org", self._banners()[0][1])

        self._clear_banners()
        hypr._reset_for_tests()
        hypr.apply_rules([expand_entry("X")])
        self._hypr_clients(clients("1"))
        feedback._maybe_banner("api.x.com", peer_port=port)
        self.assertEqual(len(self._banners()), 1)

    def test_r2_no_matching_window_and_terminal_narrowing(self):
        hypr.apply_rules([expand_entry("X")])
        uid = os.getuid()
        with self.subTest("no matching window"):
            self._clear_banners()
            hypr._reset_for_tests()
            hypr.apply_rules([expand_entry("X")])
            helper, browser = 3101, 3100
            port, inode = 40400, 12001
            self._hypr_clients(
                [self._client("0xb", "google-chrome", "1", pid=browser)]
            )
            _write_proc(
                self.proc_root,
                tcp_rows=[(port, inode, uid)],
                fds={helper: [inode]},
                ppid={helper: browser, browser: 1},
            )
            feedback._maybe_banner("api.x.com", peer_port=port)
            self.assertEqual(len(self._banners()), 1)
        with self.subTest("terminal narrowing"):
            self._clear_banners()
            hypr._reset_for_tests()
            hypr.apply_rules([expand_entry("X")])
            term, browser = 3200, 3300
            port, inode = 40410, 12002
            self._hypr_clients(
                [
                    self._client("0xf", "foot", "1", pid=term),
                    self._client(
                        "0xx", "chrome-x.com__-Default", hypr.SPACE, pid=browser
                    ),
                ]
            )
            _write_proc(
                self.proc_root,
                tcp_rows=[(port, inode, uid)],
                fds={term: [inode]},
                ppid={term: 1, browser: 1},
            )
            feedback._maybe_banner("api.x.com", peer_port=port)
            self.assertEqual(len(self._banners()), 1)

    def test_r3_per_entry_debounce(self):
        hypr.apply_rules([expand_entry("X")])
        clock = _Clock(100.0)
        with patch("ds.feedback.time.monotonic", clock):
            feedback._maybe_banner("x.com")
            feedback._maybe_banner("api.x.com")
            banners = self._banners()
            self.assertEqual(len(banners), 1)
            self.assertIn("X opens in the distraction space", banners[0][1])
            self.assertIn("Super+Ctrl+Shift+D", banners[0][1])
            clock.t = 130.0
            feedback._maybe_banner("x.com")
            banners = self._banners()
            self.assertEqual(len(banners), 2)
            feedback._maybe_banner("early.example")
            banners = self._banners()
            self.assertEqual(len(banners), 3)
            self.assertIn("early.example", banners[-1][1])
            self.assertIn("early.example opens in the distraction space", banners[-1][1])


if __name__ == "__main__":
    unittest.main()
