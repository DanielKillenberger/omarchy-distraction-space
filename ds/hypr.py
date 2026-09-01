"""Hyprland workspace queries now; window rules in a later task."""

import json
import subprocess

SPACE = "distraction"


def hyprctl_json(*args):
    r = subprocess.run(
        ["hyprctl", "-j", *args], capture_output=True, text=True, timeout=5, check=True
    )
    return json.loads(r.stdout)


def active_workspace():
    try:
        data = hyprctl_json("activeworkspace")
    except Exception:
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return name if isinstance(name, str) else None


def on_space():
    try:
        data = hyprctl_json("activeworkspace")
    except Exception:
        return None
    return isinstance(data, dict) and data.get("name") == SPACE


def apply_rules(expanded): raise NotImplementedError
def handle_event(line): raise NotImplementedError
def move_to_space(address): raise NotImplementedError
def cycle(direction): raise NotImplementedError
def cmd_next(args): raise NotImplementedError
def cmd_prev(args): raise NotImplementedError
