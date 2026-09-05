#!/usr/bin/env python3
"""HTTP block page and TLS SNI catcher."""

from __future__ import annotations

import errno
import json
import os
import socket
import sys
import threading
import time
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
CFG = {"nudges": {"block_page": True}, "site_block": {"pass_through": False}}
CFG_ON = {"nudges": {"block_page": True}, "site_block": {"pass_through": True}}
REPLY = b"SPLICE-REPLY-OK"


def _free_loopback_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _free_port_pair(avoid=()):
    avoid = set(avoid)
    for _ in range(32):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", 0))
            base = probe.getsockname()[1]
        finally:
            probe.close()
        if any(61000 <= base + off <= 61999 for off in (0, 1)):
            continue
        if base in avoid or base + 1 in avoid:
            continue
        held = []
        try:
            for off in (0, 1):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", base + off))
                held.append(s)
            for s in held:
                s.close()
            return base, base + 1
        except OSError:
            for s in held:
                try:
                    s.close()
                except OSError:
                    pass
    raise RuntimeError("no free splice port pair")


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
        splice_lo, splice_hi = _free_port_pair(avoid=(HTTP_PORT, TLS_PORT))
        cls._env_patch = patch.dict(
            os.environ,
            {
                "DS_FEEDBACK_HTTP_PORT": str(HTTP_PORT),
                "DS_FEEDBACK_TLS_PORT": str(TLS_PORT),
                "DS_SPLICE_PORT_MIN": str(splice_lo),
                "DS_SPLICE_PORT_MAX": str(splice_hi),
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
        self.notices: list[tuple[str, str, list | None]] = []

        def fake_notify(title, body, *, glyph=None, action=None, urgent=False):
            self.notices.append((title, body, action))

        self._patch = patch("ds.ui.notify", fake_notify)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(feedback.stop)

        self.hypr_log = self.box.runtime / "hypr.log"
        self.hypr_state = self.box.runtime / "hypr-state.json"
        os.environ["DS_HYPR_LOG"] = str(self.hypr_log)
        os.environ["DS_HYPR_STATE"] = str(self.hypr_state)
        os.environ.pop("DS_HYPR_FAIL", None)
        self.addCleanup(lambda: os.environ.pop("DS_HYPR_LOG", None))
        self.addCleanup(lambda: os.environ.pop("DS_HYPR_STATE", None))
        self.addCleanup(lambda: os.environ.pop("DS_HYPR_FAIL", None))
        self.hypr_state.write_text("{}", encoding="utf-8")
        self.box.fake_bin("hyprctl", HYPRCTL)
        hypr._reset_for_tests()

    def _clear_banners(self):
        self.notices.clear()
        feedback._banner_at.clear()
        feedback._log_at.clear()

    def _banners(self):
        return [n for n in self.notices if n[0] == "Blocked here"]

    def _banner_lines(self):
        path = state.state_path("log")
        if not path.exists():
            return []
        return [line.split(" ", 1)[1] for line in path.read_text(encoding="utf-8").splitlines()
                if " banner: " in line]

    def _active_workspace(self, name):
        self.hypr_state.write_text(json.dumps({"activeworkspace": {"id": 1, "name": name}}), encoding="utf-8")

    def _start(self, is_locked=None, config=CFG):
        if is_locked is None:
            is_locked = lambda: False
        elif not callable(is_locked):
            flag = bool(is_locked)
            is_locked = lambda: flag
        feedback.start(config, is_locked)

    def _list_hosts(self, *hosts):
        state.write_expansion({"list": [{"name": hosts[0], "classes": [], "hosts": list(hosts)}]})
        hypr._reset_for_tests()

    def _fake_dest(self, reply=REPLY):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(8)
        srv.settimeout(3.0)
        port = srv.getsockname()[1]
        rec = {"got": b"", "sport": None}

        def serve():
            try:
                conn, addr = srv.accept()
            except OSError:
                return
            rec["sport"] = addr[1]
            conn.settimeout(2.0)
            try:
                chunks = []
                while True:
                    try:
                        chunk = conn.recv(65536)
                    except (socket.timeout, OSError):
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if reply:
                        break
                rec["got"] = b"".join(chunks)
                if reply:
                    try:
                        conn.sendall(reply)
                    except OSError:
                        pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

        t = threading.Thread(target=serve, daemon=True)
        t.start()

        def _cleanup():
            try:
                srv.close()
            except OSError:
                pass
            t.join(timeout=2)

        self.addCleanup(_cleanup)
        return port, rec

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

    def test_concurrent_clienthellos_one_banner_per_host(self):
        self._list_hosts("x.com")
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
        banners = [n for n in self.notices if n[0] == "Blocked here"]
        self.assertEqual(len(banners), 1)
        self.assertIn("x.com", banners[0][1])
        self.assertIn("Super+Ctrl+Shift+D", banners[0][1])

        _exchange("127.0.0.1", TLS_PORT, hello, timeout=2.0)
        banners = [n for n in self.notices if n[0] == "Blocked here"]
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

    def test_r1_http_splice_unlisted_host(self):
        dest, rec = self._fake_dest()
        req = b"GET / HTTP/1.1\r\nHost: safebrowsing.google.com\r\n\r\n"
        with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", dest)):
            self._start(config=CFG_ON)
            got = _exchange("127.0.0.1", HTTP_PORT, req)
        self.assertEqual(rec["got"], req)
        self.assertEqual(got, REPLY)
        self.assertNotIn(b"Super+Ctrl+Shift+D", got)
        # The slot is handed back: a leak would wedge pass-through at the cap forever.
        deadline = time.monotonic() + 2.0
        while feedback._splices and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(feedback._splices, 0)

    def test_r1_tls_splice_unlisted_sni(self):
        dest, rec = self._fake_dest()
        hello = make_client_hello("safebrowsing.google.com")
        with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", dest)):
            self._start(config=CFG_ON)
            got = _exchange("127.0.0.1", TLS_PORT, hello)
        self.assertEqual(rec["got"], hello)
        self.assertEqual(got, REPLY)
        self.assertEqual(self._banners(), [])

    def test_r2_listed_keeps_block_path(self):
        self._list_hosts("x.com")
        dest, rec = self._fake_dest()
        with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", dest)):
            self._start(config=CFG_ON)
            page = _http_get("x.com")
            hello = make_client_hello("x.com")
            tls_got = _exchange("127.0.0.1", TLS_PORT, hello)
        self.assertIn(b"x.com", page)
        self.assertIn(b"Super+Ctrl+Shift+D", page)
        self.assertEqual(tls_got, b"")
        self.assertEqual(rec["got"], b"")
        self.assertIsNone(rec["sport"])
        banners = self._banners()
        self.assertEqual(len(banners), 1)
        self.assertIn("x.com", banners[0][1])
        self.assertIn("Super+Ctrl+Shift+D", banners[0][1])

    def test_r2_listed_suffix_and_www_matching(self):
        self._list_hosts("x.com")
        listed = ["x.com", "X.CoM", "www.x.com", "api.x.com", "a.b.x.com", "x.com.", "x.com:443"]
        unlisted = ["notx.com", "xx.com", "example.com", "", "com", "safebrowsing.google.com"]
        for host in listed:
            with self.subTest(host=host, expect=True):
                self.assertTrue(feedback._listed(host))
        for host in unlisted:
            with self.subTest(host=host, expect=False):
                self.assertFalse(feedback._listed(host))

    def test_r3_splice_binds_source_port_in_range(self):
        self.assertEqual(feedback.SPLICE_PORT_MIN, 61000)
        self.assertEqual(feedback.SPLICE_PORT_MAX, 61999)
        lo, hi = _free_port_pair(avoid=(HTTP_PORT, TLS_PORT))
        dest, rec = self._fake_dest()
        req = b"GET / HTTP/1.1\r\nHost: other.example\r\n\r\n"
        with patch.dict(os.environ, {"DS_SPLICE_PORT_MIN": str(lo), "DS_SPLICE_PORT_MAX": str(hi)}):
            with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", dest)):
                self._start(config=CFG_ON)
                got = _exchange("127.0.0.1", HTTP_PORT, req)
        self.assertEqual(got, REPLY)
        self.assertIsNotNone(rec["sport"])
        self.assertGreaterEqual(rec["sport"], lo)
        self.assertLessEqual(rec["sport"], hi)

    def test_r4_splice_cap_closes_and_logs_once_per_minute(self):
        dest, rec = self._fake_dest()
        clock = _Clock(1000.0)
        req = b"GET / HTTP/1.1\r\nHost: other.example\r\n\r\n"
        with patch("ds.feedback.time.monotonic", clock):
            with patch.object(feedback, "MAX_SPLICES", 0):
                with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", dest)):
                    self._start(config=CFG_ON)
                    first = _exchange("127.0.0.1", HTTP_PORT, req)
                    second = _exchange("127.0.0.1", HTTP_PORT, req)
                    log = state.state_path("log").read_text(encoding="utf-8")
                    self.assertEqual(first, b"")
                    self.assertEqual(second, b"")
                    self.assertEqual(rec["got"], b"")
                    self.assertIsNone(rec["sport"])
                    self.assertEqual(log.count("pass-through cap"), 1)
                    clock.t = 1061.0
                    third = _exchange("127.0.0.1", HTTP_PORT, req)
                    self.assertEqual(third, b"")
                    log = state.state_path("log").read_text(encoding="utf-8")
                    self.assertEqual(log.count("pass-through cap"), 2)

    def test_original_dst_failure_closes_unlisted_without_splice(self):
        dest, rec = self._fake_dest()
        req = b"GET / HTTP/1.1\r\nHost: other.example\r\n\r\n"
        with patch("ds.feedback._original_dst", lambda conn: None):
            self._start(config=CFG_ON)
            got = _exchange("127.0.0.1", HTTP_PORT, req)
        self.assertEqual(got, b"")
        self.assertNotIn(b"Super+Ctrl+Shift+D", got)
        self.assertEqual(rec["got"], b"")
        self.assertIsNone(rec["sport"])

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(srv.close)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(cli.close)
        cli.connect(srv.getsockname())
        conn, _addr = srv.accept()
        self.addCleanup(conn.close)
        # An accepted socket with no NAT entry answers SO_ORIGINAL_DST with its own local address
        # on this kernel rather than failing, so _is_self — not the OSError — is what stops a
        # direct hit on 28080/28443 from splicing to itself.
        dst = feedback._original_dst(conn)
        self.assertIn(dst, (None, conn.getsockname()))
        if dst is not None:
            self.assertTrue(feedback._is_self(conn, dst))

        # End to end, with nothing monkeypatched: a direct hit never reaches the splice path.
        self._start(config=CFG_ON)
        self.assertEqual(_http_get("direct.example"), b"")
        self.assertEqual(rec["got"], b"")

    def test_destination_unreachable_closes_and_logs_once_per_minute(self):
        dead = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dead.bind(("127.0.0.1", 0))
        port = dead.getsockname()[1]
        dead.close()
        clock = _Clock(2000.0)
        req = b"GET / HTTP/1.1\r\nHost: other.example\r\n\r\n"
        line = f"pass-through to 127.0.0.1:{port} failed"
        with patch("ds.feedback.time.monotonic", clock):
            with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", port)):
                self._start(config=CFG_ON)
                first = _exchange("127.0.0.1", HTTP_PORT, req)
                second = _exchange("127.0.0.1", HTTP_PORT, req)
                log = state.state_path("log").read_text(encoding="utf-8")
                self.assertEqual(first, b"")
                self.assertEqual(second, b"")
                self.assertEqual(log.count(line), 1)
                clock.t = 2061.0
                third = _exchange("127.0.0.1", HTTP_PORT, req)
                self.assertEqual(third, b"")
                log = state.state_path("log").read_text(encoding="utf-8")
                self.assertEqual(log.count(line), 2)

    def test_pass_through_state_on_off_unavailable(self):
        self._start()
        self.assertEqual(feedback.pass_through_state(), "off")
        self._start(config=CFG_ON)
        self.assertEqual(feedback.pass_through_state(), "on")
        feedback.stop()
        self.assertEqual(feedback.pass_through_state(), "unavailable")

    def _fake_dest_multi(self, count, reply=REPLY):
        """A destination that serves `count` connections, recording each source port."""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(8)
        srv.settimeout(3.0)
        port = srv.getsockname()[1]
        rec = {"sports": []}

        def one(conn):
            conn.settimeout(2.0)
            try:
                conn.recv(65536)
                conn.sendall(reply)
            except OSError:
                pass
            finally:
                conn.close()

        def serve():
            workers = []
            for _ in range(count):
                try:
                    conn, addr = srv.accept()
                except OSError:
                    break
                rec["sports"].append(addr[1])
                w = threading.Thread(target=one, args=(conn,), daemon=True)
                w.start()
                workers.append(w)
            for w in workers:
                w.join(timeout=3)

        t = threading.Thread(target=serve, daemon=True)
        t.start()

        def _cleanup():
            try:
                srv.close()
            except OSError:
                pass
            t.join(timeout=3)

        self.addCleanup(_cleanup)
        return port, rec

    def _wait_splices(self, want, timeout=2.0):
        deadline = time.monotonic() + timeout
        while feedback._splices != want and time.monotonic() < deadline:
            time.sleep(0.01)
        return feedback._splices

    def test_r1_concurrent_splices_to_one_destination_take_distinct_ports(self):
        dest, rec = self._fake_dest_multi(2)
        req = b"GET / HTTP/1.1\r\nHost: other.example\r\n\r\n"
        results = {}

        def go(key):
            results[key] = _exchange("127.0.0.1", HTTP_PORT, req, timeout=4.0)

        # Every splice starts its port search at the same offset, so without a registry
        # of live source ports the two would bind the same port and the second connect
        # would fail on the four-tuple.
        with patch("ds.feedback.random.randrange", lambda span: 0):
            with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", dest)):
                self._start(config=CFG_ON)
                a = threading.Thread(target=go, args=("a",))
                b = threading.Thread(target=go, args=("b",))
                a.start()
                b.start()
                a.join(timeout=6)
                b.join(timeout=6)
        self.assertEqual(results, {"a": REPLY, "b": REPLY})
        self.assertEqual(len(rec["sports"]), 2)
        self.assertNotEqual(rec["sports"][0], rec["sports"][1])
        self.assertEqual(self._wait_splices(0), 0)
        self.assertEqual(feedback._ports_in_use, set())

    def test_r1_open_splice_retries_another_port_on_tuple_collision(self):
        dest, rec = self._fake_dest()
        real_connect = socket.socket.connect
        tried = []

        def collide_once(sock, addr):
            tried.append(sock.getsockname()[1])
            if len(tried) == 1:
                raise OSError(errno.EADDRNOTAVAIL, "four-tuple still in TIME_WAIT")
            return real_connect(sock, addr)

        with patch.object(socket.socket, "connect", collide_once):
            up, port, why = feedback._open_splice(("127.0.0.1", dest), socket.AF_INET)
        self.assertIsNotNone(up)
        self.assertIsNone(why)
        self.assertEqual(len(tried), 2)
        self.assertNotEqual(tried[0], tried[1])
        self.assertEqual(port, tried[1])
        self.assertEqual(feedback._ports_in_use, {port})
        up.close()
        feedback._free_port(port)
        self.assertEqual(feedback._ports_in_use, set())

        def refuse(sock, addr):
            raise OSError(errno.ECONNREFUSED, "refused")

        with patch.object(socket.socket, "connect", refuse):
            up, port, why = feedback._open_splice(("127.0.0.1", dest), socket.AF_INET)
        self.assertIsNone(up)
        self.assertIsNone(port)
        self.assertEqual(why, "connect")
        self.assertEqual(feedback._ports_in_use, set())

    def test_r1_pass_through_serves_with_block_page_nudge_off(self):
        self._list_hosts("x.com")
        cfg = {"nudges": {"block_page": False}, "site_block": {"pass_through": True}}
        dest, rec = self._fake_dest()
        req = b"GET / HTTP/1.1\r\nHost: other.example\r\n\r\n"
        with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", dest)):
            self._start(config=cfg)
            self.assertEqual(feedback.pass_through_state(), "on")
            got = _exchange("127.0.0.1", HTTP_PORT, req)
            self.assertEqual(got, REPLY)
            self.assertEqual(rec["got"], req)
            # Listed hosts keep the pre-router behavior of the nudge being off: a fast
            # close with no page and no banner.
            page = _http_get("x.com")
            tls_got = _exchange("127.0.0.1", TLS_PORT, make_client_hello("x.com"))
        self.assertEqual(page, b"")
        self.assertEqual(tls_got, b"")
        self.assertEqual(self._banners(), [])

        both_off = {"nudges": {"block_page": False}, "site_block": {"pass_through": False}}
        self._start(config=both_off)
        self.assertEqual(feedback.pass_through_state(), "off")
        with self.assertRaises(OSError):
            sock = socket.create_connection(("127.0.0.1", HTTP_PORT), timeout=1.0)
            sock.close()

    def test_r4_reload_keeps_live_splices_counted(self):
        dest, rec = self._fake_dest(reply=b"")
        req = b"GET / HTTP/1.1\r\nHost: other.example\r\n\r\n"
        with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", dest)):
            self._start(config=CFG_ON)
            cli = socket.create_connection(("127.0.0.1", HTTP_PORT), timeout=3.0)
            self.addCleanup(cli.close)
            cli.sendall(req)
            self.assertEqual(self._wait_splices(1), 1)
            self.assertEqual(len(feedback._ports_in_use), 1)
            # A config reload restarts the listeners while the splice is still pumping.
            self._start(config=CFG_ON)
        self.assertEqual(feedback._splices, 1)
        self.assertEqual(len(feedback._ports_in_use), 1)
        cli.close()
        self.assertEqual(self._wait_splices(0, timeout=4.0), 0)
        self.assertEqual(feedback._ports_in_use, set())

    def test_r2_fragmented_clienthello_still_reaches_listed_host_block(self):
        hello = make_client_hello("x.com")
        hs = hello[5:]
        first, rest = hs[:20], hs[20:]
        frag = (b"\x16\x03\x01" + _u16(len(first)) + first
                + b"\x16\x03\x01" + _u16(len(rest)) + rest)
        self.assertEqual(feedback.parse_sni(frag), "x.com")
        self.assertFalse(feedback._tls_done(frag[:-1]))
        self.assertTrue(feedback._tls_done(frag))
        self.assertTrue(feedback._tls_done(b"GET / HTTP/1.1\r\n"))
        for cut in range(1, len(frag)):
            with self.subTest(cut=cut):
                self.assertIsNone(feedback.parse_sni(frag[:cut]))

        self._list_hosts("x.com")
        dest, rec = self._fake_dest()
        with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", dest)):
            self._start(config=CFG_ON)
            got = _exchange("127.0.0.1", TLS_PORT, frag)
        self.assertEqual(got, b"")
        self.assertEqual(rec["got"], b"")
        self.assertIsNone(rec["sport"])
        self.assertEqual(len(self._banners()), 1)

        self._clear_banners()
        dest2, rec2 = self._fake_dest()
        unlisted = make_client_hello("safebrowsing.google.com")
        hs2 = unlisted[5:]
        frag2 = (b"\x16\x03\x01" + _u16(9) + hs2[:9]
                 + b"\x16\x03\x01" + _u16(len(hs2) - 9) + hs2[9:])
        with patch("ds.feedback._original_dst", lambda conn: ("127.0.0.1", dest2)):
            self._start(config=CFG_ON)
            got2 = _exchange("127.0.0.1", TLS_PORT, frag2)
        self.assertEqual(got2, REPLY)
        self.assertEqual(rec2["got"], frag2)
        self.assertEqual(self._banners(), [])

    def test_r11_attribution_and_provenance_symbols_removed(self):
        gone = (
            "_inode_for_port", "_pid_for_inode", "_ppid_of", "_walk_to_hypr_owner", "_attribute",
            "_provenance", "_prov_submit", "_prov_writer", "_prov_flush", "_prov_at",
            "PROVENANCE_PER_MIN", "_PPID_WALK", "_proc_root",
        )
        for sym in gone:
            with self.subTest(symbol=sym):
                self.assertFalse(hasattr(feedback, sym))
        source = (ROOT / "ds" / "feedback.py").read_text(encoding="utf-8")
        for text in ("peer_port", "_inode_for_port", "_walk_to_hypr_owner", "_provenance", "PROVENANCE_PER_MIN"):
            with self.subTest(text=text):
                self.assertNotIn(text, source)
        self.assertEqual(feedback.BANNER_DEBOUNCE_S, 60)

    def test_r10_blocked_fires_debounces_refires_and_logs(self):
        hypr.apply_rules([expand_entry("X")])
        self._start()
        clock = _Clock(10.0)  # below the debounce window: the first banner still fires
        with patch("ds.feedback.time.monotonic", clock):
            feedback.blocked("api.x.com")
            feedback.blocked("x.com")
            clock.t = 69.0
            feedback.blocked("www.x.com")
            clock.t = 70.0
            feedback.blocked("t.co")
        banners = self._banners()
        self.assertEqual(len(banners), 2)
        self.assertEqual(banners[0][1], "X opens in the distraction space. Super+Ctrl+Shift+D enters.")
        self.assertEqual(banners[0][2], [feedback._CLI, "open", "https://api.x.com/"])
        self.assertEqual(banners[1][2], [feedback._CLI, "open", "https://t.co/"])
        self.assertEqual(self._banner_lines(), [
            "banner: host=api.x.com entry=X decision=shown",
            "banner: host=x.com entry=X decision=debounced",
            "banner: host=www.x.com entry=X decision=debounced",
            "banner: host=t.co entry=X decision=shown",
        ])

    def test_r10_blocked_action_host_is_normalized_or_falls_back(self):
        self._list_hosts("youtube.com")
        clock = _Clock(100.0)
        with patch("ds.feedback.time.monotonic", clock):
            feedback.blocked("WWW.YouTube.com.")
            clock.t = 200.0
            feedback.blocked("evil/.youtube.com")
        self.assertEqual([b[2] for b in self._banners()], [
            [feedback._CLI, "open", "https://youtube.com/"],
            [feedback._CLI, "open", "https://youtube.com/"],
        ])

    def test_r10_blocked_unlisted_host_raises_nothing(self):
        self._list_hosts("x.com")
        feedback.blocked("early.example")
        self.assertEqual(self._banners(), [])
        self.assertEqual(self._banner_lines(), [])

    def test_r10_blocked_respects_block_page_nudge(self):
        self._list_hosts("x.com")
        self._start(config={"nudges": {"block_page": False}, "site_block": {"pass_through": False}})
        feedback.blocked("x.com")
        self.assertEqual(self._banners(), [])
        self.assertEqual(self._banner_lines(), [])

    def test_r10_blocked_never_fires_on_the_space(self):
        self._list_hosts("x.com")
        self._active_workspace(hypr.SPACE)
        clock = _Clock(100.0)
        with patch("ds.feedback.time.monotonic", clock):
            feedback.blocked("x.com")
            self.assertEqual(self._banners(), [])
            self.assertEqual(self._banner_lines(), [])
            # Leaving the space fires: the on-space skip claimed no debounce slot.
            self._active_workspace("1")
            feedback.blocked("x.com")
            self.assertEqual(len(self._banners()), 1)
            self.assertEqual(self._banner_lines(), ["banner: host=x.com entry=x.com decision=shown"])
            feedback._banner_at.clear()
            os.environ["DS_HYPR_FAIL"] = "activeworkspace"
            feedback.blocked("x.com")
        self.assertEqual(len(self._banners()), 1)
        self.assertIn("on_space unknown; skipping banner", state.state_path("log").read_text(encoding="utf-8"))
        self.assertEqual(len(self._banner_lines()), 1)

    def test_r10_opened_banner_action_and_debounce(self):
        hypr.apply_rules([expand_entry("X"), expand_entry("Telegram")])
        self._start()
        clock = _Clock(100.0)
        with patch("ds.feedback.time.monotonic", clock):
            feedback.opened("X")
            feedback.opened("X")
            feedback.opened("Telegram")
            feedback.opened("Unknown")
        opened = [n for n in self.notices if n[0].endswith(" opened in the distraction space")]
        self.assertEqual(opened, [
            ("X opened in the distraction space", "Super+Ctrl+Shift+D enters.", [feedback._CLI, "enter"]),
            ("Telegram opened in the distraction space", "Super+Ctrl+Shift+D enters.", [feedback._CLI, "enter"]),
            ("Unknown opened in the distraction space", "Super+Ctrl+Shift+D enters.", [feedback._CLI, "enter"]),
        ])
        self.assertEqual(self._banner_lines(), [
            "banner: host=x.com entry=X decision=shown",
            "banner: host=x.com entry=X decision=debounced",
            "banner: host=org.telegram.desktop entry=Telegram decision=shown",
            "banner: host=- entry=Unknown decision=shown",
        ])
        # One table: a Blocked for the same entry inside the window is debounced too.
        with patch("ds.feedback.time.monotonic", clock):
            feedback.blocked("api.x.com")
        self.assertEqual(self._banners(), [])
        self.assertEqual(self._banner_lines()[-1], "banner: host=api.x.com entry=X decision=debounced")

    def test_r10_opened_locked_body_names_the_end_and_still_enters(self):
        hypr.apply_rules([expand_entry("X")])
        until = "2026-09-05T14:30:00+00:00"
        want = state._parse_iso(until).astimezone().strftime("%H:%M")
        timed = {"locked": True, "until": until, "purpose": "", "since": None}
        open_ended = {"locked": True, "until": None, "purpose": "", "since": None}
        self._start(is_locked=True)
        with patch("ds.state.read_lock", return_value=timed):
            feedback.opened("X")
        feedback._banner_at.clear()
        with patch("ds.state.read_lock", return_value=open_ended):
            feedback.opened("X")
        opened = [n for n in self.notices if n[0] == "X opened in the distraction space"]
        self.assertEqual([(n[1], n[2]) for n in opened], [
            (f"Locked until {want}.", [feedback._CLI, "enter"]),
            ("Locked until you unlock.", [feedback._CLI, "enter"]),
        ])

    def test_r10_opened_respects_app_banner_nudge_and_the_space(self):
        hypr.apply_rules([expand_entry("X")])
        with self.subTest("nudge off"):
            self._start(config={"nudges": {"app_banner": False, "block_page": True},
                                "site_block": {"pass_through": False}})
            feedback.opened("X")
            self.assertEqual(self.notices, [])
            self.assertEqual(self._banner_lines(), [])
        self._start()
        with self.subTest("on the space"):
            self._active_workspace(hypr.SPACE)
            feedback.opened("X")
            self.assertEqual(self.notices, [])
            self.assertEqual(self._banner_lines(), [])
        with self.subTest("workspace unknown"):
            os.environ["DS_HYPR_FAIL"] = "activeworkspace"
            feedback.opened("X")
            self.assertEqual(self.notices, [])
            self.assertEqual(self._banner_lines(), [])
            self.assertIn("on_space unknown; skipping banner",
                          state.state_path("log").read_text(encoding="utf-8"))

    def test_r10_banner_survives_an_unwritable_log(self):
        self._list_hosts("x.com")
        path = state.state_path("log")
        if path.is_file():
            path.unlink()
        path.mkdir(parents=True, exist_ok=True)
        feedback.blocked("x.com")
        self.assertEqual(len(self._banners()), 1)

    def test_maybe_banner_shim_routes_to_blocked(self):
        self._list_hosts("x.com")
        feedback._maybe_banner("x.com")
        self.assertEqual(len(self._banners()), 1)
        self.assertEqual(self._banner_lines(), ["banner: host=x.com entry=x.com decision=shown"])


if __name__ == "__main__":
    unittest.main()
