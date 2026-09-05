#!/usr/bin/env python3
"""ds/cgroup.py: slice membership from /proc, the ancestor walk, and the slice start."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import cgroup

SLICE_PATH = "/user.slice/user-1000.slice/user@1000.service/app.slice/app-distraction.slice"
SESSION_PATH = "/user.slice/user-1000.slice/user@1000.service/session.slice/wayland-wm@hyprland.desktop.service"

SYSTEMCTL = r"""
import os, sys
from pathlib import Path
Path(os.environ["DS_SYSTEMCTL_LOG"]).open("a").write(" ".join(sys.argv[1:]) + "\n")
if os.environ.get("DS_SYSTEMCTL_FAIL"):
    sys.stderr.write("Failed to connect to bus: No medium found\n")
    sys.exit(1)
"""


class FakeProc:
    def __init__(self, root: Path):
        self.root = root

    def add(self, pid: int, ppid: int, cgroup_path: str | None, comm: str = "proc") -> None:
        d = self.root / str(pid)
        d.mkdir()
        rest = " ".join(["0"] * 50)
        (d / "stat").write_text(f"{pid} ({comm}) S {ppid} {pid} {pid} {rest}\n", encoding="utf-8")
        if cgroup_path is not None:
            (d / "cgroup").write_text(f"0::{cgroup_path}\n", encoding="utf-8")

    def chain(self, root_pid: int, length: int, first_pid: int = 500) -> int:
        """`length` descendants below root_pid, each outside the slice; returns the last pid."""
        parent = root_pid
        for i in range(length):
            pid = first_pid + i
            self.add(pid, parent, SESSION_PATH)
            parent = pid
        return parent


class CgroupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proc = FakeProc(Path(self.tmp.name))

    def test_cgroup_of_reads_the_unified_line(self):
        d = self.proc.root / "7"
        d.mkdir()
        (d / "cgroup").write_text(f"1:name=systemd:/legacy\n0::{SLICE_PATH}/run-3.scope\n", encoding="utf-8")
        self.assertEqual(cgroup.cgroup_of(7, self.proc.root), f"{SLICE_PATH}/run-3.scope")
        (d / "cgroup").write_text("1:name=systemd:/legacy\n", encoding="utf-8")
        self.assertIsNone(cgroup.cgroup_of(7, self.proc.root))
        self.assertIsNone(cgroup.cgroup_of(8, self.proc.root))

    def test_proc_root_override(self):
        self.proc.add(11, 1, SLICE_PATH)
        with Sandbox() as box:
            box.apply_env()
            os.environ["DS_PROC_ROOT"] = str(self.proc.root)
            try:
                self.assertTrue(cgroup.in_slice(11))
            finally:
                os.environ.pop("DS_PROC_ROOT", None)

    def test_in_slice_is_the_fifth_component(self):
        cases = [
            ("scope_in_slice", f"{SLICE_PATH}/run-1.scope", True),
            ("slice_itself", SLICE_PATH, True),
            ("session_service", SESSION_PATH, False),
            ("sibling_slice", "/user.slice/user-1000.slice/user@1000.service/app.slice/app-other.slice", False),
            ("slice_name_at_another_level", "/app-distraction.slice/run-1.scope", False),
            ("slice_name_too_deep", f"/x{SLICE_PATH}", False),
            ("no_cgroup_file", None, False),
        ]
        for i, (name, path, expected) in enumerate(cases):
            pid = 100 + i
            self.proc.add(pid, 1, path)
            with self.subTest(name):
                self.assertIs(cgroup.in_slice(pid, self.proc.root), expected)

    def test_ancestor_within_eight_hops_is_found_and_the_ninth_is_not(self):
        self.proc.add(1, 0, "/init.scope")
        self.proc.add(200, 1, SLICE_PATH)
        eighth = self.proc.chain(200, 8, first_pid=300)
        self.proc.add(400, 1, SLICE_PATH)
        ninth = self.proc.chain(400, 9, first_pid=500)
        self.assertTrue(cgroup.ancestor_in_slice(eighth, proc=self.proc.root))
        self.assertFalse(cgroup.ancestor_in_slice(ninth, proc=self.proc.root))
        self.assertTrue(cgroup.ancestor_in_slice(ninth, hops=9, proc=self.proc.root))
        # The walk starts at the pid itself.
        self.assertTrue(cgroup.ancestor_in_slice(200, hops=0, proc=self.proc.root))
        self.assertFalse(cgroup.ancestor_in_slice(300, hops=0, proc=self.proc.root))
        # A chain that ends at init, or in a pid that has already gone, is outside.
        self.assertFalse(cgroup.ancestor_in_slice(1, proc=self.proc.root))
        self.proc.add(600, 599, SESSION_PATH)
        self.assertFalse(cgroup.ancestor_in_slice(600, proc=self.proc.root))

    def test_unreadable_cgroup_file_is_outside(self):
        self.proc.add(20, 1, SLICE_PATH)
        (self.proc.root / "20" / "cgroup").chmod(0)
        self.addCleanup((self.proc.root / "20" / "cgroup").chmod, 0o644)
        if os.geteuid() == 0:
            self.skipTest("root reads through mode 0")
        self.assertIsNone(cgroup.cgroup_of(20, self.proc.root))
        self.assertFalse(cgroup.in_slice(20, self.proc.root))
        self.assertFalse(cgroup.ancestor_in_slice(20, proc=self.proc.root))

    def test_ppid_is_read_after_the_last_paren(self):
        self.proc.add(30, 1, SLICE_PATH)
        self.proc.add(31, 30, SESSION_PATH, comm="Web Content) (x")
        self.assertEqual(cgroup._ppid(31, self.proc.root), 30)
        self.assertTrue(cgroup.ancestor_in_slice(31, proc=self.proc.root))
        (self.proc.root / "31" / "stat").write_text("31 (broken", encoding="utf-8")
        self.assertIsNone(cgroup._ppid(31, self.proc.root))
        self.assertFalse(cgroup.ancestor_in_slice(31, proc=self.proc.root))

    def test_ensure_slice_starts_the_unit_as_the_person(self):
        with Sandbox() as box:
            box.apply_env()
            log = box.runtime / "systemctl.log"
            os.environ["DS_SYSTEMCTL_LOG"] = str(log)
            os.environ.pop("DS_SYSTEMCTL_FAIL", None)
            box.fake_bin("systemctl", SYSTEMCTL)
            try:
                self.assertTrue(cgroup.ensure_slice())
                self.assertEqual(log.read_text(encoding="utf-8"), "--user start app-distraction.slice\n")
                os.environ["DS_SYSTEMCTL_FAIL"] = "1"
                self.assertFalse(cgroup.ensure_slice())
                rc, err = cgroup.systemctl_user("stop", cgroup.SLICE)
                self.assertEqual(rc, 1)
                self.assertIn("Failed to connect to bus", err)
                (box.bin / "systemctl").unlink()
                os.environ["PATH"] = str(box.bin)
                self.assertFalse(cgroup.ensure_slice())
            finally:
                for key in ("DS_SYSTEMCTL_LOG", "DS_SYSTEMCTL_FAIL"):
                    os.environ.pop(key, None)

    def test_slice_path_matches_the_wrapper(self):
        self.assertEqual(
            cgroup.slice_path(1000),
            "user.slice/user-1000.slice/user@1000.service/app.slice/app-distraction.slice",
        )
        self.assertEqual("/" + cgroup.slice_path(1000), SLICE_PATH)


if __name__ == "__main__":
    unittest.main()
