#!/usr/bin/env python3
"""Unit tests for the focus-mode network block (no root, no live nft)."""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
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
        self.kind = "resolved"
        self.writes: list[str] = []
        self.nft_applies: list[str] = []
        self.deleted = 0
        self.flushed: list[str] = []
        self.sinkholes: list[list[str]] = []
        self.stopped = 0
        self.reloads = 0
        self.resolved: str | None = None
        self.resolv = "nameserver 1.1.1.1\n"
        self.resolv_backup: str | None = None
        self.upstreams: list[str] = []
        self.verified: list[str] = []
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

    def resolve(self, host: str, upstreams: list[str] | None = None) -> tuple[list[str], list[str]]:
        return self.resolutions.get(host, ([], []))

    def flush_conntrack(self, addresses: list[str]) -> None:
        self.flushed.extend(addresses)

    def dns_targets(self) -> list[Path]:
        return []

    def resolver_kind(self) -> str:
        return self.kind

    def sinkhole_port(self, kind: str) -> int:
        return 53 if kind == "resolv" else focus_block.SINKHOLE_PORT

    def read_resolved(self) -> str | None:
        return self.resolved

    def write_resolved(self, text: str | None) -> None:
        if self.fail_on == "write_resolved":
            raise RuntimeError("resolved write failed")
        self.resolved = text

    def read_resolv(self) -> str:
        return self.resolv

    def write_resolv(self, text: str) -> None:
        if self.fail_on == "write_resolv":
            raise RuntimeError("resolv write failed")
        self.resolv = text

    def backup_resolv(self) -> str | None:
        current = self.resolv
        if self.resolv_backup is None:
            self.resolv_backup = current
        return current

    def restore_resolv(self) -> None:
        if self.resolv_backup is None:
            return
        self.resolv = self.resolv_backup
        self.resolv_backup = None

    def capture_upstreams(self) -> list[str]:
        return ["1.1.1.1"]

    def write_upstreams(self, servers: list[str]) -> None:
        self.upstreams = list(servers)

    def clear_runtime_files(self) -> None:
        self.upstreams = []

    def reload_resolver(self, kind: str) -> None:
        if self.fail_on == "reload_dns":
            raise RuntimeError("reload failed")
        self.reloads += 1

    def read_suffixes(self) -> list[str] | None:
        return self.sinkholes[-1] if self.sinkholes else None

    def nft_list(self) -> str | None:
        if self.fail_on == "nft_list":
            raise focus_block.BlockError("sudo: a password is required")
        return self.nft

    def start_sinkhole(self, suffixes: list[str], port: int = focus_block.SINKHOLE_PORT, upstreams: list[str] | None = None) -> None:
        if self.fail_on == "start_sinkhole":
            raise RuntimeError("sinkhole start failed")
        if upstreams is not None:
            self.upstreams = list(upstreams)
        if self.sinkholes:
            self.stopped += 1
        self.sinkholes.append(list(suffixes))
        self.sinkhole_port_used = port

    def stop_sinkhole(self) -> None:
        self.stopped += 1

    def verify_suffix_block(self, suffixes: list[str], port: int, kind: str) -> None:
        if self.fail_on == "verify":
            raise RuntimeError("suffix verify failed")
        self.verified.append(suffixes[0] if suffixes else "")


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
            names_with_telegram = focus_block.active_names(
                config={"destinations": ["YouTube", "Telegram", "example.com"]},
                defaults_path=missing,
            )
            self.assertIn("Telegram", names_with_telegram)
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
        self.assertIn("2001:db8::10", rules)
        self.assertIn("ip daddr @v4 drop", rules)
        self.assertIn("ip6 daddr @v6 drop", rules)
        self.assertNotIn("dnat", rules)
        self.assertNotIn("dnsnat", rules)

    def test_youtube_hostnames_from_catalog(self):
        defaults = focus_block.load_defaults()
        hosts = focus_block.hostnames_for("YouTube", defaults)
        self.assertIn("youtube.com", hosts)
        self.assertIn("www.youtube.com", hosts)
        self.assertIn("youtu.be", hosts)
        self.assertTrue(focus_block.suffix_matches("r4---sn-abc.googlevideo.com", "googlevideo.com"))
        fragment = focus_block.dns_fragment(hosts)
        self.assertIn("address=/googlevideo.com/0.0.0.0", fragment)
        self.assertIn("address=/youtube.com/0.0.0.0", fragment)
        self.assertNotIn("address=/www.youtube.com/", fragment)
        resolved = focus_block.resolved_fragment(["youtube.com", "googlevideo.com"])
        self.assertIn("Domains=~youtube.com ~googlevideo.com", resolved)
        self.assertIn("DNS=127.0.0.1:53553 [::1]:53553", resolved)
        self.assertEqual(focus_block.sinkhole_probe_name("googlevideo.com"), "r4---sn-abc.googlevideo.com")

    def test_missing_table_error_is_classified_before_later_attempts(self):
        self.assertTrue(focus_block._missing_table_text("Error: No such file or directory"))
        self.assertTrue(focus_block._missing_table_text("table inet omarchy_focus does not exist"))
        self.assertFalse(focus_block._missing_table_text("sudo: a password is required"))


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
        self.assertIn("::1 youtube.com", backend.hosts)
        self.assertTrue(backend.nft_applies)
        self.assertIn("203.0.113.10", backend.nft_applies[-1])
        self.assertIn("2001:db8::10", backend.nft_applies[-1])
        self.assertNotIn("dnat", backend.nft_applies[-1])
        self.assertTrue(backend.sinkholes)
        self.assertIn("youtube.com", backend.sinkholes[-1])
        self.assertIn("googlevideo.com", backend.sinkholes[-1])
        self.assertIsNotNone(backend.resolved)
        self.assertIn("Domains=~", backend.resolved or "")
        self.assertIn("~googlevideo.com", backend.resolved or "")
        self.assertEqual(backend.reloads, 1)
        self.assertTrue(backend.verified)
        self.assertIn(backend.verified[0], backend.sinkholes[-1])
        self.assertEqual(backend.upstreams, ["1.1.1.1"])

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

    def test_unexpanded_active_name_does_not_replace_state(self):
        previous = "127.0.0.1 localhost\n"
        backend = FakeBackend(hosts=previous, nft="table inet omarchy_focus { old }")
        with tempfile.TemporaryDirectory() as tmp:
            defaults_path = Path(tmp) / "destinations.json"
            defaults_path.write_text(
                json.dumps({"default": [], "catalog": {"EmptyApp": []}}),
                encoding="utf-8",
            )
            with self.assertRaises(focus_block.BlockError):
                focus_block.apply_block(
                    backend=backend,
                    config={"destinations": ["EmptyApp"]},
                    defaults_path=defaults_path,
                    notify=False,
                )
        self.assertEqual(backend.hosts, previous)
        self.assertEqual(backend.nft, "table inet omarchy_focus { old }")
        self.assertFalse(backend.writes)

    def test_missing_defaults_still_expand_permanent_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            warnings: list[str] = []
            hosts = focus_block.active_hostnames(
                config={},
                defaults_path=missing,
                warnings=warnings,
            )
            self.assertIn("telegram.org", hosts)
            self.assertNotIn("youtube.com", hosts)

    def test_sinkhole_start_failure_leaves_previous_state(self):
        previous = "127.0.0.1 localhost\n"
        backend = FakeBackend(hosts=previous, fail_on="start_sinkhole")
        with self.assertRaises(focus_block.BlockError):
            focus_block.apply_block(
                backend=backend,
                config={"destinations": ["YouTube"]},
                notify=False,
            )
        self.assertEqual(backend.hosts, previous)
        self.assertFalse(backend.writes)

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
        backend.resolved = focus_block.resolved_fragment(["youtube.com"])
        backend.upstreams = ["1.1.1.1"]
        focus_block.lift_block(backend=backend, notify=False)
        self.assertNotIn("youtube.com", backend.hosts)
        self.assertIsNone(backend.nft)
        self.assertIsNone(backend.resolved)
        self.assertEqual(backend.stopped, 1)
        self.assertEqual(backend.upstreams, [])

    def test_empty_active_list_does_not_install_empty_block(self):
        previous = "127.0.0.1 localhost\n"
        previous_nft = "table inet omarchy_focus { old }"
        backend = FakeBackend(hosts=previous, nft=previous_nft)
        with self.assertRaises(focus_block.BlockError):
            focus_block.apply_block(
                backend=backend,
                config={"destinations": []},
                notify=False,
            )
        self.assertEqual(backend.hosts, previous)
        self.assertEqual(backend.nft, previous_nft)
        self.assertFalse(backend.writes)
        self.assertFalse(backend.sinkholes)

    def test_missing_defaults_youtube_only_does_not_install_empty_block(self):
        previous = "127.0.0.1 localhost\n"
        backend = FakeBackend(hosts=previous, nft="table inet omarchy_focus { old }")
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            with self.assertRaises(focus_block.BlockError):
                focus_block.apply_block(
                    backend=backend,
                    config={"destinations": ["YouTube"]},
                    defaults_path=missing,
                    notify=False,
                )
        self.assertEqual(backend.hosts, previous)
        self.assertFalse(backend.writes)
        self.assertFalse(backend.sinkholes)

    def test_resolver_reload_failure_restores_previous_state(self):
        previous = "127.0.0.1 localhost\n"
        previous_nft = "table inet omarchy_focus { old }"
        backend = FakeBackend(hosts=previous, nft=previous_nft, fail_on="reload_dns")
        with self.assertRaises(focus_block.BlockError):
            focus_block.apply_block(
                backend=backend,
                config={"destinations": ["YouTube"]},
                notify=False,
            )
        self.assertEqual(backend.hosts, previous)
        self.assertEqual(backend.nft, previous_nft)

    def test_suffix_verify_failure_restores_previous_state(self):
        previous = "127.0.0.1 localhost\n"
        previous_nft = "table inet omarchy_focus { old }"
        backend = FakeBackend(hosts=previous, nft=previous_nft, fail_on="verify")
        with self.assertRaises(focus_block.BlockError):
            focus_block.apply_block(
                backend=backend,
                config={"destinations": ["YouTube"]},
                notify=False,
            )
        self.assertEqual(backend.hosts, previous)
        self.assertEqual(backend.nft, previous_nft)

    def test_dnsmasq_path_reloads_or_fails(self):
        previous = "127.0.0.1 localhost\n"
        dropin = Path("/tmp/omarchy-focus-test-dnsmasq.conf")
        backend = FakeBackend(hosts=previous)
        backend.kind = "dnsmasq"
        backend.dns_files = {}

        def targets() -> list[Path]:
            return [dropin]

        def read_dns(path: Path) -> str | None:
            return backend.dns_files.get(str(path))

        def write_dns(path: Path, text: str | None) -> None:
            if text is None:
                backend.dns_files.pop(str(path), None)
                return
            backend.dns_files[str(path)] = text

        backend.dns_targets = targets  # type: ignore[method-assign]
        backend.read_dns = read_dns  # type: ignore[method-assign]
        backend.write_dns = write_dns  # type: ignore[method-assign]
        focus_block.apply_block(
            backend=backend,
            config={"destinations": ["YouTube"]},
            notify=False,
        )
        self.assertIn("address=/googlevideo.com/0.0.0.0", backend.dns_files[str(dropin)])
        self.assertIn("address=/googlevideo.com/::", backend.dns_files[str(dropin)])
        self.assertEqual(backend.reloads, 1)
        self.assertFalse(backend.sinkholes)

    def test_sinkhole_and_loopback_addrs_are_not_installed(self):
        previous_nft = (
            "table inet omarchy_focus {\n"
            "  set v4 { elements = { 203.0.113.10 } }\n"
            "  set v6 { elements = { 2001:db8::10 } }\n"
            "}"
        )
        backend = FakeBackend(nft=previous_nft)
        backend.resolutions = {
            "youtube.com": (["0.0.0.0"], ["::1"]),
            "www.youtube.com": (["127.0.0.1"], []),
        }
        focus_block.apply_block(
            backend=backend,
            config={"destinations": ["YouTube"]},
            notify=False,
        )
        installed = backend.nft_applies[-1]
        v4, v6 = focus_block.parse_nft_sets(installed)
        self.assertEqual(v4, [])
        self.assertEqual(v6, [])

    def test_reapply_does_not_keep_removed_destination_addrs(self):
        previous_nft = (
            "table inet omarchy_focus {\n"
            "  set v4 { elements = { 198.51.100.1, 203.0.113.10 } }\n"
            "  set v6 { elements = { 2001:db8::99 } }\n"
            "}"
        )
        backend = FakeBackend(nft=previous_nft)
        focus_block.apply_block(
            backend=backend,
            config={"destinations": ["YouTube"]},
            notify=False,
        )
        v4, v6 = focus_block.parse_nft_sets(backend.nft_applies[-1])
        self.assertEqual(v4, ["203.0.113.10"])
        self.assertEqual(v6, ["2001:db8::10"])
        self.assertNotIn("198.51.100.1", v4)
        self.assertNotIn("2001:db8::99", v6)

    def test_dnsmasq_verify_failure_reloads_restored_dropin(self):
        dropin = Path("/tmp/omarchy-focus-test-dnsmasq-rollback.conf")
        previous = "127.0.0.1 localhost\n"
        backend = FakeBackend(hosts=previous, nft="table inet omarchy_focus { old }", fail_on="verify")
        backend.kind = "dnsmasq"
        backend.dns_files = {str(dropin): "address=/old.example/0.0.0.0\n"}

        def targets() -> list[Path]:
            return [dropin]

        def read_dns(path: Path) -> str | None:
            return backend.dns_files.get(str(path))

        def write_dns(path: Path, text: str | None) -> None:
            if text is None:
                backend.dns_files.pop(str(path), None)
                return
            backend.dns_files[str(path)] = text

        backend.dns_targets = targets  # type: ignore[method-assign]
        backend.read_dns = read_dns  # type: ignore[method-assign]
        backend.write_dns = write_dns  # type: ignore[method-assign]
        with self.assertRaises(focus_block.BlockError):
            focus_block.apply_block(
                backend=backend,
                config={"destinations": ["YouTube"]},
                notify=False,
            )
        self.assertEqual(backend.dns_files[str(dropin)], "address=/old.example/0.0.0.0\n")
        self.assertGreaterEqual(backend.reloads, 2)
        self.assertEqual(backend.hosts, previous)

    def test_resolv_path_without_upstreams_fails(self):
        previous = "127.0.0.1 localhost\n"
        backend = FakeBackend(hosts=previous)
        backend.kind = "resolv"
        backend.capture_upstreams = lambda: []  # type: ignore[method-assign]
        with self.assertRaises(focus_block.BlockError):
            focus_block.apply_block(
                backend=backend,
                config={"destinations": ["YouTube"]},
                notify=False,
            )
        self.assertEqual(backend.hosts, previous)
        self.assertFalse(backend.writes)

    def test_nft_list_failure_is_reported_as_apply_failure(self):
        previous = "127.0.0.1 localhost\n"
        backend = FakeBackend(hosts=previous, nft="table inet omarchy_focus { old }", fail_on="nft_list")
        with self.assertRaises(focus_block.BlockError) as raised:
            focus_block.apply_block(
                backend=backend,
                config={"destinations": ["YouTube"]},
                notify=False,
            )
        self.assertIn("Could not apply", str(raised.exception))
        self.assertEqual(backend.hosts, previous)
        self.assertFalse(backend.writes)

    def test_resolv_reapply_failure_keeps_previous_resolv(self):
        previous = "127.0.0.1 localhost\n"
        backend = FakeBackend(hosts=previous, fail_on="verify")
        backend.kind = "resolv"
        backend.resolv = "nameserver 127.0.0.1\n"
        backend.resolv_backup = "nameserver 9.9.9.9\n"
        with self.assertRaises(focus_block.BlockError):
            focus_block.apply_block(
                backend=backend,
                config={"destinations": ["YouTube"]},
                notify=False,
            )
        self.assertEqual(backend.resolv, "nameserver 127.0.0.1\n")
        self.assertEqual(backend.resolv_backup, "nameserver 9.9.9.9\n")

    def test_nft_delete_failure_is_not_success(self):
        hosts = focus_block.splice_hosts(
            "127.0.0.1 localhost\n",
            focus_block.hosts_fragment(["youtube.com"]),
        )
        backend = FakeBackend(hosts=hosts, nft="table inet omarchy_focus { }", fail_on="nft_delete")
        with self.assertRaises(focus_block.BlockError) as raised:
            focus_block.lift_block(backend=backend, notify=False)
        self.assertIn("Could not lift", str(raised.exception))
        self.assertIsNotNone(backend.nft)


class DnsSinkholeTests(unittest.TestCase):
    def test_sinkhole_answers_blocked_suffix(self):
        import focus_dns

        qname = b"\x03www\x07youtube\x03com\x00"
        query = b"\x00\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + qname + b"\x00\x01\x00\x01"
        parsed = focus_dns.parse_qname(query)
        self.assertIsNotNone(parsed)
        qname_text, end = parsed
        self.assertEqual(qname_text, "www.youtube.com")
        self.assertTrue(focus_dns.blocked_qname(qname_text, ["youtube.com"]))
        reply = focus_dns.sinkhole_response(query, focus_dns.query_type(query, end), end)
        self.assertTrue(reply.endswith(b"\x00\x00\x00\x00"))
        self.assertEqual(int.from_bytes(reply[4:6], "big"), 1)
        self.assertEqual(int.from_bytes(reply[6:8], "big"), 1)
        self.assertEqual(int.from_bytes(reply[10:12], "big"), 0)
        aaaa_query = b"\x00\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + qname + b"\x00\x1c\x00\x01"
        aaaa_parsed = focus_dns.parse_qname(aaaa_query)
        self.assertIsNotNone(aaaa_parsed)
        _name, aaaa_end = aaaa_parsed
        aaaa = focus_dns.sinkhole_response(aaaa_query, focus_dns.query_type(aaaa_query, aaaa_end))
        self.assertTrue(aaaa.endswith(bytes(16)))
        self.assertTrue(focus_dns.blocked_qname("r4---sn-abc.googlevideo.com", ["googlevideo.com"]))
        with tempfile.TemporaryDirectory() as tmp:
            upstreams = Path(tmp) / "upstreams"
            upstreams.write_text("9.9.9.9\n127.0.0.53\n", encoding="utf-8")
            self.assertEqual(focus_dns.load_upstreams(upstreams), ["9.9.9.9"])

    def test_edns_query_does_not_copy_opt_into_answer(self):
        import focus_dns

        qname = b"\x03www\x07youtube\x03com\x00"
        opt = b"\x00\x00\x29\x10\x00\x00\x00\x00\x00\x00\x00"
        query = b"\x00\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x01" + qname + b"\x00\x01\x00\x01" + opt
        parsed = focus_dns.parse_qname(query)
        self.assertIsNotNone(parsed)
        _name, end = parsed
        reply = focus_dns.sinkhole_response(query, 1, end)
        self.assertTrue(reply.endswith(b"\x00\x00\x00\x00"))
        self.assertNotIn(b"\x00\x29", reply)
        self.assertEqual(int.from_bytes(reply[6:8], "big"), 1)
        self.assertEqual(int.from_bytes(reply[10:12], "big"), 0)
        self.assertEqual(len(reply), end + 16)

    def test_live_sinkhole_answers_service_subdomain(self):
        import focus_dns

        with tempfile.TemporaryDirectory() as tmp:
            suffix_path = Path(tmp) / "suffixes"
            suffix_path.write_text("googlevideo.com\n", encoding="utf-8")
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            thread = threading.Thread(
                target=focus_dns.serve,
                args=("127.0.0.1", port, suffix_path, Path(tmp) / "upstreams"),
                daemon=True,
            )
            thread.start()
            query = focus_block.dns_query_packet("r4---sn-abc.googlevideo.com", 1)
            reply = None
            deadline = time.time() + 2
            while time.time() < deadline:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    sock.settimeout(0.2)
                    sock.sendto(query, ("127.0.0.1", port))
                    reply, _addr = sock.recvfrom(512)
                    break
                except OSError:
                    time.sleep(0.05)
                finally:
                    sock.close()
            self.assertIsNotNone(reply)
            self.assertTrue(reply.endswith(b"\x00\x00\x00\x00"))
            aaaa = focus_block.dns_query_packet("r4---sn-abc.googlevideo.com", 28)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.settimeout(0.5)
                sock.sendto(aaaa, ("127.0.0.1", port))
                answer, _addr = sock.recvfrom(512)
            finally:
                sock.close()
            self.assertTrue(answer.endswith(bytes(16)))


if __name__ == "__main__":
    unittest.main()
