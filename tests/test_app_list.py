#!/usr/bin/env python3
"""Hyprland-free app-list store and expand checks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIPPED_NAMES = [
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
# Messaging apps are windowed but NOT host-blocked: the window rule keeps them
# out of the way, while the off-space IP block would sever their long-lived
# socket every time the active workspace changes.
MESSAGING = ("Telegram", "Discord", "WhatsApp", "Signal", "Google Messages")
WINDOWED = {
    "Telegram": ("org.telegram.desktop", []),
    "Discord": (r"^chrome-discord\.com__.*$", []),
    "WhatsApp": (r"^chrome-web\.whatsapp\.com__.*$", []),
    "X": (
        r"^chrome-x\.com__.*$",
        [
            "x.com",
            "www.x.com",
            "twitter.com",
            "www.twitter.com",
            "mobile.twitter.com",
            "m.twitter.com",
            "api.x.com",
            "api.twitter.com",
            "t.co",
            "www.t.co",
            "abs.twimg.com",
            "pbs.twimg.com",
            "video.twimg.com",
            "cf.twimg.com",
            "abs-0.twimg.com",
            "ton.twimg.com",
            "platform.twitter.com",
        ],
    ),
    "Signal": (r"^signal$", []),
    "Google Messages": (r"^chrome-messages\.google\.com__.*$", []),
}
HOSTS_ONLY = {
    "Facebook": ["facebook.com", "www.facebook.com"],
    "Instagram": ["instagram.com", "www.instagram.com"],
    "Threads": ["threads.net", "www.threads.net"],
    "Reddit": ["reddit.com", "www.reddit.com"],
    "TikTok": ["tiktok.com", "www.tiktok.com"],
    "Snapchat": ["snapchat.com", "www.snapchat.com"],
    "YouTube": ["youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"],
    "Twitch": ["twitch.tv", "www.twitch.tv"],
    "Netflix": ["netflix.com", "www.netflix.com"],
}


def load_mod():
    loader = SourceFileLoader("distractions", str(ROOT / "distractions"))
    spec = spec_from_loader("distractions", loader)
    assert spec is not None
    mod = module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class AppListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_mod()
        self.notes: list[tuple] = []
        self.mod.notify = lambda *args, **kwargs: self.notes.append(args)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.user = self.home / ".config/omarchy/app-list.json"
        self.last_good = Path(self.tmp.name) / "state" / "last-good.json"
        self.defaults = ROOT / "app-list-defaults.json"

    def prepare(self, defaults=None):
        return self.mod.prepare_app_list(
            user_path=self.user,
            defaults_path=defaults if defaults is not None else self.defaults,
        )

    def expand_apply(self, defaults=None):
        return self.mod.app_list_for_apply(
            user_path=self.user,
            defaults_path=defaults if defaults is not None else self.defaults,
            last_good_path=self.last_good,
        )

    def print_expand(self, defaults=None) -> str:
        from io import StringIO

        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            self.mod.print_expand(
                user_path=self.user,
                defaults_path=defaults if defaults is not None else self.defaults,
                last_good_path=self.last_good,
            )
        finally:
            sys.stdout = old
        return buf.getvalue()

    def by_name(self, rows):
        return {row["name"]: row for row in rows}

    def test_missing_user_file_copies_shipped_names(self):
        self.assertFalse(self.user.exists())
        rows = self.prepare()
        self.assertEqual([row["name"] for row in rows], SHIPPED_NAMES)
        copied = json.loads(self.user.read_text())
        self.assertEqual([row["name"] for row in copied], SHIPPED_NAMES)
        self.user.unlink()
        self.prepare()
        recopied = json.loads(self.user.read_text())
        self.assertEqual([row["name"] for row in recopied], SHIPPED_NAMES)

    def test_shipped_expand_classes_and_hosts(self):
        rows = self.by_name(self.expand_apply())
        self.assertEqual(set(rows), set(SHIPPED_NAMES))
        for name, (klass, hosts) in WINDOWED.items():
            self.assertEqual(rows[name]["class"], klass, name)
            self.assertEqual(rows[name]["hosts"], hosts, name)
        for name, hosts in HOSTS_ONLY.items():
            self.assertIsNone(rows[name]["class"], name)
            self.assertEqual(rows[name]["hosts"], hosts, name)

    def test_custom_hosts_only_and_class_only(self):
        self.user.parent.mkdir(parents=True)
        self.user.write_text(
            json.dumps(
                [
                    {"name": "ExampleSite", "hosts": ["example.com"]},
                    {"name": "ExampleApp", "class": "app.example"},
                ]
            )
        )
        rows = self.by_name(self.expand_apply())
        self.assertEqual(rows["ExampleSite"]["hosts"], ["example.com"])
        self.assertIsNone(rows["ExampleSite"]["class"])
        self.assertEqual(rows["ExampleApp"]["class"], "app.example")
        self.assertEqual(rows["ExampleApp"]["hosts"], [])

    def test_corrupt_list_notifies_keeps_last_good(self):
        good = self.expand_apply()
        self.assertTrue(good)
        before = self.user.read_text()
        last = json.loads(self.last_good.read_text())
        self.user.write_text("{not-json")
        printed = json.loads(self.print_expand())
        self.assertEqual(printed, [])
        self.assertTrue(self.notes)
        self.assertEqual(self.user.read_text(), "{not-json")
        self.assertNotEqual(before, "{not-json")
        self.assertEqual(self.expand_apply(), last)

    def test_unreadable_list_notifies_keeps_last_good(self):
        good = self.expand_apply()
        last = json.loads(self.last_good.read_text())
        self.user.unlink()
        self.user.mkdir()
        printed = json.loads(self.print_expand())
        self.assertEqual(printed, [])
        self.assertTrue(self.notes)
        self.assertTrue(self.user.is_dir())
        self.assertEqual(self.expand_apply(), last)
        self.assertEqual(good, last)

    def test_missing_defaults_notifies_and_starts_empty(self):
        missing = Path(self.tmp.name) / "no-defaults.json"
        rows = self.prepare(defaults=missing)
        self.assertEqual(rows, [])
        self.assertFalse(self.user.exists())
        self.assertTrue(self.notes)
        printed = json.loads(self.print_expand(defaults=missing))
        self.assertEqual(printed, [])

    def test_rejected_entry_stays_out(self):
        self.user.parent.mkdir(parents=True)
        self.user.write_text(
            json.dumps(
                [
                    {"name": "Telegram"},
                    {"name": ""},
                    {"name": "Unknown"},
                    {"name": "Telegram"},
                    {"name": "Kept", "hosts": ["kept.example"]},
                ]
            )
        )
        rows = self.expand_apply()
        names = [row["name"] for row in rows]
        self.assertEqual(names, ["Telegram", "Kept"])
        self.assertEqual(rows[1]["hosts"], ["kept.example"])

    def test_colliding_sanitized_names_rejected(self):
        self.user.parent.mkdir(parents=True)
        self.user.write_text(
            json.dumps(
                [
                    {"name": "Telegram"},
                    {"name": "!!!", "class": "punct.a"},
                    {"name": "???", "class": "punct.b"},
                ]
            )
        )
        rows = self.expand_apply()
        self.assertEqual([row["name"] for row in rows], ["Telegram"])
        self.assertEqual(
            self.mod.window_rule_name("!!!"),
            self.mod.window_rule_name("???"),
        )

    def test_print_expand_does_not_replace_last_good(self):
        applied = self.expand_apply()
        last = json.loads(self.last_good.read_text())
        self.assertEqual(applied, last)
        self.user.write_text(json.dumps([{"name": "CustomApp", "class": "app.custom"}]))
        printed = json.loads(self.print_expand())
        self.assertEqual(printed[0]["name"], "CustomApp")
        self.assertEqual(json.loads(self.last_good.read_text()), last)

    def test_print_expand_runs_without_hyprland(self):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["XDG_STATE_HOME"] = str(Path(self.tmp.name) / "state")
        env["PATH"] = "/nonexistent"
        result = subprocess.run(
            [sys.executable, str(ROOT / "distractions"), "print-expand"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual([row["name"] for row in rows], SHIPPED_NAMES)
        self.assertNotIn("hyprctl", result.stderr)



class MessagingDefaultsTests(unittest.TestCase):
    """Messaging apps ship corralled but reachable; time-sinks stay blocked."""

    def setUp(self) -> None:
        self.mod = load_mod()

    def test_messaging_apps_are_windowed_but_not_host_blocked(self) -> None:
        for name in MESSAGING:
            row = self.mod.EXPAND_MAP[name]
            self.assertTrue(row.get("class"), f"{name} lost its window rule")
            self.assertEqual(row.get("hosts"), [], f"{name} would be IP-blocked")

    def test_time_sinks_keep_their_host_block(self) -> None:
        # X in particular: it is a time-sink, not a messaging app, and its block
        # is what the keep-reachable carve-out exists to protect Grok from.
        for name in ("X", "Reddit", "YouTube", "Netflix", "Facebook"):
            hosts = self.mod.EXPAND_MAP[name].get("hosts") or []
            self.assertTrue(hosts, f"{name} unexpectedly lost its host block")
        self.assertIn("x.com", self.mod.EXPAND_MAP["X"]["hosts"])

    def test_no_messaging_host_reaches_the_off_space_block(self) -> None:
        rows = [{"name": name} for name in SHIPPED_NAMES]
        hosts = self.mod.listed_hosts(
            [dict(r, **self.mod.EXPAND_MAP[r["name"]]) for r in rows]
        )
        for needle in ("whatsapp", "telegram", "discord", "signal.org", "messages.google"):
            self.assertFalse(
                [h for h in hosts if needle in h],
                f"{needle} still reaches the IP block",
            )
        self.assertIn("x.com", hosts)

    def test_a_user_can_restore_the_block_from_config_alone(self) -> None:
        # The old behaviour must stay reachable without a code change.
        row = {
            "name": "WhatsApp",
            "class": r"^chrome-web\.whatsapp\.com__.*$",
            "hosts": ["web.whatsapp.com"],
        }
        self.assertEqual(self.mod.listed_hosts([row]), ["web.whatsapp.com"])


if __name__ == "__main__":
    unittest.main()
