#!/usr/bin/env python3
"""Catalog expansion and catalog CLI tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds.catalog import DEFAULT_LIST, expand, expand_entry, load_catalog, names


class CatalogTests(unittest.TestCase):
    def test_telegram_native_and_pwa_class(self):
        item = expand_entry("Telegram")
        self.assertEqual(
            item["classes"],
            ["org.telegram.desktop", "^chrome-web\\.telegram\\.org__.*$"],
        )
        spec = load_catalog()["Telegram"]
        self.assertEqual(item["hosts"], spec["hosts"])
        self.assertEqual(item["senders"], spec["senders"])
        self.assertEqual(item["audio"], spec["audio"])

    def test_discord_pwa_class_only(self):
        item = expand_entry("Discord")
        self.assertEqual(item["classes"], ["^chrome-discord\\.com__.*$"])

    def test_hostname_entry(self):
        item = expand_entry("x.com")
        self.assertEqual(item["classes"], ["^chrome-x\\.com__.*$"])
        self.assertEqual(item["hosts"], ["x.com", "www.x.com"])
        self.assertEqual(item["senders"], [])
        self.assertEqual(item["audio"], {})

    def test_www_hostname_twin_is_bare(self):
        item = expand_entry("www.example.com")
        self.assertEqual(item["hosts"], ["www.example.com", "example.com"])
        self.assertEqual(item["classes"], ["^chrome-www\\.example\\.com__.*$"])

    def test_class_entry(self):
        item = expand_entry("class=^Slack$")
        self.assertEqual(item["classes"], ["^Slack$"])
        self.assertEqual(item["hosts"], [])
        self.assertEqual(item["name"], "class=^Slack$")

    def test_object_class_and_hosts(self):
        item = expand_entry(
            {"name": "Slack", "class": "^Slack$", "hosts": ["slack.com", "app.slack.com"]}
        )
        self.assertEqual(item["classes"], ["^Slack$", "^chrome-slack\\.com__.*$"])
        self.assertEqual(item["hosts"], ["slack.com", "app.slack.com"])

    def test_object_hosts_only(self):
        item = expand_entry({"name": "Site", "hosts": ["example.com"]})
        self.assertEqual(item["classes"], ["^chrome-example\\.com__.*$"])
        self.assertEqual(item["hosts"], ["example.com"])

    def test_object_senders_and_audio_expand_without_crash(self):
        item = expand_entry(
            {
                "name": "Slack",
                "class": "^Slack$",
                "hosts": ["slack.com"],
                "senders": ["Slack"],
                "audio": {"name": ["Slack"], "binary": ["slack"]},
            }
        )
        self.assertEqual(item["senders"], ["Slack"])
        self.assertEqual(item["audio"], {"name": ["Slack"], "binary": ["slack"]})
        missing = expand_entry({"name": "Site", "hosts": ["example.com"]})
        self.assertEqual(missing["senders"], [])
        self.assertEqual(missing["audio"], {})

    def test_unknown_catalog_name_skipped(self):
        self.assertIsNone(expand_entry("NotAProduct"))
        self.assertEqual(expand({"list": ["NotAProduct"]}), [])

    def test_names_and_defaults(self):
        n = names()
        self.assertEqual(len(n), 19)
        self.assertEqual(n[:15], DEFAULT_LIST)
        self.assertEqual(
            set(n) - set(DEFAULT_LIST),
            {"Bluesky", "Pinterest", "Tumblr", "LinkedIn"},
        )
        self.assertEqual(len(DEFAULT_LIST), 15)

    def test_catalog_cli_prints_names(self):
        with Sandbox() as box:
            r = box.run("catalog")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.splitlines(), names())


if __name__ == "__main__":
    unittest.main()

    def test_moved_versus_blocked_table(self):
        moved_only = ["Telegram", "Discord", "WhatsApp", "Signal", "Google Messages"]
        blocked_only = ["Facebook", "Instagram", "Threads", "Reddit", "TikTok",
                        "Snapchat", "YouTube", "Twitch", "Netflix"]
        for name in moved_only:
            item = expand_entry(name)
            self.assertTrue(item["classes"], f"{name} must still move windows")
            self.assertEqual(item["hosts"], [], f"{name} must not be network-blocked")
        x = expand_entry("X")
        self.assertTrue(x["classes"])
        self.assertTrue(x["hosts"])
        for name in blocked_only:
            item = expand_entry(name)
            self.assertTrue(item["hosts"], f"{name} must be network-blocked")
        self.assertEqual(sorted(moved_only + ["X"] + blocked_only), sorted(DEFAULT_LIST))

