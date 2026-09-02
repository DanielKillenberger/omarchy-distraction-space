#!/usr/bin/env python3
"""Cutover: deleted files gone, no leftover module name, no stale hotkey text."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_NEEDLE = "focus" + "_block"
_OLD_KEY = "Super" + "+D"
_KEY_PHRASES = ("Super+Ctrl+Shift" + "+D", "Super+Alt" + "+D")
_DELETED = (
    "focus" + "_block.py",
    "focus" + "_dns.py",
    "NotificationFilter.qml",
    "PingCapture.qml",
    "notification-members.json",
    "app-list-defaults.json",
    "defaults/destinations.json",
    "focus.json",
)


def _skip_dir(name: str) -> bool:
    return name in {".git", "__pycache__", ".pyc", ".worktrees", ".clawpatch"}


class TreeTests(unittest.TestCase):
    def test_deleted_files_absent(self):
        missing_ok = []
        for rel in _DELETED:
            path = ROOT / rel
            self.assertFalse(path.exists(), f"deleted file still present: {rel}")
            missing_ok.append(rel)
        self.assertFalse((ROOT / "defaults").exists(), "empty defaults/ directory still present")
        self.assertEqual(len(missing_ok), len(_DELETED))

    def test_no_deleted_module_name_outside_flow(self):
        hits = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [n for n in dirnames if not _skip_dir(n) and n != ".flow"]
            rel_dir = Path(dirpath).relative_to(ROOT)
            if ".flow" in rel_dir.parts:
                continue
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if _NEEDLE in text:
                    hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [], f"{_NEEDLE} remains outside .flow/: {hits}")

    def test_bindings_toggle_is_super_ctrl_shift_d(self):
        lua = (ROOT / "hypr" / "bindings.lua").read_text(encoding="utf-8")
        self.assertIn('o.bind("SUPER + CTRL + SHIFT + D", "Toggle distraction space"', lua)
        self.assertNotIn('"SUPER + D"', lua)
        self.assertIn('o.bind("SUPER + ALT + D"', lua)
        self.assertIn('o.bind("SUPER + CTRL + SHIFT + F"', lua)

    def test_no_bare_old_hotkey_outside_flow(self):
        hits = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [n for n in dirnames if not _skip_dir(n) and n != ".flow"]
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for phrase in _KEY_PHRASES:
                    text = text.replace(phrase, "")
                if _OLD_KEY in text:
                    hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [], f"bare {_OLD_KEY} remains outside .flow/: {hits}")


if __name__ == "__main__":
    unittest.main()
