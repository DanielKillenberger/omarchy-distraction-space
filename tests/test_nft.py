#!/usr/bin/env python3
"""distractions-nft render and argv/stdin contract."""

from __future__ import annotations

import ipaddress
import json
import io
import time
from unittest.mock import patch
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT

WRAPPER = ROOT / "distractions-nft"
UID = 1000
CGROUP = f"user.slice/user-{UID}.slice/user@{UID}.service/app.slice/app-distraction.slice"
SLICE_ACCEPT = f'socket cgroupv2 level 5 "{CGROUP}" accept'

FAKE_NFT = r"""
import os, sys
from pathlib import Path
root = Path(os.environ["NFT_FAKE"])
script = sys.stdin.read()
(root / "argv.log").write_text("\n".join(sys.argv[1:]))
(root / "stdin.log").write_text(script)
(root / "calls.log").open("a").write("1\n")
"""


def load_nft():
    loader = SourceFileLoader("distractions_nft", str(WRAPPER))
    spec = spec_from_loader("distractions_nft", loader)
    mod = module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class NftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.bin / "nft"
        fake.write_text("#!/usr/bin/env python3\n" + FAKE_NFT, encoding="utf-8")
        fake.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = f"{self.bin}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["NFT_FAKE"] = str(self.root)
        # What sudo hands the wrapper, and the slice cgroup it looks for under the mount.
        self.cgroup_root = self.root / "cgroup"
        (self.cgroup_root / CGROUP).mkdir(parents=True)
        self.env["SUDO_UID"] = str(UID)
        self.env["DS_CGROUP_ROOT"] = str(self.cgroup_root)
        self.nft = load_nft()

    def run_wrapper(self, args, stdin=""):
        return subprocess.run(
            [sys.executable, str(WRAPPER), *args],
            input=stdin,
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        )

    def stdin_log(self):
        path = self.root / "stdin.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def address_lines(self, count):
        base = int(ipaddress.IPv4Address("10.0.0.0"))
        return [str(ipaddress.IPv4Address(base + i)) for i in range(count)]

    def padded_payload(self, lines, size):
        payload = "".join(line + "\n" for line in lines)
        # Blank lines are skipped by the parser, so padding moves the byte count
        # without moving the address count.
        payload += "\n" * (size - len(payload.encode("utf-8")))
        self.assertEqual(len(payload.encode("utf-8")), size)
        return payload

    def test_render_has_redirect_per_family_and_reject(self):
        script = self.nft.render_table(["203.0.113.5"], ["2001:db8::5"], CGROUP)
        self.assertIn("chain output_nat", script)
        self.assertIn("type nat hook output priority dstnat", script)
        self.assertIn("ip daddr @omarchy_ds_v4 tcp dport 80 redirect to :28080", script)
        self.assertIn("ip daddr @omarchy_ds_v4 tcp dport 443 redirect to :28443", script)
        self.assertIn("ip6 daddr @omarchy_ds_v6 tcp dport 80 redirect to :28080", script)
        self.assertIn("ip6 daddr @omarchy_ds_v6 tcp dport 443 redirect to :28443", script)
        self.assertIn("ip daddr @omarchy_ds_v4 meta l4proto tcp reject with tcp reset", script)
        self.assertIn("ip6 daddr @omarchy_ds_v6 meta l4proto tcp reject with tcp reset", script)
        self.assertIn("ip daddr @omarchy_ds_v4 reject\n", script)
        self.assertIn("ip6 daddr @omarchy_ds_v6 reject\n", script)
        self.assertNotIn(" drop\n", script)
        self.assertNotIn(" drop;", script)
        result = self.run_wrapper(["replace", "ds"], "203.0.113.5\n2001:db8::5\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        logged = self.stdin_log()
        self.assertIn("redirect to :28080", logged)
        self.assertIn("meta l4proto tcp reject with tcp reset", logged)

    def test_splice_source_port_accept_precedes_redirect_and_reject(self):
        script = self.nft.render_table(["203.0.113.5"], ["2001:db8::5"], CGROUP)
        filter_body = script[
            script.index("chain output {") : script.index("chain output_nat {")
        ]
        nat_body = script[script.index("chain output_nat {") :]
        first_rules = (
            f"\n    {SLICE_ACCEPT}"
            "\n    meta nfproto ipv4 tcp sport 61000-61999 accept"
            "\n    meta nfproto ipv6 tcp sport 61000-61999 accept\n"
        )
        for body, type_line, chain in (
            (
                filter_body,
                "type filter hook output priority filter; policy accept;",
                "output",
            ),
            (
                nat_body,
                "type nat hook output priority dstnat; policy accept;",
                "output_nat",
            ),
        ):
            with self.subTest(chain=chain, check="first_rules"):
                after_type = body[body.index(type_line) + len(type_line) :]
                self.assertTrue(after_type.startswith(first_rules), after_type[:200])
        families = (
            (
                "ipv4",
                "meta nfproto ipv4 tcp sport 61000-61999 accept",
                "ip daddr @omarchy_ds_v4",
            ),
            (
                "ipv6",
                "meta nfproto ipv6 tcp sport 61000-61999 accept",
                "ip6 daddr @omarchy_ds_v6",
            ),
        )
        for family, accept, daddr in families:
            with self.subTest(family=family, chain="output"):
                self.assertLess(
                    filter_body.index(accept),
                    filter_body.index(f"{daddr} meta l4proto tcp reject with tcp reset"),
                )
                self.assertLess(
                    filter_body.index(accept),
                    filter_body.index(f"{daddr} reject\n"),
                )
            with self.subTest(family=family, chain="output_nat"):
                self.assertLess(
                    nat_body.index(accept),
                    nat_body.index(f"{daddr} tcp dport 80 redirect"),
                )
                self.assertLess(
                    nat_body.index(accept),
                    nat_body.index(f"{daddr} tcp dport 443 redirect"),
                )

    def test_cgroup_accept_is_the_first_rule_and_names_the_invoking_uid(self):
        script = self.nft.render_table(["203.0.113.5"], ["2001:db8::5"], CGROUP)
        self.assertEqual(self.nft.slice_path(UID), CGROUP)
        self.assertEqual(script.count(SLICE_ACCEPT), 2)
        for chain, type_line, later in (
            ("output", "type filter hook output priority filter; policy accept;", " reject"),
            ("output_nat", "type nat hook output priority dstnat; policy accept;", " redirect to"),
        ):
            with self.subTest(chain=chain):
                body = script[script.index(f"chain {chain} {{") :]
                after_type = body[body.index(type_line) + len(type_line) :]
                self.assertTrue(after_type.startswith(f"\n    {SLICE_ACCEPT}\n"), after_type[:200])
                self.assertLess(body.index(SLICE_ACCEPT), body.index("tcp sport 61000-61999 accept"))
                self.assertLess(body.index(SLICE_ACCEPT), body.index(later))
        # Another uid, another slice: the path is derived from SUDO_UID and nothing else.
        other = 4242
        (self.cgroup_root / self.nft.slice_path(other)).mkdir(parents=True)
        self.env["SUDO_UID"] = str(other)
        result = self.run_wrapper(["replace", "ds"], "203.0.113.5\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'level 5 "{self.nft.slice_path(other)}" accept', self.stdin_log())
        self.assertNotIn(CGROUP, self.stdin_log())

    def test_refuses_without_an_invoking_uid_before_any_nft_call(self):
        cases = [None, "", "abc", "1000x", "-1", " 1000", "1000\n", "\uff11\uff10\uff10\uff10"]
        for raw in cases:
            with self.subTest(sudo_uid=raw):
                if raw is None:
                    self.env.pop("SUDO_UID", None)
                else:
                    self.env["SUDO_UID"] = raw
                for args in (["replace", "ds"], ["flush", "ds"]):
                    result = self.run_wrapper(args, "203.0.113.1\n" if args[0] == "replace" else "")
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stderr.strip(), "refused: no invoking uid")
                self.assertFalse((self.root / "calls.log").exists())
                self.assertFalse((self.root / "stdin.log").exists())

    def test_missing_slice_cgroup_exits_1_before_any_nft_call(self):
        shutil.rmtree(self.cgroup_root / CGROUP)
        result = self.run_wrapper(["replace", "ds"], "203.0.113.1\n")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr.strip(), "refused: slice cgroup missing")
        self.assertFalse((self.root / "calls.log").exists())
        self.assertFalse((self.root / "stdin.log").exists())
        # A file where the directory should be is not a cgroup either.
        (self.cgroup_root / CGROUP).write_text("", encoding="utf-8")
        result = self.run_wrapper(["replace", "ds"], "203.0.113.1\n")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse((self.root / "calls.log").exists())
        # `flush` renders nothing that needs the slice: it destroys the table and
        # succeeds with the cgroup gone, which is what lets the block be switched off.
        result = self.run_wrapper(["flush", "ds"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.stdin_log().strip(), "destroy table inet omarchy_ds")

    def test_empty_sets_render_table_that_matches_nothing(self):
        script = self.nft.render_table([], [], CGROUP)
        self.assertIn("table inet omarchy_ds", script)
        self.assertIn("set omarchy_ds_v4", script)
        self.assertIn("set omarchy_ds_v6", script)
        self.assertNotIn("elements =", script)
        # `flush` is a bare destroy: no sets, no chains, no cgroup rule left behind.
        result = self.run_wrapper(["flush", "ds"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.stdin_log().strip(), "destroy table inet omarchy_ds")

    def test_refuses_argv_outside_contract(self):
        cases = [
            [],
            ["replace"],
            ["replace", "ds", "extra"],
            ["flush", "other"],
            ["replace", "OTHER"],
            ["drop", "ds"],
            ["replace", "ds", "ds"],
        ]
        for args in cases:
            with self.subTest(args=args):
                result = self.run_wrapper(args, "203.0.113.1\n")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse((self.root / "stdin.log").exists())

    def test_refuses_stdin_outside_contract(self):
        for token in ("example.com", "/etc/passwd", "203.0.113.0/24", "not_an_ip", "::1/128"):
            with self.subTest(token=token):
                result = self.run_wrapper(["replace", "ds"], token + "\n")
                self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((self.root / "calls.log").exists())

    def test_flush_rejects_non_whitespace_stdin(self):
        result = self.run_wrapper(["flush", "ds"], "203.0.113.1\n")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("flush takes no stdin", result.stderr)
        self.assertFalse((self.root / "calls.log").exists())
        blank = self.run_wrapper(["flush", "ds"], "  \n\t\n")
        self.assertEqual(blank.returncode, 0, blank.stderr)
        self.assertTrue((self.root / "calls.log").exists())

    def test_refuses_input_over_caps_before_any_nft_call(self):
        over_bytes = "\n" * (self.nft.MAX_STDIN_BYTES + 1)
        over_addresses = "".join(
            line + "\n" for line in self.address_lines(self.nft.MAX_ADDRESSES + 1)
        )
        cases = [
            ("replace_stdin_over_byte_cap", ["replace", "ds"], over_bytes),
            ("replace_over_address_cap", ["replace", "ds"], over_addresses),
            ("flush_stdin_over_byte_cap", ["flush", "ds"], over_bytes),
        ]
        for name, args, stdin in cases:
            with self.subTest(case=name):
                result = self.run_wrapper(args, stdin)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(
                    result.stderr.startswith("refused:"), result.stderr
                )
                self.assertFalse((self.root / "calls.log").exists())
                self.assertFalse((self.root / "stdin.log").exists())

    def test_accepts_payload_exactly_at_caps(self):
        lines = self.address_lines(self.nft.MAX_ADDRESSES)
        payload = self.padded_payload(lines, self.nft.MAX_STDIN_BYTES)
        result = self.run_wrapper(["replace", "ds"], payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.root / "calls.log").read_text(encoding="utf-8"), "1\n"
        )
        logged = self.stdin_log()
        for addr in (lines[0], lines[-1]):
            with self.subTest(addr=addr):
                self.assertIn(addr, logged)

    def listed_policy(self):
        return (self.nft.render_table(["203.0.113.8", "203.0.113.2"], ["2001:db8::8"], CGROUP)
                .split("\n", 1)[1]
                .replace("priority filter;", "priority 0;")
                .replace("priority dstnat;", "priority -100;")
                .replace("@omarchy_ds_v4 reject\n", "@omarchy_ds_v4 reject with icmp port-unreachable\n")
                .replace("@omarchy_ds_v6 reject\n", "@omarchy_ds_v6 reject with icmpv6 port-unreachable\n"))

    def test_check_matches_full_policy_and_returns_identity(self):
        text = self.listed_policy().replace("203.0.113.8, 203.0.113.2", "203.0.113.2,\n 203.0.113.8")
        (self.bin / "nft").write_text("#!/usr/bin/env python3\nimport sys\nassert sys.argv[1:] == ['-y','list','table','inet','omarchy_ds']\nprint(" + repr(text) + ")\n")
        result = self.run_wrapper(["check", "ds"], "2001:db8::8\n203.0.113.2\n203.0.113.8\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        st = (self.cgroup_root / CGROUP).stat()
        self.assertEqual(json.loads(result.stdout), {"dev": st.st_dev, "ino": st.st_ino})

    def test_check_rejects_policy_drift(self):
        text = self.listed_policy()
        changes = [
            ("level 5", "level 4"), (CGROUP, CGROUP + "x"),
            (f'"{CGROUP}"', "123456"),
            ("61000-61999", "60000-61999"), ("priority -100", "priority -99"),
            ("hook output", "hook input"), ("203.0.113.8", "203.0.113.9"),
            ("type ipv4_addr", "type ipv4_addr; flags interval"),
            ("chain output {", "chain extra { }\n chain output {"),
            ("set omarchy_ds_v4 {", "set extra { type ipv4_addr }\n set omarchy_ds_v4 {"),
            (" accept\n", " counter accept\n"),
            (" accept\n", ' accept comment "extra"\n'),
            ("    ip daddr @omarchy_ds_v4 reject with icmp port-unreachable\n", ""),
            ("    ip daddr @omarchy_ds_v4 reject with icmp port-unreachable\n", "    accept\n"),
        ]
        for old, new in changes:
            with self.subTest(change=(old, new)):
                actual = text.replace(old, new)
                self.assertNotEqual(self.nft.canonical_policy(actual), self.nft.canonical_policy(text))
                output = io.StringIO()
                with patch.object(self.nft, "slice_identity", return_value=(1, 2)), patch.object(self.nft, "list_policy", return_value=actual), patch("sys.stdout", output):
                    with self.assertRaises(SystemExit):
                        self.nft.check_policy(["203.0.113.8", "203.0.113.2"], ["2001:db8::8"], CGROUP)
                self.assertEqual(output.getvalue(), "")
        lines = text.splitlines()
        i = next(i for i, line in enumerate(lines) if 'tcp sport' in line)
        lines[i], lines[i+1] = lines[i+1], lines[i]
        self.assertNotEqual(self.nft.canonical_policy('\n'.join(lines)), self.nft.canonical_policy(text))
        for malformed in ("", "garbage", text + "extra"):
            self.assertNotEqual(self.nft.canonical_policy(malformed), self.nft.canonical_policy(text))

    def test_check_missing_changed_slice_and_failed_listing(self):
        with patch.dict(os.environ, self.env), patch.object(self.nft, "list_policy", return_value=self.listed_policy()):
            with patch.object(self.nft, "slice_identity", side_effect=[(1, 2), (1, 3)]):
                with self.assertRaises(SystemExit):
                    self.nft.check_policy(["203.0.113.8", "203.0.113.2"], ["2001:db8::8"], CGROUP)
        shutil.rmtree(self.cgroup_root / CGROUP)
        result = self.run_wrapper(["check", "ds"])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "calls.log").exists())
        self.assertEqual(result.stdout, "")

    def test_check_refuses_input_and_operands(self):
        for args, data in [(["check", "other"], ""), (["check", "ds", "x"], ""),
                           (["check", "ds"], "flush ruleset"),
                           (["check", "ds"], "\n" * (self.nft.MAX_STDIN_BYTES + 1)),
                           (["check", "ds"], "\n".join(self.address_lines(self.nft.MAX_ADDRESSES + 1)))]:
            result = self.run_wrapper(args, data)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
        self.assertFalse((self.root / "calls.log").exists())

    def test_listing_bounds_output_time_and_reaps(self):
        cases = ["import os; os.write(1,b'x'*20000)",
                 "import os; os.write(2,b'x'*20000)",
                 "import time; time.sleep(30)",
                 "import os,time; os.close(1); os.close(2); time.sleep(30)",
                 "import os,time; pid=os.fork(); time.sleep(30) if pid==0 else os._exit(0)",
                 "raise SystemExit(1)", "import os; os.write(1,b'\\xff')"]
        for body in cases:
            with self.subTest(body=body):
                (self.bin / "nft").write_text("#!/usr/bin/env python3\n" + body + "\n")
                launched = []
                original = subprocess.Popen
                def launch(*a, **kw):
                    child = original(*a, **kw)
                    launched.append(child)
                    return child
                with patch.dict(os.environ, self.env), patch.object(self.nft, "CHECK_TIMEOUT", 0.15), patch.object(self.nft, "MAX_OUTPUT_BYTES", 1024), patch.object(self.nft.subprocess, "Popen", side_effect=launch):
                    start = time.monotonic()
                    with self.assertRaises(SystemExit):
                        self.nft.list_policy()
                    self.assertLess(time.monotonic() - start, 2)
                self.assertTrue(launched)
                self.assertIsNotNone(launched[0].poll())

    def test_listing_launch_failure_is_not_proof(self):
        with patch.object(self.nft.subprocess, "Popen", side_effect=FileNotFoundError), patch("sys.stdout", new_callable=io.StringIO) as output:
            with self.assertRaises(SystemExit):
                self.nft.list_policy()
            self.assertEqual(output.getvalue(), "")

    def test_nft_check_skips_without_cap(self):
        nft = shutil.which("nft")
        if not nft:
            self.skipTest("nft not on PATH")
        script = self.nft.render_table(["203.0.113.8"], ["2001:db8::8"], CGROUP)
        result = subprocess.run(
            [nft, "-c", "-f", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        err = (result.stderr or "") + (result.stdout or "")
        if result.returncode != 0:
            lowered = err.lower()
            if any(w in lowered for w in ("permission", "operation not permitted", "netlink", "cap_net")):
                return
            self.fail(f"nft -c rejected ruleset: {err}")


if __name__ == "__main__":
    unittest.main()
