import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "distraction-space"

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

  FileView {
    id: stateFile
    path: root.statePath
    watchChanges: true
    onLoaded: root.applyState(stateFile.text())
    onFileChanged: stateFile.reload()
  }

  Process {
    id: actionProcess
  }

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
