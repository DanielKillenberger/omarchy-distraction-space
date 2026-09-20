"""Temp HOME/XDG sandbox and fake-binary-on-PATH helper for plugin tests."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ENV_KEYS = ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR",
             "PATH", "PYTHONPATH")


class Tty(io.StringIO):
    """stdin as a terminal: what the person types, or nothing at all."""

    def isatty(self):
        return True


class ClosedTty(Tty):
    """A terminal where nobody types: setup may run, but a prompt is a test failure."""

    def readline(self):
        raise AssertionError("setup prompted")


class Sandbox:
    def __init__(self, isolate_path: bool = False):
        self.isolate_path = isolate_path
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.home = base / "home"
        self.config = base / "config"
        self.data = base / "data"
        self.state = base / "state"
        self.runtime = base / "runtime"
        self.bin = base / "bin"
        for p in (self.home, self.config, self.data, self.state, self.runtime, self.bin):
            p.mkdir()
        (self.config / "omarchy").mkdir()
        (self.state / "omarchy" / "distraction-space").mkdir(parents=True)
        # The two root-owned destinations are module constants with no environment
        # override, so a sandbox moves them the only way there is: into the module,
        # in this process and in every `distractions` child. Without that, whether
        # the firewall helper is installed would be a fact about the machine running
        # the suite, and every test that asks would answer differently on a
        # developer's box and on CI.
        self.root = base / "root"
        self.wrapper = self.root / "libexec" / "omarchy-distraction-space" / "distractions-nft"
        self.sudoers = self.root / "etc" / "sudoers.d" / "omarchy-distraction-space"
        for p in (self.wrapper.parent, self.sudoers.parent):
            p.mkdir(parents=True)
        self.site = base / "pysite"
        self.site.mkdir()
        self._site_lines: list[str] = []
        self.install_helper()
        self._write_site()
        self._orig_env: dict[str, str | None] | None = None
        self._orig_destinations: tuple[str, str] | None = None
        self._path_inserted = False
        self._closed = False

    def install_helper(self, installed: bool = True) -> None:
        """Whether this sandbox looks like a machine whose setup installed the helper.

        Installed is the default, so a test that says nothing about site blocking
        behaves as it did before the question existed.
        """
        if installed:
            self.wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            self.wrapper.chmod(0o755)
        elif self.wrapper.exists() or self.wrapper.is_symlink():
            self.wrapper.unlink()

    def _write_site(self) -> None:
        """A `sitecustomize` the `distractions` children import, and nothing else does.

        Guarding on the program name keeps the fake binaries on PATH -- which run
        far more often than the CLI -- from importing the plugin at all.
        """
        body = [
            f"sys.path.insert(0, {str(ROOT)!r})",
            "from ds import setup",
            f"setup.WRAPPER_DEFAULT = {str(self.wrapper)!r}",
            f"setup.SUDOERS_DEFAULT = {str(self.sudoers)!r}",
            *self._site_lines,
        ]
        (self.site / "sitecustomize.py").write_text(
            "import os, sys\n"
            "if os.path.basename(sys.argv[0] or '') == 'distractions':\n"
            + "".join(f"    {line}\n" for line in body),
            encoding="utf-8",
        )

    def cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.restore_env()
        self._tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()
        return False

    def env(self, isolate_path: bool | None = None, extra: dict | None = None) -> dict:
        iso = self.isolate_path if isolate_path is None else isolate_path
        path = str(self.bin)
        if not iso:
            path = path + os.pathsep + os.environ.get("PATH", "")
        out = dict(os.environ)
        out.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.config),
            XDG_DATA_HOME=str(self.data),
            XDG_STATE_HOME=str(self.state),
            XDG_RUNTIME_DIR=str(self.runtime),
            PATH=path,
            PYTHONPATH=str(self.site),
        )
        if extra:
            for k, v in extra.items():
                if v is None:
                    out.pop(k, None)
                else:
                    out[k] = v
        return out

    def apply_env(self) -> None:
        if self._orig_env is None:
            self._orig_env = {k: os.environ.get(k) for k in _ENV_KEYS}
        os.environ.update(self.env())
        root = str(ROOT)
        if root not in sys.path:
            sys.path.insert(0, root)
            self._path_inserted = True
        from ds import setup
        if self._orig_destinations is None:
            self._orig_destinations = (setup.WRAPPER_DEFAULT, setup.SUDOERS_DEFAULT)
        setup.WRAPPER_DEFAULT, setup.SUDOERS_DEFAULT = str(self.wrapper), str(self.sudoers)

    def restore_env(self) -> None:
        if self._orig_destinations is not None:
            from ds import setup
            setup.WRAPPER_DEFAULT, setup.SUDOERS_DEFAULT = self._orig_destinations
            self._orig_destinations = None
        if self._orig_env is None:
            return
        for k, v in self._orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._orig_env = None
        if self._path_inserted:
            root = str(ROOT)
            sys.path[:] = [p for p in sys.path if p != root]
            self._path_inserted = False

    def fake_bin(self, name: str, source: str) -> Path:
        text = source if source.startswith("#!") else "#!/usr/bin/env python3\n" + source
        path = self.bin / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
        return path

    def run(self, *args, input=None, timeout=60, extra_env=None, stdin=None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "distractions"), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=input,
            timeout=timeout,
            env=self.env(extra=extra_env),
            **({"stdin": stdin} if input is None and stdin is not None else {}),
        )

    def popen(self, *args, extra_env=None) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, str(ROOT / "distractions"), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            env=self.env(extra=extra_env),
        )

    def hold_config_lock(self, marker: str = "holder-ready") -> subprocess.Popen:
        ready = self.runtime / marker
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import fcntl, os, time\n"
                "from pathlib import Path\n"
                "runtime = Path(os.environ['XDG_RUNTIME_DIR'])\n"
                "lock = runtime / 'distraction-space.config.lock'\n"
                "lock.parent.mkdir(parents=True, exist_ok=True)\n"
                "f = open(lock, 'a+')\n"
                "fcntl.flock(f, fcntl.LOCK_EX)\n"
                f"Path({str(ready)!r}).write_text('1')\n"
                "time.sleep(60)\n",
            ],
            env=self.env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not ready.exists():
            time.sleep(0.01)
        if not ready.exists():
            holder.kill()
            holder.wait(timeout=5)
            raise RuntimeError("config lock holder did not acquire")
        return holder

    def batch_deadline_env(self, seconds: float) -> dict[str, str]:
        self._site_lines = ["from ds import net", f"net.BATCH_DEADLINE = {float(seconds)!r}"]
        self._write_site()
        return {"PYTHONPATH": str(self.site)}

    def wait_file(self, path, timeout: float = 5.0) -> Path:
        path = Path(path)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                return path
            time.sleep(0.02)
        raise TimeoutError(f"timed out waiting for {path}")

    @property
    def config_file(self) -> Path:
        return self.config / "omarchy" / "distraction-space.json"

    @property
    def old_app_list(self) -> Path:
        return self.config / "omarchy" / "app-list.json"

    @property
    def old_focus(self) -> Path:
        return self.config / "omarchy" / "focus.json"

    @property
    def state_dir(self) -> Path:
        return self.state / "omarchy" / "distraction-space"

    @property
    def runtime_dir(self) -> Path:
        return self.runtime
