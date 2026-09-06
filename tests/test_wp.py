#!/usr/bin/env python3
"""WirePlumber hold hook: rendering, the loaded check, and the hook script under a real Lua interpreter."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import hypr, state, wp

LUA = shutil.which("lua5.4") or shutil.which("lua") or shutil.which("luajit")

PW_METADATA = r"""
import os, sys
from pathlib import Path
log = os.environ.get("DS_PW_METADATA_LOG")
if log:
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    Path(log).open("a").write(" ".join(sys.argv[1:]) + "\n")
if os.environ.get("DS_PW_METADATA_FAIL"):
    sys.exit(1)
marker = os.environ.get("DS_PW_METADATA_LOADED")
if marker and Path(marker).exists():
    print('Found "io.github.danielkillenberger.distraction-space" metadata 7')
sys.exit(0)
"""

HARNESS = r"""
local hooks = {}
Log = { open_topic = function(name) return {
  info = function(self, ...) end,
  warning = function(self, ...) local t = {...}; io.write("warning ", tostring(t[#t]), "\n") end } end }
SimpleEventHook = function(spec)
  spec.register = function(self) io.write("register ", self.name, " after=", tostring(self.after), "\n") end
  hooks[#hooks + 1] = spec
  return spec
end
EventInterest = function(t) return t end
Constraint = function(t) return t end
Pod = { Object = function(t) return t end }
Features = { ALL = 0 }
ImplMetadata = function(name)
  return { activate = function(self, features, cb)
    io.write("metadata ", name, "\n")
    cb({ set = function(self, subject, key, kind, value) io.write("set ", tostring(subject), " ", key, " ", kind, " ", value, "\n") end }, nil)
  end }
end
dofile(arg[1])
for _, interest in ipairs(hooks[1].interests) do
  for _, c in ipairs(interest) do io.write("constraint ", c[1], " ", c[2], " ", c[3], "\n") end
end
local node = { properties = { ["node.name"] = "chrome-out" },
  set_param = function(self, id, props) io.write("set_param ", id, " ", props[1], " mute=", tostring(props.mute), "\n") end }
hooks[1].execute({ get_subject = function() return node end })
"""


class WpTests(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.cleanup)
        self.box.apply_env()
        self.log = self.box.runtime / "pw-metadata.log"
        self.marker = self.box.runtime / "pw-metadata.loaded"
        os.environ["DS_PW_METADATA_LOG"] = str(self.log)
        os.environ["DS_PW_METADATA_LOADED"] = str(self.marker)
        os.environ.pop("DS_PW_METADATA_FAIL", None)
        self.addCleanup(os.environ.pop, "DS_PW_METADATA_LOG", None)
        self.addCleanup(os.environ.pop, "DS_PW_METADATA_LOADED", None)
        self.addCleanup(os.environ.pop, "DS_PW_METADATA_FAIL", None)

    def test_render_script_embeds_the_flag_path_as_a_lua_string(self):
        default = wp.render_script()
        self.assertIn(hypr.lua_string(str(state.state_path("hold.flag"))), default)
        self.assertNotIn("@HOLD_FLAG@", default)
        path = str(self.box.runtime / 'quote"and\\slash')
        rendered = wp.render_script(flag=path)
        self.assertIn(hypr.lua_string(path), rendered)
        self.assertNotIn("@HOLD_FLAG@", rendered)
        root = self.box.runtime / "alt-root"
        (root / "install").mkdir(parents=True)
        (root / "install" / wp.SCRIPT_NAME).write_text("local FLAG = nil\n", encoding="utf-8")
        with mock.patch.object(wp, "ROOT", root):
            with self.assertRaises(ValueError):
                wp.render_script()

    def test_loaded_reads_pw_metadata(self):
        self.box.fake_bin("pw-metadata", PW_METADATA)
        self.marker.write_text("1", encoding="utf-8")
        self.assertIs(wp.loaded(), True)
        self.assertEqual(self.log.read_text(encoding="utf-8").splitlines()[-1],
                         "-n io.github.danielkillenberger.distraction-space")
        self.marker.unlink()
        self.assertIs(wp.loaded(), False)
        os.environ["DS_PW_METADATA_FAIL"] = "1"
        self.assertIsNone(wp.loaded())
        os.environ.pop("DS_PW_METADATA_FAIL", None)
        (self.box.bin / "pw-metadata").unlink()
        orig_path = os.environ["PATH"]
        os.environ["PATH"] = str(self.box.bin)
        try:
            self.assertIsNone(wp.loaded())
        finally:
            os.environ["PATH"] = orig_path

    def _want(self, muted):
        return [
            "register node/distraction-space-hold-mute after=node/restore-stream",
            "metadata io.github.danielkillenberger.distraction-space",
            'set 0 hold-mute Spa:String:JSON "loaded"',
            "constraint event.type = node-added",
            "constraint media.class = Stream/Output/Audio",
            "constraint application.id = io.github.danielkillenberger.distraction-space",
            f"set_param Props Spa:Pod:Object:Param:Props mute={muted}",
        ]

    @unittest.skipUnless(LUA, "no Lua interpreter on PATH")
    def test_hook_script_mutes_only_while_the_flag_is_readable(self):
        harness = self.box.runtime / "harness.lua"
        harness.write_text(HARNESS, encoding="utf-8")
        missing = self.box.runtime / "no-such-dir" / "hold.flag"
        cases = (
            ("present", None, True, "true"),
            ("absent", None, False, "false"),
            ("unreadable", str(missing), False, "false"),
        )
        for label, flag, write_flag, muted in cases:
            with self.subTest(label=label):
                path = Path(flag) if flag is not None else wp.flag_path()
                if write_flag:
                    path.write_text("on\n", encoding="utf-8")
                elif path.exists():
                    path.unlink()
                rendered = self.box.runtime / f"hook-{label}.lua"
                rendered.write_text(wp.render_script(flag=flag), encoding="utf-8")
                proc = subprocess.run(
                    [LUA, str(harness), str(rendered)],
                    capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                lines = proc.stdout.splitlines()
                self.assertEqual(lines, self._want(muted))
                self.assertFalse(any(ln.startswith("warning") for ln in lines))
                id_lines = [ln for ln in lines if ln.startswith("constraint application.id")]
                self.assertEqual(len(id_lines), 1)
                self.assertFalse(any("application.name" in ln for ln in lines))


if __name__ == "__main__":
    unittest.main()
