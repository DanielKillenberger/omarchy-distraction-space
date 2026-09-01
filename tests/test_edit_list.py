#!/usr/bin/env python3
"""Injected-command tests for the zenity list editor and UI-save signaling."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIG_PATH = os.environ.get("PATH", "/usr/bin")

ZENITY_SRC = r"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
log = Path(os.environ["ZENITY_LOG"])
stdin = sys.stdin.read()
log.write_text(json.dumps({"argv": sys.argv[1:], "stdin": stdin}))
if os.environ.get("ZENITY_MODE") == "cancel":
    raise SystemExit(1)
out = os.environ.get("ZENITY_STDOUT")
sys.stdout.write(stdin if out is None else out)
"""

NFT_SRC = r"""#!/usr/bin/env python3
import os
from pathlib import Path
Path(os.environ["NFT_CALL_LOG"]).open("a").write("called\n")
raise SystemExit(77)
"""


def load_mod():
    loader = SourceFileLoader("distractions_edit", str(ROOT / "distractions"))
    spec = spec_from_loader("distractions_edit", loader)
    assert spec is not None
    mod = module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class EditListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.state = self.root / "state"
        self.runtime = self.root / "runtime"
        self.bin = self.root / "bin"
        for path in (self.home, self.state, self.runtime, self.bin):
            path.mkdir()
        self.user = self.home / ".config/omarchy/app-list.json"
        self.user.parent.mkdir(parents=True)
        self.nft_call_log = self.root / "nft-calls.log"
        self.zenity_log = self.root / "zenity.log"
        self._write_bin("zenity", ZENITY_SRC)
        self._write_bin("nft", NFT_SRC)
        env = {
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.state),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "PATH": f"{self.bin}:{ORIG_PATH}",
            "ZENITY_LOG": str(self.zenity_log),
            "NFT_CALL_LOG": str(self.nft_call_log),
        }
        for key, value in env.items():
            os.environ[key] = value
        self.mod = load_mod()
        self.notes: list[tuple] = []
        self.mod.notify = lambda *args, **kwargs: self.notes.append(args)

    def _write_bin(self, name: str, source: str) -> None:
        path = self.bin / name
        path.write_text(source)
        path.chmod(0o755)

    def write_list(self, rows: list[dict]) -> None:
        self.user.write_text(json.dumps(rows, indent=2) + "\n")

    def read_list(self) -> list:
        return json.loads(self.user.read_text())

    def serve_reload(self, reply: bytes = b"ok\n"):
        path = self.mod.reload_sock_path()
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(path))
        sock.listen(1)
        received: list[bytes] = []

        def run() -> None:
            conn, _unused = sock.accept()
            try:
                received.append(conn.recv(64))
                conn.sendall(reply)
            finally:
                conn.close()
                sock.close()

        thread = threading.Thread(target=run)
        thread.start()
        return received, thread

    def test_edit_list_add_remove_change(self):
        self.write_list([{"name": "Telegram"}, {"name": "Discord"}])
        os.environ["ZENITY_STDOUT"] = (
            "Telegram\n"
            "CustomApp | app.custom\n"
            "ExampleSite | | site.example\n"
        )
        received, thread = self.serve_reload()
        self.mod.edit_list(user_path=self.user, defaults_path=ROOT / "app-list-defaults.json")
        thread.join(timeout=2)
        self.assertEqual(
            self.read_list(),
            [
                {"name": "Telegram"},
                {"name": "CustomApp", "class": "app.custom"},
                {"name": "ExampleSite", "hosts": ["site.example"]},
            ],
        )
        self.assertEqual(received, [b"reload\n"])

    def test_edit_list_rejected_rows_omitted(self):
        self.write_list([{"name": "Telegram"}])
        os.environ["ZENITY_STDOUT"] = (
            "Telegram\n"
            "\n"
            "Unknown\n"
            "Telegram\n"
            "Kept | | kept.example\n"
        )
        received, thread = self.serve_reload()
        self.mod.edit_list(user_path=self.user, defaults_path=ROOT / "app-list-defaults.json")
        thread.join(timeout=2)
        self.assertEqual(
            self.read_list(),
            [{"name": "Telegram"}, {"name": "Kept", "hosts": ["kept.example"]}],
        )
        self.assertEqual(received, [b"reload\n"])

    def test_edit_list_colliding_names_rejected(self):
        self.write_list([{"name": "Telegram"}])
        os.environ["ZENITY_STDOUT"] = (
            "Telegram\n"
            "!!! | punct.a\n"
            "??? | punct.b\n"
        )
        received, thread = self.serve_reload()
        self.mod.edit_list(user_path=self.user, defaults_path=ROOT / "app-list-defaults.json")
        thread.join(timeout=2)
        self.assertEqual(self.read_list(), [{"name": "Telegram"}])
        self.assertEqual(self.mod.window_rule_name("!!!"), self.mod.window_rule_name("???"))
        self.assertEqual(received, [b"reload\n"])

    def test_edit_list_missing_zenity(self):
        self.write_list([{"name": "Telegram"}])
        before = self.user.read_text()
        os.environ["PATH"] = str(self.root / "empty-path")
        (self.root / "empty-path").mkdir(exist_ok=True)
        self.mod.edit_list(user_path=self.user, defaults_path=ROOT / "app-list-defaults.json")
        self.assertEqual(self.user.read_text(), before)
        self.assertTrue(self.notes)
        self.assertIn("zenity is missing", self.notes[0][1])
        self.assertFalse(self.nft_call_log.exists())

    def test_edit_list_save_requests_reload_without_nft(self):
        self.write_list([{"name": "Telegram"}])
        os.environ["ZENITY_STDOUT"] = "Telegram\nCustomApp | app.custom\n"
        received, thread = self.serve_reload()
        env = os.environ.copy()
        result = subprocess.run(
            [sys.executable, str(ROOT / "distractions"), "edit-list"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        thread.join(timeout=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(received, [b"reload\n"])
        self.assertEqual(
            self.read_list(),
            [{"name": "Telegram"}, {"name": "CustomApp", "class": "app.custom"}],
        )
        self.assertFalse(self.nft_call_log.exists())
        logged = json.loads(self.zenity_log.read_text())
        self.assertIn("--editable", logged["argv"])

    def test_edit_list_dead_listener_notifies(self):
        self.write_list([{"name": "Telegram"}])
        os.environ["ZENITY_STDOUT"] = "Telegram\nKept | | kept.example\n"
        self.mod.edit_list(user_path=self.user, defaults_path=ROOT / "app-list-defaults.json")
        self.assertEqual(
            self.read_list(),
            [{"name": "Telegram"}, {"name": "Kept", "hosts": ["kept.example"]}],
        )
        self.assertTrue(self.notes)
        self.assertIn("listener is not running", self.notes[0][1])
        self.assertFalse(self.nft_call_log.exists())

    def test_edit_list_reload_failure_notifies(self):
        self.write_list([{"name": "Telegram"}])
        os.environ["ZENITY_STDOUT"] = "Telegram\nKept | | kept.example\n"
        received, thread = self.serve_reload(reply=b"error\n")
        self.mod.edit_list(user_path=self.user, defaults_path=ROOT / "app-list-defaults.json")
        thread.join(timeout=2)
        self.assertEqual(
            self.read_list(),
            [{"name": "Telegram"}, {"name": "Kept", "hosts": ["kept.example"]}],
        )
        self.assertEqual(received, [b"reload\n"])
        self.assertTrue(any("could not reload" in (note[1] if len(note) > 1 else "") for note in self.notes))
        self.assertFalse(self.nft_call_log.exists())


if __name__ == "__main__":
    unittest.main()
