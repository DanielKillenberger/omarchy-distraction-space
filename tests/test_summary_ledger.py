#!/usr/bin/env python3
"""Summary ledger and README (fn-3.4)."""

from __future__ import annotations

import json
import os
import sys
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

    def test_docs_describe_start_timer_and_close(self):
        text = README.read_text()
        self.assertIn("start dialog", text.lower())
        self.assertIn("closing window", text.lower())
        self.assertIn("session_close_ui", text)
        self.assertIn('"session_start_ui": true', text)
        manifest = (ROOT / "manifest.json").read_text()
        self.assertIn("start popup", manifest)
        self.assertIn("timer", manifest)
        self.assertIn("closing window", manifest)
        focus = (ROOT / "focus.json").read_text()
        self.assertIn("session_close_ui", focus)
        self.assertIn("session_close_eval", focus)


class CloseDialogLedgerTests(LedgerHarness):
    def test_helpful_on_close_dialog_appends_ledger_without_menu_select(self):
        selected: list[str] = []

        def track_menu(*args, **kwargs):
            selected.append("menu")
            return "Helpful"

        with mock.patch.object(distractions, "menu_select", track_menu):
            with mock.patch.object(distractions, "collect_summary_feedback") as collect:
                self.assertTrue(distractions.append_ledger_entry(True, "from-close"))
                collect.assert_not_called()
        self.assertEqual(selected, [])
        row = json.loads(distractions.summary_ledger_path().read_text().splitlines()[-1])
        self.assertEqual(row["helpful"], True)
        self.assertEqual(row["note"], "from-close")
        self.assertNotIn("importance", row)

    def test_close_dialog_reads_current_fields_on_helpful(self):
        class FakeEntry:
            def __init__(self, text):
                self._text = text

            def set_placeholder_text(self, text):
                return None

            def get_text(self):
                return self._text

        class FakeLabel:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def set_line_wrap(self, *_args):
                return None

            def set_selectable(self, *_args):
                return None

        added: list[object] = []

        class FakeBox:
            def set_spacing(self, *_args):
                return None

            def set_margin_top(self, *_args):
                return None

            def set_margin_bottom(self, *_args):
                return None

            def set_margin_start(self, *_args):
                return None

            def set_margin_end(self, *_args):
                return None

            def add(self, widget):
                added.append(widget)

        class FakeDialog:
            def __init__(self, **kwargs):
                self.box = FakeBox()

            def set_default_size(self, *args):
                return None

            def add_button(self, *args):
                return None

            def get_content_area(self):
                return self.box

            def show_all(self):
                return None

            def run(self):
                return 1

            def destroy(self):
                return None

        class FakeGtk:
            class ResponseType:
                CANCEL = 0

            Dialog = FakeDialog
            Label = FakeLabel

            class Entry:
                created: list[FakeEntry] = []

                def __init__(self, **kwargs):
                    text = "hit it" if len(self.created) == 0 else "note-text"
                    entry = FakeEntry(text)
                    type(self).created.append(entry)
                    self._entry = entry

                def set_placeholder_text(self, text):
                    self._entry.set_placeholder_text(text)

                def get_text(self):
                    return self._entry.get_text()

        FakeGtk.Entry.created = []
        fake_gi = mock.Mock()
        fake_gi.require_version = mock.Mock()
        fake_repo = mock.Mock()
        fake_repo.Gtk = FakeGtk
        with mock.patch.dict(sys.modules, {"gi": fake_gi, "gi.repository": fake_repo}):
            outcome = distractions.prompt_focus_close(
                purpose="ship it",
                summary="Here's what you missed\nping",
                ask_eval=True,
                ask_feedback=True,
            )
        self.assertEqual(
            outcome,
            {"action": "helpful", "eval": "hit it", "note": "note-text"},
        )
        labels = [item.kwargs.get("label") for item in added if isinstance(item, FakeLabel)]
        self.assertIn("ship it", labels)
        self.assertIn("Here's what you missed\nping", labels)


if __name__ == "__main__":
    unittest.main()
