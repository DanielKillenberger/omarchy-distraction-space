"""Temp HOME/XDG sandbox and fake-binary-on-PATH helper for plugin tests."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ENV_KEYS = ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "PATH")


class Sandbox:
    def __init__(self, isolate_path: bool = False):
        self.isolate_path = isolate_path
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.home = base / "home"
        self.config = base / "config"
        self.state = base / "state"
        self.runtime = base / "runtime"
        self.bin = base / "bin"
        for p in (self.home, self.config, self.state, self.runtime, self.bin):
            p.mkdir()
        (self.config / "omarchy").mkdir()
        (self.state / "omarchy" / "distraction-space").mkdir(parents=True)
        self._orig_env: dict[str, str | None] | None = None
        self._path_inserted = False
        self._closed = False

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
            XDG_STATE_HOME=str(self.state),
            XDG_RUNTIME_DIR=str(self.runtime),
            PATH=path,
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

    def restore_env(self) -> None:
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

    def run(self, *args, input=None, timeout=60, extra_env=None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "distractions"), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=input,
            timeout=timeout,
            env=self.env(extra=extra_env),
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
