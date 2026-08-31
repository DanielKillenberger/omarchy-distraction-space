import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "distraction-space"

  property bool focusOn: true
  readonly property string helperPath: localPath(Qt.resolvedUrl("distractions"))

  function localPath(url) {
    var value = String(url)
    if (value.indexOf("file://") === 0)
      return decodeURIComponent(value.substring(7))
    return value
  }

  function refresh() {
    if (!statusProcess.running)
      statusProcess.running = true
  }

  function toggle() {
    if (actionProcess.running)
      return
    actionProcess.command = [root.helperPath, "focus"]
    actionProcess.running = true
  }

  IpcHandler {
    target: "distraction-space-bar"
    function refresh(): void {
      root.refresh()
    }
  }

  Process {
    id: statusProcess
    command: [root.helperPath, "focus-status"]
    onExited: function (exitCode) {
      root.focusOn = exitCode === 0
    }
  }

  Process {
    id: actionProcess
    onExited: function () {
      root.refresh()
    }
  }

  Timer {
    interval: 2000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰈈"
    active: root.focusOn
    activeColor: Color.urgent
    useActiveColor: true
    dimmed: !root.focusOn
    interactive: !actionProcess.running
    tooltipText: root.focusOn
      ? "Focus mode on — distraction space locked. Click or Super+Ctrl+Shift+F and write a reason to leave."
      : "Focus mode off — Super+D opens the distraction space. Click to turn focus on."
    onPressed: function (buttonCode) {
      if (buttonCode === Qt.LeftButton)
        root.toggle()
    }
  }
}
