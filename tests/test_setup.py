#!/usr/bin/env python3
"""Privileged setup must not list /etc/sudoers.d."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_mod():
    loader = SourceFileLoader("distractions_setup", str(ROOT / "distractions"))
    spec = spec_from_loader("distractions_setup", loader)
    assert spec is not None
    mod = module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class SetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ.setdefault("HOME", self.tmp.name)
        self.mod = load_mod()
        self.calls: list[list[str]] = []

    def test_readme_does_not_ls_sudoers(self):
        text = (ROOT / "README.md").read_text()
        self.assertIn("distractions setup", text)
        self.assertNotIn("ls ", text)
        self.assertIn("sudo -n", text)
        self.assertNotIn("chmod 0644 /etc/sudoers.d/", text)

    def test_refuses_non_tty(self):
        with mock.patch.object(self.mod, "_wrapper_grant_ok", return_value=False):
            with mock.patch.object(self.mod, "_setup_has_tty", return_value=False):
                with self.assertRaises(SystemExit) as ctx:
                    self.mod.setup_privileged_helper()
        self.assertIn("terminal", str(ctx.exception))

    def test_already_installed_skips_sudo(self):
        with mock.patch.object(self.mod, "_wrapper_grant_ok", return_value=True):
            with mock.patch.object(self.mod, "subprocess") as sp:
                self.mod.setup_privileged_helper()
        sp.run.assert_not_called()

    def test_one_sudo_and_verifies_without_listing_sudoers(self):
        dest = Path(self.tmp.name) / "wrapper"
        sudoers = Path(self.tmp.name) / "sudoers"
        self.mod.NFT_WRAPPER = str(dest)
        self.mod.SUDOERS_PATH = str(sudoers)

        def fake_run(cmd, **kwargs):
            argv = [str(part) for part in cmd]
            self.calls.append(argv)
            if argv[:1] == ["visudo"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="parsed OK\n", stderr="")
            if argv[:1] == ["sudo"] and argv[1:2] != ["-n"]:
                dest.write_text("wrapper\n")
                dest.chmod(0o755)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if argv[:2] == ["sudo", "-n"]:
                self.assertEqual(argv[2], str(dest))
                self.assertNotIn("/etc/sudoers.d", " ".join(argv))
                return subprocess.CompletedProcess(
                    cmd, 2, stdout="usage: distractions-nft replace|flush ds\n", stderr=""
                )
            raise AssertionError(argv)

        with mock.patch.object(self.mod, "_wrapper_grant_ok", side_effect=[False, True]):
            with mock.patch.object(self.mod, "_setup_has_tty", return_value=True):
                with mock.patch.object(self.mod.subprocess, "run", fake_run):
                    self.mod.setup_privileged_helper()
        joined = [" ".join(c) for c in self.calls]
        self.assertTrue(any(c[0] == "visudo" for c in self.calls))
        self.assertTrue(any(c[:1] == ["sudo"] and c[1:2] != ["-n"] for c in self.calls))
        self.assertFalse(any(part == "ls" or part.startswith("ls ") for c in self.calls for part in c))
        self.assertFalse(any("/etc/sudoers.d" in row for row in joined))


if __name__ == "__main__":
    unittest.main()
