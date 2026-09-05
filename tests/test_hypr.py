#!/usr/bin/env python3
"""Window rules, the three containment layers, adoption, the Opened banner wiring, and workspace cycle."""

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
from test_cgroup import SESSION_PATH, SLICE_PATH, FakeProc

sys.path.insert(0, str(ROOT))
from ds import feedback, hypr, state
from ds.catalog import expand_entry

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

# Stands in for this checkout's `distractions` CLI, which adoption runs: logs the
# argv and fails like `open` does when no browser is available.
OPEN = r"""
import json, os, sys
from pathlib import Path

p = Path(os.environ["DS_OPEN_LOG"])
p.parent.mkdir(parents=True, exist_ok=True)
with p.open("a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
if os.environ.get("DS_OPEN_FAIL"):
    sys.stderr.write("No distraction browser: none found\n")
    sys.exit(1)
"""

LUA = shutil.which("lua5.4") or shutil.which("lua") or shutil.which("luajit")

TELEGRAM = expand_entry("Telegram")
WHATSAPP = expand_entry("WhatsApp")
NATIVE = "org.telegram.desktop"
PROFILE_WA = "chrome-web.whatsapp.com__-Distraction"
FOREIGN_WA = "chrome-web.whatsapp.com__-Default"
OPENED = "opened in the distraction space"


def _entries(*names):
    return [expand_entry(n) for n in names]


class HyprTests(unittest.TestCase):
    def setUp(self) -> None:
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.hypr_log = self.box.runtime / "hypr.log"
        self.notify_log = self.box.runtime / "notify.log"
        self.open_log = self.box.runtime / "open.log"
        self.hypr_state = self.box.runtime / "hypr-state.json"
        proc = self.box.runtime / "proc"
        proc.mkdir()
        self.proc = FakeProc(proc)
        os.environ["DS_HYPR_LOG"] = str(self.hypr_log)
        os.environ["DS_NOTIFY_LOG"] = str(self.notify_log)
        os.environ["DS_OPEN_LOG"] = str(self.open_log)
        os.environ["DS_HYPR_STATE"] = str(self.hypr_state)
        os.environ["DS_PROC_ROOT"] = str(proc)
        self.addCleanup(os.environ.pop, "DS_PROC_ROOT", None)
        for key in ("DS_HYPR_FAIL", "DS_NOTIFY_FAIL", "DS_OPEN_FAIL"):
            os.environ.pop(key, None)
        self.box.fake_bin("hyprctl", HYPRCTL)
        self.box.fake_bin("omarchy-notification-send", NOTIFY)
        cli = self.box.fake_bin("distractions", OPEN)
        patcher = mock.patch.object(hypr, "CLI", str(cli))
        patcher.start()
        self.addCleanup(patcher.stop)
        hypr._reset_for_tests()
        # The Opened banner goes through feedback: the nudge on, no lock, no routers bound.
        feedback.start({"nudges": {"block_page": False}, "site_block": {"pass_through": False}}, False)
        self.addCleanup(feedback.stop)

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

    def _dispatches(self):
        return [c[1] for c in self._hypr_cmds() if c[0] == "dispatch"]

    def _notifies(self):
        if not self.notify_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.notify_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _opened_titles(self):
        return [a for args in self._notifies() for a in args if OPENED in a]

    def _open_calls(self):
        if not self.open_log.exists():
            return []
        return [json.loads(line) for line in self.open_log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _log_lines(self, needle):
        path = state.state_path("log")
        if not path.exists():
            return []
        return [ln for ln in path.read_text(encoding="utf-8").splitlines() if needle in ln]

    def _client(self, address, klass, workspace="1", pid=None):
        client = {
            "address": address,
            "class": klass,
            "workspace": {"id": 1 if workspace != hypr.SPACE else 99, "name": workspace},
        }
        if pid is not None:
            client["pid"] = pid
        return client

    def _profile_spec(self):
        return {hypr.PROFILE_RULE: hypr.profile_rule_class()}

    def test_one_profile_rule_plus_native_rules_and_no_per_host_web_rule(self):
        self.assertEqual(hypr.profile_rule_class(), r"^[a-z-]+-.+__-Distraction$")
        self.assertTrue(hypr.apply_rules(_entries("Telegram", "Discord", "X")))
        native, _ = hypr._rule_names([TELEGRAM])
        self.assertEqual(native, [hypr._rule_name("Telegram", 0)])
        creates = [j for j in self._joined() if "hl.window_rule(" in j]
        self.assertEqual(len(creates), 2, creates)
        joined = "\n".join(creates)
        self.assertIn(f"name = {hypr.lua_string(hypr.PROFILE_RULE)}", joined)
        self.assertIn(f"class = {hypr.lua_string(hypr.profile_rule_class())}", joined)
        self.assertIn(f"name = {hypr.lua_string(native[0])}", joined)
        self.assertIn(f"class = {hypr.lua_string(NATIVE)}", joined)
        self.assertIn(f'workspace = "name:{hypr.SPACE} silent"', joined)
        for host in ("web.telegram.org", "discord.com", "x.com"):
            self.assertNotIn(host, joined, "no per-host web rule")
        self.assertEqual([c[0] for c in self._hypr_cmds() if c[0] != "-j"], ["eval", "eval"])
        names = state.read_json(state.state_path("rules.json"), [])
        self.assertEqual(set(names), {hypr.PROFILE_RULE, native[0]})
        self.assertEqual(state.read_json(state.state_path("rule-specs.json"), {}),
                         {**self._profile_spec(), native[0]: NATIVE})
        # A re-apply (the listener's configreloaded path) sets the same fragments again.
        self.hypr_log.write_text("", encoding="utf-8")
        self.assertTrue(hypr.apply_rules(_entries("Telegram", "Discord", "X")))
        self.assertEqual([j for j in self._joined() if "hl.window_rule(" in j], creates)

    def test_removed_entries_have_rules_disabled(self):
        hypr.apply_rules(_entries("Telegram", "Signal"))
        before = set(state.read_json(state.state_path("rules.json"), []))
        signal_names, _ = hypr._rule_names(_entries("Signal"))
        telegram_names, _ = hypr._rule_names(_entries("Telegram"))
        self.assertEqual(len(signal_names), 1)
        self.assertTrue(set(signal_names) <= before)
        self.hypr_log.write_text("", encoding="utf-8")
        hypr.apply_rules(_entries("Telegram"))
        joined = "\n".join(self._joined())
        self.assertIn(f"omarchy-ds disable {signal_names[0]}", joined)
        self.assertNotIn(f"omarchy-ds disable {telegram_names[0]}", joined)
        self.assertNotIn(f"omarchy-ds disable {hypr.PROFILE_RULE}", joined)
        after = set(state.read_json(state.state_path("rules.json"), []))
        self.assertEqual(after, {hypr.PROFILE_RULE, *telegram_names})

    def test_profile_and_native_windows_off_the_space_move_silently(self):
        hypr.apply_rules([TELEGRAM, WHATSAPP])
        self.proc.add(300, 1, SESSION_PATH)
        self._state(
            clients=[
                self._client("0xaaa", NATIVE, "1"),
                self._client("0xbbb", PROFILE_WA, "1"),
                self._client("0xccc", "chrome-music.example.org__-Distraction", "1"),
                self._client("0xddd", "firefox", "1"),
                self._client("0xeee", "google-chrome", "1", pid=300),
            ]
        )
        self.hypr_log.write_text("", encoding="utf-8")
        for line in (
            f"openwindow>>0xaaa,1,{NATIVE},Telegram",
            f"openwindow>>0xbbb,1,{PROFILE_WA},WhatsApp",
            "openwindow>>0xccc,1,chrome-music.example.org__-Distraction,Music",
            "openwindow>>0xddd,1,firefox,Mozilla Firefox",
            "openwindow>>0xeee,1,google-chrome,Chrome",
            "movewindow>>0xaaa,2",
            "movewindow>>0xddd,2",
        ):
            hypr.handle_event(line)
        moves = [hypr.move_window_lua(a) for a in ("0xaaa", "0xbbb", "0xccc", "0xaaa")]
        self.assertEqual(self._dispatches(), moves)
        self.assertTrue(all("follow = false" in m for m in moves))
        self.assertFalse(any("hl.dsp.focus" in j for j in self._joined()), "the focused workspace never changes")
        self.assertEqual(self._open_calls(), [])
        # A profile window of an unlisted host is moved with no banner; the second
        # Telegram event is inside the debounce window.
        self.assertEqual(self._opened_titles(), [f"Telegram {OPENED}", f"WhatsApp {OPENED}"])

    def test_slice_popup_moved_and_unreadable_cgroup_falls_back_to_class(self):
        hypr.apply_rules([TELEGRAM])
        self.proc.add(100, 1, f"{SLICE_PATH}/run-1.scope")
        popup = self.proc.chain(100, 3, first_pid=110)
        self.proc.add(200, 1, None)  # no readable cgroup file
        self.proc.add(210, 1, SESSION_PATH)
        self._state(
            clients=[
                self._client("0xaaa", "google-chrome", "1", pid=popup),
                self._client("0xbbb", "google-chrome", "1", pid=200),
                self._client("0xccc", NATIVE, "1", pid=200),
                self._client("0xddd", "google-chrome", "1", pid=210),
            ]
        )
        self.hypr_log.write_text("", encoding="utf-8")
        for address in ("0xaaa", "0xbbb", "0xccc", "0xddd"):
            hypr.handle_event(f"openwindow>>{address},1,google-chrome,Chrome")
        self.assertEqual(self._dispatches(), [hypr.move_window_lua("0xaaa"), hypr.move_window_lua("0xccc")])
        self.assertEqual(self._open_calls(), [])
        # A slice popup names no list entry, so only the native window is announced.
        self.assertEqual(self._opened_titles(), [f"Telegram {OPENED}"])
        self.assertEqual(hypr.classify("google-chrome", popup), ("slice", None))
        self.assertIsNone(hypr.classify("google-chrome", 200))
        self.assertEqual(hypr.classify(NATIVE, 200), ("class", TELEGRAM))
        self.assertIsNone(hypr.classify("google-chrome", None))

    def test_foreign_webapp_closed_once_and_opened_once_per_address(self):
        hypr.apply_rules([TELEGRAM, WHATSAPP])
        self.proc.add(300, 1, SESSION_PATH)
        self.proc.add(100, 1, f"{SLICE_PATH}/run-1.scope")
        self._state(
            clients=[
                self._client("0xdead", FOREIGN_WA, "1", pid=300),
                self._client("0xbeef", "brave-web.whatsapp.com__-Profile_2", "2", pid=300),
                self._client("0xcafe", "google-chrome", "1", pid=300),
            ]
        )
        self.hypr_log.write_text("", encoding="utf-8")
        hypr.handle_event(f"openwindow>>0xdead,1,{FOREIGN_WA},WhatsApp")
        hypr.handle_event("movewindow>>0xdead,1")
        hypr.handle_event(f"openwindow>>0xdead,1,{FOREIGN_WA},WhatsApp")
        hypr.handle_event("openwindow>>0xbeef,2,brave-web.whatsapp.com__-Profile_2,WhatsApp")
        hypr.handle_event("openwindow>>0xcafe,1,google-chrome,Chrome")
        self.assertEqual(self._open_calls(), [["open", "WhatsApp"], ["open", "WhatsApp"]])
        self.assertEqual(self._dispatches(), [hypr.close_window_lua("0xdead"), hypr.close_window_lua("0xbeef")])
        self.assertEqual(hypr.close_window_lua("0xdead"), 'hl.dsp.window.close({ window = "address:0xdead" })')
        self.assertEqual(self._opened_titles(), [f"WhatsApp {OPENED}"])
        self.assertEqual(self._log_lines("adopt:"), [])
        # `closewindow` forgets the address, so a reused one is adopted again.
        hypr.handle_event("closewindow>>0xdead")
        hypr.handle_event(f"openwindow>>0xdead,1,{FOREIGN_WA},WhatsApp")
        self.assertEqual(len(self._open_calls()), 3)
        # The layers in order: the slice claims a foreign-profile window before adoption does.
        self.assertEqual(hypr.classify(FOREIGN_WA, 100), ("slice", None))
        self.assertEqual(hypr.classify(FOREIGN_WA, 300), ("adopt", WHATSAPP))
        self.assertEqual(hypr.classify("chrome-m.web.whatsapp.com__-Default", None), ("adopt", WHATSAPP))
        self.assertEqual(hypr.classify(PROFILE_WA, 300), ("class", WHATSAPP))
        self.assertIsNone(hypr.classify("chrome-web.example.org__-Default", 300))
        self.assertIsNone(hypr.classify("chrome-notweb.whatsapp.com__-Default", 300))

    def test_failed_open_leaves_the_window_moved_by_class_with_one_log_line(self):
        hypr.apply_rules([WHATSAPP])
        self._state(clients=[self._client("0xdead", FOREIGN_WA, "1"), self._client("0xf00d", FOREIGN_WA, "2")])
        os.environ["DS_OPEN_FAIL"] = "1"
        self.hypr_log.write_text("", encoding="utf-8")
        hypr.handle_event(f"openwindow>>0xdead,1,{FOREIGN_WA},WhatsApp")
        hypr.handle_event("movewindow>>0xdead,1")
        self.assertEqual(self._open_calls(), [["open", "WhatsApp"]])
        self.assertEqual(self._dispatches(), [hypr.move_window_lua("0xdead")])
        lines = self._log_lines("adopt:")
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("open WhatsApp failed (exit 1: No distraction browser: none found); window 0xdead moved by class", lines[0])
        self.assertEqual(self._opened_titles(), [f"WhatsApp {OPENED}"])
        # A CLI that cannot be started at all is the same outcome.
        with mock.patch.object(hypr, "CLI", str(self.box.runtime / "missing" / "distractions")):
            hypr.handle_event(f"openwindow>>0xf00d,2,{FOREIGN_WA},WhatsApp")
        self.assertEqual(self._dispatches(), [hypr.move_window_lua("0xdead"), hypr.move_window_lua("0xf00d")])
        self.assertEqual(len(self._log_lines("adopt:")), 2)
        self.assertEqual(len(self._open_calls()), 1)
        # A failed open whose fallback move is refused too: nothing landed, no banner.
        self._state(clients=[self._client("0xbad", FOREIGN_WA, "3")])
        os.environ["DS_HYPR_FAIL"] = "hl.dsp.window.move"
        before = len(self._opened_titles())
        hypr.handle_event(f"openwindow>>0xbad,3,{FOREIGN_WA},WhatsApp")
        self.assertEqual(len(self._open_calls()), 2)
        self.assertEqual(len(self._log_lines("adopt:")), 3)
        self.assertEqual(len(self._opened_titles()), before)

    def test_refused_close_is_retried_without_a_second_open(self):
        hypr.apply_rules([WHATSAPP])
        self._state(clients=[self._client("0xdead", FOREIGN_WA, "1")])
        os.environ["DS_HYPR_FAIL"] = "hl.dsp.window.close"
        self.hypr_log.write_text("", encoding="utf-8")
        close = hypr.close_window_lua("0xdead")
        hypr.handle_event(f"openwindow>>0xdead,1,{FOREIGN_WA},WhatsApp")
        self.assertEqual(self._open_calls(), [["open", "WhatsApp"]])
        # The fake logs every dispatch it refuses, so attempts are countable.
        self.assertEqual(self._dispatches(), [close])
        self.assertEqual(len(self._log_lines("adopt: close of 0xdead refused")), 1)
        # The product did open in the space, so the banner is right even though
        # the foreign window is still up.
        self.assertEqual(self._opened_titles(), [f"WhatsApp {OPENED}"])
        hypr.handle_event("movewindow>>0xdead,1")
        self.assertEqual(len(self._open_calls()), 1)
        self.assertEqual(self._dispatches(), [close, close])
        os.environ.pop("DS_HYPR_FAIL")
        hypr.handle_event("movewindow>>0xdead,1")
        self.assertEqual(len(self._open_calls()), 1)
        self.assertEqual(self._dispatches(), [close, close, close])
        # Closed for good: nothing more is owed for this address.
        hypr.handle_event("movewindow>>0xdead,1")
        self.assertEqual(self._dispatches(), [close, close, close])

    def test_failed_move_on_a_scan_raises_no_banner(self):
        hypr.apply_rules([TELEGRAM])
        client = self._client("0xaaa", NATIVE, "1")
        self._state(clients=[client])
        os.environ["DS_HYPR_FAIL"] = "hl.dsp.window.move"
        self.assertEqual(hypr.contain(client), "class")
        self.assertEqual(self._opened_titles(), [])
        self.assertIn("hyprctl", state.state_path("log").read_text(encoding="utf-8"))
        os.environ.pop("DS_HYPR_FAIL")
        self.assertEqual(hypr.contain(client), "class")
        self.assertEqual(self._opened_titles(), [f"Telegram {OPENED}"])

    def test_opened_banner_once_per_entry_per_60s_and_never_on_the_space(self):
        hypr.apply_rules([TELEGRAM])
        self._state(clients=[self._client("0xaaa", NATIVE, hypr.SPACE)])
        clock = mock.Mock()
        clock.side_effect = lambda: clock.t
        with mock.patch("ds.feedback.time.monotonic", clock):
            for t, shown in ((1000.0, 1), (1030.0, 1), (1059.9, 1), (1060.5, 2)):
                clock.t = t
                hypr.handle_event(f"openwindow>>0xaaa,99,{NATIVE},Telegram")
                self.assertEqual(len(self._notifies()), shown, t)
            self.assertEqual(self._dispatches(), [], "the rule placed it; nothing to move")
            args = self._notifies()[0]
            self.assertIn(f"Telegram {OPENED}", args)
            self.assertIn("Super+Ctrl+Shift+D enters.", args)
            self.assertEqual(args[args.index("--exec") + 1:], [feedback._CLI, "enter"])
            self.assertEqual(
                [ln.split(" decision=")[1] for ln in self._log_lines("banner: ")],
                ["shown", "debounced", "debounced", "shown"],
            )
            # A scan finding a window already on the space announces nothing.
            clock.t = 2000.0
            self.notify_log.write_text("", encoding="utf-8")
            self.assertEqual(hypr.contain(self._client("0xaaa", NATIVE, hypr.SPACE)), "class")
            self.assertEqual(self._notifies(), [])
            # A scan that moves one does.
            self.assertEqual(hypr.contain(self._client("0xaaa", NATIVE, "1")), "class")
            self.assertEqual(self._opened_titles(), [f"Telegram {OPENED}"])
            # Never on the space.
            clock.t = 3000.0
            self.notify_log.write_text("", encoding="utf-8")
            self._state(activeworkspace={"id": 99, "name": hypr.SPACE}, clients=[self._client("0xaaa", NATIVE, "1")])
            hypr.handle_event(f"openwindow>>0xaaa,99,{NATIVE},Telegram")
            self.assertEqual(self._notifies(), [])

    def test_banner_off_when_nudge_disabled(self):
        feedback.start({"nudges": {"app_banner": False, "block_page": False}, "site_block": {"pass_through": False}}, False)
        hypr.apply_rules([TELEGRAM])
        self._state(clients=[self._client("0xaaa", NATIVE, "1")])
        hypr.handle_event(f"openwindow>>0xaaa,1,{NATIVE},Telegram")
        self.assertEqual(self._notifies(), [])
        self.assertEqual(self._dispatches(), [hypr.move_window_lua("0xaaa")])

    def test_hyprctl_failure_logged_and_skipped(self):
        hypr.apply_rules([TELEGRAM])
        self._state(clients=[self._client("0xaaa", NATIVE, "1")])
        os.environ["DS_HYPR_FAIL"] = "hl.dsp.window.move"
        hypr.handle_event(f"openwindow>>0xaaa,1,{NATIVE},Telegram")
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("hyprctl", log)
        # The window is still on workspace 1: nothing opened in the space, no banner.
        self.assertEqual(self._opened_titles(), [])
        # A fresh window the rule already placed on the space is announced without a move.
        self._state(clients=[self._client("0xbbb", NATIVE, hypr.SPACE)])
        hypr.handle_event(f"openwindow>>0xbbb,{hypr.SPACE},{NATIVE},Telegram")
        self.assertEqual(self._opened_titles(), [f"Telegram {OPENED}"])

        os.environ["DS_HYPR_FAIL"] = "-- omarchy-ds "  # both the set and the disable fragments
        self.hypr_log.write_text("", encoding="utf-8")
        self.assertFalse(hypr.apply_rules(_entries("Signal")))
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("omarchy-ds set", log)
        names = set(state.read_json(state.state_path("rules.json"), []))
        signal_names, _ = hypr._rule_names(_entries("Signal"))
        telegram_names, _ = hypr._rule_names([TELEGRAM])
        self.assertFalse(set(signal_names) & names, "a failed install is not recorded")
        self.assertEqual(names, {hypr.PROFILE_RULE, *telegram_names}, "the previous registry is kept")
        self.assertTrue(any("Window rules could not be updated" in " ".join(a) for a in self._notifies()))

    def test_partial_install_failure_rolls_back_created_rules(self):
        native, _ = hypr._rule_names([TELEGRAM])
        expected = [hypr.PROFILE_RULE, *native]
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
        specs = {**self._profile_spec(), foo_name[0]: "ClassA"}
        self.assertEqual(state.read_json(state.state_path("rule-specs.json"), {}), specs)
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
        self.assertEqual(state.read_json(state.state_path("rules.json"), []), [hypr.PROFILE_RULE, *foo_name])
        self.assertEqual(state.read_json(state.state_path("rule-specs.json"), {}), specs)

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
        self.assertEqual(state.read_json(state.state_path("rule-specs.json"), {}),
                         {**self._profile_spec(), foo_name[0]: "ClassA"})

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
        self.assertEqual(state.read_json(state.state_path("rules.json"), []), [hypr.PROFILE_RULE, *foo_name])

    def test_notify_failure_ignored(self):
        hypr.apply_rules([TELEGRAM])
        self._state(clients=[self._client("0xaaa", NATIVE, "1")])
        os.environ["DS_NOTIFY_FAIL"] = "1"
        hypr.handle_event(f"openwindow>>0xaaa,1,{NATIVE},Telegram")
        self.assertEqual(self._dispatches(), [hypr.move_window_lua("0xaaa")])

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
        self.assertIn("hl.dsp.focus", joined)
        self.assertIn("name:2", joined)
        self.assertNotIn("name:distraction", joined.split("hl.dsp.focus", 1)[-1])

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
        self.assertNotIn("name:distraction", dest.split("hl.dsp.focus", 1)[-1])

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
        self.assertNotIn("name:distraction", dest.split("hl.dsp.focus", 1)[-1])

    def test_failed_disable_kept_in_rules_json_and_retried(self):
        hypr.apply_rules(_entries("Telegram", "Signal"))
        signal_names, _ = hypr._rule_names(_entries("Signal"))
        telegram_names, _ = hypr._rule_names(_entries("Telegram"))
        self.hypr_log.write_text("", encoding="utf-8")
        os.environ["DS_HYPR_FAIL"] = "omarchy-ds disable"
        hypr.apply_rules(_entries("Telegram"))
        recorded = set(state.read_json(state.state_path("rules.json"), []))
        self.assertTrue(set(signal_names) <= recorded)
        self.assertTrue(set(telegram_names) <= recorded)
        joined = "\n".join(self._joined())
        self.assertIn(f"omarchy-ds disable {signal_names[0]}", joined)
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("omarchy-ds disable", log)

        os.environ.pop("DS_HYPR_FAIL", None)
        self.hypr_log.write_text("", encoding="utf-8")
        hypr.apply_rules(_entries("Telegram"))
        retried = "\n".join(self._joined())
        self.assertIn(f"omarchy-ds disable {signal_names[0]}", retried)
        after = set(state.read_json(state.state_path("rules.json"), []))
        self.assertEqual(after, {hypr.PROFILE_RULE, *telegram_names})
        self.assertFalse(set(signal_names) & after)

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

    def test_lua_dispatcher_fragments(self):
        self.assertEqual(
            hypr.move_window_lua("0xaaa"),
            'hl.dsp.window.move({ window = "address:0xaaa", workspace = "name:distraction", follow = false })',
        )
        self.assertEqual(hypr.close_window_lua("0xaaa"), 'hl.dsp.window.close({ window = "address:0xaaa" })')
        self.assertEqual(hypr.focus_workspace_lua("2"), 'hl.dsp.focus({ workspace = "name:2" })')
        for frag in (hypr.move_window_lua("0xaaa"), hypr.close_window_lua("0xaaa"), hypr.focus_workspace_lua("distraction")):
            self.assertFalse(frag.startswith("-"))
        self._state(clients=[self._client("0xaaa", NATIVE, "1")])
        hypr.apply_rules([TELEGRAM])
        hypr.handle_event(f"openwindow>>0xaaa,1,{NATIVE},Telegram")
        moves = [c for c in self._hypr_cmds() if c[0] == "dispatch"]
        self.assertEqual(moves, [["dispatch", hypr.move_window_lua("0xaaa")]])

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
            hypr.profile_rule_class(),
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
                f"set_enabled {name} false",  # the old handle, retired before the new create
                f"create {name} ^org\\.telegram\\..*$ {ws}",
                f"set_enabled {name} false",  # the explicit disable
            ],
        )

    @unittest.skipUnless(LUA, "no Lua interpreter on PATH")
    def test_lua_failed_reset_retires_old_handle_then_python_rollback_restores(self):
        name = "omarchy-ds-telegram-0"
        ws = hypr.WORKSPACE_EFFECT
        proc = self._run_lua(
            hypr.set_rule_lua(name, NATIVE),
            hypr.set_rule_lua(name, r"^org\.telegram\..*$"),
            fail_after=1,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("window_rule refused", proc.stderr)
        self.assertEqual(
            proc.stdout.splitlines(),
            [f"create {name} {NATIVE} {ws}", f"set_enabled {name} false"],
            "the old handle is retired before the failing create; apply_rules re-sets it",
        )
        # The recovery fragment apply_rules sends creates the recorded class again.
        proc = self._run_lua(hypr.set_rule_lua(name, NATIVE))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), [f"create {name} {NATIVE} {ws}"])
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
        names = [n for n in state.read_json(state.state_path("rules.json"), []) if n != hypr.PROFILE_RULE]
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
        hypr.handle_event(f"openwindow>>0xaaa,1,{NATIVE},Telegram")
        self.assertEqual(self._dispatches(), [hypr.move_window_lua("0xaaa")])
        self.assertEqual(self._notifies(), [])
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertIn("hyprctl", log)
        self.assertIn("activeworkspace", log)
        self.assertIn("skipping banner", log)

    def test_clients_cached_once_per_second_and_failed_read_not_cached(self):
        clients = [self._client("0xaaa", NATIVE, "1")]
        self._state(clients=clients)
        clock = mock.Mock()
        clock.side_effect = lambda: clock.t
        clock.t = 10.0
        with mock.patch("ds.hypr.time.monotonic", clock):
            first = hypr.clients_cached()
            clock.t = 10.4
            second = hypr.clients_cached()
            self.assertEqual(first, clients)
            self.assertIs(first, second)
            n = sum(1 for c in self._hypr_cmds() if c[:2] == ["-j", "clients"])
            self.assertEqual(n, 1)
            clock.t = 11.1
            third = hypr.clients_cached()
            n = sum(1 for c in self._hypr_cmds() if c[:2] == ["-j", "clients"])
            self.assertEqual(n, 2)
            self.assertEqual(third, clients)

        os.environ["DS_HYPR_FAIL"] = "clients"
        hypr._reset_for_tests()
        self.hypr_log.write_text("", encoding="utf-8")
        self.assertIsNone(hypr.clients_cached())
        self.assertIsNone(hypr.clients_cached())
        n = sum(1 for c in self._hypr_cmds() if c[:2] == ["-j", "clients"])
        self.assertEqual(n, 2)

    def test_entry_for_host_www_and_case(self):
        x = expand_entry("X")
        extra = {"name": "Ex", "hosts": ["www.Example.COM"], "classes": ["ExClass"]}
        hypr._entries = [x, extra]
        self.assertEqual(hypr.entry_for_host("x.com")["name"], "X")
        self.assertEqual(hypr.entry_for_host("www.x.com")["name"], "X")
        self.assertEqual(hypr.entry_for_host("API.X.COM")["name"], "X")
        self.assertEqual(hypr.entry_for_host("example.com")["name"], "Ex")
        self.assertEqual(hypr.entry_for_host("WWW.example.com")["name"], "Ex")
        self.assertIsNone(hypr.entry_for_host("unknown.example"))
        self.assertIsNone(hypr.entry_for_host(None))
        self.assertIsNone(hypr.entry_for_host(""))

    def test_entry_clients_on_space(self):
        x = expand_entry("X")
        klass = "chrome-x.com__-Default"
        on = [self._client("0xa", klass, hypr.SPACE, pid=10)]
        self.assertTrue(hypr.entry_clients_on_space(x, on))
        mixed = [
            self._client("0xa", klass, hypr.SPACE, pid=10),
            self._client("0xb", klass, "1", pid=10),
        ]
        self.assertFalse(hypr.entry_clients_on_space(x, mixed))
        none = [self._client("0xc", "google-chrome", hypr.SPACE, pid=10)]
        self.assertFalse(hypr.entry_clients_on_space(x, none))
        self.assertFalse(hypr.entry_clients_on_space({"name": "Z", "hosts": ["z.com"]}, on))

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
        self.assertIn("hl.dsp.focus", dest)
        self.assertIn("name:2", dest)
        self.assertNotIn("name:distraction", dest.split("hl.dsp.focus", 1)[-1])

        self.hypr_log.write_text("", encoding="utf-8")
        self._state(activeworkspace={"id": 2, "name": "2"}, workspaces=occupied)
        r = self.box.run("prev")
        self.assertEqual(r.returncode, 0, r.stderr)
        dest = "\n".join(self._joined())
        self.assertIn("hl.dsp.focus", dest)
        self.assertIn("name:1", dest)
        self.assertNotIn("name:distraction", dest.split("hl.dsp.focus", 1)[-1])


if __name__ == "__main__":
    unittest.main()
