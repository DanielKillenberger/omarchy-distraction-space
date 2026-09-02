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

  function localPath(url) {
    var value = String(url)
    if (value.indexOf("file://") === 0)
      return decodeURIComponent(value.substring(7))
    return value
  }

  function applyState(text) {
    try {
      var data = JSON.parse(text)
      root.locked = !!(data && data.locked)
      root.until = (data && data.until) ? String(data.until) : ""
      root.purpose = (data && data.purpose) ? String(data.purpose) : ""
    } catch (e) {
      root.locked = false
      root.until = ""
      root.purpose = ""
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
    text: "󰈈"
    active: root.locked
    activeColor: Color.urgent
    useActiveColor: true
    dimmed: !root.locked
    interactive: !actionProcess.running
    tooltipText: root.locked
      ? ("Locked" + (root.until ? (" until " + root.until) : "") + (root.purpose ? (" — " + root.purpose) : ""))
      : "Distraction space unlocked"
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
