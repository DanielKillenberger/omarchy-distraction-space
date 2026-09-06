#!/usr/bin/env python3
"""WirePlumber hold hook: paths, the loaded check, the hold key, and the hook script under a real Lua interpreter."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT, Sandbox

sys.path.insert(0, str(ROOT))
from ds import wp

LUA = shutil.which("lua5.4") or shutil.which("lua") or shutil.which("luajit")

PW_METADATA = r"""
import os, sys
from pathlib import Path
log = os.environ.get("DS_PW_METADATA_LOG")
if log:
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    Path(log).open("a").write(" ".join(sys.argv[1:]) + "\n")
if os.environ.get("DS_PW_METADATA_FAIL"):
    print("boom", file=sys.stderr)
    sys.exit(1)
marker = os.environ.get("DS_PW_METADATA_LOADED")
name = "io.github.danielkillenberger.distraction-space"
oid = os.environ.get("DS_PW_METADATA_ID", "7")
args = sys.argv[1:]
if marker and Path(marker).exists():
    print(f'Found "{name}" metadata {oid}')
    if args == ["-n", name]:
        print("update: id:0 key:'hold-mute' value:'\"loaded\"' type:'Spa:String:JSON'")
    elif args == ["-n", name, "0", "hold", "-d"]:
        print("delete property: id:0 key:hold")
    elif args[:4] == ["-n", name, "0", "hold"] and len(args) == 6:
        print(f"set property: id:0 key:hold value:{args[4]} type:{args[5]}")
sys.exit(0)
"""

HARNESS = r"""
local write = io.write
local run = dofile
local HOLD
if arg[2] == "on" then
  HOLD = "\"on\""
elseif arg[2] == "off" then
  HOLD = nil
end
local hooks = {}
Log = { open_topic = function(name) return {
  info = function(self, ...) end,
  warning = function(self, ...) local t = {...}; write("warning ", tostring(t[#t]), "\n") end } end }
SimpleEventHook = function(spec)
  spec.register = function(self) write("register ", self.name, " after=", tostring(self.after), "\n") end
  hooks[#hooks + 1] = spec
  return spec
end
EventInterest = function(t) return t end
Constraint = function(t) return t end
Pod = { Object = function(t) return t end }
Features = { ALL = 0 }
ImplMetadata = function(name)
  local obj = {
    set = function(self, subject, key, kind, value)
      write("set ", tostring(subject), " ", key, " ", kind, " ", value, "\n")
    end,
    find = function(self, subject, key)
      write("find ", tostring(subject), " ", key, "\n")
      if arg[2] == "broken" then error("no metadata") end
      return HOLD
    end,
  }
  obj.activate = function(self, features, cb)
    write("metadata ", name, "\n")
    cb(self, nil)
  end
  return obj
end
io = nil
os = nil
require = nil
dofile = nil
loadfile = nil
load = nil
package = nil
debug = nil
run(arg[1])
for _, interest in ipairs(hooks[1].interests) do
  for _, c in ipairs(interest) do write("constraint ", c[1], " ", c[2], " ", c[3], "\n") end
end
local node = { properties = { ["node.name"] = "chrome-out" },
  set_param = function(self, id, props) write("set_param ", id, " ", props[1], " mute=", tostring(props.mute), "\n") end }
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
        os.environ.pop("DS_PW_METADATA_ID", None)
        self.addCleanup(os.environ.pop, "DS_PW_METADATA_LOG", None)
        self.addCleanup(os.environ.pop, "DS_PW_METADATA_LOADED", None)
        self.addCleanup(os.environ.pop, "DS_PW_METADATA_FAIL", None)
        self.addCleanup(os.environ.pop, "DS_PW_METADATA_ID", None)

    def test_script_paths_follow_xdg(self):
        data = Path(os.environ["XDG_DATA_HOME"])
        config = Path(os.environ["XDG_CONFIG_HOME"])
        self.assertEqual(wp.script_path(), data / "wireplumber" / "scripts" / "distraction-space-hold-mute.lua")
        self.assertEqual(wp.fragment_path(), config / "wireplumber" / "wireplumber.conf.d" / "distraction-space-hold-mute.conf")
        self.assertEqual(wp.script_text(), (ROOT / "install" / wp.SCRIPT_NAME).read_text(encoding="utf-8"))
        self.assertNotIn("@", wp.script_text())
        self.assertIn("custom.distraction-space.hold-mute = required", wp.fragment_text())

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

    def test_hold_sets_and_deletes_the_key_through_pw_metadata(self):
        self.box.fake_bin("pw-metadata", PW_METADATA)
        self.marker.write_text("1", encoding="utf-8")
        os.environ["DS_PW_METADATA_ID"] = "42"
        self.assertEqual(wp.hold(True), (42, None))
        self.assertEqual(self.log.read_text(encoding="utf-8").splitlines()[-1],
                         '-n io.github.danielkillenberger.distraction-space 0 hold "on" Spa:String:JSON')
        self.assertEqual(wp.hold(False), (42, None))
        self.assertEqual(self.log.read_text(encoding="utf-8").splitlines()[-1],
                         "-n io.github.danielkillenberger.distraction-space 0 hold -d")
        self.marker.unlink()
        self.assertEqual(wp.hold(True), (None, None))
        os.environ["DS_PW_METADATA_FAIL"] = "1"
        object_id, error = wp.hold(True)
        self.assertIsNone(object_id)
        self.assertIsNotNone(error)
        self.assertIn("boom", error)
        os.environ.pop("DS_PW_METADATA_FAIL", None)
        (self.box.bin / "pw-metadata").unlink()
        orig_path = os.environ["PATH"]
        os.environ["PATH"] = str(self.box.bin)
        try:
            object_id, error = wp.hold(True)
            self.assertIsNone(object_id)
            self.assertIsNotNone(error)
            self.assertIn("pw-metadata", error)
        finally:
            os.environ["PATH"] = orig_path

    def _want(self, muted):
        return [
            "metadata io.github.danielkillenberger.distraction-space",
            'set 0 hold-mute Spa:String:JSON "loaded"',
            "register node/distraction-space-hold-mute after=node/restore-stream",
            "constraint event.type = node-added",
            "constraint media.class = Stream/Output/Audio",
            "constraint application.id = io.github.danielkillenberger.distraction-space",
            "find 0 hold",
            f"set_param Props Spa:Pod:Object:Param:Props mute={muted}",
        ]

    @unittest.skipUnless(LUA, "no Lua interpreter on PATH")
    def test_hook_script_mutes_only_while_the_hold_key_is_readable(self):
        harness = self.box.runtime / "harness.lua"
        harness.write_text(HARNESS, encoding="utf-8")
        script = ROOT / "install" / wp.SCRIPT_NAME
        for hold_arg, muted in (("on", "true"), ("off", "false"), ("broken", "false")):
            with self.subTest(hold=hold_arg):
                proc = subprocess.run(
                    [LUA, str(harness), str(script), hold_arg],
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
