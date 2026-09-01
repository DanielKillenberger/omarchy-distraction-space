#!/usr/bin/env python3
"""Summary ledger and README (fn-3.4)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
distractions = SourceFileLoader("distractions_ledger", str(ROOT / "distractions")).load_module()
README = ROOT / "README.md"


class LedgerHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / "state"
        self.runtime = root / "run"
        self.state.mkdir()
        self.runtime.mkdir()
        self.notices: list[tuple] = []
        self.patches = [
            mock.patch.object(distractions, "STATE_DIR", self.state),
            mock.patch.object(distractions, "SUMMARY_LEDGER_LOCK", self.runtime / "ledger.lock"),
            mock.patch.object(distractions, "notify", self.fake_notify),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def fake_notify(self, title, body="", timeout_ms=4000):
        self.notices.append((title, body, timeout_ms))
        return True


class LedgerWriteTests(LedgerHarness):
    def test_helpful_and_not_helpful_are_distinct_from_cancel(self):
        with mock.patch.object(distractions, "menu_select", return_value="Helpful"):
            with mock.patch.object(distractions, "prompt_ledger_note", return_value="good"):
                written = distractions.collect_summary_feedback()
        self.assertEqual(written, {"helpful": True, "note": "good"})
        with mock.patch.object(distractions, "menu_select", return_value="Not helpful"):
            with mock.patch.object(distractions, "prompt_ledger_note", return_value=""):
                written = distractions.collect_summary_feedback()
        self.assertEqual(written, {"helpful": False, "note": ""})
        lines = [
            json.loads(raw)
            for raw in distractions.summary_ledger_path().read_text().splitlines()
            if raw
        ]
        self.assertEqual([row["helpful"] for row in lines], [True, False])
        self.assertEqual(lines[0]["note"], "good")
        self.assertIn("at", lines[0])
        self.assertEqual(oct(distractions.summary_ledger_path().stat().st_mode & 0o777), "0o600")

    def test_cancel_does_not_append(self):
        with mock.patch.object(distractions, "menu_select", return_value=None):
            self.assertIsNone(distractions.collect_summary_feedback())
        self.assertFalse(distractions.summary_ledger_path().exists())

    def test_rejected_note_is_not_written(self):
        with mock.patch.object(distractions, "append_ledger_entry", return_value=False) as append:
            with mock.patch.object(distractions, "menu_select", return_value="Helpful"):
                with mock.patch.object(distractions, "prompt_ledger_note", return_value="nope"):
                    self.assertIsNone(distractions.collect_summary_feedback())
            append.assert_called_once_with(True, "nope")
        self.assertFalse(distractions.summary_ledger_path().exists())

    def test_write_failure_notifies_and_keeps_summary(self):
        path = distractions.summary_ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n")
        os.chmod(path, 0o400)
        path.chmod(0o400)
        with mock.patch.object(distractions, "write_private_atomic", side_effect=OSError("disk")):
            self.assertFalse(distractions.append_ledger_entry(True, "note"))
        self.assertTrue(any("Could not save summary feedback" in item[1] for item in self.notices))

    def test_next_prompt_includes_capped_ledger_lines(self):
        for index in range(25):
            self.assertTrue(distractions.append_ledger_entry(index % 2 == 0, f"n{index}"))
        prompt = distractions.read_ledger_prompt()
        self.assertNotIn('"n0"', prompt)
        self.assertIn('"n24"', prompt)
        self.assertLessEqual(len(prompt.encode()), distractions.LEDGER_PROMPT_BYTES)
        self.assertLessEqual(len(prompt.splitlines()), distractions.LEDGER_PROMPT_LINES)

    def test_oversized_note_is_truncated_and_stays_valid_json(self):
        huge = "n" * (distractions.LEDGER_NOTE_MAX + 200)
        self.assertTrue(distractions.append_ledger_entry(True, huge))
        raw = distractions.summary_ledger_path().read_text().splitlines()[-1]
        row = json.loads(raw)
        self.assertTrue(row["helpful"])
        self.assertLessEqual(len(row["note"].encode()), distractions.LEDGER_NOTE_MAX)
        self.assertLessEqual(len(raw.encode()), distractions.LEDGER_PROMPT_BYTES)
        prompt = distractions.read_ledger_prompt()
        self.assertIn('"helpful":true', prompt)

    def test_lock_failure_notifies_without_raising(self):
        with mock.patch.object(distractions, "_lock_summary_ledger", side_effect=OSError("lock")):
            self.assertFalse(distractions.append_ledger_entry(True, "x"))
        self.assertTrue(any("Could not save summary feedback" in item[1] for item in self.notices))

    def test_xor_success_asks_for_feedback(self):
        asked: list[str] = []

        def track():
            asked.append("ask")
            return {"helpful": True, "note": ""}

        control = {
            "session_id": "sess-1",
        }
        with mock.patch.object(distractions, "read_summary_control", return_value=control):
            with mock.patch.object(
                distractions, "read_summary_result", return_value={"session_id": "sess-1", "text": "hi"}
            ):
                with mock.patch.object(distractions, "agent_summaries_enabled", return_value=True):
                    with mock.patch.object(distractions, "resolve_summary_agent", return_value="claude"):
                        with mock.patch.object(distractions, "clear_counts"):
                            with mock.patch.object(distractions, "collect_summary_feedback", track):
                                self.assertEqual(distractions.apply_summary_xor(), "summary")
        self.assertEqual(asked, ["ask"])


class ReadmeTests(unittest.TestCase):
    def test_agent_summaries_section_and_config_example(self):
        text = README.read_text()
        use = text.find("## Use")
        agent = text.find("## Agent summaries")
        commands = text.find("## Commands")
        self.assertGreater(agent, use)
        self.assertGreater(commands, agent)
        section = text[agent:commands]
        self.assertIn("stay off", section.lower())
        self.assertIn("claude", section.lower())
        self.assertIn("grok", section.lower())
        self.assertIn("one summary", section.lower())
        self.assertIn("ledger", section.lower())
        self.assertIn("grouped-count", section.lower())
        self.assertIn("agent-summaries", text[commands:])
        self.assertIn("summary-agent", text[commands:])
        self.assertIn('"agent_summaries": false', text)
        self.assertIn('"summary_agent": null', text)
        self.assertIn("no history screen", section.lower())
        self.assertIn("no per-app notification toggle", section.lower())


if __name__ == "__main__":
    unittest.main()
