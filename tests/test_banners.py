#!/usr/bin/env python3
"""banners: newest banner provenance lines from the state log."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Sandbox

BANNER_A = (
    "2026-09-02T20:29:37+00:00 banner: host=x.com entry=X port=51234 "
    "pid=4321 exe=firefox class=firefox ws=1 decision=shown"
)
BANNER_B = (
    "2026-09-02T20:29:38+00:00 banner: host=x.com entry=X port=51240 "
    "pid=- exe=- class=- ws=- decision=unattributed"
)
BANNER_C = (
    "2026-09-02T20:29:39+00:00 banner: host=x.com entry=X port=51241 "
    "pid=4322 exe=firefox class=firefox ws=1 decision=shown dropped=3"
)

MIXED_LOG = "\n".join(
    [
        "2026-09-02T20:29:36+00:00 hyprctl clients: 3 windows",
        BANNER_A,
        "2026-09-02T20:29:37+00:00 hyprctl clients: 4 windows",
        "",
        BANNER_B,
        BANNER_C,
    ]
) + "\n"


class BannersTests(unittest.TestCase):
    def _box(self, isolate_path=False) -> Sandbox:
        box = Sandbox(isolate_path=isolate_path)
        self.addCleanup(box.cleanup)
        return box

    def _write_mixed(self, box: Sandbox) -> Path:
        path = box.state_dir / "log"
        path.write_text(MIXED_LOG, encoding="utf-8")
        return path

    def test_mixed_log_prints_banner_lines_newest_first(self):
        box = self._box()
        self._write_mixed(box)
        r = box.run("banners")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [BANNER_C, BANNER_B, BANNER_A])

    def test_count_limits_output(self):
        box = self._box()
        self._write_mixed(box)
        r = box.run("banners", "--count", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [BANNER_C, BANNER_B])

    def test_default_count_is_20(self):
        box = self._box()
        lines = [
            (
                f"2026-09-02T20:29:{i:02d}+00:00 banner: host=x.com entry=X "
                f"port={50000 + i} pid=1 exe=firefox class=firefox ws=1 decision=shown"
            )
            for i in range(25)
        ]
        (box.state_dir / "log").write_text("\n".join(lines) + "\n", encoding="utf-8")
        r = box.run("banners")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), list(reversed(lines[-20:])))

    def test_empty_log_prints_nothing(self):
        box = self._box()
        (box.state_dir / "log").write_text("", encoding="utf-8")
        r = box.run("banners")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_missing_log_prints_nothing(self):
        box = self._box()
        r = box.run("banners")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_invalid_count_exits_2(self):
        box = self._box()
        for v in ("0", "-1", "abc"):
            with self.subTest(v=v):
                r = box.run("banners", "--count", v)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertEqual(r.stdout, "")

    def test_unreadable_log_prints_nothing(self):
        if os.geteuid() == 0:
            self.skipTest("root can read mode 0o000")
        box = self._box()
        path = box.state_dir / "log"
        path.write_text(MIXED_LOG, encoding="utf-8")
        os.chmod(path, 0o000)
        self.addCleanup(os.chmod, path, 0o644)
        r = box.run("banners")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
