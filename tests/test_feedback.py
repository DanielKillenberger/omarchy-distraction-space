#!/usr/bin/env python3
"""HTTP block page and TLS SNI catcher."""

from __future__ import annotations

import os
import socket
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import feedback

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


if __name__ == "__main__":
    unittest.main()
