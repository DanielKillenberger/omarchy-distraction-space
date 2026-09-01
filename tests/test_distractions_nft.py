#!/usr/bin/env python3
"""Wrapper tests against a fake nft binary."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "distractions-nft"

FAKE_NFT = r"""#!/usr/bin/env python3
import os, sys
from pathlib import Path
root = Path(os.environ["NFT_FAKE"])
(root / "argv.log").write_text("\n".join(sys.argv[1:]))
(root / "stdin.log").write_text(sys.stdin.read())
(root / "calls.log").open("a").write("1\n")
"""


class WrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.bin / "nft"
        fake.write_text(FAKE_NFT)
        fake.chmod(0o755)
        os.environ["NFT_FAKE"] = str(self.root)
        self.env = os.environ.copy()
        self.env["PATH"] = f"{self.bin}:{self.env.get('PATH', '')}"
        self.env["NFT_FAKE"] = str(self.root)

    def run_wrapper(self, args: list[str], stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(WRAPPER), *args],
            input=stdin,
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        )

    def stdin(self) -> str:
        path = self.root / "stdin.log"
        return path.read_text() if path.exists() else ""

    def call_count(self) -> int:
        path = self.root / "calls.log"
        if not path.exists():
            return 0
        return len([line for line in path.read_text().splitlines() if line.strip()])

    def test_replace_accepts_ipv4_and_ipv6(self):
        result = self.run_wrapper(
            ["replace", "ds"],
            "203.0.113.5\n2001:db8::5\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        script = self.stdin()
        self.assertIn("table inet omarchy_ds", script)
        self.assertIn("set omarchy_ds_v4", script)
        self.assertIn("set omarchy_ds_v6", script)
        self.assertIn("203.0.113.5", script)
        self.assertIn("2001:db8::5", script)
        self.assertIn("ip daddr @omarchy_ds_v4 drop", script)
        self.assertIn("ip6 daddr @omarchy_ds_v6 drop", script)
        self.assertIn("hook output", script)
        self.assertEqual(self.call_count(), 1)

    def test_rejects_hostname_and_path(self):
        host = self.run_wrapper(["replace", "ds"], "example.com\n")
        self.assertNotEqual(host.returncode, 0)
        self.assertEqual(self.call_count(), 0)
        path = self.run_wrapper(["replace", "ds"], "/etc/passwd\n")
        self.assertNotEqual(path.returncode, 0)
        self.assertEqual(self.call_count(), 0)

    def test_rejects_non_ds_target(self):
        result = self.run_wrapper(["replace", "other"], "203.0.113.5\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only target ds", result.stderr)
        self.assertEqual(self.call_count(), 0)

    def test_table_confinement(self):
        result = self.run_wrapper(["replace", "ds"], "198.51.100.8\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        script = self.stdin()
        self.assertEqual(script.count("table "), 1)
        self.assertIn("table inet omarchy_ds", script)
        self.assertNotIn("inet filter", script)
        self.assertNotIn("ip filter", script)

    def test_one_transaction_for_both_sets(self):
        result = self.run_wrapper(["flush", "ds"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.call_count(), 1)
        argv = (self.root / "argv.log").read_text().splitlines()
        self.assertEqual(argv, ["-f", "-"])
        script = self.stdin()
        self.assertIn("set omarchy_ds_v4", script)
        self.assertIn("set omarchy_ds_v6", script)
        self.assertIn("hook output", script)


if __name__ == "__main__":
    unittest.main()
