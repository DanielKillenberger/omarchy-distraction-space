#!/usr/bin/env python3
"""ds/launch.py: `distractions open` resolution, the slice launch, focus, and forwarding.

Every launch goes through fakes on PATH: `systemd-run`, `xdg-settings`, `hyprctl`,
`omarchy-notification-send`, `omarchy-launch-browser`, and a fake previous handler.
Desktop files live in a sandbox share directory reached through `XDG_DATA_DIRS`.
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import catalog, launch, state

_ENV_KEYS = (
    "DS_SYSTEMD_RUN_LOG", "DS_FORWARD_LOG", "DS_NOTIFY_LOG", "DS_HYPR_LOG", "DS_HYPR_STATE",
    "DS_XDG_BROWSER", "XDG_DATA_HOME", "XDG_DATA_DIRS", "DS_LAUNCH_SETTLE", "DS_FAKE_RC",
)

LOGGER = r"""
import json, os, sys
from pathlib import Path
p = Path(os.environ[%r])
p.parent.mkdir(parents=True, exist_ok=True)
with p.open("a", encoding="utf-8") as f:
    f.write(json.dumps([os.path.basename(sys.argv[0])] + sys.argv[1:]) + "\n")
sys.exit(int(os.environ.get("DS_FAKE_RC", "0")))
"""

NOOP = "import sys\nsys.exit(0)\n"

XDG_SETTINGS = r"""
import os, sys
if sys.argv[1:3] == ["get", "default-web-browser"]:
    print(os.environ.get("DS_XDG_BROWSER", "google-chrome.desktop"))
    sys.exit(0)
sys.exit(1)
"""

HYPRCTL = r"""
import json, os, sys
from pathlib import Path
log = Path(os.environ["DS_HYPR_LOG"])
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
state_path = Path(os.environ.get("DS_HYPR_STATE", ""))
data = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
args = sys.argv[1:]
if args[:1] == ["-j"] and len(args) >= 2:
    if args[1] == "activeworkspace":
        print(json.dumps(data.get("activeworkspace") or {"id": 1, "name": "1"}))
        sys.exit(0)
    if args[1] == "clients":
        print(json.dumps(data.get("clients") or []))
        sys.exit(0)
    sys.exit(1)
if args[:1] == ["dispatch"]:
    sys.exit(0)
sys.exit(1)
"""

SLICE_PREFIX = ["systemd-run", "--user", "--scope", "--quiet", "--collect", "--slice=app-distraction.slice", "--"]


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self._orig = {k: os.environ.get(k) for k in _ENV_KEYS}
        self.addCleanup(self._restore)
        self.share = self.box.runtime / "share"
        self.apps = self.share / "applications"
        self.apps.mkdir(parents=True)
        self.data_home = self.box.data
        self.run_log = self.box.runtime / "systemd-run.log"
        self.forward_log = self.box.runtime / "forward.log"
        self.notify_log = self.box.runtime / "notify.log"
        self.hypr_log = self.box.runtime / "hypr.log"
        self.hypr_state = self.box.runtime / "hypr-state.json"
        os.environ.update({
            "DS_SYSTEMD_RUN_LOG": str(self.run_log),
            "DS_FORWARD_LOG": str(self.forward_log),
            "DS_NOTIFY_LOG": str(self.notify_log),
            "DS_HYPR_LOG": str(self.hypr_log),
            "DS_HYPR_STATE": str(self.hypr_state),
            "XDG_DATA_HOME": str(self.data_home),
            "XDG_DATA_DIRS": str(self.share),
        })
        os.environ.pop("DS_XDG_BROWSER", None)
        self.box.fake_bin("systemd-run", LOGGER % "DS_SYSTEMD_RUN_LOG")
        # The browsers the desktop files and the config name: a launch checks the
        # binary is on PATH, and the real machine's browsers must not stand in.
        for binary in ("google-chrome-stable", "chromium", "brave"):
            self.box.fake_bin(binary, NOOP)
        os.environ["DS_LAUNCH_SETTLE"] = "0.2"
        self.box.fake_bin("omarchy-launch-browser", LOGGER % "DS_FORWARD_LOG")
        self.box.fake_bin("firefox-fake", LOGGER % "DS_FORWARD_LOG")
        self.box.fake_bin("omarchy-notification-send", LOGGER % "DS_NOTIFY_LOG")
        self.box.fake_bin("xdg-settings", XDG_SETTINGS)
        self.box.fake_bin("hyprctl", HYPRCTL)
        self._desktop("google-chrome", "google-chrome-stable %U")
        self._desktop("firefox", "firefox-fake %u")
        self._desktop("org.telegram.desktop", "Telegram -- %U")
        state.write_expansion({
            "list": [catalog.expand_entry("YouTube"), catalog.expand_entry("Telegram")],
            "keep_reachable": [], "nudges": {"app_banner": True, "block_page": True},
            "site_block": {"enabled": True},
        })

    def _restore(self):
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _desktop(self, desktop_id, exec_line):
        (self.apps / f"{desktop_id}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={desktop_id}\nExec={exec_line}\n", encoding="utf-8"
        )

    def _lines(self, path):
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def _wait_lines(self, path, n):
        """The launched fakes run detached, so their log lines land after `open` has exited."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            lines = self._lines(path)
            if len(lines) >= n:
                return lines
            time.sleep(0.02)
        raise TimeoutError(f"{path} has {len(self._lines(path))} lines, wanted {n}")

    def _launches(self, n=1):
        return self._wait_lines(self.run_log, n)

    def _hypr(self):
        return [" ".join(a) for a in self._lines(self.hypr_log)]

    def _profile_flags(self, url):
        return [
            f"--user-data-dir={self.data_home / 'omarchy' / 'distraction-space' / 'browser'}",
            "--profile-directory=Distraction",
            f"--app={url}",
        ]

    def test_listed_url_launches_the_profile_in_the_slice(self):
        url = "https://www.youtube.com/watch?v=1"
        r = self.box.run("open", url)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._launches(), [SLICE_PREFIX + ["google-chrome-stable", *self._profile_flags(url)]])
        self.assertFalse(any("dispatch" in line for line in self._hypr()), self._hypr())

    def test_subdomain_is_listed_and_unlisted_forwards_to_the_recorded_handler(self):
        state.write_entries({"files": [], "previous_handler": "firefox.desktop"})
        r = self.box.run("open", "https://m.youtube.com/x")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._launches()[0][-1], "--app=https://m.youtube.com/x")
        r = self.box.run("open", "https://example.com/p?q=1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._wait_lines(self.forward_log, 1), [["firefox-fake", "https://example.com/p?q=1"]])
        self.assertEqual(len(self._lines(self.run_log)), 1)

    def test_missing_or_self_handler_falls_back_and_unparseable_exec_exits_1(self):
        for n, record in enumerate((None, launch.HANDLER_ID), start=1):
            with self.subTest(record=record):
                state.write_entries({"files": [], "previous_handler": record})
                r = self.box.run("open", "https://example.com/")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self._wait_lines(self.forward_log, n)[-1], ["omarchy-launch-browser", "https://example.com/"])
        self._desktop("broken", 'firefox-fake "unbalanced %u')
        state.write_entries({"files": [], "previous_handler": "broken.desktop"})
        r = self.box.run("open", "https://example.com/")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(self._lines(self.notify_log)), 1)
        self.assertEqual(len(self._lines(self.forward_log)), 2)
        self.assertFalse(self.run_log.exists())

    def test_existing_profile_window_is_focused_instead_of_relaunched(self):
        window = {"address": "0xabc", "class": "chrome-www.youtube.com__-Distraction",
                  "workspace": {"id": 99, "name": "distraction"}}
        cases = (
            ("on the space", "distraction", "distraction", True, False),
            ("off the space, window elsewhere", "1", "2", False, True),
        )
        for label, active, window_ws, focused, moved in cases:
            with self.subTest(label):
                if self.hypr_log.exists():
                    self.hypr_log.unlink()
                window["workspace"] = {"id": 1, "name": window_ws}
                self.hypr_state.write_text(json.dumps({
                    "activeworkspace": {"id": 1, "name": active}, "clients": [window],
                }), encoding="utf-8")
                r = self.box.run("open", "https://www.youtube.com/")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertFalse(self.run_log.exists())
                dispatched = [line for line in self._hypr() if line.startswith("dispatch")]
                self.assertEqual(any("hl.dsp.focus" in d and "0xabc" in d for d in dispatched), focused, dispatched)
                self.assertEqual(any("hl.dsp.window.move" in d and "0xabc" in d for d in dispatched), moved, dispatched)
                self.assertFalse(any("hl.dsp.focus" in d and "workspace" in d for d in dispatched), dispatched)

    def test_native_target_and_unlisted_catalog_name(self):
        r = self.box.run("open", "Telegram")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._launches(), [SLICE_PREFIX + ["Telegram", "--"]])
        # After setup the plugin's own launcher shadows the system entry under
        # XDG_DATA_HOME; a native launch must pass it over, never launch itself.
        own = self.data_home / "applications"
        own.mkdir(parents=True, exist_ok=True)
        (own / "org.telegram.desktop.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName=Telegram\nExec={ROOT / 'distractions'} open Telegram\n",
            encoding="utf-8")
        r = self.box.run("open", "Telegram")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._launches(2)[1], SLICE_PREFIX + ["Telegram", "--"])
        # With only the plugin's own entry present there is nothing to launch: one notice, exit 1.
        (self.apps / "org.telegram.desktop.desktop").unlink()
        r = self.box.run("open", "Telegram")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(self._launches(2)), 2)
        self._desktop("org.telegram.desktop", "Telegram -- %u")
        r = self.box.run("open", "Discord")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._launches(3)[2], SLICE_PREFIX + ["google-chrome-stable", *self._profile_flags("https://discord.com/")])
        log = state.state_path("log").read_text(encoding="utf-8")
        self.assertEqual(log.count("not network-restricted"), 1)
        self.assertIn("Discord", log)

    def test_auto_pick_behind_the_plugin_handler_uses_the_recorded_browser(self):
        # After setup the default is this plugin's own handler; the pick must
        # follow the recorded previous browser, not fall through to chromium.
        state.write_entries({"files": [], "previous_handler": "google-chrome.desktop"})
        r = self.box.run("open", "https://youtu.be/abc", extra_env={"DS_XDG_BROWSER": launch.HANDLER_ID})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._launches()[0][len(SLICE_PREFIX)], "google-chrome-stable")
        # No record behind the handler: the chromium fallback, as for any unknown id.
        self._desktop("chromium", "chromium %U")
        state.write_entries({"files": [], "previous_handler": None})
        r = self.box.run("open", "https://youtu.be/abc", extra_env={"DS_XDG_BROWSER": launch.HANDLER_ID})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._launches(2)[1][len(SLICE_PREFIX)], "chromium")

    def test_launch_reports_a_browser_that_did_not_start(self):
        # A configured binary that is not on PATH: no scope is started at all.
        self.box.config_file.write_text(json.dumps({"browser": ["/definitely/missing/browser"]}), encoding="utf-8")
        r = self.box.run("open", "https://youtu.be/abc")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(self._lines(self.run_log), [])
        self.assertEqual(len(self._lines(self.notify_log)), 1)
        self.box.config_file.unlink()
        # The scope launcher exits non-zero inside the settle window: the launch failed.
        r = self.box.run("open", "https://youtu.be/abc", extra_env={"DS_FAKE_RC": "1"})
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(len(self._lines(self.notify_log)), 2)
        # A zero exit at once is Chromium's single-instance handoff: success.
        r = self.box.run("open", "https://youtu.be/abc")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_browser_override_missing_browser_and_usage(self):
        self.box.config_file.write_text(json.dumps({"browser": ["brave", "--foo"]}), encoding="utf-8")
        r = self.box.run("open", "https://youtu.be/abc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._launches()[0][len(SLICE_PREFIX):len(SLICE_PREFIX) + 2], ["brave", "--foo"])
        self.box.config_file.unlink()
        r = self.box.run("open", "https://youtu.be/abc", extra_env={"DS_XDG_BROWSER": "firefox.desktop"})
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(self._lines(self.notify_log)), 1)
        self.assertEqual(len(self._lines(self.run_log)), 1)
        for argv in (["open", "ftp://x"], ["open", "mailto:a@b"], ["open"], ["open", "no-such-thing"],
                     ["open", "https://[::1"], ["open", "https://a b.com/"], ["open", "https://x.com:99999/"],
                     ["open", "https://-bad-.example/"], ["open", "https://x.com:0/"],
                     ["open", "https://youtube.com\\@evil.com/"], ["open", "https://a@b@youtube.com/"],
                     ["open", "https://user%zz@evil.com/"], ["open", "https://youtube.com\n@evil.com/"],
                     ["open", "https://youtube.com/\tx"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.box.run(*argv).returncode, 2)


class ExecParsingTests(unittest.TestCase):
    def test_parse_exec_table(self):
        cases = (
            ("firefox %u", ["firefox", "%u"]),
            ('"/opt/my browser/bin" --new-tab %U', ["/opt/my browser/bin", "--new-tab", "%U"]),
            ('x "a \\"q\\" \\$b" y', ["x", 'a "q" $b', "y"]),
            ('"env\\sFOO=1" app', ["env FOO=1", "app"]),
            ("env\\sFOO=1 app", ["env", "FOO=1", "app"]),
            ("  spaced   out  ", ["spaced", "out"]),
            ('"unbalanced', None),
            ("foo\\ bar baz", ["foo bar", "baz"]),
            ("'single quoted' x", ["single quoted", "x"]),
            (r"a\\\\b", ["a\\b"]),  # four in the file, two after the key-file pass, one argument char
            ("'unterminated", None),
            ("trailing\\", None),
            ("", None),
            (None, None),
        )
        for value, want in cases:
            with self.subTest(value=value):
                self.assertEqual(launch.parse_exec(value), want)

    def test_expand_fields_table(self):
        url = "https://e.com/?a=1"
        cases = (
            (["firefox", "%u"], ["firefox", url]),
            (["chrome", "%U", "--x"], ["chrome", url, "--x"]),
            (["app", "--url=%u"], ["app", "--url=" + url]),
            (["app", "%i", "%c", "%k", "100%%"], ["app", "100%", url]),
            (["app"], ["app", url]),
        )
        for argv, want in cases:
            with self.subTest(argv=argv):
                self.assertEqual(launch.expand_fields(argv, url), want)
        self.assertEqual(launch.expand_fields(["Telegram", "--", "%U"], None), ["Telegram", "--"])


class ReadExecTests(unittest.TestCase):
    def test_exec_comes_from_the_main_group_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.desktop"
            path.write_text("[Desktop Entry]\nName=A\nActions=new;\n\n[Desktop Action new]\nExec=a --new %u\n", encoding="utf-8")
            self.assertIsNone(launch.read_exec(path))
            path.write_text("[Desktop Action new]\nExec=a --new %u\n\n[Desktop Entry]\nExec=a %u\n", encoding="utf-8")
            self.assertEqual(launch.read_exec(path), "a %u")
            path.write_text("Exec=stray\n[Desktop Entry]\nName=A\n", encoding="utf-8")
            self.assertIsNone(launch.read_exec(path))


class ClassifyTests(unittest.TestCase):
    def test_classify_host_table(self):
        exp = {"list": [catalog.expand_entry("YouTube"), catalog.expand_entry("Discord"), catalog.expand_entry("class=^foo$")]}
        cases = (
            ("youtube.com", "YouTube"),
            ("WWW.YOUTUBE.COM.", "YouTube"),
            ("music.youtube.com:443", "YouTube"),
            ("discord.com", "Discord"),
            ("cdn.discord.com", "Discord"),
            ("notyoutube.com", None),
            ("youtube.com.evil.net", None),
            ("", None),
        )
        for host, want in cases:
            with self.subTest(host=host):
                got = launch.classify_host(host, exp)
                self.assertEqual(got["name"] if got else None, want)
        self.assertEqual(launch.classify_host("youtube.com", [catalog.expand_entry("YouTube")])["name"], "YouTube")
        # `www.` is an alias the list names explicitly, never one the classifier invents.
        www_only = [{"name": "W", "classes": [], "hosts": ["www.example.com"]}]
        self.assertIsNotNone(launch.classify_host("www.example.com", www_only))
        self.assertIsNotNone(launch.classify_host("a.www.example.com", www_only))
        self.assertIsNone(launch.classify_host("example.com", www_only))
        self.assertIsNone(launch.classify_host("api.example.com", www_only))


if __name__ == "__main__":
    unittest.main()
