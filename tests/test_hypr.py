#!/usr/bin/env python3
"""Window rules, silent moves, intercept banner, and workspace cycle."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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
if args[:1] == ["keyword"]:
    print("keyword can't work with non-legacy parsers. Use eval.")
    sys.exit(1)
if args[:1] == ["eval"] and (len(args) < 2 or args[1].startswith("-")):
    sys.stderr.write("usage: hyprctl [flags] <command> [args...|--help]\n")
    sys.exit(1)
if args[:1] in (["eval"], ["dispatch"]):
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

LUA = shutil.which("lua5.4") or shutil.which("lua") or shutil.which("luajit")

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
        self.assertTrue(hypr.apply_rules([TELEGRAM]))
        expected, _ = hypr._rule_names([TELEGRAM])
        joined = "\n".join(self._joined())
        self.assertEqual(len(expected), 2)
        self.assertIn(f"name = {hypr.lua_string(expected[0])}", joined)
        self.assertIn(f"name = {hypr.lua_string(expected[1])}", joined)
        self.assertIn(f"class = {hypr.lua_string(NATIVE)}", joined)
        self.assertIn(f"class = {hypr.lua_string(PWA_CLASS)}", joined)
        self.assertIn(f'workspace = "name:{hypr.SPACE} silent"', joined)
        self.assertIn("hl.window_rule(", joined)
        self.assertEqual([c[0] for c in self._hypr_cmds() if c[0] != "-j"], ["eval", "eval"])
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
        self.assertIn(f"omarchy-ds disable {discord_names[0]}", joined)
        self.assertNotIn(f"omarchy-ds disable {telegram_names[0]}", joined)
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

        os.environ["DS_HYPR_FAIL"] = "-- omarchy-ds "  # both the set and the disable fragments
        self.hypr_log.write_text("", encoding="utf-8")
        self.assertFalse(hypr.apply_rules(_entries("Discord")))
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("omarchy-ds set", log)
        names = set(state.read_json(state.state_path("rules.json"), []))
        discord_names, _ = hypr._rule_names(_entries("Discord"))
        telegram_names, _ = hypr._rule_names([TELEGRAM])
        self.assertFalse(set(discord_names) & names, "a failed install is not recorded")
        self.assertEqual(names, set(telegram_names), "the previous registry is kept")
        self.assertTrue(any("Window rules could not be updated" in " ".join(a) for a in self._notifies()))

    def test_partial_install_failure_rolls_back_created_rules(self):
        expected, _ = hypr._rule_names([TELEGRAM])
        self.assertEqual(len(expected), 2)
        os.environ["DS_HYPR_FAIL"] = f"omarchy-ds set {expected[1]}"
        self.assertFalse(hypr.apply_rules([TELEGRAM]))
        joined = self._joined()
        self.assertTrue(any(f"omarchy-ds set {expected[0]}" in j for j in joined))
        self.assertTrue(any(f"omarchy-ds disable {expected[0]}" in j for j in joined), "first rule rolled back")
        self.assertTrue(any(f"omarchy-ds disable {expected[1]}" in j for j in joined), "failing name rolled back too")
        self.assertEqual(state.read_json(state.state_path("rules.json"), []), [])
        self.assertEqual(len([a for a in self._notifies() if "Window rules" in " ".join(a)]), 1)

        os.environ.pop("DS_HYPR_FAIL", None)
        self.hypr_log.write_text("", encoding="utf-8")
        self.assertTrue(hypr.apply_rules([TELEGRAM]))
        self.assertEqual(set(state.read_json(state.state_path("rules.json"), [])), set(expected))

    def test_reset_of_existing_name_is_restored_on_failure(self):
        foo_a = [{"name": "Foo", "classes": ["ClassA"]}]
        self.assertTrue(hypr.apply_rules(foo_a))
        foo_name, _ = hypr._rule_names(foo_a)
        bar_name, _ = hypr._rule_names([{"name": "Bar", "classes": ["ClassC"]}])
        self.assertEqual(state.read_json(state.state_path("rule-specs.json"), {}), {foo_name[0]: "ClassA"})
        os.environ["DS_HYPR_FAIL"] = f"omarchy-ds set {bar_name[0]}"
        self.hypr_log.write_text("", encoding="utf-8")
        self.assertFalse(hypr.apply_rules([
            {"name": "Foo", "classes": ["ClassB"]},
            {"name": "Bar", "classes": ["ClassC"]},
        ]))
        joined = self._joined()
        sets_for_foo = [j for j in joined if f"omarchy-ds set {foo_name[0]}" in j]
        self.assertEqual(len(sets_for_foo), 2, "re-set to ClassB, then restored")
        self.assertIn('class = "ClassB"', sets_for_foo[0])
        self.assertIn('class = "ClassA"', sets_for_foo[1], "previous class re-set on rollback")
        self.assertFalse(any(f"omarchy-ds disable {foo_name[0]}" in j for j in joined), "a pre-existing name is never disabled")
        self.assertTrue(any(f"omarchy-ds disable {bar_name[0]}" in j for j in joined), "the failing new name is disabled")
        self.assertEqual(state.read_json(state.state_path("rules.json"), []), foo_name)
        self.assertEqual(state.read_json(state.state_path("rule-specs.json"), {}), {foo_name[0]: "ClassA"})

    def test_failing_reset_of_existing_name_is_restored(self):
        foo_a = [{"name": "Foo", "classes": ["ClassA"]}]
        self.assertTrue(hypr.apply_rules(foo_a))
        foo_name, _ = hypr._rule_names(foo_a)
        os.environ["DS_HYPR_FAIL"] = 'class = "ClassB"'
        self.hypr_log.write_text("", encoding="utf-8")
        self.assertFalse(hypr.apply_rules([{"name": "Foo", "classes": ["ClassB"]}]))
        sets_for_foo = [j for j in self._joined() if f"omarchy-ds set {foo_name[0]}" in j]
        self.assertEqual(len(sets_for_foo), 2)
        self.assertIn('class = "ClassB"', sets_for_foo[0])
        self.assertIn('class = "ClassA"', sets_for_foo[1], "the failing name is re-set with its recorded class")
        self.assertFalse(any("omarchy-ds disable" in j for j in self._joined()))
        self.assertEqual(state.read_json(state.state_path("rule-specs.json"), {}), {foo_name[0]: "ClassA"})

    def test_pre_existing_name_without_recorded_class_is_disabled_on_rollback(self):
        foo_a = [{"name": "Foo", "classes": ["ClassA"]}]
        self.assertTrue(hypr.apply_rules(foo_a))
        foo_name, _ = hypr._rule_names(foo_a)
        bar_name, _ = hypr._rule_names([{"name": "Bar", "classes": ["ClassC"]}])
        state.state_path("rule-specs.json").unlink()  # registry written before specs were kept
        os.environ["DS_HYPR_FAIL"] = f"omarchy-ds set {bar_name[0]}"
        self.hypr_log.write_text("", encoding="utf-8")
        self.assertFalse(hypr.apply_rules([foo_a[0], {"name": "Bar", "classes": ["ClassC"]}]))
        self.assertTrue(any(f"omarchy-ds disable {foo_name[0]}" in j for j in self._joined()))
        self.assertEqual(state.read_json(state.state_path("rules.json"), []), foo_name)
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
        os.environ["DS_HYPR_FAIL"] = "omarchy-ds disable"
        hypr.apply_rules(_entries("Telegram"))
        recorded = set(state.read_json(state.state_path("rules.json"), []))
        self.assertTrue(set(discord_names) <= recorded)
        self.assertTrue(set(telegram_names) <= recorded)
        joined = "\n".join(self._joined())
        self.assertIn(f"omarchy-ds disable {discord_names[0]}", joined)
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("omarchy-ds disable", log)

        os.environ.pop("DS_HYPR_FAIL", None)
        self.hypr_log.write_text("", encoding="utf-8")
        hypr.apply_rules(_entries("Telegram"))
        retried = "\n".join(self._joined())
        self.assertIn(f"omarchy-ds disable {discord_names[0]}", retried)
        after = set(state.read_json(state.state_path("rules.json"), []))
        self.assertEqual(after, set(telegram_names))
        self.assertFalse(set(discord_names) & after)

    def test_keyword_is_never_used_for_rules(self):
        hypr.apply_rules(_entries("Telegram", "Discord"))
        hypr.apply_rules(_entries("Telegram"))
        verbs = {c[0] for c in self._hypr_cmds()}
        self.assertNotIn("keyword", verbs)
        self.assertIn("eval", verbs)
        self.assertFalse(state.state_path("log").exists(), "the eval double accepted every fragment")

    def test_keyword_double_refuses_like_the_lua_parser(self):
        r = hypr._run("keyword", "windowrule[x]:enable false")
        self.assertIsNone(r)
        self.assertIn("non-legacy parsers", state.state_path("log").read_text(encoding="utf-8"))

    def test_is_config_reload(self):
        self.assertTrue(hypr.is_config_reload("configreloaded>>"))
        self.assertTrue(hypr.is_config_reload(">>configreloaded>>"))
        self.assertFalse(hypr.is_config_reload("openwindow>>0xaaa,1,c,t"))
        self.assertFalse(hypr.is_config_reload("configreloadedx>>"))
        self.assertFalse(hypr.is_config_reload(""))
        self.assertFalse(hypr.is_config_reload(None))

    @unittest.skipUnless(LUA, "no Lua interpreter on PATH")
    def test_lua_string_round_trips_through_lua(self):
        cases = [
            NATIVE,
            PWA_CLASS,
            r"^chrome-discord\.com__.*$",
            'quote"inside',
            "apos'trophe",
            "long]]bracket",
            "new\nline\ttab",
            "ctl\x019\x7f",
            "back\\slash\\",
        ]
        for value in cases:
            with self.subTest(value=value):
                proc = subprocess.run([LUA, "-e", f"io.write({hypr.lua_string(value)})"], capture_output=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.decode("utf-8"), value)

    def _run_lua(self, *fragments, fail_create=False, fail_after=None):
        harness = self.box.runtime / "harness.lua"
        limit = 0 if fail_create else (fail_after if fail_after is not None else -1)
        harness.write_text(
            "hl = {}\n"
            f"local fail_after = {limit}\n"
            "local creates = 0\n"
            "hl.window_rule = function(spec)\n"
            "  if fail_after >= 0 and creates >= fail_after then error('window_rule refused') end\n"
            "  creates = creates + 1\n"
            "  local h = { enabled = true }\n"
            "  function h:set_enabled(v) self.enabled = v; io.write('set_enabled ', spec.name, ' ', tostring(v), '\\n') end\n"
            "  io.write('create ', spec.name, ' ', spec.match.class, ' ', spec.workspace, '\\n')\n"
            "  return h\n"
            "end\n"
            "for i = 1, #arg do dofile(arg[i]) end\n",
            encoding="utf-8",
        )
        paths = []
        for i, fragment in enumerate(fragments):
            path = self.box.runtime / f"fragment{i}.lua"
            path.write_text(fragment, encoding="utf-8")
            paths.append(str(path))
        return subprocess.run([LUA, str(harness), *paths], capture_output=True, text=True)

    @unittest.skipUnless(LUA, "no Lua interpreter on PATH")
    def test_lua_fragments_disable_old_handle_and_noop_when_missing(self):
        name = "omarchy-ds-telegram-0"
        ws = hypr.WORKSPACE_EFFECT
        proc = self._run_lua(
            hypr.disable_rule_lua(name),
            hypr.set_rule_lua(name, NATIVE),
            hypr.set_rule_lua(name, r"^org\.telegram\..*$"),
            hypr.disable_rule_lua(name),
            hypr.disable_rule_lua(name),
            hypr.disable_rule_lua("omarchy-ds-never"),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.splitlines(),
            [
                f"create {name} {NATIVE} {ws}",
                f"create {name} ^org\\.telegram\\..*$ {ws}",
                f"set_enabled {name} false",  # the old handle, retired after the new create
                f"set_enabled {name} false",  # the explicit disable
            ],
        )

    @unittest.skipUnless(LUA, "no Lua interpreter on PATH")
    def test_lua_failed_reset_keeps_previous_rule_live(self):
        name = "omarchy-ds-telegram-0"
        proc = self._run_lua(
            hypr.set_rule_lua(name, NATIVE),
            hypr.set_rule_lua(name, r"^org\.telegram\..*$"),
            fail_after=1,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("window_rule refused", proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), [f"create {name} {NATIVE} {hypr.WORKSPACE_EFFECT}"],
                         "the previous handle was not retired")

    @unittest.skipUnless(LUA, "no Lua interpreter on PATH")
    def test_lua_fragment_create_error_is_not_swallowed(self):
        proc = self._run_lua(hypr.set_rule_lua("omarchy-ds-telegram-0", NATIVE), fail_create=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("window_rule refused", proc.stderr)

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
        self.assertIn('class = "FooBarClass"', joined)
        self.assertIn('class = "FooDashClass"', joined)
        self.assertIn(f"name = {hypr.lua_string(names[0])}", joined)
        self.assertIn(f"name = {hypr.lua_string(names[1])}", joined)

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
