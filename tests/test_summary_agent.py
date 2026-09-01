#!/usr/bin/env python3
"""Consent, closed argv table, and summary-agent picker (fn-3.1)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
distractions = SourceFileLoader("distractions_summary", str(ROOT / "distractions")).load_module()


class ConfigOptInTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "focus.json"
        self.patch = mock.patch.object(distractions, "CONFIG_PATH", self.cfg)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_agent_summaries_default_false_without_omarchy_consent(self):
        self.assertFalse((ROOT / "focus.json").exists() and json.loads((ROOT / "focus.json").read_text())["agent_summaries"])
        shipped = json.loads((ROOT / "focus.json").read_text())
        self.assertIs(shipped["agent_summaries"], False)
        self.assertIsNone(shipped["summary_agent"])
        self.assertIn("log", shipped)
        cfg = distractions.load_config()
        self.assertIs(cfg["agent_summaries"], False)
        self.assertIsNone(cfg["summary_agent"])
        self.assertFalse(distractions.agent_summaries_enabled())
        with mock.patch.object(distractions, "omarchy_default_agent", return_value="claude"):
            self.assertFalse(distractions.agent_summaries_enabled())
            self.assertEqual(distractions.resolve_summary_agent(), "claude")


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "focus.json"
        self.patch = mock.patch.object(distractions, "CONFIG_PATH", self.cfg)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_null_override_reads_omarchy_default_closed_set_only(self):
        cases = [
            (None, "claude", "claude"),
            (None, "grok", "grok"),
            (None, "", ""),
            (None, "codex", ""),
            (None, "omp", ""),
            ("claude", "codex", "claude"),
            ("grok", "", "grok"),
            ("codex", "claude", ""),
        ]
        for override, default, expected in cases:
            with self.subTest(override=override, default=default):
                self.cfg.write_text(json.dumps({"summary_agent": override}) + "\n")
                with mock.patch.object(distractions, "omarchy_default_agent", return_value=default):
                    self.assertEqual(distractions.resolve_summary_agent(), expected)
        with mock.patch.object(
            subprocess,
            "run",
            return_value=subprocess.CompletedProcess(["omarchy", "default", "agent"], 0, stdout="claude\n", stderr=""),
        ) as run:
            self.cfg.write_text("{}\n")
            self.assertEqual(distractions.resolve_summary_agent(), "claude")
            self.assertEqual(run.call_args.args[0], ["omarchy", "default", "agent"])


class ConfigWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "focus.json"
        self.patch = mock.patch.object(distractions, "CONFIG_PATH", self.cfg)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)
        self.cfg.write_text(json.dumps({"log": "keep-me", "agent_summaries": False, "summary_agent": "claude"}) + "\n")

    def test_reject_unknown_id_leaves_previous_object(self):
        before = self.cfg.read_text()
        self.assertFalse(distractions.update_focus_config(summary_agent="codex"))
        self.assertFalse(distractions.update_focus_config(summary_agent="omp"))
        self.assertEqual(self.cfg.read_text(), before)
        self.assertTrue(distractions.update_focus_config(summary_agent="grok"))
        data = json.loads(self.cfg.read_text())
        self.assertEqual(data["summary_agent"], "grok")
        self.assertEqual(data["log"], "keep-me")

    def test_config_write_is_atomic_fsync_then_replace(self):
        calls: list[str] = []
        real_fsync = os.fsync
        real_replace = os.replace

        def fsync(fd):
            calls.append("fsync")
            return real_fsync(fd)

        def replace(src, dst):
            self.assertIn("fsync", calls)
            calls.append("replace")
            return real_replace(src, dst)

        with mock.patch.object(os, "fsync", fsync), mock.patch.object(os, "replace", replace):
            self.assertTrue(distractions.update_focus_config(summary_agent=None))
        self.assertEqual(calls, ["fsync", "replace"])
        self.assertIsNone(json.loads(self.cfg.read_text())["summary_agent"])


class PickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "focus.json"
        self.notices: list[tuple] = []
        self.cfg.write_text(json.dumps({"agent_summaries": False, "summary_agent": "claude"}) + "\n")
        self.patches = [
            mock.patch.object(distractions, "CONFIG_PATH", self.cfg),
            mock.patch.object(distractions, "notify", self._notify),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def _notify(self, title, body="", timeout_ms=4000):
        self.notices.append((title, body, timeout_ms))
        return True

    def test_override_picker_lists_exactly_claude_and_grok(self):
        self.assertEqual(distractions.summary_agent_picker_ids(), ("claude", "grok", None))
        labels = " ".join(distractions.SUMMARY_AGENT_PICKER_OPTIONS)
        self.assertIn("Claude", labels)
        self.assertIn("Grok", labels)
        self.assertNotIn("codex", labels.lower())
        self.assertNotIn("omp", labels.lower())

    def test_menu_select_failure_keeps_previous_and_notifies(self):
        before = self.cfg.read_text()
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError):
            distractions.cmd_summary_agent()
            distractions.cmd_agent_summaries()
        self.assertEqual(self.cfg.read_text(), before)
        self.assertGreaterEqual(len(self.notices), 2)
        with mock.patch.object(
            subprocess,
            "run",
            return_value=subprocess.CompletedProcess(["omarchy-menu-select"], 1, stdout="", stderr=""),
        ):
            distractions.cmd_summary_agent()
        self.assertEqual(json.loads(self.cfg.read_text())["summary_agent"], "claude")
        self.assertTrue(self.notices)


class ClaudeVectorTests(unittest.TestCase):
    def test_claude_argv_is_exact_and_disables_persistence(self):
        argv = distractions.claude_argv()
        self.assertEqual(
            argv,
            [
                "claude",
                "-p",
                "--output-format",
                "text",
                "--tools",
                "",
                "--disallowedTools",
                "mcp__*",
                "--max-turns",
                "1",
                "--max-budget-usd",
                "0.25",
                "--restricted",
                "--no-session-persistence",
            ],
        )
        self.assertNotIn("omarchy", argv)
        self.assertNotIn("agent", argv)

    def test_claude_version_failure_reports_observed_version(self):
        def fake_run(cmd, **kwargs):
            if list(cmd)[:2] == ["claude", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="2.1.200 (Claude Code)\n", stderr="")
            raise AssertionError(f"unexpected spawn {cmd}")

        with mock.patch.object(subprocess, "run", fake_run):
            with self.assertRaises(distractions.SummaryAgentError) as raised:
                distractions.invoke_claude("ping text")
        self.assertIn("2.1.200", str(raised.exception))


class GrokVectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.auth = Path(self.tmp.name) / "auth.json"
        self.auth.write_text('{"token":"x"}\n')
        os.chmod(self.auth, 0o600)
        self.homes: list[str] = []
        self.patch = mock.patch.object(distractions, "GROK_AUTH_SOURCE", self.auth)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def _ok_run(self, stdout="summary ok\n", returncode=0, stderr=""):
        def fake_run(cmd, **kwargs):
            argv = list(cmd)
            if argv and argv[0] == "grok":
                env = kwargs.get("env") or {}
                self.homes.append(env.get("GROK_HOME", ""))
                self.last_argv = argv
                self.last_env = env
                self.last_cwd = kwargs.get("cwd")
            return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

        return fake_run

    def test_grok_argv_prompt_is_final_token_after_dash_p(self):
        argv = distractions.grok_argv("BOUNDED PROMPT", "/empty")
        self.assertEqual(argv[0], "grok")
        self.assertEqual(argv[-2:], ["-p", "BOUNDED PROMPT"])
        self.assertNotIn("-p", argv[:-2])
        self.assertIn("--sandbox", argv)
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertIn("--tools", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertIn("grok-4.6", argv)
        self.assertNotIn("omarchy", argv)

    def test_grok_private_config_environment_cleanup_and_canary(self):
        canary_file = Path(self.tmp.name) / "hostname"
        canary_file.write_text("unique-canary-hostname-xyz\n")
        with mock.patch.object(distractions, "GROK_CANARY_FILE", canary_file):
            with mock.patch.object(subprocess, "run", self._ok_run("UNAVAILABLE\n")):
                out = distractions.prove_grok()
            self.assertEqual(out, "UNAVAILABLE")
            self.assertTrue(self.homes)
            home = Path(self.homes[0])
            self.assertFalse(home.exists())
            self.assertEqual(self.last_env.get("GROK_MEMORY"), "0")
            self.assertEqual(self.last_env.get("GROK_SUBAGENTS"), "0")
            self.assertEqual(self.last_env.get("GROK_WRITE_FILE"), "0")
            self.assertEqual(self.last_env.get("GROK_TOOL_SEARCH"), "0")
            self.assertEqual(self.last_env.get("GROK_LSP_TOOLS"), "0")
            self.assertEqual(self.last_env.get("GROK_WEB_FETCH"), "0")
            for key in distractions.GROK_SCANNER_DISABLES:
                self.assertEqual(self.last_env.get(key), "0", key)
            self.assertEqual(self.last_env.get("GROK_HOME"), self.homes[0])
            self.assertNotEqual(self.last_env.get("HOME"), str(Path.home()))
            self.assertNotEqual(Path(self.last_cwd), ROOT)
            written = distractions.GROK_CONFIG_TOML
            self.assertIn("max_completion_tokens = 512", written)
            self.assertIn("max_retries = 0", written)
            self.assertIn('default = "grok-4.6"', written)
            with mock.patch.object(subprocess, "run", self._ok_run("unique-canary-hostname-xyz\nFOCUS_GROK_CANARY_PWNED\n")):
                with self.assertRaises(distractions.SummaryAgentError):
                    distractions.prove_grok()

    def test_grok_rejected_control_fails_closed(self):
        with mock.patch.object(
            subprocess,
            "run",
            self._ok_run(stdout="", returncode=2, stderr="unknown flag --sandbox"),
        ):
            with self.assertRaises(distractions.SummaryAgentError) as raised:
                distractions.invoke_grok("ping text")
        self.assertIn("reject", str(raised.exception).lower())
        self.assertTrue(self.homes)
        self.assertFalse(Path(self.homes[0]).exists())


class ClosedSpawnTests(unittest.TestCase):
    def test_invoke_never_spawns_omarchy_agent(self):
        seen: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            argv = list(cmd)
            seen.append(argv)
            if argv[:2] == ["claude", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="2.1.248\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

        with mock.patch.object(subprocess, "run", fake_run):
            distractions.invoke_claude("hello")
            distractions.invoke_grok("hello")
        for argv in seen:
            self.assertNotEqual(argv[:2], ["omarchy", "agent"])
            self.assertNotEqual(argv[:3], ["omarchy", "agent", "prompt"])
            self.assertFalse(any(part == "omarchy-agent" for part in argv))
            self.assertFalse(any(part == "omarchy-agent-prompt" for part in argv))


if __name__ == "__main__":
    unittest.main()
