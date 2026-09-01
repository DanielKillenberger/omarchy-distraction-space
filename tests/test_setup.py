#!/usr/bin/env python3
"""Privileged setup must not list /etc/sudoers.d."""

from __future__ import annotations

import os
import pwd
import stat
import subprocess
import tempfile
import threading
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
        self.uid = os.getuid()
        self.principal = pwd.getpwuid(self.uid).pw_name

    def _tree(self):
        root = Path(self.tmp.name) / "root"
        root.mkdir()
        os.chmod(root, 0o755)
        src = Path(self.tmp.name) / "wrapper-src"
        src.write_bytes(b"#!/bin/sh\necho usage:\n")
        os.chmod(src, 0o755)
        dest = root / "usr/local/libexec/omarchy-distraction-space/distractions-nft"
        sudoers_dir = root / "etc/sudoers.d"
        sudoers_dir.mkdir(parents=True)
        os.chmod(root / "etc", 0o755)
        os.chmod(sudoers_dir, 0o755)
        sudoers = sudoers_dir / "omarchy-distraction-space"
        lock = Path(self.tmp.name) / "setup.lock"
        return root, src, dest, sudoers, lock

    def _install(self, **kwargs):
        root, src, dest, sudoers, lock = self._tree()
        args = {
            "wrapper_src": src,
            "wrapper_dest": dest,
            "sudoers_path": sudoers,
            "principal": self.principal,
            "trusted_uid": self.uid,
            "lock_path": lock,
            "fs_root": root,
        }
        args.update(kwargs)
        self.mod._privileged_install(**args)
        return args

    def test_readme_does_not_ls_sudoers(self):
        text = (ROOT / "README.md").read_text()
        self.assertIn("distractions setup", text)
        self.assertNotIn("ls ", text)
        self.assertIn("sudo -n", text)
        self.assertNotIn("chmod 0644 /etc/sudoers.d/", text)
        self.assertIn("rescanPlugins", text)
        self.assertIn("sudo rm -f", text)

    def test_refuses_non_tty(self):
        with mock.patch.object(self.mod, "_setup_already_installed", return_value=False):
            with mock.patch.object(self.mod, "_setup_has_tty", return_value=False):
                with self.assertRaises(SystemExit) as ctx:
                    self.mod.setup_privileged_helper()
        self.assertIn("terminal", str(ctx.exception))

    def test_already_installed_skips_sudo(self):
        with mock.patch.object(self.mod, "_setup_already_installed", return_value=True):
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
            if argv[:2] == ["sudo", "-k"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if argv[:1] == ["sudo"] and argv[1:2] not in (["-n"], ["-k"]):
                self.assertNotIn("bash", argv)
                self.assertFalse(any("install -D" in part for part in argv))
                self.assertIn("-c", argv)
                self.assertNotIn("__install-privileged-helper", argv)
                self.assertFalse(any(part.endswith("/distractions") for part in argv))
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

        with mock.patch.object(self.mod, "_setup_already_installed", return_value=False):
            with mock.patch.object(self.mod, "_setup_has_tty", return_value=True):
                with mock.patch.object(self.mod.subprocess, "run", fake_run):
                    self.mod.setup_privileged_helper()
        joined = [" ".join(c) for c in self.calls]
        interactive = [
            c for c in self.calls if c[:1] == ["sudo"] and c[1:2] not in (["-n"], ["-k"])
        ]
        self.assertEqual(len(interactive), 1)
        self.assertFalse(any(part == "ls" or part.startswith("ls ") for c in self.calls for part in c))
        self.assertFalse(any("/etc/sudoers.d" in row for row in joined))

    def test_old_install_transaction_gone(self):
        text = (ROOT / "distractions").read_text()
        self.assertNotIn("install -D -m 0755", text)
        self.assertNotIn("getpass.getuser", text)
        self.assertIn("pwd.getpwuid", text)
        self.assertNotIn("focus_block.privileged", text)
        self.assertNotIn("__install-privileged-helper", text)
        self.assertIn('["sudo", "-k"]', text)
        self.assertIn('["sudo", "-n", NFT_WRAPPER', text)

    def test_principal_from_uid_ignores_spoofed_env(self):
        with mock.patch.dict(os.environ, {"LOGNAME": "ALL", "USER": "%wheel"}):
            name = self.mod._sudoers_principal(self.uid)
        self.assertEqual(name, self.principal)
        self.assertNotEqual(name, "ALL")
        self.assertFalse(name.startswith("%"))

    def test_principal_rejects_reserved_names(self):
        for name in ("", "ALL", "%wheel", "__INSTALL_USER__", "a b"):
            with self.subTest(name=name):
                with self.assertRaises(self.mod._SetupClosed):
                    self.mod._reject_sudoers_principal(name)

    def test_denied_sudo_mentions_grant_remains(self):
        def fake_run(cmd, **kwargs):
            argv = [str(part) for part in cmd]
            if argv[:2] == ["sudo", "-k"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if argv[:1] == ["sudo"] and argv[1:2] not in (["-n"], ["-k"]):
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
            raise AssertionError(argv)

        with mock.patch.object(self.mod, "_setup_already_installed", return_value=False):
            with mock.patch.object(self.mod, "_setup_has_tty", return_value=True):
                with mock.patch.object(self.mod.subprocess, "run", fake_run):
                    with self.assertRaises(SystemExit) as ctx:
                        self.mod.setup_privileged_helper()
        self.assertIn("cannot remove a root-owned grant", str(ctx.exception))

    def test_root_install_script_is_self_contained(self):
        script = self.mod._root_install_script((ROOT / "distractions").read_text())
        compile(script, "<root-install>", "exec")
        self.assertNotIn(str(ROOT / "distractions"), script)
        self.assertIn("_root_install_main()", script)

    def test_internal_install_requires_root(self):
        if os.geteuid() == 0:
            self.skipTest("running as root")
        with self.assertRaises(SystemExit) as ctx:
            self.mod._root_install_main()
        self.assertIn("root", str(ctx.exception).lower())

    def test_grant_probe_clears_sudo_timestamp(self):
        dest = Path(self.tmp.name) / "wrapper"
        dest.write_text("#!/bin/sh\necho usage:\n")
        dest.chmod(0o755)
        self.mod.NFT_WRAPPER = str(dest)
        order: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            argv = [str(part) for part in cmd]
            order.append(argv)
            if argv[:2] == ["sudo", "-k"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if argv[:2] == ["sudo", "-n"]:
                return subprocess.CompletedProcess(
                    cmd, 2, stdout="usage: distractions-nft replace|flush ds\n", stderr=""
                )
            raise AssertionError(argv)

        with mock.patch.object(self.mod.subprocess, "run", fake_run):
            self.assertTrue(self.mod._wrapper_grant_ok())
        self.assertEqual(order[0][:2], ["sudo", "-k"])
        self.assertEqual(order[1][:2], ["sudo", "-n"])

        def fail_reset(cmd, **kwargs):
            argv = [str(part) for part in cmd]
            if argv[:2] == ["sudo", "-k"]:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
            raise AssertionError(argv)

        with mock.patch.object(self.mod.subprocess, "run", fail_reset):
            self.assertFalse(self.mod._wrapper_grant_ok())

    def test_clean_install_creates_dirs_and_0440_grant(self):
        args = self._install()
        dest = args["wrapper_dest"]
        sudoers = args["sudoers_path"]
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.read_bytes(), args["wrapper_src"].read_bytes())
        self.assertEqual(stat.S_IMODE(sudoers.stat().st_mode), 0o440)
        self.assertIn(self.principal, sudoers.read_text())
        self.assertNotIn("__INSTALL_USER__", sudoers.read_text())

    def test_refuses_symlink_ancestor(self):
        root, src, dest, sudoers, lock = self._tree()
        real = root / "real-libexec"
        real.mkdir(parents=True)
        os.chmod(real, 0o755)
        (root / "usr/local").mkdir(parents=True)
        os.chmod(root / "usr", 0o755)
        os.chmod(root / "usr/local", 0o755)
        (root / "usr/local/libexec").symlink_to(real)
        target = real / "omarchy-distraction-space" / "secret"
        target.parent.mkdir()
        target.write_text("do-not-touch")
        with self.assertRaises(self.mod._SetupClosed) as ctx:
            self.mod._privileged_install(
                wrapper_src=src,
                wrapper_dest=dest,
                sudoers_path=sudoers,
                principal=self.principal,
                trusted_uid=self.uid,
                lock_path=lock,
                fs_root=root,
            )
        self.assertIn("symlink", str(ctx.exception))
        self.assertEqual(target.read_text(), "do-not-touch")
        self.assertFalse(dest.exists())

    def test_refuses_symlink_dest_without_following(self):
        root, src, dest, sudoers, lock = self._tree()
        dest.parent.mkdir(parents=True)
        for path in dest.parents:
            if path == root or root not in path.parents and path != root:
                continue
            if str(path).startswith(str(root)):
                os.chmod(path, 0o755)
        os.chmod(dest.parent, 0o755)
        target = root / "other-wrapper"
        target.write_text("keep-me")
        dest.symlink_to(target)
        sudoers.write_text("old-grant\n")
        os.chmod(sudoers, 0o440)
        with self.assertRaises(self.mod._SetupClosed) as ctx:
            self.mod._privileged_install(
                wrapper_src=src,
                wrapper_dest=dest,
                sudoers_path=sudoers,
                principal=self.principal,
                trusted_uid=self.uid,
                lock_path=lock,
                fs_root=root,
            )
        self.assertIn("symlink", str(ctx.exception))
        self.assertEqual(target.read_text(), "keep-me")
        self.assertTrue(dest.is_symlink())
        self.assertFalse(sudoers.exists())

    def test_refuses_user_writable_ancestor(self):
        root, src, dest, sudoers, lock = self._tree()
        dest.parent.mkdir(parents=True)
        for path in [root / "usr", root / "usr/local", root / "usr/local/libexec", dest.parent]:
            os.chmod(path, 0o755)
        os.chmod(root / "usr/local/libexec", 0o777)
        sudoers.write_text("old-grant\n")
        os.chmod(sudoers, 0o440)
        with self.assertRaises(self.mod._SetupClosed) as ctx:
            self.mod._privileged_install(
                wrapper_src=src,
                wrapper_dest=dest,
                sudoers_path=sudoers,
                principal=self.principal,
                trusted_uid=self.uid,
                lock_path=lock,
                fs_root=root,
            )
        self.assertIn("untrusted", str(ctx.exception))
        self.assertFalse(dest.exists())
        self.assertFalse(sudoers.exists())

    def test_refuses_group_writable_ancestor(self):
        root, src, dest, sudoers, lock = self._tree()
        dest.parent.mkdir(parents=True)
        for path in [root / "usr", root / "usr/local", root / "usr/local/libexec", dest.parent]:
            os.chmod(path, 0o755)
        os.chmod(root / "usr/local/libexec", 0o770)
        sudoers.write_text("old-grant\n")
        os.chmod(sudoers, 0o440)
        with self.assertRaises(self.mod._SetupClosed) as ctx:
            self.mod._privileged_install(
                wrapper_src=src,
                wrapper_dest=dest,
                sudoers_path=sudoers,
                principal=self.principal,
                trusted_uid=self.uid,
                lock_path=lock,
                fs_root=root,
            )
        self.assertIn("untrusted", str(ctx.exception))
        self.assertFalse(dest.exists())
        self.assertFalse(sudoers.exists())

    def test_wrong_mode_wrapper_is_repaired(self):
        root, src, dest, sudoers, lock = self._tree()
        dest.parent.mkdir(parents=True)
        for path in [root / "usr", root / "usr/local", root / "usr/local/libexec", dest.parent]:
            os.chmod(path, 0o755)
        dest.write_bytes(src.read_bytes())
        os.chmod(dest, 0o644)
        self.mod._privileged_install(
            wrapper_src=src,
            wrapper_dest=dest,
            sudoers_path=sudoers,
            principal=self.principal,
            trusted_uid=self.uid,
            lock_path=lock,
            fs_root=root,
        )
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(sudoers.stat().st_mode), 0o440)

    def test_interrupt_after_grant_keeps_wrapper(self):
        real = self.mod._commit_grant

        def commit_then_interrupt(*args, **kwargs):
            real(*args, **kwargs)
            raise KeyboardInterrupt()

        with mock.patch.object(self.mod, "_commit_grant", commit_then_interrupt):
            args = self._install()
        dest = args["wrapper_dest"]
        sudoers = args["sudoers_path"]
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.read_bytes(), args["wrapper_src"].read_bytes())
        self.assertTrue(sudoers.exists())
        self.assertEqual(stat.S_IMODE(sudoers.stat().st_mode), 0o440)

    def test_disable_grant_when_dest_missing_then_repair(self):
        root, src, dest, sudoers, lock = self._tree()
        sudoers.write_text("old-grant\n")
        os.chmod(sudoers, 0o440)
        self.mod._privileged_install(
            wrapper_src=src,
            wrapper_dest=dest,
            sudoers_path=sudoers,
            principal=self.principal,
            trusted_uid=self.uid,
            lock_path=lock,
            fs_root=root,
        )
        self.assertTrue(dest.is_file())
        self.assertIn(self.principal, sudoers.read_text())
        self.assertNotEqual(sudoers.read_text(), "old-grant\n")

    def test_ancestor_replaced_after_pin_does_not_commit_grant(self):
        root, src, dest, sudoers, lock = self._tree()
        dest.parent.mkdir(parents=True)
        for path in [root / "usr", root / "usr/local", root / "usr/local/libexec", dest.parent]:
            os.chmod(path, 0o755)
        dest.write_bytes(src.read_bytes())
        os.chmod(dest, 0o755)
        pinned = self.mod._pin_or_create_ancestors(dest, self.uid, create=False, fs_root=root)
        libexec = root / "usr/local/libexec"
        os.rename(libexec, root / "libexec.old")
        libexec.mkdir()
        os.chmod(libexec, 0o755)
        (libexec / "omarchy-distraction-space").mkdir()
        os.chmod(libexec / "omarchy-distraction-space", 0o755)
        (libexec / "omarchy-distraction-space" / dest.name).write_bytes(src.read_bytes())
        os.chmod(libexec / "omarchy-distraction-space" / dest.name, 0o755)
        sudoers.write_text("old-grant\n")
        os.chmod(sudoers, 0o440)
        wrapper_fd = os.open(dest, os.O_RDONLY | os.O_CLOEXEC)
        try:
            with self.assertRaises(self.mod._SetupClosed) as ctx:
                self.mod._revalidate_chain(
                    pinned, dest, src.read_bytes(), self.uid, root, wrapper_fd
                )
        finally:
            os.close(wrapper_fd)
            pinned.close()
        self.assertIn("replaced", str(ctx.exception))
        self.assertEqual(sudoers.read_text(), "old-grant\n")

    def test_wrapper_identity_mismatch_does_not_commit_grant(self):
        root, src, dest, sudoers, lock = self._tree()
        dest.parent.mkdir(parents=True)
        for path in [root / "usr", root / "usr/local", root / "usr/local/libexec", dest.parent]:
            os.chmod(path, 0o755)
        dest.write_bytes(src.read_bytes())
        os.chmod(dest, 0o755)
        pinned = self.mod._pin_or_create_ancestors(dest, self.uid, create=False, fs_root=root)
        wrapper_fd = os.open(dest, os.O_RDONLY | os.O_CLOEXEC)
        os.unlink(dest)
        dest.write_bytes(src.read_bytes())
        os.chmod(dest, 0o755)
        sudoers.write_text("old-grant\n")
        os.chmod(sudoers, 0o440)
        try:
            with self.assertRaises(self.mod._SetupClosed) as ctx:
                self.mod._revalidate_chain(
                    pinned, dest, src.read_bytes(), self.uid, root, wrapper_fd
                )
        finally:
            os.close(wrapper_fd)
            pinned.close()
        self.assertIn("identity", str(ctx.exception))
        self.assertEqual(sudoers.read_text(), "old-grant\n")

    def test_interrupted_replace_leaves_previous_wrapper(self):
        root, src, dest, sudoers, lock = self._tree()
        dest.parent.mkdir(parents=True)
        for path in [root / "usr", root / "usr/local", root / "usr/local/libexec", dest.parent]:
            os.chmod(path, 0o755)
        dest.write_bytes(b"previous-wrapper\n")
        os.chmod(dest, 0o755)

        def boom(src_name, dst_name, **kwargs):
            raise OSError("interrupted replace")

        with mock.patch.object(self.mod.os, "rename", boom):
            with self.assertRaises(self.mod._SetupClosed):
                self.mod._privileged_install(
                    wrapper_src=src,
                    wrapper_dest=dest,
                    sudoers_path=sudoers,
                    principal=self.principal,
                    trusted_uid=self.uid,
                    lock_path=lock,
                    fs_root=root,
                )
        self.assertEqual(dest.read_bytes(), b"previous-wrapper\n")
        self.assertFalse(sudoers.exists())

    def test_visudo_reject_leaves_previous_grant(self):
        root, src, dest, sudoers, lock = self._tree()
        dest.parent.mkdir(parents=True)
        for path in [root / "usr", root / "usr/local", root / "usr/local/libexec", dest.parent]:
            os.chmod(path, 0o755)
        dest.write_bytes(src.read_bytes())
        os.chmod(dest, 0o755)
        sudoers.write_text("previous-grant\n")
        os.chmod(sudoers, 0o440)
        real = self.mod.subprocess.run

        def fake_run(cmd, **kwargs):
            argv = [str(part) for part in cmd]
            if argv[:1] == ["visudo"]:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="bad grant")
            return real(cmd, **kwargs)

        with mock.patch.object(self.mod.subprocess, "run", fake_run):
            with self.assertRaises(self.mod._SetupClosed) as ctx:
                self.mod._privileged_install(
                    wrapper_src=src,
                    wrapper_dest=dest,
                    sudoers_path=sudoers,
                    principal=self.principal,
                    trusted_uid=self.uid,
                    lock_path=lock,
                    fs_root=root,
                )
        self.assertIn("bad grant", str(ctx.exception))
        self.assertEqual(sudoers.read_text(), "previous-grant\n")

    def test_concurrent_setups_share_lock(self):
        lock = Path(self.tmp.name) / "lock"
        holder = self.mod._acquire_setup_lock(lock)
        started = threading.Event()
        finished = threading.Event()

        def waiter() -> None:
            started.set()
            fd = self.mod._acquire_setup_lock(lock)
            finished.set()
            self.mod.fcntl.flock(fd, self.mod.fcntl.LOCK_UN)
            os.close(fd)

        thread = threading.Thread(target=waiter)
        thread.start()
        self.assertTrue(started.wait(1))
        self.assertFalse(finished.wait(0.15))
        self.mod.fcntl.flock(holder, self.mod.fcntl.LOCK_UN)
        os.close(holder)
        self.assertTrue(finished.wait(1))
        thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
