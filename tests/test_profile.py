#!/usr/bin/env python3
"""ds/profile.py: `distractions profile import` against fixture profiles and a fake /proc.

The source profile sits under the sandbox's `XDG_CONFIG_HOME`, the destination
under the sandbox home, running-browser checks read `DS_PROC_ROOT`, and
`xdg-settings` is a fake on PATH. Nothing touches the real home or /proc.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Sandbox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ds import launch, profile, state

XDG_SETTINGS = r"""
import os, sys
if sys.argv[1:3] == ["get", "default-web-browser"]:
    print(os.environ.get("DS_XDG_BROWSER", "google-chrome.desktop"))
    sys.exit(0)
sys.exit(1)
"""

KEPT = ("Preferences", "Cookies", "Extensions/abc/manifest.json", "Service Worker/Database/y", "Local Storage/leveldb/000.log")
# What Chrome writes: the prompt on, plus a key the import must carry over untouched.
PREFERENCES = b'{"browser": {"check_default_browser": true, "show_home_button": true}, "profile": {"name": "Person 1"}}'
SKIPPED = (
    "Cache/data_0", "Code Cache/js/x", "GPUCache/x", "DawnCache/x", "DawnGraphiteCache/x", "DawnWebGPUCache/x",
    "ShaderCache/x", "GrShaderCache/x", "Service Worker/CacheStorage/x", "Service Worker/ScriptCache/x",
    "SingletonCookie", "SingletonSocket",
)


def make_profile(root: Path) -> int:
    """A Chromium-shaped profile at `root`; returns the byte count of the files an import keeps."""
    kept = 0
    for rel in KEPT:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(PREFERENCES if rel == "Preferences" else rel.encode() * 3)
        kept += p.stat().st_size
    for rel in SKIPPED:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"regenerable")
    os.symlink("otherhost-1", root / "SingletonLock")
    os.symlink("Cookies", root / "CookiesLink")
    return kept


def preferences(profile: Path) -> dict:
    return json.loads((profile / "Preferences").read_text(encoding="utf-8"))


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.box.fake_bin("xdg-settings", XDG_SETTINGS)
        self.proc = self.box.runtime / "proc"
        self.proc.mkdir()
        self._orig = {k: os.environ.get(k) for k in ("DS_PROC_ROOT", "DS_XDG_BROWSER", "XDG_DATA_HOME")}
        os.environ["DS_PROC_ROOT"] = str(self.proc)
        os.environ["DS_XDG_BROWSER"] = "google-chrome.desktop"
        # The harness pins XDG_DATA_HOME under the sandbox; the destination must
        # never resolve to the real profile, and the assertion below proves it.
        self.addCleanup(self._restore)
        self.user_data = profile.config_home() / "google-chrome"
        self.src = self.user_data / profile.MAIN_PROFILE
        self.dst = launch.profile_dir() / launch.PROFILE
        for path in (self.src, self.dst, self.proc):
            assert self.box.home.parent in path.parents, f"{path} is outside the sandbox"
        self.tmp = self.dst.with_name(f"{launch.PROFILE}.import-{os.getpid()}")

    def _restore(self):
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def add_proc(self, pid: int, argv: list[str]) -> None:
        d = self.proc / str(pid)
        d.mkdir()
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")

    def run_import(self, source=None, replace=False):
        """`cmd_import` in-process: (rc, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = profile.cmd_import(argparse.Namespace(source=source, replace=replace))
        return rc, out.getvalue(), err.getvalue()

    def assert_untouched(self):
        self.assertFalse(self.dst.exists(), "the destination was created")
        self.assertFalse(self.tmp.exists(), "the temporary sibling was left behind")

    def assert_imported_preferences(self, profile):
        """The copied `Preferences`: the prompt off, every other key as Chrome wrote it (R5)."""
        prefs = preferences(profile)
        self.assertIs(prefs["browser"]["check_default_browser"], False)
        self.assertIs(prefs["browser"]["show_home_button"], True)
        self.assertEqual(prefs["profile"], {"name": "Person 1"})

    # --- R1 -------------------------------------------------------------------

    def test_import_copies_the_profile_minus_caches_through_a_sibling(self):
        kept = make_profile(self.src)
        r = self.box.run("profile", "import")
        self.assertEqual(r.returncode, 0, r.stderr)
        for rel in KEPT[1:]:
            self.assertEqual((self.dst / rel).read_bytes(), rel.encode() * 3, rel)
        self.assert_imported_preferences(self.dst)
        self.assertEqual((self.src / "Preferences").read_bytes(), PREFERENCES, "the source Preferences was modified")
        for rel in SKIPPED:
            self.assertFalse((self.dst / rel).exists(), rel)
        self.assertFalse((self.dst / "Cache").exists())
        self.assertFalse((self.dst / "Service Worker" / "CacheStorage").exists())
        self.assertFalse((self.dst / "SingletonLock").is_symlink())
        self.assertEqual(os.readlink(self.dst / "CookiesLink"), "Cookies")
        self.assertFalse(self.tmp.exists())
        self.assertFalse(list(self.dst.parent.glob("Distraction.import-*")))
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0], str(self.dst))
        self.assertIn(f"{kept} bytes copied from {self.src}", lines[1])
        self.assertIn("signed in twice", lines[2])
        self.assertIn(f"{kept} bytes in", r.stderr)
        self.assertEqual((self.src / "Cookies").read_bytes(), b"Cookies" * 3, "the source was modified")

    def test_source_without_preferences_is_refused(self):
        other = self.box.home / "not-a-profile"
        other.mkdir()
        (other / "Cookies").write_bytes(b"x")
        rc, _out, err = self.run_import(source=str(other))
        self.assertEqual(rc, 1)
        self.assertIn(str(other), err)
        self.assertIn("Preferences", err)
        self.assert_untouched()

    def test_non_chromium_default_is_refused_unless_from_names_a_profile(self):
        os.environ["DS_XDG_BROWSER"] = "firefox.desktop"
        make_profile(self.src)
        rc, _out, err = self.run_import()
        self.assertEqual(rc, 1)
        self.assertIn("firefox.desktop", err)
        self.assertIn("Chromium-family", err)
        self.assertIn("--from", err)
        self.assert_untouched()
        rc, _out, err = self.run_import(source=str(self.src))
        self.assertEqual(rc, 0, err)
        self.assertTrue((self.dst / "Preferences").is_file())

    def test_source_for_follows_the_browser_open_would_pick(self):
        home = profile.config_home()
        cases = [
            ("omarchy_default", {}, "brave-browser.desktop", None, home / "BraveSoftware" / "Brave-Browser" / "Default"),
            ("previous_handler", {}, launch.HANDLER_ID, "chromium.desktop", home / "chromium" / "Default"),
            ("config_argv", {"browser": ["/usr/bin/microsoft-edge-stable"]}, "firefox.desktop", None, home / "microsoft-edge" / "Default"),
            ("vivaldi", {}, "vivaldi-stable.desktop", None, home / "vivaldi" / "Default"),
            ("opera_profile_is_its_root", {}, "opera.desktop", None, home / "opera"),
            ("helium", {}, "helium.desktop", None, home / "net.imput.helium" / "Default"),
        ]
        for name, cfg, default, previous, want in cases:
            with self.subTest(name):
                os.environ["DS_XDG_BROWSER"] = default
                state.write_entries({"files": [], "previous_handler": previous})
                self.assertEqual(profile.source_for(cfg), want)
        os.environ["DS_XDG_BROWSER"] = launch.HANDLER_ID
        state.write_entries({"files": [], "previous_handler": "firefox.desktop"})
        with self.assertRaises(profile.Refused) as cm:
            profile.source_for({})
        self.assertIn("firefox.desktop", str(cm.exception))
        # The user-data directory and the process names follow the layout.
        (home / "opera").mkdir()
        self.assertEqual(profile.user_data_dir_of((home / "opera").resolve()), ((home / "opera").resolve(), "opera"))
        self.assertEqual(profile.user_data_dir_of(self.src.resolve()), (self.user_data.resolve(), "google-chrome"))
        elsewhere = self.box.home / "other" / "Default"
        self.assertEqual(profile.user_data_dir_of(elsewhere), (elsewhere.parent, None))

    def test_source_that_is_or_contains_the_destination_is_refused(self):
        make_profile(self.dst)
        (self.dst.parent / "Preferences").write_bytes(b"{}")
        make_profile(self.dst / "Nested")
        for name, source in (("same", self.dst), ("contains", self.dst.parent), ("inside", self.dst / "Nested")):
            with self.subTest(name):
                rc, _out, err = self.run_import(source=str(source))
                self.assertEqual(rc, 1)
                self.assertIn(str(self.dst), err)
                self.assertFalse(self.tmp.exists())
        self.assertTrue((self.dst / "Cookies").is_file(), "the existing profile was touched")

    # --- R2 -------------------------------------------------------------------

    def test_running_browser_refuses_before_any_byte_moves(self):
        make_profile(self.src)
        distraction = launch.profile_dir()
        cases = [
            ("source_user_data_dir", ["/opt/google/chrome/chrome", f"--user-data-dir={self.user_data}"], "source browser"),
            ("source_default_dir", ["/opt/google/chrome/chrome", "--type=renderer"], "source browser"),
            ("distraction", ["/opt/google/chrome/chrome", f"--user-data-dir={distraction}", "--profile-directory=Distraction"], "distraction browser"),
        ]
        for name, argv, who in cases:
            with self.subTest(name):
                self.add_proc(4242, argv)
                try:
                    rc, _out, err = self.run_import()
                finally:
                    (self.proc / "4242" / "cmdline").unlink()
                    (self.proc / "4242").rmdir()
                self.assertEqual(rc, 1)
                self.assertIn(who, err)
                self.assertIn("4242", err)
                self.assert_untouched()
        # A Chrome on some other directory, and a process of another user, are neither.
        self.add_proc(4243, ["/opt/google/chrome/chrome", "--user-data-dir=/elsewhere"])
        self.add_proc(4244, ["/opt/google/chrome/chrome"])
        with mock.patch.object(profile.os, "getuid", return_value=os.getuid() + 1):
            self.assertIsNone(profile.is_running(self.user_data, names=profile.BROWSERS["google-chrome"][1]))
        (self.proc / "4244" / "cmdline").unlink()
        (self.proc / "4244").rmdir()
        rc, _out, err = self.run_import()
        self.assertEqual(rc, 0, err)

    def test_relative_or_symlinked_source_reaches_the_same_running_check(self):
        make_profile(self.src)
        link = self.box.home / "chrome-link"
        os.symlink(self.user_data, link)
        cwd = os.getcwd()
        os.chdir(self.box.home)
        self.addCleanup(os.chdir, cwd)
        self.add_proc(4242, ["/opt/google/chrome/chrome", f"--user-data-dir={link}/"])
        for name, source in (
            ("relative", os.path.relpath(self.src, self.box.home)),
            ("symlinked", str(link / profile.MAIN_PROFILE)),
        ):
            with self.subTest(name):
                rc, _out, err = self.run_import(source=source)
                self.assertEqual(rc, 1)
                self.assertIn("source browser", err)
                self.assertIn(str(self.user_data.resolve()), err)
                self.assert_untouched()

    def test_singleton_lock_counts_only_when_its_pid_is_alive_here(self):
        make_profile(self.src)
        lock = self.user_data / "SingletonLock"
        host = socket.gethostname()
        for name, target, live, running in (
            ("stale", f"{host}-777", False, False),
            ("foreign_host", f"not-{host}-777", True, False),
            ("live", f"{host}-777", True, True),
        ):
            with self.subTest(name):
                if lock.is_symlink():
                    lock.unlink()
                os.symlink(target, lock)
                if live and not (self.proc / "777").exists():
                    self.add_proc(777, ["/bin/sleep", "1"])
                why = profile.is_running(self.user_data)
                if running:
                    self.assertIn("SingletonLock", why)
                    self.assertIn("777", why)
                    rc, _out, err = self.run_import()
                    self.assertEqual(rc, 1)
                    self.assertIn("source browser", err)
                    self.assert_untouched()
                else:
                    self.assertIsNone(why)

    # --- R3 -------------------------------------------------------------------

    def test_existing_destination_needs_replace(self):
        make_profile(self.src)
        self.dst.mkdir(parents=True)
        (self.dst / "Preferences").write_bytes(b"old")
        rc, _out, err = self.run_import()
        self.assertEqual(rc, 1)
        self.assertIn(str(self.dst), err)
        self.assertIn("--replace", err)
        self.assertEqual((self.dst / "Preferences").read_bytes(), b"old")
        self.assertFalse(self.tmp.exists())
        self.assertFalse(list(self.dst.parent.glob("Distraction.bak-*")))

    def test_replace_renames_the_existing_profile_and_never_deletes_it(self):
        make_profile(self.src)
        self.dst.mkdir(parents=True)
        (self.dst / "Preferences").write_bytes(b"old")
        (self.dst / "Cookies").write_bytes(b"post-upgrade logins")
        rc, _out, err = self.run_import(replace=True)
        self.assertEqual(rc, 0, err)
        backups = list(self.dst.parent.glob("Distraction.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertRegex(backups[0].name, r"^Distraction\.bak-\d{8}-\d{6}$")
        self.assertEqual((backups[0] / "Cookies").read_bytes(), b"post-upgrade logins")
        self.assert_imported_preferences(self.dst)
        self.assertIn(str(backups[0]), err)
        self.assertFalse(self.tmp.exists())

    def test_symlinked_destination_is_checked_and_moved_as_the_link(self):
        make_profile(self.src)
        target = self.box.home / "elsewhere" / "Profile"
        target.mkdir(parents=True)
        (target / "Preferences").write_bytes(b"old")
        self.dst.parent.mkdir(parents=True)
        os.symlink(target, self.dst)
        # The running check is against the directory `open` passes, not the link's target.
        self.add_proc(4242, ["/opt/google/chrome/chrome", f"--user-data-dir={self.dst.parent}"])
        rc, _out, err = self.run_import(replace=True)
        self.assertEqual(rc, 1)
        self.assertIn("distraction browser", err)
        self.assertTrue(self.dst.is_symlink())
        (self.proc / "4242" / "cmdline").unlink()
        (self.proc / "4242").rmdir()
        rc, _out, err = self.run_import(replace=True)
        self.assertEqual(rc, 0, err)
        backups = list(self.dst.parent.glob("Distraction.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].is_symlink(), "the backup is the target, not the link")
        self.assertEqual(Path(os.readlink(backups[0])), target)
        self.assertEqual((target / "Preferences").read_bytes(), b"old", "the link target was moved or written")
        self.assertFalse(self.dst.is_symlink())
        self.assert_imported_preferences(self.dst)

    def test_failed_copy_keeps_the_backup_and_the_sibling(self):
        make_profile(self.src)
        self.dst.mkdir(parents=True)
        (self.dst / "Preferences").write_bytes(b"old")
        real = profile._copy_file

        def failing(s, d):
            if Path(s).name == "Cookies":
                raise OSError(28, "No space left on device")
            return real(s, d)

        with mock.patch.object(profile, "_copy_file", failing):
            rc, _out, err = self.run_import(replace=True)
        self.assertEqual(rc, 1)
        backups = list(self.dst.parent.glob("Distraction.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "Preferences").read_bytes(), b"old")
        self.assertTrue(self.tmp.is_dir(), "the partial copy was removed")
        self.assertFalse(self.dst.exists(), "a half profile was put in place")
        self.assertIn(str(self.tmp), err)
        self.assertIn(str(backups[0]), err)
        self.assertIn("No space left", err)

    def test_preferences_that_are_not_json_fail_the_copy_like_a_disk_error(self):
        make_profile(self.src)
        (self.src / "Preferences").write_bytes(b"not json")
        rc, _out, err = self.run_import()
        self.assertEqual(rc, 1)
        self.assertIn("the copy failed", err)
        self.assertIn("Preferences", err)
        self.assertNotIn("Traceback", err)
        self.assertTrue(self.tmp.is_dir(), "the partial copy was removed")
        self.assertFalse(self.dst.exists(), "a profile that would prompt was put in place")

    def test_failed_moves_are_refused_on_one_line_with_the_profile_untouched(self):
        make_profile(self.src)
        self.dst.mkdir(parents=True)
        (self.dst / "Preferences").write_bytes(b"old")
        with self.subTest("backup_rename_fails"):
            with mock.patch.object(profile.os, "rename", side_effect=PermissionError(13, "Permission denied")):
                rc, _out, err = self.run_import(replace=True)
            self.assertEqual(rc, 1)
            self.assertIn(f"could not move {self.dst} aside", err)
            self.assertIn("Permission denied", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(self.tmp.exists(), "the empty sibling was left behind")
        with self.subTest("sibling_cannot_be_made"):
            self.dst.parent.chmod(0o500)
            self.addCleanup(self.dst.parent.chmod, 0o700)
            rc, _out, err = self.run_import(replace=True)
            self.assertEqual(rc, 1)
            self.assertIn(str(self.tmp), err)
            self.assertNotIn("Traceback", err)
        self.assertEqual((self.dst / "Preferences").read_bytes(), b"old")
        self.assertFalse(list(self.dst.parent.glob("Distraction.bak-*")), "a backup was made for a copy that never started")

    def test_progress_reports_every_threshold_a_file_crosses(self):
        kept = make_profile(self.src)
        (self.src / "Cookies").write_bytes(b"x" * 13)
        with mock.patch.object(profile, "PROGRESS_STEP", 4):
            rc, _out, err = self.run_import()
        self.assertEqual(rc, 0, err)
        self.assertEqual(err.count("MB copied"), (kept - len(b"Cookies" * 3) + 13) // 4)

    def test_backup_names_carry_a_counter_on_collision(self):
        base = self.box.home / "Distraction.bak-20260905-120000"
        self.assertEqual(profile._free_name(base), base)
        base.mkdir()
        self.assertEqual(profile._free_name(base), base.with_name(base.name + "-2"))
        base.with_name(base.name + "-2").mkdir()
        self.assertEqual(profile._free_name(base), base.with_name(base.name + "-3"))

    def test_stale_sibling_from_an_interrupted_run_is_moved_aside(self):
        make_profile(self.src)
        self.tmp.mkdir(parents=True)
        (self.tmp / "half").write_bytes(b"x")
        rc, _out, err = self.run_import()
        self.assertEqual(rc, 0, err)
        stale = self.tmp.with_name(self.tmp.name + ".stale")
        self.assertEqual((stale / "half").read_bytes(), b"x")
        self.assertIn(str(stale), err)
        self.assertTrue((self.dst / "Preferences").is_file())
        self.assertFalse((self.dst / "half").exists(), "the stale sibling was reused")

    # --- usage ----------------------------------------------------------------

    def test_usage_exit_codes(self):
        self.assertEqual(self.box.run("profile").returncode, 2)
        r = self.box.run("profile", "import", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--replace", r.stdout)
        self.assertEqual(self.box.run("profile", "import", "--bogus").returncode, 2)


if __name__ == "__main__":
    unittest.main()
