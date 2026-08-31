#!/usr/bin/env python3
"""Unit tests for the focus-mode network block (no root, no live nft)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import focus_block

R7 = [
    "Telegram",
    "Discord",
    "WhatsApp",
    "Signal",
    "Google Messages",
    "Facebook",
    "Instagram",
    "Threads",
    "X",
    "Reddit",
    "TikTok",
    "Snapchat",
    "YouTube",
    "Twitch",
    "Netflix",
]


class FakeBackend(focus_block.NetworkBackend):
    def __init__(self, hosts: str = "127.0.0.1 localhost\n", nft: str | None = None, fail_on: str | None = None):
        self.hosts = hosts
        self.nft = nft
        self.fail_on = fail_on
        self.writes: list[str] = []
        self.nft_applies: list[str] = []
        self.deleted = 0
        self.flushed: list[str] = []
        self.resolutions = {
            "youtube.com": (["203.0.113.10"], ["2001:db8::10"]),
            "www.youtube.com": (["203.0.113.10"], []),
        }

    def nft_available(self) -> bool:
        return True

    def read_hosts(self) -> str:
        return self.hosts

    def write_hosts(self, text: str) -> None:
        if self.fail_on == "write_hosts":
            raise RuntimeError("hosts write failed")
        self.writes.append(text)
        self.hosts = text

    def nft_list(self) -> str | None:
        return self.nft

    def nft_apply(self, ruleset: str) -> None:
        if self.fail_on == "nft_apply":
            raise RuntimeError("nft apply failed")
        self.nft_applies.append(ruleset)
        self.nft = ruleset

    def nft_delete(self) -> None:
        if self.fail_on == "nft_delete":
            raise RuntimeError("nft delete failed")
        self.deleted += 1
        self.nft = None

    def resolve(self, host: str) -> tuple[list[str], list[str]]:
        return self.resolutions.get(host, ([], []))

    def flush_conntrack(self, addresses: list[str]) -> None:
        self.flushed.extend(addresses)


class DefaultsTests(unittest.TestCase):
    def test_r7_membership_and_youtube(self):
        defaults = focus_block.load_defaults()
        names = focus_block.shipped_default_names(defaults)
        self.assertEqual(names, R7)
        self.assertIn("YouTube", names)
        for extra in focus_block.USER_ADD_ONLY:
            self.assertNotIn(extra, names)
            self.assertIsNotNone(focus_block.catalog_lookup(defaults["catalog"], extra))

    def test_missing_defaults_omits_youtube_and_extras(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            warnings: list[str] = []
            names = focus_block.active_names(
                config={},
                defaults_path=missing,
                warnings=warnings,
            )
            self.assertNotIn("YouTube", names)
            self.assertEqual(list(focus_block.PERMANENT_OPEN), names)
            joined = " ".join(warnings).lower()
            self.assertIn("defaults", joined)
            self.assertIn("youtube", joined)

    def test_active_list_includes_permanent_and_extras(self):
        names = focus_block.active_names(config={}, defaults=focus_block.load_defaults())
        for name in focus_block.PERMANENT_OPEN:
            self.assertIn(name, names)
        for extra in ("YouTube", "Netflix", "Twitch", "Reddit"):
            self.assertIn(extra, names)

    def test_missing_defaults_omits_youtube_from_user_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            warnings: list[str] = []
            names = focus_block.active_names(
                config={"destinations": ["YouTube", "example.com", "LinkedIn"]},
                defaults_path=missing,
                warnings=warnings,
            )
            self.assertNotIn("YouTube", names)
            self.assertIn("example.com", names)
            self.assertNotIn("LinkedIn", names)
            self.assertTrue(any("youtube" in item.lower() for item in warnings))

    def test_user_list_replaces_defaults_until_changed(self):
        defaults = focus_block.load_defaults()
        names = focus_block.active_names(
            config={"destinations": ["YouTube", "Bluesky"]},
            defaults=defaults,
        )
        self.assertEqual(names, ["YouTube", "Bluesky"])


class EditTests(unittest.TestCase):
    def test_add_remove_without_rebuilding(self):
        defaults = focus_block.load_defaults()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "focus.json"
            config_path.write_text("{}\n", encoding="utf-8")
            added = focus_block.add_destination(
                "Bluesky", config_path=config_path, defaults_path=ROOT / "defaults" / "destinations.json"
            )
            self.assertEqual(added, "Bluesky")
            data = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertIn("Bluesky", data["destinations"])
            self.assertIn("YouTube", data["destinations"])
            removed = focus_block.remove_destination(
                "YouTube", config_path=config_path, defaults_path=ROOT / "defaults" / "destinations.json"
            )
            self.assertEqual(removed, "YouTube")
            data = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("YouTube", data["destinations"])
            self.assertIn("Bluesky", data["destinations"])
            plugin_defaults = json.loads((ROOT / "defaults" / "destinations.json").read_text())
            self.assertEqual(plugin_defaults["default"], R7)

    def test_rejected_entry_does_not_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "focus.json"
            config_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(focus_block.BlockError):
                focus_block.add_destination(
                    "../etc/passwd",
                    config_path=config_path,
                    defaults_path=ROOT / "defaults" / "destinations.json",
                )
            with self.assertRaises(focus_block.BlockError):
                focus_block.add_destination(
                    "#evil",
                    config_path=config_path,
                    defaults_path=ROOT / "defaults" / "destinations.json",
                )
            with self.assertRaises(focus_block.BlockError):
                focus_block.add_destination(
                    "   ",
                    config_path=config_path,
                    defaults_path=ROOT / "defaults" / "destinations.json",
                )
            self.assertEqual(json.loads(config_path.read_text()), {})
            warnings: list[str] = []
            names = focus_block.active_names(
                config={"destinations": ["YouTube", "../etc/passwd", "Reddit"]},
                defaults=focus_block.load_defaults(),
                warnings=warnings,
            )
            self.assertEqual(names, ["YouTube", "Reddit"])
            self.assertTrue(any("rejected" in item for item in warnings))
            with self.assertRaises(focus_block.BlockError):
                focus_block.add_destination(
                    "DateMeme",
                    config_path=config_path,
                    defaults_path=ROOT / "defaults" / "destinations.json",
                )
            added = focus_block.add_destination(
                "LinkedIn",
                config_path=config_path,
                defaults_path=ROOT / "defaults" / "destinations.json",
            )
            self.assertEqual(added, "LinkedIn")
            hosts = focus_block.hostnames_for("LinkedIn", focus_block.load_defaults())
            self.assertIn("linkedin.com", hosts)


class RenderTests(unittest.TestCase):
    def test_hosts_and_nft_render(self):
        fragment = focus_block.hosts_fragment(["youtube.com", "www.youtube.com"])
        self.assertIn(focus_block.HOSTS_BEGIN, fragment)
        self.assertIn("0.0.0.0 youtube.com", fragment)
        self.assertIn("::1 youtube.com", fragment)
        spliced = focus_block.splice_hosts("127.0.0.1 localhost\n", fragment)
        self.assertIn("0.0.0.0 youtube.com", spliced)
        lifted = focus_block.splice_hosts(spliced, None)
        self.assertNotIn("youtube.com", lifted)
        self.assertIn("localhost", lifted)
        rules = focus_block.nft_ruleset(["203.0.113.10"], ["2001:db8::10"])
        self.assertIn("table inet omarchy_focus", rules)
        self.assertIn("203.0.113.10", rules)
        self.assertIn("ip daddr @v4 drop", rules)

    def test_youtube_hostnames_from_catalog(self):
        defaults = focus_block.load_defaults()
        hosts = focus_block.hostnames_for("YouTube", defaults)
        self.assertIn("youtube.com", hosts)
        self.assertIn("www.youtube.com", hosts)
        self.assertIn("youtu.be", hosts)


class ApplyLiftTests(unittest.TestCase):
    def test_apply_failure_restores_previous_state(self):
        previous = "127.0.0.1 localhost\n"
        previous_nft = "table inet omarchy_focus { }"
        backend = FakeBackend(hosts=previous, nft=previous_nft, fail_on="nft_apply")
        with self.assertRaises(focus_block.BlockError):
            focus_block.apply_block(
                backend=backend,
                config={"destinations": ["YouTube"]},
                notify=False,
            )
        self.assertEqual(backend.hosts, previous)
        self.assertEqual(backend.nft, previous_nft)

    def test_apply_success_writes_hosts_and_nft(self):
        backend = FakeBackend()
        focus_block.apply_block(
            backend=backend,
            config={"destinations": ["YouTube"]},
            notify=False,
        )
        self.assertIn("0.0.0.0 youtube.com", backend.hosts)
        self.assertTrue(backend.nft_applies)
        self.assertIn("203.0.113.10", backend.nft_applies[-1])

    def test_lift_failure_leaves_blocks(self):
        hosts = focus_block.splice_hosts(
            "127.0.0.1 localhost\n",
            focus_block.hosts_fragment(["youtube.com"]),
        )
        backend = FakeBackend(hosts=hosts, nft="table inet omarchy_focus { }", fail_on="nft_delete")
        with self.assertRaises(focus_block.BlockError):
            focus_block.lift_block(backend=backend, notify=False)
        self.assertIn("youtube.com", backend.hosts)
        self.assertIsNotNone(backend.nft)

    def test_nft_unavailable_leaves_previous_state(self):
        previous = "127.0.0.1 localhost\n"
        backend = FakeBackend(hosts=previous, nft=None)
        backend.nft_available = lambda: False  # type: ignore[method-assign]
        with self.assertRaises(focus_block.BlockError):
            focus_block.apply_block(
                backend=backend,
                config={"destinations": ["YouTube"]},
                notify=False,
            )
        self.assertEqual(backend.hosts, previous)
        self.assertFalse(backend.writes)

    def test_nft_delete_failure_is_reported(self):
        hosts = focus_block.splice_hosts(
            "127.0.0.1 localhost\n",
            focus_block.hosts_fragment(["youtube.com"]),
        )
        backend = FakeBackend(hosts=hosts, nft="table inet omarchy_focus { }", fail_on="nft_delete")
        with self.assertRaises(focus_block.BlockError):
            focus_block.lift_block(backend=backend, notify=False)
        self.assertIn("youtube.com", backend.hosts)

    def test_lift_success_removes_block(self):
        hosts = focus_block.splice_hosts(
            "127.0.0.1 localhost\n",
            focus_block.hosts_fragment(["youtube.com"]),
        )
        backend = FakeBackend(hosts=hosts, nft="table inet omarchy_focus { }")
        focus_block.lift_block(backend=backend, notify=False)
        self.assertNotIn("youtube.com", backend.hosts)
        self.assertIsNone(backend.nft)


if __name__ == "__main__":
    unittest.main()
