#!/usr/bin/env python3
"""Wrapper install, sudoers, rescan-last, remove, fail-closed paths."""

from __future__ import annotations

import os
import pwd
import stat
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import setup

SUDO = r"""
import os, shutil, sys
from pathlib import Path
raw = sys.argv[1:]
args = list(raw)
nflag = False
if args[:1] == ["-n"]:
    nflag = True
    args = args[1:]
log = Path(os.environ["DS_SETUP_SUDO_LOG"])
log.parent.mkdir(parents=True, exist_ok=True)
lock = os.environ.get("DS_LOCK_PREFIX")

def relock():
    if lock:
        try:
            os.chmod(lock, 0o555)
        except OSError:
            pass

def unlock(path: Path):
    for p in [path, *path.parents]:
        if not p.exists():
            continue
        try:
            os.chmod(p, 0o755)
        except OSError:
            continue

def is_wrapper_flush(a):
    return len(a) >= 2 and a[-2:] == ["flush", "ds"] and Path(a[0]).name == "distractions-nft"

def parse_install(a):
    if a[:1] != ["install"]:
        return None
    mode = 0o755
    dflag = False
    files = []
    i = 1
    while i < len(a):
        if a[i] == "-D":
            dflag = True
            i += 1
        elif a[i] == "-m":
            mode = int(a[i + 1], 8)
            i += 2
        else:
            files.append(a[i])
            i += 1
    if len(files) != 2:
        return None
    return files[0], Path(files[1]), mode, dflag

def do_install(src, dest, mode, dflag):
    unlock(dest)
    unlock(dest.parent)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    os.chmod(dest, mode)
    relock()

# Interactive session or grant: sh -c compare-or-install, install, wrapper, rm.
# Standalone cmp (including sudo -n cmp) is not accepted.
if nflag and not is_wrapper_flush(args):
    sys.exit(1)
log.open("a").write(" ".join(raw) + "\n")
if os.environ.get("DS_SUDO_DENY"):
    sys.exit(1)
if is_wrapper_flush(args):
    err = os.environ.get("DS_FLUSH_ERR", "")
    if err:
        sys.stderr.write(err + "\n")
    sys.exit(int(os.environ.get("DS_FLUSH_RC", "0")))
if args[:2] == ["sh", "-c"] and len(args) == 6 and args[3] == "sh":
    script, src, dest = args[2], Path(args[4]), Path(args[5])
    tokens = script.split()
    if "cmp" not in tokens or "install" not in tokens:
        relock()
        sys.exit(1)
    dflag = "-D" in tokens
    mode = 0o755
    if "-m" in tokens:
        mode = int(tokens[tokens.index("-m") + 1], 8)
    dest_mode = None
    if dest.exists():
        dest_mode = dest.stat().st_mode
        try:
            os.chmod(dest, dest_mode | 0o400)
        except OSError:
            unlock(dest)
    try:
        same = dest.exists() and src.read_bytes() == dest.read_bytes()
    except OSError:
        same = False
    if dest.exists() and dest_mode is not None:
        try:
            os.chmod(dest, dest_mode)
        except OSError:
            pass
    if same:
        relock()
        sys.exit(0)
    do_install(src, dest, mode, dflag)
    log.open("a").write(
        f"install {'-D ' if dflag else ''}-m {mode:04o} {src} {dest}\n"
    )
    sys.exit(0)
parsed = parse_install(args)
if parsed is not None:
    src, dest, mode, dflag = parsed
    do_install(src, dest, mode, dflag)
    sys.exit(0)
if args[:1] == ["rm"]:
    for token in args[1:]:
        if token.startswith("-"):
            continue
        p = Path(token)
        if p.exists() or p.is_symlink():
            p.unlink()
    relock()
    sys.exit(0)
relock()
sys.exit(1)
"""

VISUDO = r"""
import sys
from pathlib import Path
if sys.argv[1:2] != ["-cf"] or len(sys.argv) != 3:
    sys.exit(2)
text = Path(sys.argv[2]).read_text(encoding="utf-8")
if "__INSTALL_USER__" in text or "ALL=(root) NOPASSWD:" not in text:
    sys.exit(1)
sys.exit(0)
"""

SHELL_OK = r"""
import os, sys
from pathlib import Path
Path(os.environ["DS_RESCAN_LOG"]).open("a").write(" ".join(sys.argv[1:]) + "\n")
sys.exit(0)
"""

SHELL_FAIL = r"""
import os, sys
from pathlib import Path
Path(os.environ["DS_RESCAN_LOG"]).open("a").write("fail " + " ".join(sys.argv[1:]) + "\n")
sys.exit(1)
"""


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.prefix = Path(self.box.runtime / "prefix")
        self.prefix.mkdir()
        os.chmod(self.prefix, 0o555)
        self.wrapper = self.prefix / "libexec" / "omarchy-distraction-space" / "distractions-nft"
        self.sudoers = self.prefix / "etc" / "sudoers.d" / "omarchy-distraction-space"
        os.environ["DS_WRAPPER_DEST"] = str(self.wrapper)
        os.environ["DS_SUDOERS_DEST"] = str(self.sudoers)
        self.sudo_log = self.box.runtime / "sudo.log"
        self.rescan_log = self.box.runtime / "rescan.log"
        os.environ["DS_SETUP_SUDO_LOG"] = str(self.sudo_log)
        os.environ["DS_RESCAN_LOG"] = str(self.rescan_log)
        os.environ["DS_LOCK_PREFIX"] = str(self.prefix)
        # No notification plugin source in the sandbox: the clone step reports
        # the hold unavailable and never reaches the live omarchy-plugin-clone.
        os.environ["DS_NOTIFICATIONS_SOURCE"] = str(self.box.runtime / "no-notifications")
        os.environ.pop("DS_SUDO_DENY", None)
        os.environ.pop("DS_FLUSH_RC", None)
        os.environ.pop("DS_FLUSH_ERR", None)
        self.box.fake_bin("sudo", SUDO)
        self.box.fake_bin("visudo", VISUDO)
        self.box.fake_bin("omarchy-shell", SHELL_OK)
        real_access = os.access
        prefix = self.prefix.resolve()

        def fake_access(path, mode, **kwargs):
            try:
                p = Path(path).resolve()
            except OSError:
                p = Path(path)
            try:
                if p != prefix and prefix.is_relative_to(p):
                    return False
                if p != prefix and p.is_relative_to(prefix):
                    return False
            except ValueError:
                pass
            return real_access(path, mode, **kwargs)

        os.access = fake_access
        self.addCleanup(setattr, os, "access", real_access)

    def _sudo_lines(self):
        if not self.sudo_log.exists():
            return []
        return [ln for ln in self.sudo_log.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _rescan_text(self):
        return self.rescan_log.read_text(encoding="utf-8") if self.rescan_log.exists() else ""

    def test_install_idempotent_and_rescan_last(self):
        rc = setup.install()
        self.assertEqual(rc, 0)
        self.assertTrue(self.wrapper.is_file())
        self.assertEqual(self.wrapper.read_bytes(), (ROOT / "distractions-nft").read_bytes())
        self.assertEqual(stat.S_IMODE(self.sudoers.stat().st_mode), 0o440)
        principal = pwd.getpwuid(os.getuid()).pw_name
        text = self.sudoers.read_text(encoding="utf-8")
        self.assertIn(principal, text)
        self.assertNotIn("__INSTALL_USER__", text)
        self.assertTrue(self._rescan_text().strip().endswith("shell rescanPlugins"))
        sudo_after_first = self._sudo_lines()
        self.assertTrue(any(ln.startswith("install") for ln in sudo_after_first))
        first_rescan = self._rescan_text()
        rc = setup.install()
        self.assertEqual(rc, 0)
        extra = self._sudo_lines()[len(sudo_after_first):]
        self.assertFalse(any(ln.startswith("install") for ln in extra))
        self.assertGreater(len(self._rescan_text()), len(first_rescan))
        self.assertTrue(self._rescan_text().splitlines()[-1].endswith("shell rescanPlugins"))

    def test_refuses_user_writable_destination_chain(self):
        writable = self.box.state / "open" / "distractions-nft"
        writable.parent.mkdir(parents=True)
        os.environ["DS_WRAPPER_DEST"] = str(writable)
        os.environ["DS_SUDOERS_DEST"] = str(self.box.state / "open" / "sudoers")
        rc = setup.install()
        self.assertEqual(rc, 1)
        self.assertFalse(writable.exists())
        self.assertFalse(Path(os.environ["DS_SUDOERS_DEST"]).exists())
        self.assertEqual(self._sudo_lines(), [])
        self.assertEqual(self._rescan_text(), "")

    def test_denied_sudo_leaves_no_partial_grant(self):
        os.environ["DS_SUDO_DENY"] = "1"
        rc = setup.install()
        self.assertEqual(rc, 1)
        self.assertFalse(self.wrapper.exists())
        self.assertFalse(self.sudoers.exists())
        self.assertEqual(self._rescan_text(), "")

    def test_failed_rescan_leaves_files_and_exits_1(self):
        self.box.fake_bin("omarchy-shell", SHELL_FAIL)
        rc = setup.install()
        self.assertEqual(rc, 1)
        self.assertTrue(self.wrapper.is_file())
        self.assertTrue(self.sudoers.is_file())
        self.assertIn("fail", self._rescan_text())

    def test_missing_rescan_leaves_files_and_exits_1(self):
        (self.box.bin / "omarchy-shell").unlink()
        rc = setup.install()
        self.assertEqual(rc, 1)
        self.assertTrue(self.wrapper.is_file())
        self.assertTrue(self.sudoers.is_file())

    def test_remove_reverses_and_rescans_last(self):
        self.assertEqual(setup.install(), 0)
        self.sudo_log.write_text("", encoding="utf-8")
        self.rescan_log.write_text("", encoding="utf-8")
        rc = setup.remove()
        self.assertEqual(rc, 0)
        self.assertFalse(self.wrapper.exists())
        self.assertFalse(self.sudoers.exists())
        lines = self._sudo_lines()
        self.assertTrue(any(ln.endswith(f"{self.wrapper} flush ds") for ln in lines))
        self.assertTrue(any(ln.startswith("rm ") for ln in lines))
        self.assertTrue(self._rescan_text().strip().endswith("shell rescanPlugins"))
        self.assertLess(self._rescan_text().find("rescanPlugins"), len(self._rescan_text()))
        last_sudo = lines[-1] if lines else ""
        self.assertFalse(last_sudo.endswith("rescanPlugins"))

    def test_remove_aborts_on_flush_failure(self):
        self.assertEqual(setup.install(), 0)
        self.sudo_log.write_text("", encoding="utf-8")
        os.environ["DS_FLUSH_RC"] = "1"
        os.environ["DS_FLUSH_ERR"] = "Error: Could not process rule: Operation not permitted"
        rc = setup.remove()
        self.assertEqual(rc, 1)
        self.assertTrue(self.wrapper.is_file())
        self.assertTrue(self.sudoers.is_file())
        self.assertFalse(any(ln.startswith("rm ") for ln in self._sudo_lines()))
        os.environ["DS_FLUSH_ERR"] = "Error: No such file or directory"
        rc = setup.remove()
        self.assertEqual(rc, 0)
        self.assertFalse(self.wrapper.exists())
        self.assertFalse(self.sudoers.exists())
        self.assertTrue(any(ln.startswith("rm ") for ln in self._sudo_lines()))

    def test_sudoers_idempotent_when_unreadable(self):
        self.assertEqual(setup.install(), 0)
        os.chmod(self.sudoers, 0o000)
        sudo_after_first = self._sudo_lines()
        try:
            rc = setup.install()
        finally:
            if self.sudoers.exists():
                os.chmod(self.sudoers, 0o440)
        self.assertEqual(rc, 0)
        extra = self._sudo_lines()[len(sudo_after_first):]
        self.assertTrue(
            any(ln.startswith("sh -c ") and str(self.sudoers) in ln for ln in extra)
        )
        self.assertFalse(any(ln.startswith(("install", "cmp ", "-n ")) for ln in extra))

    def test_cli_setup_and_remove(self):
        site = self.box.runtime / "pysite"
        site.mkdir()
        prefix = str(self.prefix.resolve())
        (site / "sitecustomize.py").write_text(
            "import os\n"
            "from pathlib import Path\n"
            f"_prefix = Path({prefix!r})\n"
            "_real = os.access\n"
            "def _access(path, mode, **kwargs):\n"
            "    try:\n"
            "        p = Path(path).resolve()\n"
            "    except OSError:\n"
            "        p = Path(path)\n"
            "    try:\n"
            "        if p != _prefix and _prefix.is_relative_to(p):\n"
            "            return False\n"
            "        if p != _prefix and p.is_relative_to(_prefix):\n"
            "            return False\n"
            "    except ValueError:\n"
            "        pass\n"
            "    return _real(path, mode, **kwargs)\n"
            "os.access = _access\n",
            encoding="utf-8",
        )
        extra = {
            "PYTHONPATH": str(site),
            "DS_WRAPPER_DEST": str(self.wrapper),
            "DS_SUDOERS_DEST": str(self.sudoers),
            "DS_SETUP_SUDO_LOG": str(self.sudo_log),
            "DS_RESCAN_LOG": str(self.rescan_log),
            "DS_LOCK_PREFIX": str(self.prefix),
        }
        r = self.box.run("setup", extra_env=extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.wrapper.is_file())
        self.assertTrue(self.sudoers.is_file())
        self.assertTrue(self._rescan_text().strip().endswith("shell rescanPlugins"))
        sudo_lines = self._sudo_lines()
        self.assertTrue(sudo_lines)
        self.assertFalse(sudo_lines[-1].endswith("rescanPlugins"))

        self.sudo_log.write_text("", encoding="utf-8")
        self.rescan_log.write_text("", encoding="utf-8")
        r = self.box.run("setup", "--remove", extra_env=extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.wrapper.exists())
        self.assertFalse(self.sudoers.exists())
        self.assertTrue(self._rescan_text().strip().endswith("shell rescanPlugins"))
        sudo_lines = self._sudo_lines()
        self.assertTrue(any("flush ds" in ln or ln.endswith("flush ds") for ln in sudo_lines))
        self.assertTrue(any(ln.startswith("rm ") for ln in sudo_lines))
        self.assertFalse(sudo_lines[-1].endswith("rescanPlugins"))

        (self.box.bin / "omarchy-shell").unlink()
        r = self.box.run("setup", extra_env=extra)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertTrue(self.wrapper.is_file())
        self.assertTrue(self.sudoers.is_file())


if __name__ == "__main__":
    unittest.main()
