#!/usr/bin/env python3
"""Notification-service clone: fresh, unchanged, drift, patch failure, upstream method, foreign, --remove."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox
from test_setup import SUDO, VISUDO

sys.path.insert(0, str(ROOT))
from ds import listener, setup

FIRST_PARTY = Path(setup.NOTIFICATIONS_SOURCE_DEFAULT)
PATCH_TEXT = setup.PATCH.read_text(encoding="utf-8")
# The context line the patch's handleNotification hunk hangs on; rewriting it
# in the source is what an incompatible Omarchy update looks like.
DND_LINE = "    if (service.doNotDisturb && !shouldBypassDnd(notification)) {"

CLONE = r"""
import json, os, shutil, subprocess, sys
from pathlib import Path
Path(os.environ["DS_SHELL_LOG"]).open("a").write("omarchy-plugin-clone " + " ".join(sys.argv[1:]) + "\n")
fail = os.environ.get("DS_CLONE_FAIL", "")
if sys.argv[1:] != ["omarchy.notifications"] or fail == "early":
    sys.stderr.write("omarchy-plugin-clone: refused\n")
    sys.exit(1)
target = Path.home() / ".config" / "omarchy" / "plugins" / (os.environ["USER"] + ".notifications")
if target.exists():
    sys.stderr.write(f"omarchy-plugin-clone: {target} already exists\n")
    sys.exit(1)
shutil.copytree(os.environ["DS_NOTIFICATIONS_SOURCE"], target)
manifest = target / "manifest.json"
data = json.loads(manifest.read_text(encoding="utf-8"))
data.update(id=target.name, name="My Notifications", omarchy={"clonedFrom": "omarchy.notifications"})
manifest.write_text(json.dumps(data), encoding="utf-8")
subprocess.run(["omarchy-shell", "shell", "rescanPlugins"], check=True)
if os.environ.get("DS_CLONE_CORRUPT"):
    (target / "Service.qml").write_text("Item {}\n", encoding="utf-8")
if fail == "late":
    # The real tool has enabled the clone by now; its closing notification failing exits 1.
    sys.stderr.write("omarchy-notification-send: failed\n")
    sys.exit(1)
print(f"Cloned omarchy.notifications to {target}")
"""

SHELL = r"""
import os, sys
from pathlib import Path
Path(os.environ["DS_SHELL_LOG"]).open("a").write("omarchy-shell " + " ".join(sys.argv[1:]) + "\n")
if os.environ.get("DS_SHELL_DOWN"):
    sys.stderr.write("Could not connect to omarchy-shell\n")
    sys.exit(1)
if sys.argv[1:3] == ["notifications", "silencedSenders"]:
    # DS_SHELL_METHOD says whether the RUNNING service already answers the patched method.
    if os.environ.get("DS_SHELL_METHOD"):
        print("[]")
        sys.exit(0)
    print("Function not found.")
    sys.exit(1)
print("ok" if sys.argv[1:3] == ["shell", "setPluginEnabled"] else "")
"""

OMARCHY = r"""
import os, sys
from pathlib import Path
Path(os.environ["DS_SHELL_LOG"]).open("a").write("omarchy " + " ".join(sys.argv[1:]) + "\n")
"""

NOTIFY = r"""
import os, sys
from pathlib import Path
Path(os.environ["DS_NOTIFY_LOG"]).open("a").write(" ".join(sys.argv[1:]) + "\n")
"""

_ENV = ("DS_NOTIFICATIONS_SOURCE", "DS_SHELL_LOG", "DS_NOTIFY_LOG", "USER", "DS_CLONE_FAIL",
        "DS_CLONE_CORRUPT", "DS_SHELL_DOWN", "DS_WRAPPER_DEST", "DS_SUDOERS_DEST", "DS_SETUP_SUDO_LOG",
        "DS_LOCK_PREFIX", "DS_SUDO_DENY", "DS_FLUSH_RC", "DS_FLUSH_ERR", "XDG_DATA_HOME")


def _preimage(text: str) -> dict[str, str]:
    """Rebuild the files a unified diff was taken against, from its context and removed lines."""
    files: dict[str, dict[int, str]] = {}
    lines, cur = None, 0
    for raw in text.splitlines():
        if raw.startswith("--- a/"):
            lines = files.setdefault(raw[6:], {})
        elif raw.startswith("@@ "):
            cur = int(raw.split()[1].split(",")[0][1:])
        elif lines is not None and raw[:1] in (" ", "-") and not raw.startswith("--- "):
            lines[cur] = raw[1:]
            cur += 1
    return {
        name: "\n".join(body.get(i, f"// line {i}") for i in range(1, max(body) + 1)) + "\n"
        for name, body in files.items()
    }


def _make_source(root: Path) -> Path:
    src = root / "first-party" / "notifications"
    (src / "components").mkdir(parents=True)
    for name, body in _preimage(PATCH_TEXT).items():
        (src / name).write_text(body, encoding="utf-8")
    (src / "manifest.json").write_text(
        json.dumps({"id": "omarchy.notifications", "entryPoints": {"service": "Service.qml"}}),
        encoding="utf-8",
    )
    (src / "components" / "Card.qml").write_text("Item {}\n", encoding="utf-8")
    return src


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CloneTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        saved = {k: os.environ.get(k) for k in _ENV}

        def restore():
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        self.addCleanup(restore)
        for k in _ENV:
            os.environ.pop(k, None)
        self.source = _make_source(self.box.runtime)
        self.shell_log = self.box.runtime / "shell.log"
        self.notify_log = self.box.runtime / "notify.log"
        os.environ.update(
            DS_NOTIFICATIONS_SOURCE=str(self.source),
            DS_SHELL_LOG=str(self.shell_log),
            DS_NOTIFY_LOG=str(self.notify_log),
            USER="tester",
        )
        self.box.fake_bin("omarchy-plugin-clone", CLONE)
        self.box.fake_bin("omarchy-shell", SHELL)
        self.box.fake_bin("omarchy", OMARCHY)
        self.box.fake_bin("omarchy-notification-send", NOTIFY)
        setup._service_changed = False
        os.environ.pop("DS_SHELL_METHOD", None)
        self.addCleanup(os.environ.pop, "DS_SHELL_METHOD", None)
        self.clone = setup.clone_dir()
        self.record = self.box.state_dir / "clone.json"
        self.assertEqual(self.clone.name, "tester.notifications")
        self.assertTrue(self.clone.is_relative_to(self.box.home))

    def _log(self) -> list[str]:
        return self.shell_log.read_text(encoding="utf-8").splitlines() if self.shell_log.exists() else []

    def _notices(self) -> list[str]:
        return self.notify_log.read_text(encoding="utf-8").splitlines() if self.notify_log.exists() else []

    def _patched(self) -> bool:
        return setup.METHOD_MARK in (self.clone / "Service.qml").read_text(encoding="utf-8")

    def _sync(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = setup.sync_clone()
        return rc, err.getvalue()

    def _break_source(self):
        service = self.source / "Service.qml"
        text = service.read_text(encoding="utf-8")
        self.assertIn(DND_LINE, text)
        service.write_text(text.replace(DND_LINE, "    if (service.quietHours) {"), encoding="utf-8")

    def _ship_upstream(self):
        subprocess.run(
            ["patch", "-p1", "-d", str(self.source)], input=PATCH_TEXT, text=True,
            capture_output=True, check=True,
        )

    def test_fresh_clone_applies_patch_and_records_hashes(self):
        rc, err = self._sync()
        self.assertEqual(rc, 0, err)
        self.assertTrue(self._patched())
        self.assertEqual(
            json.loads((self.clone / "manifest.json").read_text(encoding="utf-8"))["omarchy"],
            {"clonedFrom": "omarchy.notifications"},
        )
        record = json.loads(self.record.read_text(encoding="utf-8"))
        self.assertEqual(record["plugin"], "tester.notifications")
        self.assertEqual(record["path"], str(self.clone))
        self.assertEqual(
            set(record["files"]),
            {"Service.qml", "NotificationLogic.js", "manifest.json", "components/Card.qml"},
        )
        self.assertEqual(record["files"]["Service.qml"], _sha(self.source / "Service.qml"))
        self.assertEqual(record["patch"], _sha(setup.PATCH))
        self.assertEqual(
            self._log(),
            ["omarchy-plugin-clone omarchy.notifications", "omarchy-shell shell rescanPlugins"],
        )
        self.assertFalse(list(self.clone.glob("*.orig")) + list(self.clone.glob("*.rej")))

    def test_unchanged_clone_is_left_alone(self):
        self.assertEqual(self._sync()[0], 0)
        before = self._log()
        service_before = (self.clone / "Service.qml").read_bytes()
        rc, err = self._sync()
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(self._log(), before)
        self.assertEqual((self.clone / "Service.qml").read_bytes(), service_before)

    def test_drift_reclones_after_first_party_or_patch_change(self):
        self.assertEqual(self._sync()[0], 0)
        (self.source / "components" / "Card.qml").write_text("Item { id: card }\n", encoding="utf-8")
        rc, err = self._sync()
        self.assertEqual(rc, 0, err)
        self.assertEqual(
            self._log()[2:],
            [
                "omarchy-shell shell setPluginEnabled tester.notifications false",
                "omarchy-plugin-clone omarchy.notifications",
                "omarchy-shell shell rescanPlugins",
            ],
        )
        self.assertTrue(self._patched())
        self.assertEqual((self.clone / "components" / "Card.qml").read_text(encoding="utf-8"), "Item { id: card }\n")
        record = json.loads(self.record.read_text(encoding="utf-8"))
        self.assertEqual(record["files"]["components/Card.qml"], _sha(self.source / "components" / "Card.qml"))

        refreshed = self.box.runtime / "refreshed.patch"
        refreshed.write_text(PATCH_TEXT + "\n", encoding="utf-8")
        with mock.patch.object(setup, "PATCH", refreshed):
            rc, err = self._sync()
            self.assertEqual(rc, 0, err)
            self.assertEqual(self._log()[5], "omarchy-shell shell setPluginEnabled tester.notifications false")
            self.assertEqual(json.loads(self.record.read_text(encoding="utf-8"))["patch"], _sha(refreshed))
            self.assertTrue(self._patched())

    def test_patch_failure_removes_clone_and_exits_1(self):
        self.assertEqual(self._sync()[0], 0)
        self._break_source()
        rc, err = self._sync()
        self.assertEqual(rc, 1)
        self.assertIn("notification hold unavailable", err)
        self.assertFalse(self.clone.exists())
        self.assertFalse(self.record.exists())
        self.assertEqual(self._log()[-1], "omarchy-shell shell setPluginEnabled tester.notifications false")
        calls = len(self._log())
        rc, err = self._sync()
        self.assertEqual(rc, 1)
        self.assertIn("notification hold unavailable", err)
        self.assertFalse(self.clone.exists())
        self.assertEqual(len(self._log()), calls)

    def test_clone_tool_failure_exits_1_without_record(self):
        os.environ["DS_CLONE_FAIL"] = "early"
        rc, err = self._sync()
        self.assertEqual(rc, 1)
        self.assertIn("refused", err)
        self.assertFalse(self.clone.exists())
        self.assertFalse(self.record.exists())
        self.assertNotIn("setPluginEnabled", "\n".join(self._log()))
        os.environ["DS_CLONE_FAIL"] = "late"
        rc, err = self._sync()
        self.assertEqual(rc, 1)
        self.assertIn("notification-send: failed", err)
        self.assertFalse(self.clone.exists())
        self.assertFalse(self.record.exists())
        self.assertEqual(self._log()[-1], "omarchy-shell shell setPluginEnabled tester.notifications false")

    def test_failure_after_clone_creation_rolls_the_clone_back(self):
        os.environ["DS_CLONE_CORRUPT"] = "1"
        rc, err = self._sync()
        self.assertEqual(rc, 1)
        self.assertIn("could not be completed", err)
        self.assertFalse(self.clone.exists())
        self.assertFalse(self.record.exists())
        self.assertEqual(self._log()[-1], "omarchy-shell shell setPluginEnabled tester.notifications false")
        os.environ.pop("DS_CLONE_CORRUPT")
        os.chmod(self.box.state_dir, 0o500)
        self.addCleanup(os.chmod, self.box.state_dir, 0o700)
        rc, err = self._sync()
        self.assertEqual(rc, 1)
        self.assertIn("cannot write", err)
        self.assertFalse(self.clone.exists())
        self.assertEqual(self._log()[-1], "omarchy-shell shell setPluginEnabled tester.notifications false")

    def test_upstream_method_removes_clone(self):
        self.assertEqual(self._sync()[0], 0)
        self._ship_upstream()
        rc, err = self._sync()
        self.assertEqual(rc, 0, err)
        self.assertFalse(self.clone.exists())
        self.assertFalse(self.record.exists())
        self.assertEqual(self._log()[-1], "omarchy-shell shell setPluginEnabled tester.notifications false")
        calls = len(self._log())
        self.assertEqual(self._sync(), (0, ""))
        self.assertEqual(len(self._log()), calls)
        self.assertFalse(self.clone.exists())

    def test_foreign_clone_is_reported_when_builtin_has_method(self):
        shutil.copytree(self.source, self.clone)
        before = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*") if p.is_file()}
        self.record.unlink(missing_ok=True)
        self._ship_upstream()
        rc, err = self._sync()
        self.assertEqual(rc, 0)
        self.assertIn("not created by this plugin", err)
        self.assertIn("silencedSenders", err)
        self.assertEqual(self._log(), [])
        after = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_foreign_clone_is_never_touched(self):
        shutil.copytree(self.source, self.clone)
        before = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*") if p.is_file()}
        other = {"plugin": "tester.notifications", "path": "/elsewhere/tester.notifications",
                 "files": {}, "patch": ""}
        for record in (None, {}, {"plugin": "tester.notifications"}, other, ["tester.notifications"]):
            with self.subTest(record=record):
                if record is None:
                    self.record.unlink(missing_ok=True)
                else:
                    self.record.write_text(json.dumps(record), encoding="utf-8")
                rc, err = self._sync()
                self.assertEqual(rc, 0)
                self.assertIn("not created by this plugin", err)
                self.assertEqual(self._log(), [])
                after = {p.relative_to(self.clone): p.read_bytes() for p in self.clone.rglob("*") if p.is_file()}
                self.assertEqual(after, before)
        self.record.unlink()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(setup.remove_clone(), 0)
        self.assertIn("not created by this plugin", err.getvalue())
        self.assertTrue(self.clone.is_dir())
        self.assertEqual(self._log(), [])

    def test_remove_drops_plugin_clone_only_after_shell_restores_builtin(self):
        self.assertEqual(self._sync()[0], 0)
        os.environ["DS_SHELL_DOWN"] = "1"
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(setup.remove_clone(), 1)
        self.assertIn("Could not connect", err.getvalue())
        self.assertTrue(self.clone.is_dir())
        self.assertTrue(self.record.exists())
        os.environ.pop("DS_SHELL_DOWN")
        self.assertEqual(setup.remove_clone(), 0)
        self.assertFalse(self.clone.exists())
        self.assertFalse(self.record.exists())
        self.assertEqual(self._log()[-1], "omarchy-shell shell setPluginEnabled tester.notifications false")
        self.assertEqual(setup.remove_clone(), 0)

    def test_listener_notices_drift_once_and_never_reclones(self):
        listener._clone_check()
        self.assertEqual(self._notices(), [])
        self.assertEqual(self._sync()[0], 0)
        listener._clone_check()
        self.assertEqual(self._notices(), [])
        calls = len(self._log())
        (self.source / "components" / "Card.qml").write_text("Item { id: card }\n", encoding="utf-8")
        listener._clone_check()
        self.assertEqual(len(self._notices()), 1)
        self.assertIn("distractions setup", self._notices()[0])
        self.assertEqual(len(self._log()), calls)
        self.assertEqual(json.loads(self.record.read_text(encoding="utf-8"))["files"]["components/Card.qml"],
                         _sha(self.clone / "components" / "Card.qml"))
        shutil.rmtree(self.clone)
        listener._clone_check()
        self.assertEqual(len(self._notices()), 2)
        self._ship_upstream()
        self.assertEqual(setup.clone_drift(), "the clone is missing")

    def _arm_wrapper_install(self):
        prefix = self.box.runtime / "prefix"
        prefix.mkdir()
        sudoers = prefix / "etc" / "sudoers.d" / "omarchy-distraction-space"
        # /etc/sudoers.d is already there and root-only on a real system; the
        # setup transaction stages the grant inside it rather than creating it.
        sudoers.parent.mkdir(parents=True)
        os.chmod(sudoers.parent, 0o750)
        os.chmod(prefix, 0o555)
        self.addCleanup(os.chmod, prefix, 0o755)
        self.wrapper = prefix / "libexec" / "omarchy-distraction-space" / "distractions-nft"
        os.environ.update(
            DS_WRAPPER_DEST=str(self.wrapper),
            DS_SUDOERS_DEST=str(sudoers),
            DS_SETUP_SUDO_LOG=str(self.box.runtime / "sudo.log"),
            DS_LOCK_PREFIX=str(prefix),
        )
        self.box.fake_bin("sudo", SUDO)
        self.box.fake_bin("visudo", VISUDO)
        # setup now installs and starts the slice unit; keep the user manager out of the test.
        self.box.fake_bin("systemctl", "import sys\nsys.exit(0)\n")
        # It also writes launcher entries and registers the URL handler: the entries
        # land in the sandbox (pinned here on top of the harness default) and
        # the default browser is never the real one's.
        os.environ["XDG_DATA_HOME"] = str(self.box.runtime / "data")
        self.box.fake_bin("xdg-settings", "import sys\nprint('google-chrome.desktop')\n")
        self.box.fake_bin("update-desktop-database", "import sys\nsys.exit(0)\n")
        real_access, resolved = os.access, prefix.resolve()

        def fake_access(path, mode, **kwargs):
            try:
                p = Path(path).resolve()
            except OSError:
                p = Path(path)
            try:
                if p != resolved and (resolved.is_relative_to(p) or p.is_relative_to(resolved)):
                    return False
            except ValueError:
                pass
            return real_access(path, mode, **kwargs)

        os.access = fake_access
        self.addCleanup(setattr, os, "access", real_access)

    def test_setup_runs_clone_step_before_rescan_and_reports_patch_failure(self):
        self._arm_wrapper_install()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(setup.install(), 0, err.getvalue())
        self.assertTrue(self.wrapper.is_file())
        self.assertTrue(self._patched())
        self.assertEqual(
            self._log(),
            [
                "omarchy-plugin-clone omarchy.notifications",
                "omarchy-shell shell rescanPlugins",
                "omarchy-shell shell rescanPlugins",
                "omarchy-shell notifications silencedSenders",  # running service still answers built-in
                "omarchy restart shell",
            ],
        )
        self._break_source()
        with contextlib.redirect_stderr(err):
            self.assertEqual(setup.install(), 1)
        self.assertIn("notification hold unavailable", err.getvalue())
        self.assertFalse(self.clone.exists())
        self.assertTrue(self.wrapper.is_file())
        self.assertEqual(
            self._log()[5:],
            ["omarchy-shell shell setPluginEnabled tester.notifications false", "omarchy-shell shell rescanPlugins"],
        )

    def test_setup_remove_drops_plugin_clone_then_rescans(self):
        self._arm_wrapper_install()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(setup.install(), 0)
        calls = len(self._log())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(setup.remove(), 0)
        self.assertFalse(self.wrapper.exists())
        self.assertFalse(self.clone.exists())
        self.assertFalse(self.record.exists())
        self.assertEqual(
            self._log()[calls:],
            [
                "omarchy-shell shell setPluginEnabled tester.notifications false",
                "omarchy-shell shell rescanPlugins",
                "omarchy-shell notifications silencedSenders",  # built-in is back: no restart needed
            ],
        )

    def test_missing_first_party_source_leaves_hold_unavailable(self):
        os.environ["DS_NOTIFICATIONS_SOURCE"] = str(self.box.runtime / "absent")
        rc, err = self._sync()
        self.assertEqual(rc, 0)
        self.assertIn("notification hold unavailable", err)
        self.assertEqual(self._log(), [])
        self.assertFalse(self.clone.exists())

    def test_settle_restarts_shell_only_when_live_service_disagrees(self):
        # Fresh clone; the running shell still answers with the built-in (no method).
        os.environ.pop("DS_SHELL_METHOD", None)
        self.assertEqual(self._sync()[0], 0)
        self.assertTrue(setup._service_changed)
        setup._settle_service()
        log = self._log()
        self.assertEqual(log[-2:], ["omarchy-shell notifications silencedSenders", "omarchy restart shell"])
        self.assertFalse(setup._service_changed)
        # Nothing changed on disk: no probe, no restart.
        setup._settle_service()
        self.assertEqual(self._log(), log)
        # Changed, but the running service already answers: probe only.
        setup._mark_changed()
        os.environ["DS_SHELL_METHOD"] = "1"
        setup._settle_service()
        self.assertEqual(self._log()[-1], "omarchy-shell notifications silencedSenders")
        self.assertNotIn("omarchy restart shell", self._log()[len(log):])

    def test_remove_marks_service_changed(self):
        self.assertEqual(self._sync()[0], 0)
        setup._service_changed = False
        self.assertEqual(setup.remove_clone(), 0)
        self.assertTrue(setup._service_changed)
        self.assertFalse(self.clone.exists())


class ShippedPatchTests(unittest.TestCase):
    @unittest.skipUnless((FIRST_PARTY / "Service.qml").is_file(), "Omarchy notifications plugin not installed")
    def test_shipped_patch_applies_to_installed_first_party_files(self):
        if setup._builtin_has_method(FIRST_PARTY):
            self.skipTest("the installed built-in already provides silencedSenders")
        with Sandbox() as box:
            copy = box.runtime / "notifications"
            shutil.copytree(FIRST_PARTY, copy)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertTrue(setup._patch(copy, dry_run=True), err.getvalue())
                self.assertTrue(setup._patch(copy, dry_run=False), err.getvalue())
            self.assertIn(setup.METHOD_MARK, (copy / "Service.qml").read_text(encoding="utf-8"))
            self.assertFalse(list(copy.glob("*.orig")) + list(copy.glob("*.rej")))


if __name__ == "__main__":
    unittest.main()
