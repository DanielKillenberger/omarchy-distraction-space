#!/usr/bin/env python3
"""Wrapper install, sudoers, rescan-last, remove, fail-closed paths."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import io
import json
import os
import pwd
import shutil
import stat
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import launch, setup
from ds.config import DEFAULTS

SUDO = r"""
import os, shutil, subprocess, sys
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

# Interactive session or grant: the setup transaction, the wrapper flush, rm.
# Nothing else is accepted, and only the flush runs passwordless.
if nflag and not is_wrapper_flush(args):
    sys.exit(1)
entry = raw
if args[:2] == ["python3", "-c"]:
    entry = ["python3", "-c", "<transaction>", *args[3:]]
log.open("a").write(" ".join(entry) + "\n")
if os.environ.get("DS_SUDO_DENY"):
    sys.exit(1)
if is_wrapper_flush(args):
    err = os.environ.get("DS_FLUSH_ERR", "")
    if err:
        sys.stderr.write(err + "\n")
    sys.exit(int(os.environ.get("DS_FLUSH_RC", "0")))
if args[:2] == ["python3", "-c"] and len(args) == 5:
    # Root really runs the transaction here, against the real destinations: the
    # read-only prefix stands in for the root-only directories of an install, so
    # it is opened for the child and closed again after it exits.
    for dest in args[3:]:
        unlock(Path(dest).parent)
    try:
        rc = subprocess.run([sys.executable, "-c", args[2], *args[3:]]).returncode
    finally:
        relock()
    sys.exit(rc)
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
import hashlib, os, sys
from pathlib import Path
if sys.argv[1:2] != ["-cf"] or len(sys.argv) != 3:
    sys.exit(2)
path = Path(sys.argv[2])
data = path.read_bytes()
# What was validated, and which file it was: the test proves the same one is renamed.
log = os.environ.get("DS_VISUDO_LOG")
if log:
    st = path.stat()
    Path(log).open("a").write(
        f"{path}\t{st.st_dev}:{st.st_ino}\t{oct(st.st_mode & 0o777)}\t{hashlib.sha256(data).hexdigest()}\n"
    )
if os.environ.get("DS_VISUDO_FAIL"):
    sys.stderr.write("visudo: parse error near line 1\n")
    sys.exit(1)
text = data.decode("utf-8", "replace")
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

SYSTEMCTL = r"""
import os, sys
from pathlib import Path
Path(os.environ["DS_SYSTEMCTL_LOG"]).open("a").write(" ".join(sys.argv[1:]) + "\n")
if os.environ.get("DS_SYSTEMCTL_FAIL"):
    sys.stderr.write("Failed to connect to bus: No medium found\n")
    sys.exit(1)
verb = sys.argv[2] if len(sys.argv) > 2 else ""
unit = sys.argv[3] if len(sys.argv) > 3 else ""
if verb == "stop" and os.environ.get("DS_SYSTEMCTL_STOP_FAIL"):
    sys.stderr.write("Failed to stop %s: Connection timed out\n" % unit)
    sys.exit(1)
# Like the real manager: a unit with no file cannot be started or stopped.
if verb in ("start", "stop") and unit and not (Path(os.environ["XDG_CONFIG_HOME"]) / "systemd" / "user" / unit).is_file():
    sys.stderr.write("Failed to %s %s: Unit %s not found.\n" % (verb, unit, unit))
    sys.exit(5)
"""

SHELL_FAIL = r"""
import os, sys
from pathlib import Path
Path(os.environ["DS_RESCAN_LOG"]).open("a").write("fail " + " ".join(sys.argv[1:]) + "\n")
sys.exit(1)
"""

# The default browser lives in one file the test reads and rewrites; `set` can be
# made to fail like the real tool's exit 4. Never the real xdg-settings.
XDG_SETTINGS = r"""
import os, sys
from pathlib import Path
args = sys.argv[1:]
Path(os.environ["DS_XDG_LOG"]).open("a").write(" ".join(args) + "\n")
if os.environ.get("BROWSER"):
    sys.stderr.write("xdg-settings: $BROWSER is set and can't be changed with xdg-settings\n")
    sys.exit(4)
store = Path(os.environ["DS_XDG_DEFAULT"])
if args == ["get", "default-web-browser"]:
    if not store.exists():
        sys.exit(2)
    print(store.read_text().strip())
    sys.exit(0)
if args[:2] == ["set", "default-web-browser"] and len(args) == 3:
    rc = int(os.environ.get("DS_XDG_SET_RC", "0"))
    if rc:
        sys.stderr.write("xdg-settings: failed to set default browser\n")
        sys.exit(rc)
    store.write_text(args[2] + "\n")
    sys.exit(0)
sys.exit(1)
"""

UPDATE_DESKTOP_DATABASE = r"""
import os, sys, time
from pathlib import Path
Path(os.environ["DS_UDD_LOG"]).open("a").write(" ".join(sys.argv[1:]) + "\n")
time.sleep(float(os.environ.get("DS_UDD_SLEEP", "0")))
"""

OMARCHY_YOUTUBE = (
    "[Desktop Entry]\nVersion=1.0\nName=YouTube\nExec=omarchy-launch-webapp https://youtube.com/\n"
    "Terminal=false\nType=Application\nIcon=youtube\nStartupNotify=true\n"
)
# An Omarchy web app that is not a listed product, with a URL the desktop-entry
# grammar has to quote and an extra argument the launcher passes after it.
BASECAMP_URL = "https://launchpad.37signals.com/?ref=a&b=1"
BASECAMP_EXEC = f"omarchy-launch-webapp {BASECAMP_URL} --class=basecamp"
OMARCHY_BASECAMP = (
    f"[Desktop Entry]\nVersion=1.0\nName=Basecamp\nExec={BASECAMP_EXEC}\n"
    "Terminal=false\nType=Application\nIcon=basecamp\nStartupNotify=true\n"
)


class Tty(io.StringIO):
    """stdin as a terminal: what the person types, or nothing at all."""

    def isatty(self):
        return True


class ClosedTty(Tty):
    def readline(self):
        raise AssertionError("setup prompted")


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.prefix = Path(self.box.runtime / "prefix")
        self.prefix.mkdir()
        self.wrapper = self.prefix / "libexec" / "omarchy-distraction-space" / "distractions-nft"
        self.sudoers = self.prefix / "etc" / "sudoers.d" / "omarchy-distraction-space"
        # /etc/sudoers.d is root-only and already there on a real system; the
        # transaction stages inside it rather than creating it.
        self.sudoers.parent.mkdir(parents=True)
        os.chmod(self.sudoers.parent, 0o750)
        os.chmod(self.prefix, 0o555)
        os.environ["DS_WRAPPER_DEST"] = str(self.wrapper)
        os.environ["DS_SUDOERS_DEST"] = str(self.sudoers)
        self.sudo_log = self.box.runtime / "sudo.log"
        self.rescan_log = self.box.runtime / "rescan.log"
        self.visudo_log = self.box.runtime / "visudo.log"
        os.environ["DS_SETUP_SUDO_LOG"] = str(self.sudo_log)
        os.environ["DS_RESCAN_LOG"] = str(self.rescan_log)
        os.environ["DS_VISUDO_LOG"] = str(self.visudo_log)
        os.environ.pop("DS_VISUDO_FAIL", None)
        self.systemctl_log = self.box.runtime / "systemctl.log"
        os.environ["DS_SYSTEMCTL_LOG"] = str(self.systemctl_log)
        os.environ.pop("DS_SYSTEMCTL_FAIL", None)
        os.environ.pop("DS_SYSTEMCTL_STOP_FAIL", None)
        # The clone tests run setup.install() too and would inherit a poisoned
        # visudo or log paths that point into this sandbox after it is gone.
        for key in ("DS_VISUDO_FAIL", "DS_SYSTEMCTL_FAIL", "DS_SYSTEMCTL_STOP_FAIL",
                    "DS_VISUDO_LOG", "DS_SYSTEMCTL_LOG", "DS_SETUP_SUDO_LOG", "DS_RESCAN_LOG"):
            self.addCleanup(os.environ.pop, key, None)
        self.unit = self.box.config / "systemd" / "user" / "app-distraction.slice"
        os.environ["DS_LOCK_PREFIX"] = str(self.prefix)
        # No notification plugin source in the sandbox: the clone step reports
        # the hold unavailable and never reaches the live omarchy-plugin-clone.
        os.environ["DS_NOTIFICATIONS_SOURCE"] = str(self.box.runtime / "no-notifications")
        setup._service_changed = False
        setup._skipped.clear()
        os.environ.pop("DS_SUDO_DENY", None)
        os.environ.pop("DS_FLUSH_RC", None)
        os.environ.pop("DS_FLUSH_ERR", None)
        self.box.fake_bin("sudo", SUDO)
        self.box.fake_bin("visudo", VISUDO)
        self.box.fake_bin("omarchy-shell", SHELL_OK)
        self.box.fake_bin("systemctl", SYSTEMCTL)
        # The harness leaves XDG_DATA_HOME alone, and on a developer machine it
        # names the real applications directory: point it into the sandbox.
        self.data = self.box.runtime / "data"
        self.apps = self.data / "applications"
        self.apps.mkdir(parents=True)
        self.xdg_default = self.box.runtime / "xdg-default"
        self.xdg_default.write_text("google-chrome.desktop\n", encoding="utf-8")
        self.xdg_log = self.box.runtime / "xdg.log"
        self.udd_log = self.box.runtime / "udd.log"
        saved = {k: os.environ.get(k) for k in ("XDG_DATA_HOME", "DS_XDG_DEFAULT", "DS_XDG_LOG", "DS_UDD_LOG", "DS_XDG_SET_RC")}

        def restore():
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        self.addCleanup(restore)
        os.environ.update(
            XDG_DATA_HOME=str(self.data), DS_XDG_DEFAULT=str(self.xdg_default),
            DS_XDG_LOG=str(self.xdg_log), DS_UDD_LOG=str(self.udd_log),
        )
        os.environ.pop("DS_XDG_SET_RC", None)
        self.box.fake_bin("xdg-settings", XDG_SETTINGS)
        self.box.fake_bin("update-desktop-database", UPDATE_DESKTOP_DATABASE)
        self._cfg()
        # Every setup run prints the link choice; `_install` captures its own.
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
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

    def _visudo_lines(self):
        if not self.visudo_log.exists():
            return []
        return [ln.split("\t") for ln in self.visudo_log.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _systemctl_lines(self):
        if not self.systemctl_log.exists():
            return []
        return [ln for ln in self.systemctl_log.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _staged(self):
        """Anything the transaction left behind in the destination directories."""
        left = []
        for d in (self.sudoers.parent, self.wrapper.parent):
            if d.is_dir():
                left += [p.name for p in d.iterdir() if p.name.startswith(".ds-stage.")]
        return left

    def _ident(self, path):
        st = path.stat()
        return (st.st_dev, st.st_ino)

    def _cfg(self, **over):
        cfg = json.loads(json.dumps(DEFAULTS))
        cfg["list"] = ["YouTube", "Telegram"]
        cfg.update(over)
        self.box.config_file.write_text(json.dumps(cfg) + "\n", encoding="utf-8")

    def _xdg_lines(self):
        if not self.xdg_log.exists():
            return []
        return [ln for ln in self.xdg_log.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _default(self):
        return self.xdg_default.read_text(encoding="utf-8").strip()

    def _entries(self):
        path = self.box.state_dir / "entries.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _links(self):
        path = self.box.state_dir / "state.json"
        return json.loads(path.read_text(encoding="utf-8")).get("links") if path.exists() else None

    def _unanswered(self):
        """The config file before setup ever asked about links: every key but open_links_in_space."""
        raw = json.loads(self.box.config_file.read_text(encoding="utf-8"))
        del raw["open_links_in_space"]
        self.box.config_file.write_text(json.dumps(raw) + "\n", encoding="utf-8")
        return raw

    def _config(self):
        return json.loads(self.box.config_file.read_text(encoding="utf-8"))

    def _install(self, assume_yes=False):
        """setup.install() with its stderr, minus the clone step's expected line (no source in the sandbox); stdout in `self.stdout`."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = setup.install(assume_yes=assume_yes)
        self.stdout = out.getvalue()
        lines = [ln for ln in err.getvalue().splitlines() if not ln.startswith("notification hold unavailable")]
        return rc, "".join(ln + "\n" for ln in lines)

    def test_setup_asks_about_links_once_naming_the_browser_before_sudo_and_a_rerun_prints_the_choice(self):
        before = self._unanswered()
        (self.apps / "google-chrome.desktop").write_text(
            "[Desktop Entry]\nName=Google Chrome\nExec=/usr/bin/google-chrome-stable %U\n"
            "[Desktop Action new-window]\nName=New Window\n", encoding="utf-8")
        os.environ["DS_SUDO_DENY"] = "1"
        with patch("sys.stdin", Tty("\n")):
            rc, _err = self._install()
        # The root transaction was refused, and it ran after the question.
        self.assertEqual(rc, 1)
        self.assertTrue(self._sudo_lines())
        self.assertEqual(self.stdout.count(setup.LINKS_QUESTION), 1)
        self.assertIn("forwards everything else\nto Google Chrome unchanged", self.stdout)
        self.assertIn('"distractions setup --remove" restores Google Chrome', self.stdout)
        self.assertNotIn("google-chrome.desktop", self.stdout)
        self.assertEqual(self._config(), {**before, "open_links_in_space": True})
        os.environ.pop("DS_SUDO_DENY")
        with patch("sys.stdin", ClosedTty()):
            self.assertEqual(self._install(), (0, ""))
        self.assertNotIn("Links from other apps", self.stdout)
        self.assertIn("links: on -- change it with: distractions config set open_links_in_space false", self.stdout)
        self.assertEqual(self._default(), setup.HANDLER_ID)
        self.assertEqual(self._links(), "on")

    def test_answering_no_leaves_the_handler_unregistered_and_links_off(self):
        self._unanswered()
        with patch("sys.stdin", Tty("maybe\nno\n")):
            self.assertEqual(self._install(), (0, ""))
        self.assertEqual(self.stdout.count(setup.LINKS_QUESTION), 2)
        self.assertIs(self._config()["open_links_in_space"], False)
        self.assertFalse((self.apps / setup.HANDLER_ID).exists())
        self.assertEqual(self._links(), "off")
        self.assertEqual(self._default(), "google-chrome.desktop")
        self.assertFalse(any(ln.startswith("set ") for ln in self._xdg_lines()))
        self.assertTrue((self.apps / "YouTube.desktop").is_file())
        with patch("sys.stdin", ClosedTty()):
            self.assertEqual(self._install(), (0, ""))
        self.assertIn("links: off -- change it with: distractions config set open_links_in_space true", self.stdout)
        self.assertFalse((self.apps / setup.HANDLER_ID).exists())

    def test_an_answer_that_cannot_be_recorded_stops_setup_before_the_root_transaction(self):
        before = self._unanswered()
        with patch("sys.stdin", Tty("n\n")), patch.object(setup.config, "set_links", side_effect=setup.config.Busy("config busy")):
            rc, err = self._install()
        self.assertEqual(rc, 1)
        self.assertIn("cannot record the answer", err)
        self.assertEqual(self._sudo_lines(), [])
        self.assertFalse((self.apps / setup.HANDLER_ID).exists())
        self.assertIsNone(self._entries())
        self.assertEqual(self._config(), before)

    def test_yes_and_a_non_terminal_never_prompt_and_print_the_explanation_as_a_notice(self):
        for name, assume_yes, stdin in (("--yes", True, ClosedTty()), ("no terminal", False, io.StringIO("n\n"))):
            with self.subTest(name):
                before = self._unanswered()
                with patch("sys.stdin", stdin):
                    self.assertEqual(self._install(assume_yes=assume_yes), (0, ""))
                self.assertNotIn(setup.LINKS_QUESTION, self.stdout)
                self.assertIn("Links from other apps", self.stdout)
                self.assertIn(f"links: on ({'--yes' if assume_yes else 'no terminal to ask'}) -- change it with: "
                              "distractions config set open_links_in_space false", self.stdout)
                self.assertEqual(self._config(), {**before, "open_links_in_space": True})
                self.assertEqual(self._default(), setup.HANDLER_ID)
                self.assertEqual(self._links(), "on")

    def test_entries_shadow_the_omarchy_web_app_and_remove_restores_it(self):
        omarchy = self.apps / "YouTube.desktop"
        omarchy.write_text(OMARCHY_YOUTUBE, encoding="utf-8")
        stray = self.apps / "Stray.desktop"
        stray.write_text("[Desktop Entry]\nName=Stray\n", encoding="utf-8")
        self.assertEqual(self._install(), (0, ""))
        telegram, handler = self.apps / "org.telegram.desktop.desktop", self.apps / setup.HANDLER_ID
        youtube = omarchy.read_text(encoding="utf-8")
        self.assertIn(f"Exec={ROOT / 'distractions'} open YouTube\n", youtube)
        self.assertIn("Icon=youtube\n", youtube)
        self.assertIn("StartupWMClass=chrome-youtube.com__-Distraction\n", youtube)
        self.assertIn(f"Exec={ROOT / 'distractions'} open Telegram\n", telegram.read_text(encoding="utf-8"))
        self.assertIn("StartupWMClass=org.telegram.desktop\n", telegram.read_text(encoding="utf-8"))
        text = handler.read_text(encoding="utf-8")
        self.assertIn("MimeType=x-scheme-handler/http;x-scheme-handler/https;\n", text)
        self.assertIn(f"Exec={ROOT / 'distractions'} open %u\n", text)
        self.assertIn("NoDisplay=true\n", text)
        backup = self.box.state_dir / "entries-backup" / "YouTube.desktop"
        self.assertEqual(backup.read_text(encoding="utf-8"), OMARCHY_YOUTUBE)
        self.assertEqual(self._entries(), {
            "files": [
                {"path": str(omarchy), "backup": str(backup)},
                {"path": str(telegram), "backup": None},
                {"path": str(handler), "backup": None},
            ],
            "previous_handler": "google-chrome.desktop",
        })
        self.assertEqual(self._default(), setup.HANDLER_ID)
        self.assertEqual(self._links(), "on")
        self.assertEqual(self.udd_log.read_text(encoding="utf-8"), f"{self.apps}\n")
        # Nothing privileged in the user-level half: still the one transaction.
        self.assertEqual(len(self._sudo_lines()), 1)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(setup.remove(), 0)
        self.assertEqual(omarchy.read_text(encoding="utf-8"), OMARCHY_YOUTUBE)
        self.assertFalse(backup.exists())
        self.assertFalse(telegram.exists())
        self.assertFalse(handler.exists())
        self.assertTrue(stray.is_file())
        self.assertIsNone(self._entries())
        self.assertEqual(self._default(), "google-chrome.desktop")
        self.assertEqual(self._links(), "off")
        self.assertEqual(out.getvalue(), "")
        # The browser profile is never purged; its path is reported when it exists.
        setup.profile_dir().mkdir(parents=True)
        with contextlib.redirect_stdout(out):
            self.assertEqual(setup.remove(), 0)
        self.assertIn(str(setup.profile_dir()), out.getvalue())
        self.assertTrue(setup.profile_dir().is_dir())

    def test_rerun_keeps_the_backup_and_a_dropped_omarchy_web_app_becomes_a_forwarder(self):
        omarchy = self.apps / "YouTube.desktop"
        omarchy.write_text(OMARCHY_YOUTUBE, encoding="utf-8")
        self.assertEqual(self._install(), (0, ""))
        backup = self.box.state_dir / "entries-backup" / "YouTube.desktop"
        first = self._entries()
        # A re-run owns the file already: no second backup, the record carried forward,
        # the default not set again once it is ours, and nothing rewritten.
        self.assertEqual(self._install(), (0, ""))
        self.assertEqual(self._entries(), first)
        self.assertEqual(backup.read_text(encoding="utf-8"), OMARCHY_YOUTUBE)
        self.assertEqual(self._xdg_lines().count(f"set default-web-browser {setup.HANDLER_ID}"), 1)
        self.assertEqual(self.udd_log.read_text(encoding="utf-8"), f"{self.apps}\n")
        # Dropping YouTube from the list makes Omarchy's entry an unlisted web app:
        # rewritten from the backup to forward, the backup kept, still recorded.
        self._cfg(list=["Telegram"])
        self.assertEqual(self._install(), (0, ""))
        self.assertEqual(
            omarchy.read_text(encoding="utf-8"),
            OMARCHY_YOUTUBE.replace("omarchy-launch-webapp", f"{ROOT / 'distractions'} open --app"),
        )
        self.assertEqual(backup.read_text(encoding="utf-8"), OMARCHY_YOUTUBE)
        self.assertEqual(self._entries()["files"], [
            {"path": str(self.apps / "org.telegram.desktop.desktop"), "backup": None},
            {"path": str(omarchy), "backup": str(backup)},
            {"path": str(self.apps / setup.HANDLER_ID), "backup": None},
        ])
        self.assertEqual(self._entries()["previous_handler"], "google-chrome.desktop")

    def test_unlisted_omarchy_web_app_is_rewritten_with_every_other_key_kept_and_remove_restores_it(self):
        listed, basecamp = self.apps / "YouTube.desktop", self.apps / "Basecamp.desktop"
        listed.write_text(OMARCHY_YOUTUBE, encoding="utf-8")
        basecamp.write_text(OMARCHY_BASECAMP, encoding="utf-8")
        self.assertEqual(self._install(), (0, ""))
        backup = self.box.state_dir / "entries-backup" / "Basecamp.desktop"
        forward = f"{ROOT / 'distractions'} open --app \"{BASECAMP_URL}\" --class=basecamp"
        self.assertEqual(basecamp.read_text(encoding="utf-8"), OMARCHY_BASECAMP.replace(BASECAMP_EXEC, forward))
        # The rewritten line reads back through the desktop-entry grammar as the argv `open` gets.
        self.assertEqual(launch.parse_exec(launch.read_exec(basecamp)),
                         [str(ROOT / "distractions"), "open", "--app", BASECAMP_URL, "--class=basecamp"])
        self.assertEqual(backup.read_text(encoding="utf-8"), OMARCHY_BASECAMP)
        # The listed product keeps the space launcher: one file, no forwarder for it.
        self.assertIn(f"Exec={ROOT / 'distractions'} open YouTube\n", listed.read_text(encoding="utf-8"))
        self.assertEqual(self._entries()["files"], [
            {"path": str(listed), "backup": str(self.box.state_dir / "entries-backup" / "YouTube.desktop")},
            {"path": str(self.apps / "org.telegram.desktop.desktop"), "backup": None},
            {"path": str(basecamp), "backup": str(backup)},
            {"path": str(self.apps / setup.HANDLER_ID), "backup": None},
        ])
        self.assertEqual(setup.remove(), 0)
        self.assertEqual(basecamp.read_text(encoding="utf-8"), OMARCHY_BASECAMP)
        self.assertEqual(listed.read_text(encoding="utf-8"), OMARCHY_YOUTUBE)
        self.assertFalse(backup.exists())
        self.assertIsNone(self._entries())

    def test_an_omarchy_web_app_whose_exec_cannot_be_parsed_is_left_alone_and_named_once(self):
        broken = {
            self.apps / "Unbalanced.desktop": OMARCHY_BASECAMP.replace(BASECAMP_EXEC, 'omarchy-launch-webapp "https://x'),
            self.apps / "NoUrl.desktop": OMARCHY_BASECAMP.replace(BASECAMP_EXEC, "omarchy-launch-webapp"),
        }
        for path, text in broken.items():
            path.write_text(text, encoding="utf-8")
        rc, err = self._install()
        self.assertEqual(rc, 0)
        for path, text in broken.items():
            with self.subTest(path.name):
                self.assertEqual(path.read_text(encoding="utf-8"), text)
                self.assertEqual(len([ln for ln in err.splitlines() if str(path) in ln]), 1)
                self.assertNotIn(str(path), [f["path"] for f in self._entries()["files"]])
        self.assertFalse((self.box.state_dir / "entries-backup" / "Unbalanced.desktop").exists())
        # A rerun in the same process does not name them again.
        rc, err = self._install()
        self.assertEqual((rc, err), (0, ""))

    def test_an_owned_web_app_regenerated_with_a_malformed_exec_is_left_alone_and_still_recorded(self):
        basecamp = self.apps / "Basecamp.desktop"
        basecamp.write_text(OMARCHY_BASECAMP, encoding="utf-8")
        self.assertEqual(self._install(), (0, ""))
        backup = self.box.state_dir / "entries-backup" / "Basecamp.desktop"
        record = {"path": str(basecamp), "backup": str(backup)}
        malformed = OMARCHY_BASECAMP.replace(BASECAMP_EXEC, 'omarchy-launch-webapp "https://x')
        basecamp.write_text(malformed, encoding="utf-8")
        rc, err = self._install()
        self.assertEqual(rc, 0)
        self.assertEqual(len([ln for ln in err.splitlines() if str(basecamp) in ln]), 1)
        # Left alone means exactly that: the file, its record, and its backup as they were.
        self.assertEqual(basecamp.read_text(encoding="utf-8"), malformed)
        self.assertIn(record, self._entries()["files"])
        self.assertEqual(backup.read_text(encoding="utf-8"), OMARCHY_BASECAMP)
        # Nothing to write: no cache refresh for the rerun.
        self.assertEqual(self.udd_log.read_text(encoding="utf-8"), f"{self.apps}\n")
        self.assertEqual(self._install(), (0, ""))
        self.assertIn(record, self._entries()["files"])
        # Remove still hands Omarchy's original back over it.
        self.assertEqual(setup.remove(), 0)
        self.assertEqual(basecamp.read_text(encoding="utf-8"), OMARCHY_BASECAMP)

    def test_one_entries_transaction_at_a_time_across_setup_remove_and_the_listener(self):
        basecamp = self.apps / "Basecamp.desktop"
        basecamp.write_text(OMARCHY_BASECAMP, encoding="utf-8")
        self.assertEqual(self._install(), (0, ""))
        cfg = json.loads(self.box.config_file.read_text(encoding="utf-8"))
        exp = {"list": setup.catalog.expand(cfg)}
        regenerated = OMARCHY_BASECAMP.replace("Icon=basecamp", "Icon=basecamp-new")
        basecamp.write_text(regenerated, encoding="utf-8")
        lock = self.box.runtime / "distraction-space.entries.lock"
        with open(lock, "a+", encoding="utf-8") as holder:
            fcntl.flock(holder, fcntl.LOCK_EX)
            # The listener's sync gives way at once and touches nothing.
            self.assertEqual(setup.refresh_entries(exp, cfg), 0)
            self.assertEqual(basecamp.read_text(encoding="utf-8"), regenerated)
            # Setup and remove wait; past their budget they report busy and change nothing.
            err = io.StringIO()
            with patch.object(setup, "ENTRIES_LOCK_TIMEOUT", 0.2), contextlib.redirect_stderr(err):
                self.assertEqual(setup.sync_entries(exp, cfg), 1)
                self.assertEqual(setup.remove_entries(), 1)
            self.assertEqual(err.getvalue().count("rerun in a moment"), 2)
            self.assertEqual(basecamp.read_text(encoding="utf-8"), regenerated)
            self.assertTrue((self.box.state_dir / "entries.json").is_file())
            # Within the budget, setup waits for the holder and then runs.
            done = []
            with patch.object(setup, "ENTRIES_LOCK_TIMEOUT", 5.0):
                waiter = threading.Thread(target=lambda: done.append(setup.sync_entries(exp, cfg)))
                waiter.start()
                time.sleep(0.3)
                self.assertEqual(done, [])
                self.assertEqual(basecamp.read_text(encoding="utf-8"), regenerated)
                fcntl.flock(holder, fcntl.LOCK_UN)
                waiter.join(timeout=10)
        self.assertEqual(done, [0])
        self.assertIn(f"Exec={ROOT / 'distractions'} open --app ", basecamp.read_text(encoding="utf-8"))
        self.assertIn("Icon=basecamp-new\n", basecamp.read_text(encoding="utf-8"))

    def test_the_listener_sync_keeps_nothing_a_remove_finished_before_it_took_the_lock(self):
        basecamp = self.apps / "Basecamp.desktop"
        basecamp.write_text(OMARCHY_BASECAMP, encoding="utf-8")
        self.assertEqual(self._install(), (0, ""))
        cfg = json.loads(self.box.config_file.read_text(encoding="utf-8"))
        exp = {"list": setup.catalog.expand(cfg)}
        real_lock = setup._entries_lock

        @contextlib.contextmanager
        def lock_after_remove(wait):
            # A remove held the lock, finished, and released it before this sync gets in.
            self.assertEqual(setup._remove_entries(), 0)
            with real_lock(wait) as held:
                yield held

        with patch.object(setup, "_entries_lock", lock_after_remove):
            self.assertEqual(setup.refresh_entries(exp, cfg), 0)
        self.assertIsNone(self._entries())
        self.assertEqual(basecamp.read_text(encoding="utf-8"), OMARCHY_BASECAMP)
        self.assertFalse((self.apps / "YouTube.desktop").exists())

    def test_a_regenerated_web_app_is_rewritten_from_the_new_file_and_a_removed_one_is_not_resurrected(self):
        basecamp = self.apps / "Basecamp.desktop"
        basecamp.write_text(OMARCHY_BASECAMP, encoding="utf-8")
        self.assertEqual(self._install(), (0, ""))
        backup = self.box.state_dir / "entries-backup" / "Basecamp.desktop"
        # Omarchy reinstalls the web app over the forwarder: the new file is the
        # source and the new backup, the old backup gone.
        regenerated = OMARCHY_BASECAMP.replace("Icon=basecamp", "Icon=basecamp-new")
        basecamp.write_text(regenerated, encoding="utf-8")
        self.assertEqual(self._install(), (0, ""))
        self.assertIn("Icon=basecamp-new\n", basecamp.read_text(encoding="utf-8"))
        self.assertIn(f"Exec={ROOT / 'distractions'} open --app ", basecamp.read_text(encoding="utf-8"))
        self.assertEqual(backup.read_text(encoding="utf-8"), regenerated)
        self.assertEqual(sorted(p.name for p in backup.parent.iterdir()), ["Basecamp.desktop"])
        # The person removes the web app: the record and its backup go, nothing comes back.
        basecamp.unlink()
        self.assertEqual(self._install(), (0, ""))
        self.assertFalse(basecamp.exists())
        self.assertFalse(backup.exists())
        self.assertNotIn(str(basecamp), [f["path"] for f in self._entries()["files"]])
        # And remove does the same for a launcher removed after the last sync.
        basecamp.write_text(OMARCHY_BASECAMP, encoding="utf-8")
        self.assertEqual(self._install(), (0, ""))
        self.assertTrue(backup.is_file())
        basecamp.unlink()
        self.assertEqual(setup.remove(), 0)
        self.assertFalse(basecamp.exists())
        self.assertFalse(backup.exists())

    def test_browser_variable_in_the_session_does_not_block_the_switch(self):
        # Omarchy exports BROWSER; the real xdg-settings exits 4 while it is set.
        os.environ["BROWSER"] = "google-chrome-stable"
        self.addCleanup(os.environ.pop, "BROWSER", None)
        self.assertEqual(self._install(), (0, ""))
        self.assertEqual(self._default(), setup.HANDLER_ID)
        self.assertEqual(self._links(), "on")

    def test_handler_failure_leaves_links_displaced_and_setup_exits_0(self):
        os.environ["DS_XDG_SET_RC"] = "4"
        rc, err = self._install()
        self.assertEqual(rc, 0)
        self.assertEqual(len([ln for ln in err.splitlines() if "displaced" in ln]), 1)
        self.assertEqual(self._links(), "displaced")
        self.assertTrue((self.apps / setup.HANDLER_ID).is_file())
        self.assertEqual(self._entries()["previous_handler"], "google-chrome.desktop")
        self.assertEqual(self._default(), "google-chrome.desktop")
        # Remove sees the default was never ours and does not touch it.
        self.assertEqual(setup.remove(), 0)
        self.assertNotIn("set default-web-browser google-chrome.desktop", self._xdg_lines())

    def test_open_links_false_writes_no_handler_and_reports_off(self):
        self._cfg(open_links_in_space=False)
        self.assertEqual(self._install(), (0, ""))
        self.assertFalse((self.apps / setup.HANDLER_ID).exists())
        self.assertEqual(self._links(), "off")
        self.assertFalse(any(ln.startswith("set ") for ln in self._xdg_lines()))
        self.assertEqual([f["path"] for f in self._entries()["files"]],
                         [str(self.apps / "YouTube.desktop"), str(self.apps / "org.telegram.desktop.desktop")])
        # Switching it off after it was on hands the default back and drops the handler.
        self._cfg(open_links_in_space=True)
        self.assertEqual(self._install(), (0, ""))
        self.assertEqual(self._default(), setup.HANDLER_ID)
        self._cfg(open_links_in_space=False)
        self.assertEqual(self._install(), (0, ""))
        self.assertFalse((self.apps / setup.HANDLER_ID).exists())
        self.assertEqual(self._default(), "google-chrome.desktop")
        self.assertEqual(self._links(), "off")

    def test_unanswered_default_query_never_changes_the_default(self):
        # xdg-settings cannot say what the default is: the entries land, the
        # default is left alone, and links read displaced until it can answer.
        self.xdg_default.unlink()
        rc, err = self._install()
        self.assertEqual(rc, 0)
        self.assertEqual(len([ln for ln in err.splitlines() if "displaced" in ln]), 1)
        self.assertEqual(self._links(), "displaced")
        self.assertTrue((self.apps / setup.HANDLER_ID).is_file())
        self.assertIsNone(self._entries()["previous_handler"])
        self.assertFalse(any(ln.startswith("set ") for ln in self._xdg_lines()))
        # Remove cannot prove the default points elsewhere, so it deletes nothing.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(setup.remove_entries(), 1)
        self.assertTrue((self.apps / setup.HANDLER_ID).is_file())
        self.assertIsNotNone(self._entries())
        self.xdg_default.write_text("google-chrome.desktop\n", encoding="utf-8")
        self.assertEqual(setup.remove_entries(), 0)
        self.assertFalse((self.apps / setup.HANDLER_ID).exists())
        self.assertIsNone(self._entries())

    def test_remove_keeps_everything_while_the_default_still_points_at_the_handler(self):
        self.assertEqual(self._install(), (0, ""))
        self.assertEqual(self._default(), setup.HANDLER_ID)
        os.environ["DS_XDG_SET_RC"] = "4"
        self.addCleanup(os.environ.pop, "DS_XDG_SET_RC", None)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(setup.remove_entries(), 1)
        self.assertTrue((self.apps / setup.HANDLER_ID).is_file())
        self.assertTrue((self.apps / "YouTube.desktop").is_file())
        self.assertIsNotNone(self._entries())
        self.assertEqual(self._default(), setup.HANDLER_ID)
        del os.environ["DS_XDG_SET_RC"]
        self.assertEqual(setup.remove_entries(), 0)
        self.assertEqual(self._default(), "google-chrome.desktop")
        self.assertFalse((self.apps / setup.HANDLER_ID).exists())

    def test_manifest_naming_a_foreign_path_is_refused_whole(self):
        victim = self.box.runtime / "victim.txt"
        victim.write_text("keep me\n", encoding="utf-8")
        inside = self.apps / "YouTube.desktop"
        inside.write_text(OMARCHY_YOUTUBE, encoding="utf-8")
        manifest = self.box.state_dir / "entries.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        for record in (
            {"files": [{"path": str(victim), "backup": None}], "previous_handler": None},
            {"files": [{"path": str(self.apps / ".." / "victim.txt"), "backup": None}], "previous_handler": None},
            {"files": [{"path": str(inside), "backup": str(victim)}], "previous_handler": None},
        ):
            with self.subTest(record=record):
                manifest.write_text(json.dumps(record), encoding="utf-8")
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    self.assertEqual(setup.remove_entries(), 1)
                    rc, _ = self._install()
                self.assertEqual(rc, 1)
                self.assertIn(str(manifest), err.getvalue())
                self.assertEqual(victim.read_text(encoding="utf-8"), "keep me\n")
                self.assertEqual(inside.read_text(encoding="utf-8"), OMARCHY_YOUTUBE)
                self.assertTrue(manifest.is_file())

    def test_rollback_restores_owned_entries_and_a_dropped_entry(self):
        omarchy = self.apps / "YouTube.desktop"
        omarchy.write_text(OMARCHY_YOUTUBE, encoding="utf-8")
        self.assertEqual(self._install(), (0, ""))
        first = self._entries()
        backup = self.box.state_dir / "entries-backup" / "YouTube.desktop"
        telegram = self.apps / "org.telegram.desktop.desktop"
        # Owned files drift, then the run fails on the handler: every owned file
        # comes back with its drifted bytes and the dropped entry is un-dropped.
        omarchy.write_text("drifted youtube\n", encoding="utf-8")
        telegram.write_text("drifted telegram\n", encoding="utf-8")
        handler = self.apps / setup.HANDLER_ID
        handler.unlink()
        handler.mkdir()
        self._cfg(list=["Telegram"])
        rc, err = self._install()
        self.assertEqual(rc, 1)
        self.assertEqual(omarchy.read_text(encoding="utf-8"), "drifted youtube\n")
        self.assertEqual(telegram.read_text(encoding="utf-8"), "drifted telegram\n")
        self.assertEqual(backup.read_text(encoding="utf-8"), OMARCHY_YOUTUBE)
        self.assertEqual(self._entries(), first)
        self.assertEqual(sorted(p.name for p in backup.parent.iterdir()), ["YouTube.desktop"])

    def test_desktop_database_refresh_is_best_effort(self):
        os.environ["DS_UDD_SLEEP"] = "1"
        self.addCleanup(os.environ.pop, "DS_UDD_SLEEP", None)
        with patch.object(setup, "UDD_TIMEOUT", 0.2):
            rc, err = self._install()
        self.assertEqual(rc, 0)
        self.assertIn("update-desktop-database did not finish", err)
        self.assertIsNotNone(self._entries())
        self.assertEqual(self._links(), "on")

    def test_plan_refuses_a_name_with_control_characters(self):
        cfg = json.loads(json.dumps(DEFAULTS))
        exp = {"list": [{"name": "Bad\nName", "hosts": ["x.example"], "classes": []},
                        {"name": "Good", "hosts": ["good.example"], "classes": []}]}
        plan = setup._plan(exp, cfg, None, True, {})
        self.assertEqual([p.name for p, _text in plan], ["Good.desktop", setup.HANDLER_ID])

    def test_wm_class_follows_the_configured_browser(self):
        self._cfg(browser=["/usr/bin/brave", "--foo"])
        self.assertEqual(self._install(), (0, ""))
        youtube = (self.apps / "YouTube.desktop").read_text(encoding="utf-8")
        self.assertIn("StartupWMClass=brave-youtube.com__-Distraction\n", youtube)

    def test_switching_links_off_hands_the_default_back_before_the_handler_goes(self):
        self.assertEqual(self._install(), (0, ""))
        self.assertEqual(self._default(), setup.HANDLER_ID)
        handler = self.apps / setup.HANDLER_ID
        # The hand-back fails: the handler file stays, the record still names it,
        # and links read displaced rather than off.
        self._cfg(open_links_in_space=False)
        os.environ["DS_XDG_SET_RC"] = "4"
        self.addCleanup(os.environ.pop, "DS_XDG_SET_RC", None)
        rc, err = self._install()
        self.assertEqual(rc, 0)
        self.assertEqual(len([ln for ln in err.splitlines() if "displaced" in ln]), 1)
        self.assertTrue(handler.is_file())
        self.assertIn(str(handler), [f["path"] for f in self._entries()["files"]])
        self.assertEqual(self._entries()["previous_handler"], "google-chrome.desktop")
        self.assertEqual(self._default(), setup.HANDLER_ID)
        self.assertEqual(self._links(), "displaced")
        # Once the hand-back works the handler goes and links read off.
        del os.environ["DS_XDG_SET_RC"]
        self.assertEqual(self._install(), (0, ""))
        self.assertEqual(self._default(), "google-chrome.desktop")
        self.assertFalse(handler.exists())
        self.assertEqual(self._links(), "off")
        # With the query unanswered and the handler owned, the file stays too.
        self._cfg(open_links_in_space=True)
        self.assertEqual(self._install(), (0, ""))
        self._cfg(open_links_in_space=False)
        self.xdg_default.unlink()
        rc, err = self._install()
        self.assertEqual(rc, 0)
        self.assertTrue(handler.is_file())
        self.assertEqual(self._links(), "displaced")

    def test_write_failure_mid_run_leaves_no_manifest_and_no_plugin_files(self):
        omarchy = self.apps / "YouTube.desktop"
        omarchy.write_text(OMARCHY_YOUTUBE, encoding="utf-8")
        # A directory where the second entry goes: the write fails after the first
        # entry was backed up and written, so the rollback has both kinds to undo.
        (self.apps / "org.telegram.desktop.desktop").mkdir()
        rc, err = self._install()
        self.assertEqual(rc, 1)
        self.assertIn(str(self.apps), err)
        self.assertEqual(omarchy.read_text(encoding="utf-8"), OMARCHY_YOUTUBE)
        self.assertFalse((self.box.state_dir / "entries-backup" / "YouTube.desktop").exists())
        self.assertFalse((self.apps / setup.HANDLER_ID).exists())
        self.assertIsNone(self._entries())
        self.assertIsNone(self._links())
        self.assertFalse(any(ln.startswith("set ") for ln in self._xdg_lines()))

    def test_unwritable_applications_dir_fails_with_the_path_and_no_manifest(self):
        os.chmod(self.apps, 0o555)
        self.addCleanup(os.chmod, self.apps, 0o755)
        rc, err = self._install()
        self.assertEqual(rc, 1)
        self.assertIn(str(self.apps), err)
        self.assertEqual(sorted(p.name for p in self.apps.iterdir()), [])
        self.assertIsNone(self._entries())
        # The rest of setup still ran: the root half landed and the rescan was last.
        self.assertTrue(self.wrapper.is_file())
        self.assertTrue(self._rescan_text().strip().endswith("shell rescanPlugins"))

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
        # One privileged step for the whole install, so setup asks for a password once.
        self.assertEqual(len(self._sudo_lines()), 1)
        self.assertTrue(self._sudo_lines()[0].startswith("python3 -c <transaction> "))
        installed = (self._ident(self.wrapper), self._ident(self.sudoers))
        validated = len(self._visudo_lines())
        first_rescan = self._rescan_text()
        rc = setup.install()
        self.assertEqual(rc, 0)
        # A re-run whose bytes already match renames nothing and revalidates nothing.
        self.assertEqual((self._ident(self.wrapper), self._ident(self.sudoers)), installed)
        self.assertEqual(len(self._visudo_lines()), validated)
        # And it never reaches sudo at all, so an expired timestamp asks for nothing.
        self.assertEqual(len(self._sudo_lines()), 1)
        self.assertEqual(self._staged(), [])
        self.assertGreater(len(self._rescan_text()), len(first_rescan))
        self.assertTrue(self._rescan_text().splitlines()[-1].endswith("shell rescanPlugins"))

    def test_rerun_reinstalls_when_the_installed_bytes_drift(self):
        self.assertEqual(setup.install(), 0)
        record = setup._record_dest(self.wrapper)
        self.assertTrue(record.is_file())
        self.assertEqual(stat.S_IMODE(record.stat().st_mode), 0o444)
        digests = record.read_text(encoding="utf-8").split()
        self.assertEqual(digests[0], hashlib.sha256(self.wrapper.read_bytes()).hexdigest())
        self.assertEqual(digests[1], hashlib.sha256(self.sudoers.read_bytes()).hexdigest())

        # The record is root's claim about what it installed, so a wrapper that no
        # longer matches it sends the re-run back through the transaction.
        for target in (record.parent, record):
            os.chmod(target, 0o755)
        self.wrapper.write_bytes(b"#!/usr/bin/env python3\n# drifted\n")
        self.assertEqual(setup.install(), 0)
        self.assertEqual(len(self._sudo_lines()), 2)
        self.assertEqual(self.wrapper.read_bytes(), (ROOT / "distractions-nft").read_bytes())

        # A missing record is the same answer: reinstall rather than assume.
        record.unlink()
        self.assertEqual(setup.install(), 0)
        self.assertEqual(len(self._sudo_lines()), 3)
        self.assertTrue(setup._record_dest(self.wrapper).is_file())

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

    def test_install_writes_and_starts_the_slice_unit_once(self):
        self.assertEqual(setup.install(), 0)
        self.assertEqual(self.unit.read_bytes(), (ROOT / "install" / "app-distraction.slice").read_bytes())
        self.assertEqual(
            self._systemctl_lines(),
            ["--user daemon-reload", "--user start app-distraction.slice"],
        )
        # No root in the slice step: the one sudo line is the transaction.
        self.assertEqual(len(self._sudo_lines()), 1)
        ident = self._ident(self.unit)
        self.assertEqual(setup.install(), 0)
        self.assertEqual(self._ident(self.unit), ident)
        self.assertEqual(
            self._systemctl_lines(),
            ["--user daemon-reload", "--user start app-distraction.slice", "--user start app-distraction.slice"],
        )
        # A unit that drifted is rewritten and reloaded.
        self.unit.write_text("[Unit]\nDescription=drifted\n\n[Slice]\n", encoding="utf-8")
        self.assertEqual(setup.install(), 0)
        self.assertEqual(self.unit.read_bytes(), (ROOT / "install" / "app-distraction.slice").read_bytes())
        self.assertEqual(self._systemctl_lines()[-2:], ["--user daemon-reload", "--user start app-distraction.slice"])

    def test_remove_stops_and_deletes_the_slice_unit_after_the_flush(self):
        self.assertEqual(setup.install(), 0)
        self.systemctl_log.write_text("", encoding="utf-8")
        self.sudo_log.write_text("", encoding="utf-8")
        self.assertEqual(setup.remove(), 0)
        self.assertFalse(self.unit.exists())
        # The flush is a bare destroy and needs no slice: only the stop and the reload.
        self.assertEqual(self._systemctl_lines(), ["--user stop app-distraction.slice", "--user daemon-reload"])
        self.assertTrue(any(ln.endswith("flush ds") for ln in self._sudo_lines()))
        # The wrapper, its grant, and the unit are gone after the first remove:
        # the second run touches neither the manager nor sudo, so it succeeds
        # even once the passwordless grant no longer exists.
        self.systemctl_log.write_text("", encoding="utf-8")
        self.sudo_log.write_text("", encoding="utf-8")
        os.environ["DS_SUDO_DENY"] = "1"
        self.assertEqual(setup.remove(), 0)
        self.assertFalse(self.unit.exists())
        self.assertEqual(self._systemctl_lines(), [])
        self.assertEqual(self._sudo_lines(), [])

    def test_remove_keeps_the_root_files_when_the_slice_cannot_be_stopped(self):
        self.assertEqual(setup.install(), 0)
        self.sudo_log.write_text("", encoding="utf-8")
        os.environ["DS_SYSTEMCTL_STOP_FAIL"] = "1"
        self.assertEqual(setup.remove(), 1)
        # The flush ran, the slice step failed, and the root teardown never started,
        # so a retry can still flush through the wrapper and its grant.
        self.assertTrue(any(ln.endswith("flush ds") for ln in self._sudo_lines()))
        self.assertFalse(any(ln.startswith("rm ") for ln in self._sudo_lines()))
        self.assertTrue(self.wrapper.is_file())
        self.assertTrue(self.sudoers.is_file())
        self.assertTrue(self.unit.is_file())
        del os.environ["DS_SYSTEMCTL_STOP_FAIL"]
        self.sudo_log.write_text("", encoding="utf-8")
        self.assertEqual(setup.remove(), 0)
        self.assertFalse(self.unit.exists())
        self.assertFalse(self.wrapper.exists())

    def test_remove_with_a_missing_unit_touches_no_manager_and_still_flushes(self):
        self.assertEqual(setup.install(), 0)
        self.unit.unlink()
        self.systemctl_log.write_text("", encoding="utf-8")
        self.sudo_log.write_text("", encoding="utf-8")
        self.assertEqual(setup.remove(), 0)
        # Nothing of ours to stop, and the flush needs no slice to render.
        self.assertEqual(self._systemctl_lines(), [])
        self.assertTrue(any(ln.endswith("flush ds") for ln in self._sudo_lines()))
        self.assertFalse(self.unit.exists())
        self.assertFalse(self.wrapper.exists())

    def test_slice_manager_failure_fails_setup_and_stops_remove_before_root(self):
        os.environ["DS_SYSTEMCTL_FAIL"] = "1"
        self.assertEqual(setup.install(), 1)
        # The root half already landed; the failure is reported, not hidden by the rescan.
        self.assertTrue(self.wrapper.is_file())
        self.assertEqual(self._systemctl_lines(), ["--user daemon-reload"])
        self.assertTrue(self.unit.is_file())
        self.assertTrue(self._rescan_text().strip().endswith("shell rescanPlugins"))
        self.sudo_log.write_text("", encoding="utf-8")
        self.assertEqual(setup.remove(), 1)
        # The flush needs no slice and runs; the slice step fails; the root teardown never starts.
        self.assertTrue(self.wrapper.is_file())
        self.assertTrue(self.sudoers.is_file())
        self.assertTrue(all(ln.endswith("flush ds") for ln in self._sudo_lines()), self._sudo_lines())
        self.assertFalse(any(ln.startswith("rm ") for ln in self._sudo_lines()))

    def test_grant_is_validated_and_activated_as_one_root_owned_file(self):
        """The file visudo accepted is the file that lands: no name is resolved twice."""
        self.assertEqual(setup.install(), 0)
        lines = self._visudo_lines()
        self.assertEqual(len(lines), 1)
        path, ident, mode, digest = lines[0]
        staged = Path(path)
        # Staged inside the destination's own directory, which only root can write,
        # under a dotted name sudo's #includedir skips while it waits.
        self.assertEqual(staged.parent, self.sudoers.parent)
        self.assertTrue(staged.name.startswith(".ds-stage."))
        self.assertEqual(mode, oct(0o440))
        st = self.sudoers.stat()
        self.assertEqual(ident, f"{st.st_dev}:{st.st_ino}")
        self.assertEqual(
            digest, hashlib.sha256(self.sudoers.read_bytes()).hexdigest()
        )
        self.assertEqual(self._staged(), [])

    def test_rejected_grant_aborts_before_anything_moves(self):
        os.environ["DS_VISUDO_FAIL"] = "1"
        rc = setup.install()
        self.assertEqual(rc, 1)
        self.assertFalse(self.sudoers.exists())
        # The grant is checked first, so a rejection costs the wrapper nothing either.
        self.assertFalse(self.wrapper.exists())
        self.assertEqual(self._staged(), [])
        self.assertEqual(self._rescan_text(), "")

    def test_rejected_grant_leaves_the_prior_grant_intact(self):
        self.assertEqual(setup.install(), 0)
        before = self.sudoers.read_bytes()
        ident = self._ident(self.sudoers)
        os.chmod(self.sudoers.parent, 0o755)
        os.chmod(self.sudoers, 0o644)
        self.sudoers.write_bytes(before + b"# drifted\n")
        os.chmod(self.sudoers, 0o440)
        os.chmod(self.sudoers.parent, 0o750)
        # An edit made behind /etc/sudoers.d is invisible to the unprivileged
        # pre-check by construction, so drop root's record to send this re-run
        # through the transaction -- which is what this test is about.
        record = setup._record_dest(self.wrapper)
        os.chmod(record.parent, 0o755)
        record.unlink()
        os.environ["DS_VISUDO_FAIL"] = "1"
        self.assertEqual(setup.install(), 1)
        self.assertEqual(self.sudoers.read_bytes(), before + b"# drifted\n")
        self.assertEqual(self._ident(self.sudoers), ident)
        self.assertEqual(self._staged(), [])

    def test_wrapper_source_is_pinned_against_symlinks_and_irregular_files(self):
        src = self.box.runtime / "src"
        src.mkdir()
        real = src / "real"
        real.write_bytes(b"#!/usr/bin/env python3\n")
        link = src / "link"
        link.symlink_to(real)
        fifo = src / "fifo"
        os.mkfifo(fifo)
        self.assertEqual(setup._pinned_source(real), b"#!/usr/bin/env python3\n")
        for name, path in (("symlink", link), ("fifo", fifo), ("missing", src / "gone")):
            with self.subTest(name):
                self.assertIsNone(setup._pinned_source(path))

    def test_install_refuses_a_non_regular_wrapper_source_before_any_sudo(self):
        fake_root = self.box.runtime / "plugin"
        (fake_root / "install").mkdir(parents=True)
        shutil.copyfile(
            ROOT / "install" / "sudoers.omarchy-distraction-space",
            fake_root / "install" / "sudoers.omarchy-distraction-space",
        )
        (fake_root / "distractions-nft").symlink_to(ROOT / "distractions-nft")
        with patch.object(setup, "ROOT", fake_root):
            rc = setup.install()
        self.assertEqual(rc, 1)
        self.assertEqual(self._sudo_lines(), [])
        self.assertFalse(self.wrapper.exists())
        self.assertFalse(self.sudoers.exists())
        self.assertEqual(self._rescan_text(), "")

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
