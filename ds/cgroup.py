"""Slice membership: which processes belong to the space.

The space is `app-distraction.slice` under the person's user manager. A process
is in it when the fifth component of its unified-hierarchy cgroup path is that
slice, the same test the privileged wrapper's `socket cgroupv2 level 5` rule makes.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SLICE = "app-distraction.slice"
SLICE_LEVEL = 5
SYSTEMCTL_TIMEOUT = 30.0


def slice_path(uid: int) -> str:
    """Cgroup path of uid's distraction slice; distractions-nft renders the same one."""
    return f"user.slice/user-{uid}.slice/user@{uid}.service/app.slice/{SLICE}"


def _proc_root(proc) -> Path:
    if proc is not None:
        return Path(proc)
    return Path(os.environ.get("DS_PROC_ROOT") or "/proc")


def cgroup_of(pid, proc=None) -> str | None:
    """The `0::` cgroup path of pid, or None when the file is unreadable or has none."""
    try:
        text = (_proc_root(proc) / str(pid) / "cgroup").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("0::"):
            return line[3:].strip()
    return None


def in_slice(pid, proc=None) -> bool:
    path = cgroup_of(pid, proc)
    if path is None:
        return False
    parts = path.strip("/").split("/")
    return len(parts) >= SLICE_LEVEL and parts[SLICE_LEVEL - 1] == SLICE


def _ppid(pid, proc) -> int | None:
    """Parent pid from /proc/<pid>/stat, read after the last `)` since the comm can hold spaces."""
    try:
        text = (_proc_root(proc) / str(pid) / "stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fields = text.rpartition(")")[2].split()
    try:
        return int(fields[1])
    except (IndexError, ValueError):
        return None


def ancestor_in_slice(pid, hops=8, proc=None) -> bool:
    """True when pid itself or one of its nearest `hops` ancestors is in the slice."""
    current = pid
    for _ in range(hops + 1):
        if in_slice(current, proc):
            return True
        parent = _ppid(current, proc)
        if parent is None or parent < 1 or parent == current:
            return False
        current = parent
    return False


def systemctl_user(*args: str) -> tuple[int, str]:
    """`systemctl --user <args>` as the person, never through sudo: (rc, stderr)."""
    from ds.net import run_command
    try:
        proc = run_command(
            ["systemctl", "--user", *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=SYSTEMCTL_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return proc.returncode, (proc.stderr or "").strip()


def ensure_slice() -> bool:
    """Start the persistent slice so its cgroup exists before the wrapper renders."""
    rc, _err = systemctl_user("start", SLICE)
    return rc == 0
