#!/usr/bin/env python3
"""Injected-command tests for named rules, ds block, and R10 banner."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HYPRCTL_SRC = r"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
root = Path(os.environ["HYPR_FAKE"])
(root / "hyprctl.log").open("a").write(json.dumps(sys.argv[1:]) + "\n")
fail = root / "fail_contains"
if fail.exists():
    needle = fail.read_text().strip()
    if needle and needle in " ".join(sys.argv[1:]):
        sys.exit(1)
if len(sys.argv) >= 3 and sys.argv[1] == "-j":
    print((root / f"{sys.argv[2]}.json").read_text())
    raise SystemExit(0)
if sys.argv[1:2] == ["keyword"]:
    (root / "keywords.log").open("a").write(sys.argv[2] + "\n")
    raise SystemExit(0)
if sys.argv[1:2] == ["dispatch"]:
    (root / "dispatch.log").open("a").write(" ".join(sys.argv[2:]) + "\n")
    raise SystemExit(0)
raise SystemExit(0)
"""

SUDO_SRC = r"""#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
if args[:1] == ["-n"]:
    args = args[1:]
os.execv(args[0], args)
"""

WRAPPER_SRC = r"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
log = Path(os.environ["DS_NFT_LOG"])
log.open("a").write(json.dumps({"argv": sys.argv[1:], "stdin": sys.stdin.read()}) + "\n")
"""

NFT_SRC = r"""#!/usr/bin/env python3
import os
from pathlib import Path
Path(os.environ["NFT_CALL_LOG"]).open("a").write("called\n")
raise SystemExit(77)
"""


def load_mod():
    loader = SourceFileLoader("distractions_enforce", str(ROOT / "distractions"))
    spec = spec_from_loader("distractions_enforce", loader)
    assert spec is not None
    mod = module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class EnforcementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.state = self.root / "state"
        self.runtime = self.root / "runtime"
        self.bin = self.root / "bin"
        self.hypr = self.root / "hypr"
        for path in (self.home, self.state, self.runtime, self.bin, self.hypr):
            path.mkdir()
        self.user = self.home / ".config/omarchy/app-list.json"
        self.user.parent.mkdir(parents=True)
        self.nft_log = self.root / "wrapper.log"
        self.nft_call_log = self.root / "nft-calls.log"
        self.wrapper = self.bin / "distractions-nft"
        self._write_bin("hyprctl", HYPRCTL_SRC)
        self._write_bin("sudo", SUDO_SRC)
        self._write_bin(self.wrapper.name, WRAPPER_SRC)
        self._write_bin("nft", NFT_SRC)
        self.write_hypr("activeworkspace", {"id": 1, "name": "1"})
        self.write_hypr("clients", [])
        self.write_hypr("workspaces", [])
        self.clock = [1000.0]
        env = {
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.state),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "PATH": f"{self.bin}:{os.environ.get('PATH', '')}",
            "HYPR_FAKE": str(self.hypr),
            "DS_NFT_LOG": str(self.nft_log),
            "NFT_CALL_LOG": str(self.nft_call_log),
        }
        for key, value in env.items():
            os.environ[key] = value
        self.mod = load_mod()
        self.notes: list[tuple] = []
        self.mod.notify = lambda *args, **kwargs: self.notes.append(args)
        self.mod.NFT_WRAPPER = str(self.wrapper)
        self.mod.now = lambda: self.clock[0]
        self.real_resolve_host = self.mod.resolve_host
        self.mod.resolve_host = lambda host, timeout=2.0: ["192.0.2.1"]
        self.addCleanup(self.mod.reset_runtime_state)

    def _write_bin(self, name: str, source: str) -> None:
        path = self.bin / name
        path.write_text(source)
        path.chmod(0o755)

    def write_hypr(self, name: str, data) -> None:
        (self.hypr / f"{name}.json").write_text(json.dumps(data))

    def write_list(self, rows: list[dict]) -> None:
        self.user.write_text(json.dumps(rows))

    def keywords(self) -> list[str]:
        path = self.hypr / "keywords.log"
        if not path.exists():
            return []
        return path.read_text().splitlines()

    def dispatches(self) -> list[str]:
        path = self.hypr / "dispatch.log"
        if not path.exists():
            return []
        return path.read_text().splitlines()

    def hypr_args(self) -> list[list]:
        path = self.hypr / "hyprctl.log"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def wrapper_calls(self) -> list[dict]:
        if not self.nft_log.exists():
            return []
        return [json.loads(line) for line in self.nft_log.read_text().splitlines() if line]

    def fail_on(self, needle: str) -> None:
        (self.hypr / "fail_contains").write_text(needle)

    def telegram_row(self) -> dict:
        return {"name": "Telegram"}

    def discord_row(self) -> dict:
        return {"name": "Discord"}

    def site_row(self) -> dict:
        return {"name": "ExampleSite", "hosts": ["blocked.example"]}

    def client(self, klass: str, workspace_name: str, address: str = "0xabc") -> dict:
        ident = 99 if workspace_name == "distraction" else 1
        return {
            "address": address,
            "class": klass,
            "workspace": {"id": ident, "name": workspace_name},
        }

    def wait_net(self) -> None:
        self.mod._net.wait_idle()

    def test_unanchored_regex_class_matches_and_literals_stay_exact(self):
        self.assertTrue(self.mod.class_matches("chrome-.*", "chrome-discord.com__-Default"))
        self.assertTrue(self.mod.class_matches(r"^chrome-discord\.com__.*$", "chrome-discord.com__-Default"))
        self.assertTrue(self.mod.class_matches("org.telegram.desktop", "org.telegram.desktop"))
        self.assertFalse(self.mod.class_matches("org.telegram.desktop", "orgXtelegramYdesktop"))
        self.write_list([{"name": "CustomChrome", "class": "chrome-.*"}])
        self.mod.bootstrap_enforcement()
        self.write_hypr("clients", [self.client("chrome-discord.com__-Default", "distraction")])
        self.notes.clear()
        self.mod.process_socket2_line("openwindow>>0xabc,99,chrome-discord.com__-Default,Chrome")
        self.assertTrue(self.notes)
        self.assertEqual(self.notes[0][0], self.mod.BANNER_TITLE)

    def test_named_rule_update_enable_disable(self):
        self.write_list([self.telegram_row(), self.discord_row()])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        keys = self.keywords()
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:match:class" in k for k in keys))
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:workspace name:distraction silent" in k for k in keys))
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:enable true" in k for k in keys))
        self.assertTrue(any("windowrule[omarchy-ds-discord]:enable true" in k for k in keys))
        (self.hypr / "keywords.log").write_text("")
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        keys = self.keywords()
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:enable true" in k for k in keys))
        self.assertTrue(any("windowrule[omarchy-ds-discord]:enable false" in k for k in keys))

    def test_remove_then_readd_enables_again(self):
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.write_list([])
        self.mod.bootstrap_enforcement()
        (self.hypr / "keywords.log").write_text("")
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        keys = self.keywords()
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:enable true" in k for k in keys))
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:match:class" in k for k in keys))

    def test_existing_client_moved_on_start(self):
        self.write_list([self.telegram_row()])
        self.write_hypr("clients", [self.client("org.telegram.desktop", "1")])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.assertTrue(
            any("movetoworkspacesilent name:distraction,address:0xabc" in line for line in self.dispatches())
        )
        self.assertFalse(self.notes)

    def test_apply_replace_and_lift_flush(self):
        self.write_list([self.site_row()])
        self.mod.resolve_host = lambda host, timeout=2.0: ["203.0.113.10", "2001:db8::10"]
        self.mod.bootstrap_enforcement()
        self.wait_net()
        first = self.wrapper_calls()
        self.assertEqual(first[-1]["argv"], ["replace", "ds"])
        self.assertIn("203.0.113.10", first[-1]["stdin"])
        self.assertIn("2001:db8::10", first[-1]["stdin"])
        self.write_hypr("activeworkspace", {"id": 99, "name": "distraction"})
        self.mod.process_socket2_line("workspacev2>>99,distraction")
        self.wait_net()
        self.assertEqual(self.wrapper_calls()[-1]["argv"], ["flush", "ds"])

    def test_corrupt_load_keeps_last_good_rules(self):
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        (self.hypr / "keywords.log").write_text("")
        self.user.write_text("{not-json")
        self.mod.bootstrap_enforcement()
        self.wait_net()
        keys = self.keywords()
        self.assertFalse(any("enable false" in k for k in keys))
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:enable true" in k for k in keys))
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:match:class" in k for k in keys))
        self.assertTrue(self.notes)

    def test_corrupt_without_last_good_expand_does_not_flush(self):
        self.user.write_text("{not-json")
        self.mod.save_addrs_last_good({"blocked.example": ["198.51.100.40"]})
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.assertFalse(any(call["argv"] == ["flush", "ds"] for call in self.wrapper_calls()))
        self.assertFalse(any(call["argv"] == ["replace", "ds"] for call in self.wrapper_calls()))

    def test_missing_wrapper_skips_network_only(self):
        self.mod.NFT_WRAPPER = str(self.root / "missing-wrapper")
        self.write_list([self.telegram_row(), self.site_row()])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:enable true" in k for k in self.keywords()))
        self.assertFalse(self.nft_log.exists())
        self.assertTrue(any("unavailable" in (note[1] if len(note) > 1 else "") for note in self.notes))

    def test_reload_changes_later_window_and_dns(self):
        self.write_list([self.telegram_row()])
        self.mod.resolve_host = lambda host, timeout=2.0: ["203.0.113.4"]
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.write_list([{"name": "CustomApp", "class": "app.custom", "hosts": ["custom.example"]}])
        left, right = socket.socketpair()
        thread = threading.Thread(target=self.mod.handle_reload_conn, args=(left,))
        thread.start()
        right.sendall(b"reload\n")
        self.assertTrue(right.recv(64).startswith(b"ok"))
        thread.join(timeout=2)
        right.close()
        self.write_hypr("clients", [self.client("app.custom", "distraction")])
        self.notes.clear()
        self.mod.process_socket2_line("openwindow>>0xabc,99,app.custom,Custom")
        self.assertTrue(self.notes)
        self.assertEqual(self.notes[0][0], self.mod.BANNER_TITLE)
        self.wait_net()
        last = self.wrapper_calls()[-1]
        self.assertEqual(last["argv"], ["replace", "ds"])
        self.assertIn("203.0.113.4", last["stdin"])

    def test_reload_network_failure_replies_error(self):
        self.wrapper.write_text("#!/bin/sh\nexit 1\n")
        self.wrapper.chmod(0o755)
        self.write_list([self.site_row()])
        left, right = socket.socketpair()
        thread = threading.Thread(target=self.mod.handle_reload_conn, args=(left,))
        thread.start()
        right.sendall(b"reload\n")
        self.assertTrue(right.recv(64).startswith(b"error"))
        thread.join(timeout=4)
        right.close()

    def test_reload_apply_failure_replies_error(self):
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.write_list([self.telegram_row(), self.discord_row()])
        self.fail_on("windowrule[omarchy-ds-discord]:match:class")
        left, right = socket.socketpair()
        thread = threading.Thread(target=self.mod.handle_reload_conn, args=(left,))
        thread.start()
        right.sendall(b"reload\n")
        self.assertTrue(right.recv(64).startswith(b"error"))
        thread.join(timeout=2)
        right.close()

    def test_socket2_unprefixed_address_matches_hyprctl_client(self):
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.write_hypr("clients", [self.client("org.telegram.desktop", "distraction", address="0x0abc")])
        self.notes.clear()
        self.mod.process_socket2_line("openwindow>>abc,99,org.telegram.desktop,Telegram")
        self.assertTrue(self.notes)
        self.assertEqual(self.notes[0][0], self.mod.BANNER_TITLE)

    def test_openwindow_banner_off_space_already_on_distraction(self):
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.write_hypr("clients", [self.client("org.telegram.desktop", "distraction")])
        (self.hypr / "dispatch.log").write_text("")
        self.notes.clear()
        self.mod.process_socket2_line("openwindow>>0xabc,99,org.telegram.desktop,Telegram")
        self.assertEqual(self.notes[0][0], self.mod.BANNER_TITLE)
        self.assertEqual(self.notes[0][1], "Telegram")
        self.assertFalse(self.dispatches())
        self.assertFalse(any("show" in d or "hl.dsp.focus" in d for d in self.dispatches()))

    def test_movewindow_silent_move_then_banner(self):
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.write_hypr("clients", [self.client("org.telegram.desktop", "1")])
        self.notes.clear()
        (self.hypr / "dispatch.log").write_text("")
        self.mod.process_socket2_line("movewindow>>0xabc,1")
        self.assertTrue(
            any("movetoworkspacesilent name:distraction,address:0xabc" in line for line in self.dispatches())
        )
        self.assertEqual(self.notes[0][0], self.mod.BANNER_TITLE)

    def test_banner_debounce_per_product(self):
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.write_hypr("clients", [self.client("org.telegram.desktop", "distraction")])
        self.notes.clear()
        self.mod.process_socket2_line("openwindow>>0xabc,99,org.telegram.desktop,Telegram")
        self.mod.process_socket2_line("openwindow>>0xabc,99,org.telegram.desktop,Telegram")
        self.assertEqual(len(self.notes), 1)
        self.clock[0] += 31
        self.mod.process_socket2_line("openwindow>>0xabc,99,org.telegram.desktop,Telegram")
        self.assertEqual(len(self.notes), 2)

    def test_start_scan_silent(self):
        self.write_list([self.telegram_row()])
        self.write_hypr("clients", [self.client("org.telegram.desktop", "1")])
        self.mod.bootstrap_enforcement()
        self.assertFalse(self.notes)
        self.assertTrue(self.dispatches())

    def test_restart_after_remove_while_dead(self):
        self.write_list([self.telegram_row()])
        last_good = {
            "omarchy-ds-telegram": {
                "class": "org.telegram.desktop",
                "workspace": "name:distraction silent",
                "enabled": True,
            },
            "omarchy-ds-discord": {
                "class": r"^chrome-discord\.com__.*$",
                "workspace": "name:distraction silent",
                "enabled": True,
            },
        }
        self.mod.save_rule_registry(self.mod.rules_last_good_path(), last_good)
        self.mod.bootstrap_enforcement()
        keys = self.keywords()
        self.assertTrue(any("windowrule[omarchy-ds-discord]:enable false" in k for k in keys))
        listed = [" ".join(args) for args in self.hypr_args()]
        self.assertFalse(any("windowrule" in line and "-j" in line for line in listed))
        self.assertFalse(any(args[:1] == ["clients"] and "rules" in args for args in self.hypr_args()))

    def test_restart_after_valid_empty_list(self):
        last_good = {
            "omarchy-ds-telegram": {
                "class": "org.telegram.desktop",
                "workspace": "name:distraction silent",
                "enabled": True,
            }
        }
        self.mod.save_rule_registry(self.mod.rules_last_good_path(), last_good)
        self.mod.save_last_good_expand([{"name": "Telegram", "class": "org.telegram.desktop", "hosts": []}])
        self.write_list([])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:enable false" in k for k in self.keywords()))
        self.assertEqual(self.wrapper_calls()[-1]["argv"], ["flush", "ds"])

    def test_restart_from_pending_without_rule_enumeration(self):
        last_good = {
            "omarchy-ds-telegram": {
                "class": "org.telegram.desktop",
                "workspace": "name:distraction silent",
                "enabled": True,
            }
        }
        pending = {
            **last_good,
            "omarchy-ds-orphan": {
                "class": "orphan.app",
                "workspace": "name:distraction silent",
                "enabled": True,
            },
        }
        self.mod.save_rule_registry(self.mod.rules_last_good_path(), last_good)
        self.mod.save_rule_registry(self.mod.rules_pending_path(), pending)
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        keys = self.keywords()
        self.assertTrue(any("windowrule[omarchy-ds-orphan]:enable false" in k for k in keys))
        self.assertFalse(any("enumerat" in " ".join(args).lower() for args in self.hypr_args()))
        self.assertFalse(any(args[:1] == ["windowrules"] for args in self.hypr_args()))

    def test_notify_absorbs_missing_and_nonzero(self):
        original = subprocess.check_call
        fresh = load_mod()

        def boom(cmd, *args, **kwargs):
            if cmd[0] == "omarchy-notification-send":
                raise FileNotFoundError("omarchy-notification-send")
            raise subprocess.CalledProcessError(1, cmd)

        def always_fail(cmd, *args, **kwargs):
            raise subprocess.CalledProcessError(2, cmd)

        try:
            subprocess.check_call = boom
            fresh.notify("title", "body")
            subprocess.check_call = always_fail
            fresh.notify("title", "body")
        finally:
            subprocess.check_call = original
            fresh.reset_runtime_state()

    def test_stalled_dns_does_not_block_socket2(self):
        self.write_list([self.telegram_row(), self.site_row()])
        gate = threading.Event()
        started = threading.Event()

        def stall(host, timeout=2.0):
            started.set()
            gate.wait(timeout=2)
            return ["203.0.113.9"]

        self.mod.resolve_host = stall
        self.mod.bootstrap_enforcement()
        self.assertTrue(started.wait(timeout=1))
        self.write_hypr("clients", [self.client("org.telegram.desktop", "distraction")])
        self.notes.clear()
        self.mod.process_socket2_line("openwindow>>0xabc,99,org.telegram.desktop,Telegram")
        self.assertTrue(self.notes)
        gate.set()
        self.wait_net()

    def test_stale_dns_generation_discarded_after_flush(self):
        self.write_list([self.site_row()])
        gate = threading.Event()
        started = threading.Event()

        def stall(host, timeout=2.0):
            started.set()
            gate.wait(timeout=2)
            return ["203.0.113.8"]

        self.mod.resolve_host = stall
        self.mod.bootstrap_enforcement()
        self.assertTrue(started.wait(timeout=1))
        self.write_hypr("activeworkspace", {"id": 99, "name": "distraction"})
        self.mod.process_socket2_line("workspacev2>>99,distraction")
        gate.set()
        self.wait_net()
        calls = self.wrapper_calls()
        self.assertTrue(calls)
        self.assertEqual(calls[-1]["argv"], ["flush", "ds"])
        self.assertFalse(any(call["argv"] == ["replace", "ds"] and "203.0.113.8" in call["stdin"] for call in calls))

    def test_generation_bump_during_resolve_skips_replace(self):
        self.write_list([self.site_row()])
        gate = threading.Event()
        started = threading.Event()

        def stall(host, timeout=2.0):
            started.set()
            gate.wait(timeout=2)
            return ["203.0.113.77"]

        self.mod.resolve_host = stall
        self.mod.bootstrap_enforcement()
        self.assertTrue(started.wait(timeout=1))
        self.mod._net.bump()
        gate.set()
        self.wait_net()
        self.assertFalse(
            any(call["argv"] == ["replace", "ds"] and "203.0.113.77" in call["stdin"] for call in self.wrapper_calls())
        )

    def test_overlapping_periodic_tick_skipped(self):
        self.write_list([self.site_row()])
        gate = threading.Event()
        started = threading.Event()

        def stall(host, timeout=2.0):
            started.set()
            gate.wait(timeout=2)
            return ["203.0.113.7"]

        self.mod.resolve_host = stall
        self.mod.bootstrap_enforcement()
        self.assertTrue(started.wait(timeout=1))
        self.assertFalse(self.mod.maybe_dns_tick())
        self.assertGreaterEqual(self.mod._net.skipped_periodic, 1)
        gate.set()
        self.wait_net()

    def test_dns_failure_keeps_persisted_last_good(self):
        self.write_list([self.site_row()])
        self.mod.resolve_host = lambda host, timeout=2.0: ["198.51.100.20"]
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.mod.reset_runtime_state()
        self.mod.NFT_WRAPPER = str(self.wrapper)
        self.mod.notify = lambda *args, **kwargs: self.notes.append(args)
        self.mod.resolve_host = lambda host, timeout=2.0: (_ for _ in ()).throw(TimeoutError("dns"))
        self.nft_log.write_text("")
        self.mod.bootstrap_enforcement()
        self.wait_net()
        last = self.wrapper_calls()[-1]
        self.assertEqual(last["argv"], ["replace", "ds"])
        self.assertIn("198.51.100.20", last["stdin"])

    def test_helper_never_invokes_nft(self):
        self.write_list([self.telegram_row(), self.site_row()])
        self.mod.resolve_host = lambda host, timeout=2.0: ["198.51.100.2"]
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.assertFalse(self.nft_call_log.exists() and self.nft_call_log.read_text().strip())
        self.assertTrue(self.wrapper_calls())

    def test_unlisted_window_not_assigned(self):
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.write_hypr("clients", [self.client("firefox", "1")])
        (self.hypr / "dispatch.log").write_text("")
        self.notes.clear()
        self.mod.process_socket2_line("openwindow>>0xabc,1,firefox,Firefox")
        self.assertFalse(self.dispatches())
        self.assertFalse(self.notes)

    def test_resolve_host_timeout_does_not_wait_for_lookup(self):
        hung = threading.Event()

        def hang(*args, **kwargs):
            hung.wait()
            return []

        original = self.mod.lookup_addresses
        self.mod.lookup_addresses = hang
        try:
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                self.real_resolve_host("blocked.example", timeout=0.2)
            self.assertLess(time.monotonic() - start, 1.0)
        finally:
            hung.set()
            self.mod.lookup_addresses = original

    def test_startup_apply_failure_keeps_last_good_runtime(self):
        self.mod.save_last_good_expand(
            [{"name": "Telegram", "class": "org.telegram.desktop", "hosts": ["web.telegram.org"]}]
        )
        self.mod.save_rule_registry(
            self.mod.rules_last_good_path(),
            {
                "omarchy-ds-telegram": {
                    "class": "org.telegram.desktop",
                    "workspace": "name:distraction silent",
                    "enabled": True,
                }
            },
        )
        self.write_list([self.telegram_row()])
        self.fail_on("windowrule[omarchy-ds-telegram]:match:class")
        self.write_hypr("clients", [self.client("org.telegram.desktop", "1")])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.assertEqual(self.mod._active_expand[0]["name"], "Telegram")
        self.assertTrue(
            any("movetoworkspacesilent name:distraction,address:0xabc" in line for line in self.dispatches())
        )
        calls = self.wrapper_calls()
        self.assertTrue(any(call["argv"] == ["replace", "ds"] for call in calls))
        self.assertFalse(any(call["argv"] == ["flush", "ds"] for call in calls))

    def test_apply_failure_keeps_pending_orphans(self):
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        pending = {
            "omarchy-ds-telegram": {
                "class": "org.telegram.desktop",
                "workspace": "name:distraction silent",
                "enabled": True,
            },
            "omarchy-ds-orphan": {
                "class": "orphan.app",
                "workspace": "name:distraction silent",
                "enabled": True,
            },
        }
        self.mod.save_rule_registry(self.mod.rules_pending_path(), pending)
        self.write_list([self.telegram_row(), self.discord_row()])
        self.fail_on("windowrule[omarchy-ds-discord]:match:class")
        self.mod.bootstrap_enforcement()
        kept = self.mod.load_rule_registry(self.mod.rules_pending_path())
        self.assertIn("omarchy-ds-orphan", kept)

    def test_first_banner_soon_after_boot_is_not_suppressed(self):
        self.clock[0] = 5.0
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.write_hypr("clients", [self.client("org.telegram.desktop", "distraction")])
        self.notes.clear()
        self.mod.process_socket2_line("openwindow>>0xabc,99,org.telegram.desktop,Telegram")
        self.assertTrue(self.notes)
        self.assertEqual(self.notes[0][0], self.mod.BANNER_TITLE)

    def test_reload_bumps_generation_before_apply(self):
        self.write_list([self.site_row()])
        gate = threading.Event()
        started = threading.Event()

        def stall(host, timeout=2.0):
            started.set()
            gate.wait(timeout=2)
            return ["203.0.113.66"]

        self.mod.resolve_host = stall
        self.mod.bootstrap_enforcement()
        self.assertTrue(started.wait(timeout=1))
        self.write_list([{"name": "OtherSite", "hosts": ["other.example"]}])
        self.mod.resolve_host = lambda host, timeout=2.0: ["198.51.100.66"]
        left, right = socket.socketpair()
        thread = threading.Thread(target=self.mod.handle_reload_conn, args=(left,))
        thread.start()
        right.sendall(b"reload\n")
        self.assertTrue(right.recv(64).startswith(b"ok"))
        thread.join(timeout=8)
        right.close()
        gate.set()
        self.wait_net()
        self.assertFalse(
            any("203.0.113.66" in call.get("stdin", "") for call in self.wrapper_calls())
        )

    def test_create_failure_rolls_back_batch(self):
        self.write_list([self.telegram_row()])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.write_list([self.telegram_row(), self.discord_row()])
        self.fail_on("windowrule[omarchy-ds-discord]:match:class")
        (self.hypr / "keywords.log").write_text("")
        self.mod.bootstrap_enforcement()
        keys = self.keywords()
        self.assertTrue(any("windowrule[omarchy-ds-discord]:enable false" in k for k in keys))
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:match:class" in k for k in keys))
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:enable true" in k for k in keys))
        self.assertFalse(any("windowrule[omarchy-ds-telegram]:enable false" in k for k in keys))
        self.assertTrue(self.notes)

    def test_openwindow_on_space_does_not_notify(self):
        self.write_list([self.telegram_row()])
        self.write_hypr("activeworkspace", {"id": 99, "name": "distraction"})
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.write_hypr("clients", [self.client("org.telegram.desktop", "distraction")])
        self.notes.clear()
        self.mod.process_socket2_line("openwindow>>0xabc,99,org.telegram.desktop,Telegram")
        self.assertFalse(self.notes)

    def test_disable_failure_keeps_desired_and_leftovers(self):
        self.write_list([self.telegram_row(), self.discord_row()])
        self.mod.bootstrap_enforcement()
        self.wait_net()
        self.write_list([self.telegram_row()])
        self.fail_on("windowrule[omarchy-ds-discord]:enable false")
        (self.hypr / "keywords.log").write_text("")
        self.mod.bootstrap_enforcement()
        self.wait_net()
        keys = self.keywords()
        self.assertTrue(any("windowrule[omarchy-ds-telegram]:enable true" in k for k in keys))
        last = self.mod.load_rule_registry(self.mod.rules_last_good_path())
        self.assertIn("omarchy-ds-telegram", last)
        self.assertIn("omarchy-ds-discord", last)
        self.assertTrue(self.notes)

    def test_windows_lua_dropped_membership_lines(self):
        text = (ROOT / "hypr/windows.lua").read_text()
        self.assertIn("hl.workspace_rule", text)
        self.assertNotIn("o.window", text)


if __name__ == "__main__":
    unittest.main()
