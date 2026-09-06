"""WirePlumber hold hook: the flag the listener writes, the script and fragment setup installs, and the loaded check."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from ds import hypr, launch, state

ROOT = Path(__file__).resolve().parent.parent
APP_ID = launch._PULSE_APPLICATION_ID
SCRIPT_NAME = "distraction-space-hold-mute.lua"
FRAGMENT_NAME = "distraction-space-hold-mute.conf"
FLAG_NAME = "hold.flag"
METADATA_NAME = APP_ID
PW_METADATA_TIMEOUT = 5
LOAD_WAIT = 5.0


def flag_path():
    return state.state_path(FLAG_NAME)


def config_dir():
    raw = os.environ.get("XDG_CONFIG_HOME")
    base = Path(raw) if raw else Path.home() / ".config"
    return base / "wireplumber"


def script_path():
    return config_dir() / "scripts" / SCRIPT_NAME


def fragment_path():
    return config_dir() / "wireplumber.conf.d" / FRAGMENT_NAME


def render_script(flag=None):
    text = (ROOT / "install" / SCRIPT_NAME).read_text(encoding="utf-8")
    if text.count("@HOLD_FLAG@") != 1:
        raise ValueError(f"{SCRIPT_NAME} must contain @HOLD_FLAG@ exactly once")
    path = flag if flag is not None else flag_path()
    return text.replace("@HOLD_FLAG@", hypr.lua_string(str(path)))


def fragment_text():
    return (ROOT / "install" / FRAGMENT_NAME).read_text(encoding="utf-8")


def wireplumber_bin():
    found = shutil.which(os.environ.get("DS_WIREPLUMBER", "wireplumber"))
    return Path(found).resolve() if found else None


def installed():
    return script_path().is_file() and fragment_path().is_file()


def loaded():
    """True when the hook's metadata is visible, False when it is not, None when that cannot be told."""
    try:
        proc = subprocess.run(
            ["pw-metadata", "-n", METADATA_NAME],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
            timeout=PW_METADATA_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    marker = f'Found "{METADATA_NAME}" metadata'
    for line in (proc.stdout or "").splitlines():
        if line.startswith(marker):
            return True
    return False


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
