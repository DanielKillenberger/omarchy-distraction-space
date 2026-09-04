import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "io.github.danielkillenberger.distraction-space"

  readonly property string helperPath: localPath(Qt.resolvedUrl("distractions"))
  readonly property string statePath: {
    var env = Quickshell.env("XDG_STATE_HOME")
    var base = (env && env.length) ? env : (Quickshell.env("HOME") + "/.local/state")
    return base + "/omarchy/distraction-space/state.json"
  }

  property bool locked: false
  property string until: ""
  property string purpose: ""
  property int heldTotal: 0
  property bool refreshPending: false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function localPath(url) {
    var value = String(url)
    if (value.indexOf("file://") === 0)
      return decodeURIComponent(value.substring(7))
    return value
  }

  function heldCount(held) {
    var total = 0
    if (held && typeof held === "object") {
      for (var app in held)
        total += Math.max(0, parseInt(held[app], 10) || 0)
    }
    return total
  }

  function applyState(text) {
    try {
      var data = JSON.parse(text)
      root.locked = !!(data && data.locked)
      root.until = (data && data.until) ? String(data.until) : ""
      root.purpose = (data && data.purpose) ? String(data.purpose) : ""
      root.heldTotal = heldCount(data && data.held)
    } catch (e) {
      root.locked = false
      root.until = ""
      root.purpose = ""
      root.heldTotal = 0
    }
  }

  function run(args) {
    if (actionProcess.running)
      return
    actionProcess.command = [root.helperPath].concat(args)
    actionProcess.running = true
  }

  function refresh() {
    if (stateProcess.running) {
      root.refreshPending = true
      return
    }
    root.refreshPending = false
    stateProcess.running = true
  }

  // The state path is predictable and anyone running as this account can replace
  // it. FileView has no regular-file or size bound to give (checked against the
  // installed Quickshell API), and this widget lives as long as the shell, so the
  // file is watched here and read through the helper, which refuses an irregular
  // path and stops at a size cap. Nothing the path holds is materialized in-process.
  FileView {
    id: stateFile
    path: root.statePath
    watchChanges: true
    onFileChanged: root.refresh()
  }

  Process {
    id: stateProcess
    command: [root.helperPath, "status", "--json"]
    stdout: StdioCollector {
      onStreamFinished: root.applyState(this.text)
    }
    // A watch that lands mid-read is not lost: the next read starts when this one ends.
    onExited: function (code) {
      if (code !== 0)
        root.applyState("")
      if (root.refreshPending)
        root.refresh()
    }
  }

  Process {
    id: actionProcess
  }

  Component.onCompleted: root.refresh()

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // The held total follows the glyph while pings are waiting; the slot widens to fit it.
    text: root.heldTotal > 0 ? ("󰈈 " + root.heldTotal) : "󰈈"
    slotSize: root.heldTotal > 0 && !root.vertical ? -1 : Style.bar.iconSlot
    active: root.locked
    activeColor: Color.urgent
    useActiveColor: true
    dimmed: !root.locked && root.heldTotal === 0
    interactive: !actionProcess.running
    tooltipText: (root.locked
      ? ("Locked" + (root.until ? (" until " + root.until) : "") + (root.purpose ? (" — " + root.purpose) : ""))
      : "Distraction space unlocked")
      + (root.heldTotal > 0 ? (", " + root.heldTotal + " held") : "")
    onPressed: function (buttonCode) {
      if (buttonCode === Qt.LeftButton)
        root.run([root.locked ? "unlock" : "lock"])
      else if (buttonCode === Qt.RightButton)
        root.run(["menu"])
      else if (buttonCode === Qt.MiddleButton)
        root.run(["toggle"])
    }
  }
}
