#!/usr/bin/env python3
"""Off-space set drops addresses shared with a keep-reachable host."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# pbs.twimg.com and grok.com answer on the same Cloudflare anycast addresses.
SHARED = ["104.18.28.234", "104.18.29.234"]
TWIMG_ONLY = ["104.18.37.127", "146.75.116.159"]
X_APEX = ["172.66.0.227", "162.159.140.229"]


def load_mod():
    loader = SourceFileLoader("distractions", str(ROOT / "distractions"))
    spec = spec_from_loader("distractions", loader)
    assert spec is not None
    mod = module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class KeepReachableSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_mod()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir(parents=True)
        self.mod.state_dir = lambda: self.state
        self.mod.wrapper_present = lambda: True
        self.mod.load_config = lambda: {}
        self.mod.request_keep_reapply = lambda: None
        self.sent: list[str] = []

        def fake_sudo_nft(command: str, stdin_text: str = "") -> int:
            self.sent.append(stdin_text)
            return 0

        self.mod.sudo_nft = fake_sudo_nft

    def set_keep(self, addrs: set[str]) -> None:
        """Seed the carve-out the way a warm daemon holds it."""
        with self.mod._keep_lock:
            self.mod._keep_addrs = set(addrs)
            self.mod._keep_fetched_at = time.time()

    def keep_cache(self) -> list[str]:
        path = self.state / self.mod.KEEP_ADDRS_LAST_GOOD_NAME
        if not path.exists():
            return []
        return json.loads(path.read_text())["addrs"]

    def test_shared_address_leaves_the_set_and_x_stays_blocked(self) -> None:
        self.set_keep(set(SHARED))
        ok = self.mod.replace_ds(
            {"pbs.twimg.com": SHARED + TWIMG_ONLY, "x.com": X_APEX}
        )
        self.assertTrue(ok)
        installed = self.sent[0].split()
        for addr in SHARED:
            self.assertNotIn(addr, installed)
        for addr in TWIMG_ONLY + X_APEX:
            self.assertIn(addr, installed)

    def test_last_good_addrs_still_record_the_full_answer(self) -> None:
        self.set_keep(set(SHARED))
        self.mod.replace_ds({"pbs.twimg.com": SHARED + TWIMG_ONLY})
        saved = json.loads((self.state / self.mod.ADDRS_LAST_GOOD_NAME).read_text())
        self.assertEqual(saved["pbs.twimg.com"], SHARED + TWIMG_ONLY)

    def test_a_fresh_answer_is_written_to_the_cache(self) -> None:
        self.mod.lookup_addresses = lambda host: list(SHARED)
        self.assertEqual(self.mod.refresh_keep_addrs(), set(SHARED))
        self.assertEqual(self.keep_cache(), sorted(SHARED))

    def test_dns_failure_falls_back_to_the_cache(self) -> None:
        self.mod.lookup_addresses = lambda host: list(SHARED)
        self.mod.refresh_keep_addrs()

        def boom(_host: str):
            raise OSError("dns down")

        self.mod.lookup_addresses = boom
        self.assertEqual(self.mod.refresh_keep_addrs(), set(SHARED))
        self.assertEqual(self.keep_cache(), sorted(SHARED))

    def test_an_empty_carve_out_still_applies_the_block(self) -> None:
        self.set_keep(set())
        self.assertTrue(self.mod.replace_ds({"x.com": X_APEX}))
        self.assertIn("172.66.0.227", self.sent[0].split())


class ApplyPathLatencyTests(unittest.TestCase):
    """Entering the distraction space queues a flush behind the worker.

    A carve-out lookup that stalls on the apply path would keep X blocked on
    the one space that is meant to allow it, so the cache must answer directly.
    """

    def setUp(self) -> None:
        self.mod = load_mod()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir(parents=True)
        self.mod.state_dir = lambda: self.state
        self.mod.load_config = lambda: {}
        self.mod.request_keep_reapply = lambda: None

    def settle(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.mod._keep_lock:
                if not self.mod._keep_refreshing:
                    return
            time.sleep(0.01)
        self.fail("refresh thread did not finish")

    def test_a_cold_start_returns_at_once_and_fills_in_behind(self) -> None:
        self.mod.lookup_addresses = lambda host: ["104.18.28.234"]
        start = time.monotonic()
        first = self.mod.keep_reachable_addrs()
        self.assertLess(time.monotonic() - start, 1.0, "cold apply waited on DNS")
        self.assertEqual(first, set())
        self.settle()
        self.assertEqual(self.mod.keep_reachable_addrs(), {"104.18.28.234"})

    def test_a_warm_cache_does_no_dns_at_all(self) -> None:
        calls: list[str] = []

        def resolver(host: str):
            calls.append(host)
            return ["104.18.28.234"]

        self.mod.lookup_addresses = resolver
        self.mod.keep_reachable_addrs()
        self.settle()
        calls.clear()
        for _ in range(5):
            self.assertEqual(self.mod.keep_reachable_addrs(), {"104.18.28.234"})
        self.assertEqual(calls, [])

    def test_a_hanging_resolver_does_not_stall_a_warm_apply(self) -> None:
        self.mod.lookup_addresses = lambda host: ["104.18.28.234"]
        self.mod.keep_reachable_addrs()
        self.settle()
        self.mod._keep_fetched_at = 0.0  # force stale

        release = threading.Event()
        self.addCleanup(release.set)
        self.mod.lookup_addresses = lambda host: (release.wait(30), [])[1]

        start = time.monotonic()
        addrs = self.mod.keep_reachable_addrs()
        elapsed = time.monotonic() - start
        self.assertEqual(addrs, {"104.18.28.234"})
        self.assertLess(elapsed, 1.0, "apply path waited on DNS")

    def test_a_refresh_that_changes_the_set_asks_for_a_reapply(self) -> None:
        asked: list[bool] = []
        self.mod.request_keep_reapply = lambda: asked.append(True)
        self.mod.lookup_addresses = lambda host: ["104.18.28.234"]
        self.mod.keep_reachable_addrs()
        self.settle()
        self.assertEqual(asked, [True])

        # An unchanged answer must not queue more work.
        self.mod._keep_fetched_at = 0.0
        self.mod.keep_reachable_addrs()
        self.settle()
        self.assertEqual(asked, [True])

    def test_a_reapply_is_not_requested_on_the_distraction_space(self) -> None:
        self.mod = load_mod()
        self.mod.state_dir = lambda: self.state
        self.mod.load_config = lambda: {}
        self.mod.on_distractions = lambda: True
        asked: list[str] = []
        self.mod.ensure_net_worker = lambda: asked.append("worker")
        self.mod.request_keep_reapply()
        self.assertEqual(asked, [])



if __name__ == "__main__":
    unittest.main()
