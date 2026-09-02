#!/usr/bin/env python3
"""distractions-nft render and argv/stdin contract."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT

WRAPPER = ROOT / "distractions-nft"

FAKE_NFT = r"""
import os, sys
from pathlib import Path
root = Path(os.environ["NFT_FAKE"])
script = sys.stdin.read()
(root / "argv.log").write_text("\n".join(sys.argv[1:]))
(root / "stdin.log").write_text(script)
(root / "calls.log").open("a").write("1\n")
"""


def load_nft():
    loader = SourceFileLoader("distractions_nft", str(WRAPPER))
    spec = spec_from_loader("distractions_nft", loader)
    mod = module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class NftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.bin / "nft"
        fake.write_text("#!/usr/bin/env python3\n" + FAKE_NFT, encoding="utf-8")
        fake.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = f"{self.bin}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["NFT_FAKE"] = str(self.root)
        self.nft = load_nft()

    def run_wrapper(self, args, stdin=""):
        return subprocess.run(
            [sys.executable, str(WRAPPER), *args],
            input=stdin,
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        )

    def stdin_log(self):
        path = self.root / "stdin.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_render_has_redirect_per_family_and_reject(self):
        script = self.nft.render_table(["203.0.113.5"], ["2001:db8::5"])
        self.assertIn("chain output_nat", script)
        self.assertIn("type nat hook output priority dstnat", script)
        self.assertIn("ip daddr @omarchy_ds_v4 tcp dport 80 redirect to :28080", script)
        self.assertIn("ip daddr @omarchy_ds_v4 tcp dport 443 redirect to :28443", script)
        self.assertIn("ip6 daddr @omarchy_ds_v6 tcp dport 80 redirect to :28080", script)
        self.assertIn("ip6 daddr @omarchy_ds_v6 tcp dport 443 redirect to :28443", script)
        self.assertIn("ip daddr @omarchy_ds_v4 meta l4proto tcp reject with tcp reset", script)
        self.assertIn("ip6 daddr @omarchy_ds_v6 meta l4proto tcp reject with tcp reset", script)
        self.assertIn("ip daddr @omarchy_ds_v4 reject\n", script)
        self.assertIn("ip6 daddr @omarchy_ds_v6 reject\n", script)
        self.assertNotIn(" drop\n", script)
        self.assertNotIn(" drop;", script)
        result = self.run_wrapper(["replace", "ds"], "203.0.113.5\n2001:db8::5\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        logged = self.stdin_log()
        self.assertIn("redirect to :28080", logged)
        self.assertIn("meta l4proto tcp reject with tcp reset", logged)

    def test_splice_source_port_accept_precedes_redirect_and_reject(self):
        script = self.nft.render_table(["203.0.113.5"], ["2001:db8::5"])
        filter_body = script[
            script.index("chain output {") : script.index("chain output_nat {")
        ]
        nat_body = script[script.index("chain output_nat {") :]
        first_rules = (
            "\n    meta nfproto ipv4 tcp sport 61000-61999 accept"
            "\n    meta nfproto ipv6 tcp sport 61000-61999 accept\n"
        )
        for body, type_line, chain in (
            (
                filter_body,
                "type filter hook output priority filter; policy accept;",
                "output",
            ),
            (
                nat_body,
                "type nat hook output priority dstnat; policy accept;",
                "output_nat",
            ),
        ):
            with self.subTest(chain=chain, check="first_rules"):
                after_type = body[body.index(type_line) + len(type_line) :]
                self.assertTrue(after_type.startswith(first_rules), after_type[:200])
        families = (
            (
                "ipv4",
                "meta nfproto ipv4 tcp sport 61000-61999 accept",
                "ip daddr @omarchy_ds_v4",
            ),
            (
                "ipv6",
                "meta nfproto ipv6 tcp sport 61000-61999 accept",
                "ip6 daddr @omarchy_ds_v6",
            ),
        )
        for family, accept, daddr in families:
            with self.subTest(family=family, chain="output"):
                self.assertLess(
                    filter_body.index(accept),
                    filter_body.index(f"{daddr} meta l4proto tcp reject with tcp reset"),
                )
                self.assertLess(
                    filter_body.index(accept),
                    filter_body.index(f"{daddr} reject\n"),
                )
            with self.subTest(family=family, chain="output_nat"):
                self.assertLess(
                    nat_body.index(accept),
                    nat_body.index(f"{daddr} tcp dport 80 redirect"),
                )
                self.assertLess(
                    nat_body.index(accept),
                    nat_body.index(f"{daddr} tcp dport 443 redirect"),
                )

    def test_empty_sets_render_table_that_matches_nothing(self):
        script = self.nft.render_table([], [])
        self.assertIn("table inet omarchy_ds", script)
        self.assertIn("set omarchy_ds_v4", script)
        self.assertIn("set omarchy_ds_v6", script)
        self.assertNotIn("elements =", script)
        result = self.run_wrapper(["flush", "ds"])
        self.assertEqual(result.returncode, 0, result.stderr)
        logged = self.stdin_log()
        self.assertNotIn("elements =", logged)
        self.assertIn("ip daddr @omarchy_ds_v4 reject", logged)

    def test_refuses_argv_outside_contract(self):
        cases = [
            [],
            ["replace"],
            ["replace", "ds", "extra"],
            ["flush", "other"],
            ["replace", "OTHER"],
            ["drop", "ds"],
            ["replace", "ds", "ds"],
        ]
        for args in cases:
            with self.subTest(args=args):
                result = self.run_wrapper(args, "203.0.113.1\n")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse((self.root / "stdin.log").exists())

    def test_refuses_stdin_outside_contract(self):
        for token in ("example.com", "/etc/passwd", "203.0.113.0/24", "not_an_ip", "::1/128"):
            with self.subTest(token=token):
                result = self.run_wrapper(["replace", "ds"], token + "\n")
                self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((self.root / "calls.log").exists())

    def test_flush_rejects_non_whitespace_stdin(self):
        result = self.run_wrapper(["flush", "ds"], "203.0.113.1\n")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("flush takes no stdin", result.stderr)
        self.assertFalse((self.root / "calls.log").exists())
        blank = self.run_wrapper(["flush", "ds"], "  \n\t\n")
        self.assertEqual(blank.returncode, 0, blank.stderr)
        self.assertTrue((self.root / "calls.log").exists())

    def test_nft_check_skips_without_cap(self):
        nft = shutil.which("nft")
        if not nft:
            self.skipTest("nft not on PATH")
        script = self.nft.render_table(["203.0.113.8"], ["2001:db8::8"])
        result = subprocess.run(
            [nft, "-c", "-f", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        err = (result.stderr or "") + (result.stdout or "")
        if result.returncode != 0:
            lowered = err.lower()
            if any(w in lowered for w in ("permission", "operation not permitted", "netlink", "cap_net")):
                return
            self.fail(f"nft -c rejected ruleset: {err}")


if __name__ == "__main__":
    unittest.main()
