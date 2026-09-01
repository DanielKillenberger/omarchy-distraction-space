#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
distractions = SourceFileLoader("distractions", str(ROOT / "distractions")).load_module()


MEMBERS = distractions.load_members()
QML = Path(__file__).resolve().parents[1] / "NotificationFilter.qml"


class IdentityMapTests(unittest.TestCase):
    def test_members_match_windows_lua(self):
        distractions.members_match_windows()

    def test_named_members_cover_shipped_apps(self):
        labels = {member["label"] for member in MEMBERS}
        self.assertEqual(labels, {"Telegram", "Discord", "WhatsApp", "X", "Signal", "Messages"})

    def test_generic_browser_identity_is_rejected_in_table(self):
        bad = {
            "label": "Chrome",
            "window_class": "google-chrome",
            "native": {"app": ["Google Chrome"]},
        }
        with self.assertRaises(ValueError):
            distractions._reject_generic_member(bad)

    def test_native_banner_matches_app_or_icon(self):
        self.assertEqual(distractions.match_banner("Telegram Desktop", "", ""), "Telegram")
        self.assertEqual(distractions.match_banner("Signal", "signal", ""), "Signal")

    def test_plugin_toasts_stay_visible(self):
        self.assertIsNone(distractions.match_banner("omarchy-action", "", "https://discord.com/x"))
        self.assertIsNone(distractions.match_banner("notify-send", "", "https://x.com/y"))

    def test_chromium_leading_origin_only(self):
        self.assertEqual(
            distractions.match_banner("Google Chrome", "chromium", "https://discord.com/app Hello"),
            "Discord",
        )
        self.assertEqual(
            distractions.match_banner(
                "Chromium",
                "",
                '<a href="https://web.whatsapp.com/">https://web.whatsapp.com/</a> ping',
            ),
            "WhatsApp",
        )
        self.assertEqual(
            distractions.match_banner("Brave", "", "https://x.com/home more text"),
            "X",
        )
        self.assertEqual(
            distractions.match_banner("microsoft-edge", "", "https://messages.google.com/web"),
            "Messages",
        )

    def test_chromium_negatives_stay_visible(self):
        self.assertIsNone(distractions.match_banner("Google Chrome", "", "plain browser ping"))
        self.assertIsNone(distractions.match_banner("Chromium", "", "not a url"))
        self.assertIsNone(
            distractions.match_banner("Brave", "", "later mention of discord.com in prose")
        )
        self.assertIsNone(distractions.match_banner("Google Chrome", "chromium", ""))
        self.assertIsNone(
            distractions.match_banner("firefox", "", "https://discord.com/app")
        )
        self.assertIsNone(
            distractions.match_banner("Google Chrome", "signal", "plain chrome toast")
        )

    def test_leading_origin_extracts_same_forms_as_notification_logic(self):
        self.assertEqual(distractions.leading_origin_host("https://discord.com/app hi"), "discord.com")
        self.assertEqual(
            distractions.leading_origin_host('<a href="x">https://web.whatsapp.com/send</a>'),
            "web.whatsapp.com",
        )
        self.assertEqual(distractions.leading_origin_host("www.x.com/home more"), "x.com")
        self.assertEqual(distractions.leading_origin_host("see https://discord.com later"), "")


class StreamMatchTests(unittest.TestCase):
    def test_native_pulse_keys_match(self):
        self.assertEqual(
            distractions.match_stream(
                {"application.name": "Telegram Desktop", "application.process.binary": "telegram-desktop"},
                [],
            ),
            "Telegram",
        )

    def test_bare_chrome_is_never_muted(self):
        props = {
            "application.name": "Google Chrome",
            "application.process.binary": "chrome",
        }
        self.assertIsNone(distractions.match_stream(props, ["/usr/bin/google-chrome --type=renderer"]))
        self.assertIsNone(distractions.match_stream(props, ["chromium --enable-extensions"]))

    def test_chromium_ancestry_requires_host_or_app_id(self):
        props = {
            "application.name": "Chromium",
            "application.process.binary": "chrome",
        }
        self.assertEqual(
            distractions.match_stream(props, ["chrome --type=renderer", "chrome --app-id=discord.com"]),
            "Discord",
        )
        self.assertEqual(
            distractions.match_stream(props, ["chrome --app=https://web.whatsapp.com/"]),
            "WhatsApp",
        )
        self.assertEqual(
            distractions.match_stream(props, ["chrome --app-id x.com"]),
            "X",
        )
        self.assertEqual(
            distractions.match_stream(props, ["google-chrome --class=chrome-discord.com__-Default"]),
            "Discord",
        )
        self.assertEqual(
            distractions.match_stream(props, ["chrome-web.whatsapp.com__-Default --type=app"]),
            "WhatsApp",
        )
        self.assertIsNone(distractions.match_stream(props, ["chrome --type=renderer"]))
        self.assertIsNone(
            distractions.match_stream(props, ["chrome --app=https://fox.com/news"])
        )

    def test_casual_chrome_url_is_never_pwa_identity(self):
        props = {
            "application.name": "Google Chrome",
            "application.process.binary": "chrome",
        }
        self.assertIsNone(distractions.match_stream(props, ["google-chrome https://discord.com"]))
        self.assertIsNone(
            distractions.match_stream(props, ["google-chrome --new-window https://discord.com"])
        )
        self.assertIsNone(
            distractions.match_stream(props, ["chrome https://web.whatsapp.com/ https://x.com/"])
        )
        self.assertIsNone(
            distractions.match_stream(props, ["chrome --origin=https://discord.com"])
        )
        self.assertEqual(
            distractions.cmdline_identity_tokens(["google-chrome https://discord.com"]),
            set(),
        )
        self.assertEqual(
            distractions.cmdline_identity_tokens(["chrome --app=https://web.whatsapp.com/"]),
            {"web.whatsapp.com"},
        )


class RowRelocateTests(unittest.TestCase):
    def test_relocate_uses_immutable_keys_not_index(self):
        rows = [
            {"originalId": 1, "timestamp": 10, "app": "Signal"},
            {"originalId": 1, "timestamp": 99, "app": "Mail"},
        ]
        self.assertEqual(distractions.relocate_row(rows, 1, 99), 1)
        self.assertEqual(distractions.relocate_row(rows, 1, 10), 0)
        self.assertEqual(distractions.relocate_row(rows, 2, 10), -1)

    def test_restored_row_skips_live_ref_lookup(self):
        row = {"originalId": 1, "timestamp": 10}
        self.assertFalse(distractions.should_use_live_ref(row, True))
        self.assertTrue(distractions.should_use_live_ref(row, False))


class ApplyLiftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runtime = root / "run"
        self.state = root / "state"
        self.runtime.mkdir()
        self.state.mkdir()
        self.calls: list[tuple[str, ...]] = []
        self.ping = "ready"
        self.arm_out = "ok"
        self.disarm_out = "drained"
        self.drain_out = "drained"
        self.pactl_fail = False
        self.status_armed = False
        self.status_error = ""
        self.generation = 0
        self.patches = [
            mock.patch.object(distractions, "STATE_DIR", self.state),
            mock.patch.object(distractions, "FOCUS", self.state / "distractions.focus"),
            mock.patch.object(distractions, "MUTED_PATH", self.state / "distractions.muted.json"),
            mock.patch.object(distractions, "NOTIFY_LOCK", self.runtime / "notify.lock"),
            mock.patch.object(distractions, "WATCHER_REQUEST", self.runtime / "request.json"),
            mock.patch.object(distractions, "WATCHER_STATUS", self.runtime / "status.json"),
            mock.patch.object(distractions, "APPLY_WAIT_S", 0.4),
            mock.patch.object(distractions, "shell_ipc", self.fake_shell),
            mock.patch.object(distractions, "which_cmd", lambda _name: True),
            mock.patch.object(distractions, "notify", lambda *args, **kwargs: None),
            mock.patch.object(distractions, "wait_watcher_ack", self.fake_ack),
            mock.patch.object(distractions, "pactl_mute", self.fake_mute),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def fake_shell(self, *args, timeout=4.0):
        self.calls.append(args)
        if args[:2] == ("notifications", "dndState"):
            return 0, "off"
        if args[:2] == (distractions.PLUGIN_IPC, "ping"):
            return (0, self.ping) if self.ping else (1, "")
        if args[:2] == (distractions.PLUGIN_IPC, "arm"):
            return 0, self.arm_out
        if args[:2] == (distractions.PLUGIN_IPC, "disarm"):
            return 0, self.disarm_out
        if args[:2] == (distractions.PLUGIN_IPC, "drainState"):
            return 0, self.drain_out
        if args[:2] == ("shell", "rescanPlugins"):
            return 0, "ok"
        if "toggleDnd" in args or "setDnd" in args:
            raise AssertionError(f"DND mutation is forbidden: {args}")
        return 1, "unknown"

    def fake_ack(self, generation, want_armed, timeout=8.0):
        self.generation = generation
        if self.pactl_fail:
            return False, "pactl subscribe exited"
        self.status_armed = want_armed
        distractions.write_watcher_status(
            {
                "pid": 1,
                "generation": generation,
                "armed": want_armed,
                "last_error": self.status_error,
                "muted": [],
            }
        )
        return True, ""

    def fake_mute(self, index, muted):
        current = distractions.muted_ids()
        if muted and index not in current:
            current.append(index)
        if not muted and index in current:
            current.remove(index)
        distractions.save_muted_ids(current)
        return True

    def test_apply_is_noop_when_focus_is_off(self):
        distractions.FOCUS.write_text("off\n")
        self.assertTrue(distractions.apply_notification_block())
        self.assertNotIn((distractions.PLUGIN_IPC, "arm"), self.calls)

    def test_unmute_treats_missing_sink_as_restored(self):
        with mock.patch.object(distractions, "pactl_mute", return_value=False):
            with mock.patch.object(distractions, "list_sink_inputs", return_value=[]):
                self.assertEqual(distractions.unmute_owned([4, 5]), [])

    def test_apply_arms_plugin_and_watcher_without_dnd(self):
        self.assertTrue(distractions.apply_notification_block())
        methods = [call[1] if len(call) > 1 else call[0] for call in self.calls]
        self.assertIn("arm", methods)
        self.assertNotIn("toggleDnd", methods)
        self.assertNotIn("setDnd", methods)
        self.assertTrue(any("dndState" == (call[1] if len(call) > 1 else "") for call in self.calls))
        forbidden = " ".join(" ".join(call) for call in self.calls)
        self.assertNotIn("omarchy-toggle-notification-silencing", forbidden)

    def test_apply_fail_notifies_and_rolls_back(self):
        distractions.save_muted_ids([3])
        self.ping = ""
        with mock.patch.object(distractions, "notify") as notify:
            self.assertFalse(distractions.apply_notification_block())
            notify.assert_called()
            title, body = notify.call_args[0][:2]
            self.assertEqual(title, "Focus mode")
            self.assertIn("Could not mute", body)
        self.assertEqual(distractions.muted_ids(), [3])
        self.assertIn((distractions.PLUGIN_IPC, "disarm"), self.calls)

    def test_apply_fail_on_dead_subscribe_does_not_claim_armed(self):
        self.pactl_fail = True
        self.assertFalse(distractions.apply_notification_block())
        self.assertFalse(self.status_armed)

    def test_lift_disarms_and_unmutes_only_snapshot(self):
        self.assertTrue(distractions.lift_notification_block())
        self.assertIn((distractions.PLUGIN_IPC, "disarm"), self.calls)
        self.assertFalse(self.status_armed)

    def test_lift_fails_when_drain_ipc_errors(self):
        self.drain_out = "error"
        self.fake_shell_drain_code = 1

        def shell_with_drain_error(*args, timeout=4.0):
            if args[:2] == (distractions.PLUGIN_IPC, "drainState"):
                self.calls.append(args)
                return 1, "broken"
            return self.fake_shell(*args, timeout=timeout)

        with mock.patch.object(distractions, "shell_ipc", shell_with_drain_error):
            self.assertFalse(distractions.lift_notification_block())

    def test_watcher_disarms_when_focus_off_without_new_generation(self):
        request = {"generation": 4, "want_armed": True}
        distractions.FOCUS.write_text("on\n")
        self.assertTrue(distractions.watcher_desired_armed(request))
        self.assertFalse(distractions.watcher_needs_transition(4, True, request))
        distractions.FOCUS.write_text("off\n")
        self.assertFalse(distractions.watcher_desired_armed(request))
        self.assertTrue(distractions.watcher_needs_transition(4, True, request))

    def test_rollback_uses_live_status_not_stale_request(self):
        distractions.write_watcher_request(1, True)
        distractions.write_watcher_status(
            {"pid": 1, "generation": 1, "armed": False, "last_error": "", "muted": []}
        )
        with mock.patch.object(distractions, "read_proc_starttime", return_value=None):
            self.assertFalse(distractions.watcher_acknowledged_armed())
        self.ping = ""
        with mock.patch.object(distractions, "notify"):
            self.assertFalse(distractions.apply_notification_block())
        request = distractions.read_json(distractions.WATCHER_REQUEST, {})
        self.assertGreater(int(request.get("generation") or 0), 1)
        self.assertFalse(request.get("want_armed"))
        self.assertIn((distractions.PLUGIN_IPC, "disarm"), self.calls)

    def test_rollback_rearms_from_acknowledged_status(self):
        distractions.write_watcher_status(
            {
                "pid": os.getpid(),
                "starttime": "99",
                "generation": 2,
                "armed": True,
                "last_error": "",
                "muted": [],
            }
        )
        distractions.write_watcher_request(2, True)
        self.ping = ""
        with mock.patch.object(distractions, "read_proc_starttime", return_value="99"):
            with mock.patch.object(distractions, "notify"):
                self.assertFalse(distractions.apply_notification_block())
        request = distractions.read_json(distractions.WATCHER_REQUEST, {})
        self.assertGreater(int(request.get("generation") or 0), 2)
        self.assertTrue(request.get("want_armed"))
        self.assertIn((distractions.PLUGIN_IPC, "arm"), self.calls)

    def test_install_command_rescans_plugins(self):
        self.assertTrue(distractions.install_notification_service())
        self.assertIn(("shell", "rescanPlugins"), self.calls)

    def test_install_notifies_when_ping_times_out(self):
        self.ping = ""
        with mock.patch.object(distractions, "notify") as notify:
            self.assertFalse(distractions.install_notification_service())
            notify.assert_called()
            self.assertIn("did not become ready", notify.call_args[0][1])

    def test_armed_rollback_keeps_newly_muted_streams(self):
        distractions.save_muted_ids([10, 11])
        status = {
            "pid": os.getpid(),
            "generation": 9,
            "armed": True,
            "last_error": "",
            "muted": [10, 11],
        }

        def ack(generation, want_armed, timeout=8.0):
            distractions.write_watcher_status({**status, "generation": generation, "armed": want_armed})
            return True, ""

        with mock.patch.object(distractions, "wait_watcher_ack", ack):
            with mock.patch.object(distractions, "plugin_call", return_value=(0, "ok")):
                with mock.patch.object(distractions, "pactl_mute") as mute:
                    distractions._rollback_apply([10], 8, True)
                    mute.assert_not_called()
        self.assertEqual(distractions.muted_ids(), [10, 11])

    def test_malformed_generation_still_notifies(self):
        distractions.WATCHER_REQUEST.write_text('{"generation":"broken","want_armed":true}\n')
        self.ping = ""
        with mock.patch.object(distractions, "notify") as notify:
            self.assertFalse(distractions.apply_notification_block())
            notify.assert_called()
            self.assertIn("Could not mute", notify.call_args[0][1])
        request = distractions.read_watcher_request()
        self.assertGreaterEqual(request["generation"], 1)

    def test_next_generation_recovers_from_malformed_request(self):
        distractions.WATCHER_REQUEST.write_text('{"generation":"broken"}\n')
        self.assertEqual(distractions.next_generation(), 1)

    def test_muted_ids_rejects_corrupt_values(self):
        distractions.MUTED_PATH.write_text('["corrupt"]\n')
        with self.assertRaises(RuntimeError):
            distractions.muted_ids()

    def test_corrupt_mute_snapshot_fails_apply(self):
        distractions.MUTED_PATH.write_text('["corrupt"]\n')
        with mock.patch.object(distractions, "notify") as notify:
            self.assertFalse(distractions.apply_notification_block())
            notify.assert_called()
            self.assertIn("Could not mute", notify.call_args[0][1])
        self.assertEqual(distractions.muted_ids(), [])

    def test_persist_failure_does_not_ack_armed(self):
        with mock.patch.object(distractions, "save_muted_ids", side_effect=OSError("disk full")):
            armed, error = distractions.persist_then_ack_status(3, True, "", [4])
        self.assertFalse(armed)
        self.assertIn("disk full", error)
        self.assertFalse(distractions.read_watcher_status().get("armed"))

    def test_evaluate_sink_mute_failure_is_fatal(self):
        members = distractions.load_members()
        entry = {
            "index": 9,
            "properties": {
                "application.name": "Telegram Desktop",
                "application.process.binary": "telegram-desktop",
            },
        }
        with mock.patch.object(distractions, "list_sink_inputs", return_value=[entry]):
            with mock.patch.object(distractions, "pactl_mute", return_value=False):
                _seen, _muted, error = distractions.evaluate_sink_inputs(True, members, set(), [])
        self.assertIn("failed to mute", error)

    def test_change_event_reevaluates_initially_unmatched_stream(self):
        members = distractions.load_members()
        first = {"index": 7, "mute": False, "properties": {"application.name": "Unknown"}}
        changed = {
            "index": 7,
            "mute": False,
            "properties": {
                "application.name": "Telegram Desktop",
                "application.process.binary": "telegram-desktop",
            },
        }
        mute_calls: list[tuple[int, bool]] = []

        def record_mute(index, muted):
            mute_calls.append((index, muted))
            return True

        with mock.patch.object(distractions, "pactl_mute", record_mute):
            with mock.patch.object(distractions, "list_sink_inputs", return_value=[first]):
                seen, muted, error = distractions.evaluate_sink_inputs(True, members, set(), [])
            self.assertEqual(error, "")
            self.assertEqual(muted, [])
            with mock.patch.object(distractions, "list_sink_inputs", return_value=[changed]):
                seen, muted, error = distractions.evaluate_sink_inputs(True, members, seen, muted)
        self.assertEqual(error, "")
        self.assertEqual(muted, [7])
        self.assertIn((7, True), mute_calls)

    def test_premuted_matching_stream_is_not_owned(self):
        members = distractions.load_members()
        premuted = {
            "index": 9,
            "mute": True,
            "properties": {
                "application.name": "Telegram Desktop",
                "application.process.binary": "telegram-desktop",
            },
        }
        mute_calls: list[tuple[int, bool]] = []

        def record_mute(index, muted):
            mute_calls.append((index, muted))
            return True

        with mock.patch.object(distractions, "list_sink_inputs", return_value=[premuted]):
            with mock.patch.object(distractions, "pactl_mute", record_mute):
                _seen, muted, error = distractions.evaluate_sink_inputs(True, members, set(), [])
        self.assertEqual(error, "")
        self.assertEqual(muted, [])
        self.assertEqual(mute_calls, [])

    def test_apply_fail_rollback_unmutes_only_streams_this_spec_muted(self):
        members = distractions.load_members()
        premuted = {
            "index": 9,
            "mute": True,
            "properties": {
                "application.name": "Telegram Desktop",
                "application.process.binary": "telegram-desktop",
            },
        }
        fresh = {
            "index": 10,
            "mute": False,
            "properties": {
                "application.name": "Signal",
                "application.process.binary": "signal-desktop",
            },
        }
        mute_calls: list[tuple[int, bool]] = []

        def record_mute(index, muted):
            mute_calls.append((index, muted))
            return True

        with mock.patch.object(distractions, "list_sink_inputs", return_value=[premuted, fresh]):
            with mock.patch.object(distractions, "pactl_mute", record_mute):
                _seen, muted, error = distractions.evaluate_sink_inputs(True, members, set(), [])
                self.assertEqual(error, "")
                self.assertEqual(muted, [10])
                snapshot_muted: list[int] = []
                extras = [item for item in muted if item not in snapshot_muted]
                leftover = distractions.unmute_owned(extras)
        self.assertEqual(leftover, [])
        self.assertEqual(mute_calls, [(10, True), (10, False)])
        self.assertNotIn((9, True), mute_calls)
        self.assertNotIn((9, False), mute_calls)

    def test_sink_is_muted_reads_pulse_fields(self):
        self.assertTrue(distractions.sink_is_muted({"mute": True}))
        self.assertTrue(distractions.sink_is_muted({"muted": "yes"}))
        self.assertFalse(distractions.sink_is_muted({"mute": False}))
        self.assertFalse(distractions.sink_is_muted({"index": 1}))


class WatcherAckLivenessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runtime = root / "run"
        self.state = root / "state"
        self.runtime.mkdir()
        self.state.mkdir()
        self.patches = [
            mock.patch.object(distractions, "STATE_DIR", self.state),
            mock.patch.object(distractions, "FOCUS", self.state / "distractions.focus"),
            mock.patch.object(distractions, "MUTED_PATH", self.state / "distractions.muted.json"),
            mock.patch.object(distractions, "NOTIFY_LOCK", self.runtime / "notify.lock"),
            mock.patch.object(distractions, "WATCHER_REQUEST", self.runtime / "request.json"),
            mock.patch.object(distractions, "WATCHER_STATUS", self.runtime / "status.json"),
            mock.patch.object(distractions, "APPLY_WAIT_S", 0.35),
            mock.patch.object(distractions, "notify", lambda *args, **kwargs: None),
            mock.patch.object(distractions, "shell_ipc", self.fake_shell),
            mock.patch.object(distractions, "which_cmd", lambda _name: True),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        distractions.FOCUS.write_text("on\n")

    def tearDown(self):
        self.tmp.cleanup()

    def fake_shell(self, *args, timeout=4.0):
        if args[:2] == ("notifications", "dndState"):
            return 0, "off"
        if args[:2] == (distractions.PLUGIN_IPC, "ping"):
            return 0, "ready"
        if args[:2] == (distractions.PLUGIN_IPC, "arm"):
            return 0, "ok"
        if args[:2] == (distractions.PLUGIN_IPC, "disarm"):
            return 0, "drained"
        if args[:2] == (distractions.PLUGIN_IPC, "drainState"):
            return 0, "drained"
        return 1, "unknown"

    def test_stale_status_without_live_listener_is_rejected(self):
        distractions.write_watcher_status(
            {"pid": 1, "generation": 1, "armed": True, "last_error": "", "muted": []}
        )
        with mock.patch.object(distractions, "read_proc_starttime", return_value=None):
            ok, err = distractions.wait_watcher_ack(1, True)
        self.assertFalse(ok)
        self.assertIn("not running", err)

    def test_status_without_starttime_cannot_ack(self):
        distractions.write_watcher_status(
            {"pid": os.getpid(), "generation": 1, "armed": True, "last_error": "", "muted": []}
        )
        status = distractions.read_watcher_status()
        status.pop("starttime", None)
        distractions.WATCHER_STATUS.write_text(json.dumps(status) + "\n")
        with mock.patch.object(distractions, "read_proc_starttime", return_value="99"):
            ok, err = distractions.wait_watcher_ack(1, True)
        self.assertFalse(ok)
        self.assertIn("not running", err)

    def test_pid_reuse_with_mismatched_starttime_is_rejected(self):
        distractions.write_watcher_status(
            {
                "pid": 4242,
                "starttime": "111",
                "generation": 1,
                "armed": True,
                "last_error": "",
                "muted": [],
            }
        )
        with mock.patch.object(distractions, "read_proc_starttime", return_value="222"):
            ok, err = distractions.wait_watcher_ack(1, True)
        self.assertFalse(ok)
        self.assertIn("not running", err)

    def test_live_listener_ack_is_accepted(self):
        distractions.write_watcher_status(
            {
                "pid": os.getpid(),
                "starttime": "99",
                "generation": 4,
                "armed": True,
                "last_error": "",
                "muted": [],
            }
        )
        with mock.patch.object(distractions, "read_proc_starttime", return_value="99"):
            ok, err = distractions.wait_watcher_ack(4, True)
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_apply_rejects_malformed_request_plus_stale_status(self):
        distractions.WATCHER_REQUEST.write_text('{"generation":"broken","want_armed":true}\n')
        distractions.write_watcher_status(
            {"pid": 1, "generation": 1, "armed": True, "last_error": "", "muted": []}
        )
        with mock.patch.object(distractions, "read_proc_starttime", return_value=None):
            with mock.patch.object(distractions, "notify") as notify:
                self.assertFalse(distractions.apply_notification_block())
                notify.assert_called()
        self.assertFalse(distractions.watcher_acknowledged_armed())

    def test_lift_rejects_stale_disarmed_status(self):
        distractions.write_watcher_status(
            {"pid": 1, "generation": 1, "armed": False, "last_error": "", "muted": []}
        )
        with mock.patch.object(distractions, "read_proc_starttime", return_value=None):
            with mock.patch.object(distractions, "notify") as notify:
                self.assertFalse(distractions.lift_notification_block())
                notify.assert_called()


class QmlFilterContractTests(unittest.TestCase):
    def setUp(self):
        self.text = QML.read_text()

    def test_uses_exact_row_path(self):
        self.assertIn('shell.serviceFor("omarchy.notifications")', self.text)
        self.assertIn("Instantiator", self.text)
        self.assertIn("Qt.callLater", self.text)
        self.assertIn("isRestoredRow", self.text)
        self.assertIn("deletePopupFileFor", self.text)
        self.assertIn("liveRefs", self.text)
        self.assertIn("onObjectAdded", self.text)
        self.assertIn("scanExistingRows", self.text)
        self.assertIn("setArmed", self.text)
        self.assertIn("enqueueObserved", self.text)

    def test_never_uses_dnd_or_summary_dismiss(self):
        self.assertNotIn("toggleDnd", self.text)
        self.assertNotIn("setDnd", self.text)
        self.assertNotIn("dismiss(summary)", self.text)
        self.assertNotIn("dismissAll", self.text)
        self.assertNotIn("dismissOne", self.text)
        self.assertNotIn("writeSilenced", self.text)

    def test_leading_origin_and_generic_browser_guards_are_present(self):
        self.assertIn("leadingOriginHost", self.text)
        self.assertIn("isChromiumDerived", self.text)
        self.assertIn("isGenericBrowserIdentity", self.text)
        self.assertIn("omarchy-action", self.text)


if __name__ == "__main__":
    unittest.main()
