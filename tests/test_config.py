#!/usr/bin/env python3
"""Config schema, flock, migration, and list CLI tests."""

from __future__ import annotations

import inspect
import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds.config import DEFAULTS, is_schema_key, _lock_timeout, update as config_update

DEFAULT_LIST = [
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

GOOD_VALUES = [
    ("list", json.dumps(["Telegram", "x.com"]), ["Telegram", "x.com"]),
    ("keep_reachable", json.dumps(["example.com"]), ["example.com"]),
    ("nudges.app_banner", "false", False),
    ("nudges.block_page", "false", False),
    ("site_block.pass_through", "false", False),
    ("hold_notifications", "locked", "locked"),
    ("hold_notifications", "never", "never"),
    ("hold_notifications", "off-space", "off-space"),
    ("mute_sounds", "false", False),
    ("lock.default_minutes", "40", 40),
    ("lock.ask_purpose", "false", False),
    ("lock.reason_min_chars", "0", 0),
    ("summary.command", "off", "off"),
    ("summary.command", "auto", "auto"),
    ("summary.command", '["agent","--flag"]', ["agent", "--flag"]),
    ("summary.timeout_seconds", "90", 90),
    ("hooks.lock", '[["/bin/true"]]', [["/bin/true"]]),
    ("hooks.unlock", "[]", []),
    ("hooks.enter", '[["echo","hi"]]', [["echo", "hi"]]),
    ("hooks.leave", "[]", []),
    ("log", "~/custom.log", "~/custom.log"),
]

BAD_VALUES = [
    ("hold_notifications", "sometimes"),
    ("mute_sounds", "yes"),
    ("summary.command", "later"),
    ("summary.command", '[""]'),
    ("summary.timeout_seconds", "-1"),
    ("summary.timeout_seconds", "x"),
    ("lock.default_minutes", "-5"),
    ("lock.reason_min_chars", "true"),
    ("nudges.app_banner", "1"),
    ("site_block.pass_through", "yes"),
    ("list", '["not a host"]'),
    ("list", '[{"name": "Y"}]'),
    ("keep_reachable", '["nodots"]'),
    ("hooks.enter", '["notlist"]'),
    ("log", ""),
]


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)

    def test_defaults_written_on_first_run(self):
        r = self.box.run("config", "get", "lock.default_minutes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), 25)
        self.assertTrue(self.box.config_file.is_file())
        r = self.box.run("config", "get", "list")
        self.assertEqual(json.loads(r.stdout), DEFAULT_LIST)

    def test_invalid_values_leave_file_unchanged(self):
        self.assertEqual(self.box.run("config", "get", "mute_sounds").returncode, 0)
        before = self.box.config_file.read_bytes()
        for key, value in BAD_VALUES:
            with self.subTest(key=key, value=value):
                r = self.box.run("config", "set", key, value)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn(key.split(".")[0], r.stderr)
                self.assertEqual(self.box.config_file.read_bytes(), before)

    def test_every_schema_key_roundtrips(self):
        self.assertEqual(self.box.run("config", "get", "mute_sounds").returncode, 0)
        for key, raw, expected in GOOD_VALUES:
            with self.subTest(key=key, value=raw):
                r = self.box.run("config", "set", key, raw)
                self.assertEqual(r.returncode, 0, r.stderr)
                got = json.loads(self.box.run("config", "get", key).stdout)
                self.assertEqual(got, expected)
        slack = [{"name": "Slack", "class": "^Slack$", "hosts": ["slack.com", "app.slack.com"]}]
        r = self.box.run("config", "set", "list", json.dumps(slack))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.box.run("config", "get", "list").stdout), slack)

    def test_start_locked_absent_from_schema(self):
        self.assertNotIn("start_locked", DEFAULTS["lock"])
        self.assertFalse(is_schema_key("lock.start_locked"))
        self.assertTrue(is_schema_key("hold_notifications"))
        self.assertTrue(is_schema_key("mute_sounds"))
        self.assertTrue(is_schema_key("summary.command"))
        self.assertTrue(DEFAULTS["site_block"]["pass_through"])
        self.assertTrue(is_schema_key("site_block.pass_through"))

    def test_config_path_honors_xdg(self):
        r = self.box.run("config", "path")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(self.box.config_file))
        self.assertTrue(str(self.box.config_file).startswith(str(self.box.config)))

    def test_update_timeout_default_is_five_seconds(self):
        self.assertEqual(_lock_timeout(), 5.0)
        self.assertEqual(inspect.signature(config_update).parameters["timeout"].default, None)

    def test_start_locked_unknown_key_round_trips(self):
        self.box.config_file.write_text(
            json.dumps(
                {"lock": {"start_locked": True}, "extra_top": "keep-me"},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        r = self.box.run("config", "set", "lock.ask_purpose", "false")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.box.run("config", "get", "lock.start_locked").stdout), True)
        self.assertEqual(json.loads(self.box.run("config", "get", "extra_top").stdout), "keep-me")
        self.assertEqual(json.loads(self.box.run("config", "get", "lock.ask_purpose").stdout), False)
        before = self.box.config_file.read_bytes()
        r = self.box.run("config", "set", "lock.start_locked", "true")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(self.box.config_file.read_bytes(), before)

    def test_saved_entry_confirm_loads_and_survives_save(self):
        self.assertNotIn("entry_confirm", DEFAULTS["nudges"])
        self.assertFalse(is_schema_key("nudges.entry_confirm"))
        for value in (True, False):
            with self.subTest(entry_confirm=value):
                self.box.config_file.write_text(
                    json.dumps({"nudges": {"app_banner": True, "block_page": True, "entry_confirm": value}}) + "\n",
                    encoding="utf-8",
                )
                r = self.box.run("config", "get", "nudges.app_banner")
                self.assertEqual(r.returncode, 0, r.stderr)
                r = self.box.run("config", "set", "nudges.block_page", "false")
                self.assertEqual(r.returncode, 0, r.stderr)
                saved = json.loads(self.box.config_file.read_text(encoding="utf-8"))
                self.assertIs(saved["nudges"]["entry_confirm"], value)
                self.assertIs(saved["nudges"]["block_page"], False)

    def test_unknown_top_level_key_survives(self):
        self.box.config_file.write_text(
            json.dumps({"mystery": 7}) + "\n",
            encoding="utf-8",
        )
        r = self.box.run("config", "set", "mute_sounds", "false")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.box.run("config", "get", "mystery").stdout), 7)

    def test_concurrent_sets_both_land(self):
        self.assertEqual(self.box.run("config", "get", "mute_sounds").returncode, 0)
        p1 = self.box.popen("config", "set", "mute_sounds", "false")
        p2 = self.box.popen("config", "set", "hold_notifications", "locked")
        out1, err1 = p1.communicate(timeout=30)
        out2, err2 = p2.communicate(timeout=30)
        self.assertEqual(p1.returncode, 0, err1)
        self.assertEqual(p2.returncode, 0, err2)
        self.assertEqual(json.loads(self.box.run("config", "get", "mute_sounds").stdout), False)
        self.assertEqual(json.loads(self.box.run("config", "get", "hold_notifications").stdout), "locked")

    def test_held_flock_refuses_with_config_busy(self):
        self.assertEqual(self.box.run("config", "get", "mute_sounds").returncode, 0)
        before = self.box.config_file.read_bytes()
        holder = self.box.hold_config_lock()
        try:
            t0 = time.monotonic()
            r = self.box.run(
                "config", "set", "mute_sounds", "false",
                extra_env={"DS_CONFIG_LOCK_TIMEOUT": "0.2"},
            )
            elapsed = time.monotonic() - t0
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("config busy", r.stderr)
            self.assertGreaterEqual(elapsed, 0.15)
            self.assertLess(elapsed, 2)
            self.assertEqual(self.box.config_file.read_bytes(), before)
        finally:
            holder.kill()
            holder.wait(timeout=5)

    def test_reads_take_no_lock(self):
        self.assertEqual(self.box.run("config", "get", "mute_sounds").returncode, 0)
        holder = self.box.hold_config_lock()
        try:
            r = self.box.run("config", "get", "mute_sounds")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout), True)
        finally:
            holder.kill()
            holder.wait(timeout=5)

    def test_atomic_write_leaves_no_tmp(self):
        r = self.box.run("config", "set", "mute_sounds", "false")
        self.assertEqual(r.returncode, 0, r.stderr)
        leftovers = [
            p for p in (self.box.config / "omarchy").iterdir()
            if p.name.endswith(".tmp") or ".tmp" in p.name
        ]
        self.assertEqual(leftovers, [])
        self.assertTrue(self.box.config_file.is_file())

    def test_migration_from_old_files(self):
        self.box.old_app_list.write_text(
            json.dumps([{"name": "Telegram"}, {"name": "Reddit"}, {"name": ""}]),
            encoding="utf-8",
        )
        self.box.old_focus.write_text(
            json.dumps({"destinations": ["Reddit", "x.com"], "log": "~/custom.log"}),
            encoding="utf-8",
        )
        app_bytes = self.box.old_app_list.read_bytes()
        focus_bytes = self.box.old_focus.read_bytes()
        r = self.box.run("config", "get", "list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), ["Telegram", "Reddit", "x.com"])
        self.assertEqual(json.loads(self.box.run("config", "get", "log").stdout), "~/custom.log")
        self.assertEqual(self.box.old_app_list.read_bytes(), app_bytes)
        self.assertEqual(self.box.old_focus.read_bytes(), focus_bytes)

    def test_migration_carries_valid_forms_and_converts_objects(self):
        slack = {"name": "Slack", "class": "^Slack$", "hosts": ["slack.com", "app.slack.com"]}
        converted = {
            "name": "LegacyWin",
            "window_class": "^LegacyWin$",
            "hosts": ["legacy.example", "not a host"],
            "senders": 1,
        }
        self.box.old_app_list.write_text(
            json.dumps(
                [
                    {"name": "Telegram"},
                    slack,
                    "class=^Foo$",
                    "news.example",
                    {"name": "NotInCatalog"},
                    {"name": "CustomSite", "hosts": ["custom.example"]},
                    converted,
                    {"name": "BadClassOnly", "class": "["},
                ]
            ),
            encoding="utf-8",
        )
        self.box.old_focus.write_text(
            json.dumps({"destinations": ["Bluesky"], "log": "~/migrated.log"}),
            encoding="utf-8",
        )
        r = self.box.run("config", "get", "list")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assertEqual(got[0], "Telegram")
        self.assertEqual(got[1], slack)
        self.assertEqual(got[2], "class=^Foo$")
        self.assertEqual(got[3], "news.example")
        self.assertEqual(got[4], {"name": "CustomSite", "hosts": ["custom.example"]})
        self.assertEqual(
            got[5],
            {"name": "LegacyWin", "class": "^LegacyWin$", "hosts": ["legacy.example"]},
        )
        self.assertEqual(got[6], "Bluesky")
        self.assertNotIn("NotInCatalog", [e if isinstance(e, str) else e.get("name") for e in got])
        self.assertEqual(json.loads(self.box.run("config", "get", "log").stdout), "~/migrated.log")

    def test_present_empty_legacy_union_seeds_empty_list(self):
        self.box.old_app_list.write_text("[]", encoding="utf-8")
        self.box.old_focus.write_text(json.dumps({"destinations": []}), encoding="utf-8")
        r = self.box.run("config", "get", "list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [])
        self.assertTrue(self.box.config_file.is_file())

    def test_unreadable_old_files_use_defaults(self):
        self.box.old_app_list.write_text("{not json", encoding="utf-8")
        self.box.old_focus.write_text("nope", encoding="utf-8")
        r = self.box.run("config", "get", "list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), DEFAULT_LIST)

    def test_invalid_first_set_does_not_create_file(self):
        self.assertFalse(self.box.config_file.exists())
        r = self.box.run("config", "set", "hold_notifications", "sometimes")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(self.box.config_file.exists())

    def test_invalid_new_file_get_exits_1_unchanged(self):
        self.box.config_file.write_text("{not json", encoding="utf-8")
        before = self.box.config_file.read_bytes()
        r = self.box.run("config", "get", "list")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.box.config_file.read_bytes(), before)

    def test_list_add_remove_expand(self):
        self.assertEqual(self.box.run("config", "get", "list").returncode, 0)
        r = self.box.run("list", "add", "x.com")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.box.run("list", "add", "Telegram")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.box.run("list", "add", "Telegram")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.box.run("list", "add", "class=^Foo$")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.box.run("list", "add", "nonsense")
        self.assertEqual(r.returncode, 1)
        r = self.box.run("list", "remove", "Reddit")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.box.run("list", "remove", "Missing")
        self.assertEqual(r.returncode, 1)
        listed = self.box.run("list").stdout.splitlines()
        self.assertIn("x.com", listed)
        self.assertIn("Telegram", listed)
        self.assertIn("class=^Foo$", listed)
        self.assertNotIn("Reddit", listed)
        self.assertEqual(listed.count("Telegram"), 1)
        expanded = json.loads(self.box.run("list", "expand").stdout)
        names = [e["name"] for e in expanded]
        self.assertIn("x.com", names)
        self.assertIn("class=^Foo$", names)
        by_name = {e["name"]: e for e in expanded}
        self.assertEqual(by_name["x.com"]["classes"], ["^chrome-x\\.com__.*$"])
        self.assertEqual(by_name["x.com"]["hosts"], ["x.com", "www.x.com"])
        self.assertEqual(by_name["class=^Foo$"]["classes"], ["^Foo$"])
        self.assertEqual(by_name["class=^Foo$"]["hosts"], [])
        self.assertEqual(
            by_name["Telegram"]["classes"],
            ["org.telegram.desktop", "^chrome-web\\.telegram\\.org__.*$"],
        )
        self.assertIn("hosts", by_name["Telegram"])
        self.assertIn("senders", by_name["Telegram"])
        self.assertIn("audio", by_name["Telegram"])

    def test_list_add_json_object_entry(self):
        self.assertEqual(self.box.run("config", "get", "list").returncode, 0)
        obj = {"name": "Slack", "class": "^Slack$", "hosts": ["slack.com", "app.slack.com"]}
        r = self.box.run("list", "add", json.dumps(obj))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.box.run("list", "add", json.dumps({"name": "Slack", "class": "^Other$"}))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.box.run("list", "add", '  {"name": "Work", "hosts": ["work.example"]}')
        self.assertEqual(r.returncode, 0, r.stderr)
        listed = self.box.run("list").stdout.splitlines()
        self.assertEqual(listed.count("Slack"), 1)
        self.assertIn("Work", listed)
        stored = json.loads(self.box.config_file.read_text(encoding="utf-8"))["list"]
        self.assertIn(obj, stored)
        self.assertIn({"name": "Work", "hosts": ["work.example"]}, stored)
        by_name = {e["name"]: e for e in json.loads(self.box.run("list", "expand").stdout)}
        self.assertEqual(by_name["Slack"]["classes"], ["^Slack$", "^chrome-slack\\.com__.*$"])
        self.assertEqual(by_name["Slack"]["hosts"], ["slack.com", "app.slack.com"])
        before = self.box.config_file.read_bytes()
        for bad in (
            '{"name": "Bad"}',
            '{"name": "", "class": "^X$"}',
            '{"name": "Bad", "class": "(unclosed"}',
            '{"name": "Bad", "hosts": ["nodot"]}',
            '{not json',
            '{"name": "Bad", "class": "^X$"} trailing',
        ):
            with self.subTest(bad=bad):
                r = self.box.run("list", "add", bad)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn("list", r.stderr)
                self.assertEqual(self.box.config_file.read_bytes(), before)

    def test_invalid_class_regex_refused_file_unchanged(self):
        self.assertEqual(self.box.run("config", "get", "mute_sounds").returncode, 0)
        before = self.box.config_file.read_bytes()
        for value in (
            json.dumps(["class=["]),
            json.dumps([{"name": "Bad", "class": "(unclosed"}]),
        ):
            with self.subTest(value=value):
                r = self.box.run("config", "set", "list", value)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn("list", r.stderr)
                self.assertEqual(self.box.config_file.read_bytes(), before)
        r = self.box.run("list", "add", "class=(unclosed")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(self.box.config_file.read_bytes(), before)

    def test_senders_and_audio_on_custom_list_objects(self):
        self.assertEqual(self.box.run("config", "get", "mute_sounds").returncode, 0)
        good = [
            {
                "name": "Slack",
                "class": "^Slack$",
                "hosts": ["slack.com"],
                "senders": ["Slack"],
                "audio": {"name": ["Slack"], "binary": ["slack"]},
            }
        ]
        r = self.box.run("config", "set", "list", json.dumps(good))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.box.run("config", "get", "list").stdout), good)
        expanded = json.loads(self.box.run("list", "expand").stdout)
        self.assertEqual(expanded[0]["senders"], ["Slack"])
        self.assertEqual(expanded[0]["audio"], {"name": ["Slack"], "binary": ["slack"]})
        before = self.box.config_file.read_bytes()
        for value in (
            json.dumps([{"name": "Slack", "class": "^Slack$", "senders": "Slack"}]),
            json.dumps([{"name": "Slack", "class": "^Slack$", "audio": ["Slack"]}]),
            json.dumps([{"name": "Slack", "class": "^Slack$", "audio": {"name": "Slack"}}]),
            json.dumps([{"name": "Slack", "class": "^Slack$", "audio": {"other": []}}]),
        ):
            with self.subTest(value=value):
                r = self.box.run("config", "set", "list", value)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertEqual(self.box.config_file.read_bytes(), before)

    def test_config_edit_splits_editor_or_falls_back(self):
        self.assertEqual(self.box.run("config", "get", "mute_sounds").returncode, 0)
        rec = self.box.runtime / "editor-argv.json"
        recorder = (
            "import json, sys\n"
            "from pathlib import Path\n"
            f"Path({str(rec)!r}).write_text(json.dumps(sys.argv), encoding='utf-8')\n"
        )
        self.box.fake_bin("my-editor", recorder)
        r = self.box.run("config", "edit", extra_env={"EDITOR": "my-editor --wait"})
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = json.loads(rec.read_text(encoding="utf-8"))
        self.assertTrue(argv[0].endswith("my-editor"))
        self.assertEqual(argv[1:], ["--wait", str(self.box.config_file)])
        rec.unlink()
        self.box.fake_bin("omarchy-launch-editor", recorder)
        r = self.box.run("config", "edit", extra_env={"EDITOR": None})
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = json.loads(rec.read_text(encoding="utf-8"))
        self.assertTrue(argv[0].endswith("omarchy-launch-editor"))
        self.assertEqual(argv[1:], [str(self.box.config_file)])


if __name__ == "__main__":
    unittest.main()
