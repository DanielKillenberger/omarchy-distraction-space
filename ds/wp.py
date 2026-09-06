"""WirePlumber hold hook: the hold key the listener asserts, the script and fragment setup installs, and the loaded check."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from ds import launch

ROOT = Path(__file__).resolve().parent.parent
APP_ID = launch._PULSE_APPLICATION_ID
SCRIPT_NAME = "distraction-space-hold-mute.lua"
FRAGMENT_NAME = "distraction-space-hold-mute.conf"
HOLD_KEY = "hold"
METADATA_NAME = APP_ID
PW_METADATA_TIMEOUT = 5
LOAD_WAIT = 5.0


def config_dir():
    raw = os.environ.get("XDG_CONFIG_HOME")
    base = Path(raw) if raw else Path.home() / ".config"
    return base / "wireplumber"


def data_dir():
    return launch.data_home() / "wireplumber"


def script_path():
    return data_dir() / "scripts" / SCRIPT_NAME


def fragment_path():
    return config_dir() / "wireplumber.conf.d" / FRAGMENT_NAME


def script_text():
    return (ROOT / "install" / SCRIPT_NAME).read_text(encoding="utf-8")


def fragment_text():
    return (ROOT / "install" / FRAGMENT_NAME).read_text(encoding="utf-8")


def wireplumber_bin():
    found = shutil.which(os.environ.get("DS_WIREPLUMBER", "wireplumber"))
    return Path(found).resolve() if found else None


def installed():
    return script_path().is_file() and fragment_path().is_file()


def _pw_metadata(*args):
    """Run `pw-metadata -n METADATA_NAME *args`. `(object_id, error)`: the PipeWire id, or None when the object is absent; `error` is a one-line string on failure."""
    try:
        proc = subprocess.run(
            ["pw-metadata", "-n", METADATA_NAME, *args],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
            timeout=PW_METADATA_TIMEOUT,
        )
    except FileNotFoundError:
        return None, "pw-metadata not found"
    except subprocess.TimeoutExpired:
        return None, "pw-metadata timed out"
    except OSError as e:
        return None, f"pw-metadata: {e}"
    if proc.returncode != 0:
        first = next((ln for ln in (proc.stderr or "").splitlines() if ln), "")
        return None, first or f"pw-metadata: exit {proc.returncode}"
    prefix = f'Found "{METADATA_NAME}" metadata '
    for line in (proc.stdout or "").splitlines():
        if line.startswith(prefix):
            rest = line[len(prefix):].split()
            if rest and rest[0].isdigit():
                return int(rest[0]), None
            break
    return None, None


def loaded():
    """True when the hook's metadata is visible, False when it is not, None when that cannot be told."""
    object_id, error = _pw_metadata()
    if error is not None:
        return None
    return object_id is not None


def hold(on):
    """Set or delete the hold key. `(object_id, error)` as `_pw_metadata`."""
    if on:
        return _pw_metadata("0", HOLD_KEY, '"on"', "Spa:String:JSON")
    return _pw_metadata("0", HOLD_KEY, "-d")


def wait_loaded(seconds=None):
    """Poll until the hook's metadata is visible, or `seconds` (default LOAD_WAIT) elapse."""
    if seconds is None:
        seconds = LOAD_WAIT
    deadline = time.monotonic() + seconds
    last = loaded()
    while last is not True and time.monotonic() < deadline:
        time.sleep(0.5)
        last = loaded()
    return last
