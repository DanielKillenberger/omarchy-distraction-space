import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: capture

  property var host: null

  readonly property string helperPath: host ? host.helperPath : ""
  readonly property string xdgState: host ? host.xdgState : ""
  readonly property string controlPath: xdgState + "focus-summary-control.json"
  readonly property string configPath: {
    var env = Quickshell.env("XDG_CONFIG_HOME")
    if (env && env.length)
      return env + "/omarchy/focus.json"
    return Quickshell.env("HOME") + "/.config/omarchy/focus.json"
  }

  property bool summariesEnabled: false
  property bool sessionReady: false
  property string sessionId: ""
  property bool parserActive: false
  property bool parserClosed: false
  property bool finishRequested: false
  property int parserRestarts: 0
  property var captureQueue: []
  property bool captureBusy: false
  property string capturePayload: ""

  function enqueueMemberToast(row) {
    if (!capture.summariesEnabled || !row)
      return
    var title = ""
    if (row.summary)
      title = String(row.summary)
    else if (row.title)
      title = String(row.title)
    capture.captureQueue = capture.captureQueue.concat([{
      app: String(row.app || ""),
      title: title,
      body: String(row.body || ""),
      at: new Date().toISOString()
    }])
    pumpCapture()
  }

  function pumpCapture() {
    if (capture.captureBusy || capture.captureQueue.length === 0)
      return
    var job = capture.captureQueue[0]
    capture.captureQueue = capture.captureQueue.slice(1)
    capture.capturePayload = Qt.btoa(JSON.stringify(job))
    capture.captureBusy = true
    captureProc.command = [
      "sh",
      "-c",
      "printf %s \"$2\" | base64 -d | exec \"$1\" capture-ping",
      "sh",
      capture.helperPath,
      capture.capturePayload
    ]
    captureProc.running = true
  }

  function applyControl(text) {
    try {
      var parsed = JSON.parse(text)
      capture.sessionReady = !!(parsed && parsed.session_ready)
      capture.sessionId = parsed && parsed.session_id ? String(parsed.session_id) : ""
      capture.parserActive = !!(parsed && parsed.parser_active)
      capture.parserClosed = !!(parsed && parsed.parser_closed)
      capture.finishRequested = !!(parsed && parsed.finish_requested)
      capture.parserRestarts = parsed && parsed.parser_restarts ? parsed.parser_restarts : 0
    } catch (e) {
      capture.sessionReady = false
      capture.sessionId = ""
      capture.parserActive = false
      capture.parserClosed = false
      capture.finishRequested = false
    }
  }

  function shouldRunParser() {
    return capture.summariesEnabled && capture.sessionReady && !capture.parserClosed && !capture.finishRequested
  }

  function syncParser() {
    if (!shouldRunParser()) {
      if (parserProc.running && (!capture.summariesEnabled || capture.finishRequested || capture.parserClosed))
        parserProc.running = false
      return
    }
    if (parserProc.running)
      return
    if (capture.parserActive) {
      parserProc.command = [capture.helperPath, "summarize-session", "--restart"]
    } else {
      parserProc.command = [capture.helperPath, "summarize-session"]
    }
    parserProc.running = true
  }

  FileView {
    id: configFile
    path: capture.configPath
    watchChanges: true
    onLoaded: {
      try {
        var parsed = JSON.parse(configFile.text())
        capture.summariesEnabled = !!(parsed && parsed.agent_summaries)
      } catch (e) {
        capture.summariesEnabled = false
      }
      capture.syncParser()
    }
    onFileChanged: configFile.reload()
  }

  FileView {
    id: controlFile
    path: capture.controlPath
    watchChanges: true
    onLoaded: {
      capture.applyControl(controlFile.text())
      capture.syncParser()
    }
    onFileChanged: controlFile.reload()
  }

  Timer {
    interval: 250
    running: true
    repeat: true
    onTriggered: {
      controlFile.reload()
      capture.syncParser()
    }
  }

  Process {
    id: captureProc
    stdout: StdioCollector {}
    stderr: StdioCollector {}
    onExited: function () {
      capture.captureBusy = false
      capture.pumpCapture()
    }
  }

  Process {
    id: parserProc
    stdout: StdioCollector {}
    stderr: StdioCollector {}
    onExited: function () {
      if (!capture.shouldRunParser())
        return
      capture.syncParser()
    }
  }
}
