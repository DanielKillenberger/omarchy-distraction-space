#!/usr/bin/env python3
from __future__ import annotations

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
        self.assertIsNone(distractions.match_stream(props, ["chrome --type=renderer"]))
        self.assertIsNone(
            distractions.match_stream(props, ["chrome --app=https://fox.com/news"])
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
