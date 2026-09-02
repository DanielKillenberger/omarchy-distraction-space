#!/usr/bin/env python3
"""Cutover: deleted files gone, no leftover module name, line cap."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINE_CAP = 2000
_NEEDLE = "focus" + "_block"
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
    return name in {".git", "__pycache__", ".pyc"}


def _non_test_python() -> list[Path]:
    paths = [ROOT / "distractions", ROOT / "distractions-nft"]
    paths.extend(sorted((ROOT / "ds").glob("*.py")))
    return paths


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

    def test_non_test_python_under_line_cap(self):
        total = 0
        for path in _non_test_python():
            self.assertTrue(path.is_file(), f"missing {path}")
            total += len(path.read_text(encoding="utf-8").splitlines())
        self.assertLess(
            total,
            LINE_CAP,
            f"non-test Python is {total} lines, cap is {LINE_CAP}",
        )


if __name__ == "__main__":
    unittest.main()
