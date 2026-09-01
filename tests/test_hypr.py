#!/usr/bin/env python3
"""Window rules, silent moves, intercept banner, and workspace cycle."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import hypr, state
from ds.catalog import expand_entry, pwa_class

HYPRCTL = r"""
import json, os, sys
from pathlib import Path

log = Path(os.environ["DS_HYPR_LOG"])
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")

joined = " ".join(sys.argv[1:])
fail = os.environ.get("DS_HYPR_FAIL", "")
if fail and fail in joined:
    sys.stderr.write("hyprctl refused\n")
    sys.exit(1)

state_path = Path(os.environ.get("DS_HYPR_STATE", ""))
data = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

args = sys.argv[1:]
if args[:1] == ["-j"] and len(args) >= 2:
    key = args[1]
    if key == "activeworkspace":
        print(json.dumps(data.get("activeworkspace") or {"id": 1, "name": "1"}))
        sys.exit(0)
    if key == "clients":
        print(json.dumps(data.get("clients") or []))
        sys.exit(0)
    if key == "workspaces":
        print(json.dumps(data.get("workspaces") or []))
        sys.exit(0)
    sys.exit(1)
if args[:1] in (["keyword"], ["dispatch"]):
    sys.exit(0)
sys.exit(1)
"""

NOTIFY = r"""
import json, os, sys
from pathlib import Path

p = Path(os.environ["DS_NOTIFY_LOG"])
p.parent.mkdir(parents=True, exist_ok=True)
with p.open("a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
if os.environ.get("DS_NOTIFY_FAIL"):
    sys.stderr.write("notify refused\n")
    sys.exit(1)
"""

TELEGRAM = expand_entry("Telegram")
PWA_CLASS = pwa_class("web.telegram.org")
NATIVE = "org.telegram.desktop"


def _entries(*names):
    return [expand_entry(n) for n in names]


class HyprTests(unittest.TestCase):
    def setUp(self) -> None:
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.hypr_log = self.box.runtime / "hypr.log"
        self.notify_log = self.box.runtime / "notify.log"
        self.hypr_state = self.box.runtime / "hypr-state.json"
        os.environ["DS_HYPR_LOG"] = str(self.hypr_log)
        os.environ["DS_NOTIFY_LOG"] = str(self.notify_log)
        os.environ["DS_HYPR_STATE"] = str(self.hypr_state)
        os.environ.pop("DS_HYPR_FAIL", None)
        os.environ.pop("DS_NOTIFY_FAIL", None)
        self.box.fake_bin("hyprctl", HYPRCTL)
        self.box.fake_bin("omarchy-notification-send", NOTIFY)
        hypr._reset_for_tests()

    def _state(self, **kwargs):
        payload = {
            "activeworkspace": {"id": 1, "name": "1"},
            "clients": [],
            "workspaces": [
                {"id": 1, "name": "1", "windows": 1},
                {"id": 2, "name": "2", "windows": 1},
                {"id": 99, "name": "distraction", "windows": 1},
            ],
        }
        payload.update(kwargs)
        self.hypr_state.write_text(json.dumps(payload), encoding="utf-8")

    def _hypr_cmds(self):
        if not self.hypr_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.hypr_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _joined(self):
        return [" ".join(cmd) for cmd in self._hypr_cmds()]

    def _notifies(self):
        if not self.notify_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.notify_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _client(self, address, klass, workspace="1"):
        return {
            "address": address,
            "class": klass,
            "workspace": {"id": 1 if workspace != hypr.SPACE else 99, "name": workspace},
        }

    def test_two_classes_yield_two_named_rules_and_rules_json(self):
        hypr.apply_rules([TELEGRAM])
        expected, _ = hypr._rule_names([TELEGRAM])
        joined = "\n".join(self._joined())
        self.assertEqual(len(expected), 2)
        self.assertIn(f"windowrule[{expected[0]}]", joined)
        self.assertIn(f"windowrule[{expected[1]}]", joined)
        self.assertIn(f"match:class {NATIVE}", joined)
        self.assertIn(f"match:class {PWA_CLASS}", joined)
        self.assertIn(f"workspace name:{hypr.SPACE} silent", joined)
        self.assertIn("enable true", joined)
        names = state.read_json(state.state_path("rules.json"), [])
        self.assertEqual(set(names), set(expected))

    def test_removed_entries_have_rules_disabled(self):
        hypr.apply_rules(_entries("Telegram", "Discord"))
        before = set(state.read_json(state.state_path("rules.json"), []))
        discord_names, _ = hypr._rule_names(_entries("Discord"))
        telegram_names, _ = hypr._rule_names(_entries("Telegram"))
        self.assertTrue(set(discord_names) <= before)
        self.hypr_log.write_text("", encoding="utf-8")
        hypr.apply_rules(_entries("Telegram"))
        joined = "\n".join(self._joined())
        self.assertIn(f"windowrule[{discord_names[0]}]:enable false", joined)
        self.assertNotIn(f"windowrule[{telegram_names[0]}]:enable false", joined)
        after = set(state.read_json(state.state_path("rules.json"), []))
        self.assertEqual(after, set(telegram_names))
        self.assertFalse(set(discord_names) & after)

    def test_open_and_move_listed_native_and_pwa_unlisted_untouched(self):
        hypr.apply_rules([TELEGRAM])
        self._state(
            clients=[
                self._client("0xaaa", NATIVE, "1"),
                self._client("0xbbb", "chrome-web.telegram.org__https___web.telegram.org", "1"),
                self._client("0xccc", "firefox", "1"),
            ]
        )
        self.hypr_log.write_text("", encoding="utf-8")
        hypr.handle_event("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
        hypr.handle_event(
            "openwindow>>0xbbb,1,chrome-web.telegram.org__https___web.telegram.org,Telegram"
        )
        hypr.handle_event("openwindow>>0xccc,1,firefox,Mozilla Firefox")
        hypr.handle_event("movewindow>>0xaaa,2")
        hypr.handle_event("movewindow>>0xccc,2")
        joined = "\n".join(self._joined())
        self.assertIn("movetoworkspacesilent", joined)
        self.assertIn("address:0xaaa", joined)
        self.assertIn("address:0xbbb", joined)
        self.assertNotIn("address:0xccc", joined)

    def test_banner_debounce_30s_and_never_on_space(self):
        hypr.apply_rules([TELEGRAM])
        self._state(
            activeworkspace={"id": 1, "name": "1"},
            clients=[self._client("0xaaa", NATIVE, hypr.SPACE)],
        )
        clock = mock.Mock(side_effect=[1000.0, 1000.0, 1029.0, 1031.0])
        with mock.patch("ds.hypr.time.monotonic", clock):
            hypr.handle_event("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
            hypr.handle_event("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
            self.assertEqual(len(self._notifies()), 1)
            hypr.handle_event("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
            self.assertEqual(len(self._notifies()), 1)
            hypr.handle_event("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
        self.assertEqual(len(self._notifies()), 2)
        args = self._notifies()[0]
        self.assertTrue(any("Telegram lives in the distraction space" in a for a in args))
        self.assertTrue(any("Super+D opens it." in a for a in args))
        self.assertIn("--exec", args)
        exec_bits = " ".join(args[args.index("--exec") + 1 :])
        self.assertIn("distractions", exec_bits)
        self.assertIn("enter", exec_bits)

        hypr._reset_for_tests()
        hypr.apply_rules([TELEGRAM])
        self.notify_log.write_text("", encoding="utf-8")
        self._state(
            activeworkspace={"id": 99, "name": hypr.SPACE},
            clients=[self._client("0xaaa", NATIVE, hypr.SPACE)],
        )
        hypr.handle_event("openwindow>>0xaaa,99,org.telegram.desktop,Telegram")
        self.assertEqual(self._notifies(), [])

    def test_banner_off_when_nudge_disabled(self):
        hypr.apply_rules(
            {
                "list": [TELEGRAM],
                "nudges": {"app_banner": False, "block_page": True, "entry_confirm": True},
            }
        )
        self._state(clients=[self._client("0xaaa", NATIVE, "1")])
        hypr.handle_event("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
        self.assertEqual(self._notifies(), [])
        self.assertTrue(any("movetoworkspacesilent" in j for j in self._joined()))

    def test_hyprctl_failure_logged_and_skipped(self):
        hypr.apply_rules([TELEGRAM])
        self._state(clients=[self._client("0xaaa", NATIVE, "1")])
        os.environ["DS_HYPR_FAIL"] = "movetoworkspacesilent"
        hypr.handle_event("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("hyprctl", log)
        self.assertTrue(any("lives in the distraction space" in " ".join(a) for a in self._notifies()))

        os.environ["DS_HYPR_FAIL"] = "windowrule"
        self.hypr_log.write_text("", encoding="utf-8")
        hypr.apply_rules(_entries("Discord"))
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("windowrule", log)
        names = set(state.read_json(state.state_path("rules.json"), []))
        discord_names, _ = hypr._rule_names(_entries("Discord"))
        telegram_names, _ = hypr._rule_names([TELEGRAM])
        self.assertTrue(set(discord_names) <= names)
        self.assertTrue(set(telegram_names) <= names)

    def test_notify_failure_ignored(self):
        hypr.apply_rules([TELEGRAM])
        self._state(clients=[self._client("0xaaa", NATIVE, "1")])
        os.environ["DS_NOTIFY_FAIL"] = "1"
        hypr.handle_event("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
        self.assertTrue(any("movetoworkspacesilent" in j and "0xaaa" in j for j in self._joined()))

    def test_cycle_skips_space(self):
        self._state(
            activeworkspace={"id": 1, "name": "1"},
            workspaces=[
                {"id": 1, "name": "1", "windows": 1},
                {"id": 2, "name": "2", "windows": 1},
                {"id": 99, "name": "distraction", "windows": 3},
            ],
        )
        hypr.cycle("next")
        joined = "\n".join(self._joined())
        self.assertIn("dispatch workspace", joined)
        self.assertIn("name:2", joined)
        self.assertNotIn("name:distraction", joined.split("dispatch workspace", 1)[-1])

        self.hypr_log.write_text("", encoding="utf-8")
        self._state(
            activeworkspace={"id": 99, "name": "distraction"},
            workspaces=[
                {"id": 1, "name": "1", "windows": 1},
                {"id": 2, "name": "2", "windows": 1},
                {"id": 99, "name": "distraction", "windows": 3},
            ],
        )
        hypr.cycle("next")
        dest = "\n".join(self._joined())
        self.assertIn("name:1", dest)
        self.assertNotIn("name:distraction", dest.split("dispatch workspace", 1)[-1])

        self.hypr_log.write_text("", encoding="utf-8")
        self._state(
            activeworkspace={"id": 2, "name": "2"},
            workspaces=[
                {"id": 1, "name": "1", "windows": 1},
                {"id": 2, "name": "2", "windows": 1},
                {"id": 99, "name": "distraction", "windows": 3},
            ],
        )
        hypr.cycle("prev")
        dest = "\n".join(self._joined())
        self.assertIn("name:1", dest)
        self.assertNotIn("name:distraction", dest.split("dispatch workspace", 1)[-1])

    def test_failed_disable_kept_in_rules_json_and_retried(self):
        hypr.apply_rules(_entries("Telegram", "Discord"))
        discord_names, _ = hypr._rule_names(_entries("Discord"))
        telegram_names, _ = hypr._rule_names(_entries("Telegram"))
        self.hypr_log.write_text("", encoding="utf-8")
        os.environ["DS_HYPR_FAIL"] = "enable false"
        hypr.apply_rules(_entries("Telegram"))
        recorded = set(state.read_json(state.state_path("rules.json"), []))
        self.assertTrue(set(discord_names) <= recorded)
        self.assertTrue(set(telegram_names) <= recorded)
        joined = "\n".join(self._joined())
        self.assertIn(f"windowrule[{discord_names[0]}]:enable false", joined)
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("enable false", log)

        os.environ.pop("DS_HYPR_FAIL", None)
        self.hypr_log.write_text("", encoding="utf-8")
        hypr.apply_rules(_entries("Telegram"))
        retried = "\n".join(self._joined())
        self.assertIn(f"windowrule[{discord_names[0]}]:enable false", retried)
        after = set(state.read_json(state.state_path("rules.json"), []))
        self.assertEqual(after, set(telegram_names))
        self.assertFalse(set(discord_names) & after)

    def test_slug_collision_gets_distinct_rule_names(self):
        entries = [
            {"name": "Foo Bar", "classes": ["FooBarClass"]},
            {"name": "Foo-Bar", "classes": ["FooDashClass"]},
        ]
        self.assertEqual(hypr._slug("Foo Bar"), hypr._slug("Foo-Bar"))
        hypr.apply_rules(entries)
        names = state.read_json(state.state_path("rules.json"), [])
        self.assertEqual(len(names), 2)
        self.assertEqual(len(set(names)), 2)
        joined = "\n".join(self._joined())
        self.assertIn("match:class FooBarClass", joined)
        self.assertIn("match:class FooDashClass", joined)
        self.assertIn(f"windowrule[{names[0]}]", joined)
        self.assertIn(f"windowrule[{names[1]}]", joined)

    def test_unknown_on_space_logs_and_skips_banner(self):
        hypr.apply_rules([TELEGRAM])
        self._state(clients=[self._client("0xaaa", NATIVE, "1")])
        self.hypr_log.write_text("", encoding="utf-8")
        os.environ["DS_HYPR_FAIL"] = "activeworkspace"
        hypr.handle_event("openwindow>>0xaaa,1,org.telegram.desktop,Telegram")
        self.assertTrue(any("movetoworkspacesilent" in j and "0xaaa" in j for j in self._joined()))
        self.assertEqual(self._notifies(), [])
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("hyprctl", log)
        self.assertIn("activeworkspace", log)
        self.assertIn("skipping banner", log)

    def test_cli_next_prev_dispatch_workspace(self):
        occupied = [
            {"id": 1, "name": "1", "windows": 1},
            {"id": 2, "name": "2", "windows": 1},
            {"id": 99, "name": "distraction", "windows": 3},
        ]
        self._state(activeworkspace={"id": 1, "name": "1"}, workspaces=occupied)
        r = self.box.run("next")
        self.assertEqual(r.returncode, 0, r.stderr)
        dest = "\n".join(self._joined())
        self.assertIn("dispatch workspace", dest)
        self.assertIn("name:2", dest)
        self.assertNotIn("name:distraction", dest.split("dispatch workspace", 1)[-1])

        self.hypr_log.write_text("", encoding="utf-8")
        self._state(activeworkspace={"id": 2, "name": "2"}, workspaces=occupied)
        r = self.box.run("prev")
        self.assertEqual(r.returncode, 0, r.stderr)
        dest = "\n".join(self._joined())
        self.assertIn("dispatch workspace", dest)
        self.assertIn("name:1", dest)
        self.assertNotIn("name:distraction", dest.split("dispatch workspace", 1)[-1])


if __name__ == "__main__":
    unittest.main()
