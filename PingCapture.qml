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
  readonly property int captureQueueLimit: 8
  readonly property int captureFieldLimit: 4096

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
  property bool parserOwned: false
  property bool singletonElsewhere: false
  property bool seenRemoteOwner: false
  property string heldSession: ""

  function clipField(value) {
    var text = String(value || "")
    if (text.length <= capture.captureFieldLimit)
      return text
    return text.substring(0, capture.captureFieldLimit)
  }

  function stopCaptureWork() {
    capture.captureQueue = []
    capture.captureBusy = false
    if (captureProc.running)
      captureProc.running = false
  }

  function enqueueMemberToast(row) {
    if (!capture.summariesEnabled || !row)
      return
    if (capture.captureQueue.length >= capture.captureQueueLimit)
      return
    var title = ""
    if (row.summary)
      title = String(row.summary)
    else if (row.title)
      title = String(row.title)
    capture.captureQueue = capture.captureQueue.concat([{
      app: capture.clipField(row.app || ""),
      title: capture.clipField(title),
      body: capture.clipField(row.body || ""),
      at: capture.clipField(new Date().toISOString())
    }])
    pumpCapture()
  }

  function pumpCapture() {
    if (!capture.summariesEnabled) {
      stopCaptureWork()
      return
    }
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
    return capture.summariesEnabled && capture.sessionReady && !capture.parserClosed && !capture.finishRequested && capture.sessionId.length > 0
  }

  function parserCommand(restart) {
    var argv = [capture.helperPath, "summarize-session", "--session", capture.sessionId]
    if (restart)
      argv.splice(2, 0, "--restart")
    return argv
  }

  function syncParser() {
    if (capture.heldSession !== capture.sessionId) {
      capture.singletonElsewhere = false
      capture.seenRemoteOwner = false
      capture.heldSession = capture.sessionId
    }
    if (!shouldRunParser()) {
      if (parserProc.running && (!capture.summariesEnabled || capture.finishRequested || capture.parserClosed))
        parserProc.running = false
      if (!capture.summariesEnabled || capture.finishRequested)
        capture.parserOwned = false
      return
    }
    if (capture.singletonElsewhere) {
      if (capture.parserActive)
        capture.seenRemoteOwner = true
      if (!(capture.seenRemoteOwner && !capture.parserActive))
        return
      capture.singletonElsewhere = false
      capture.seenRemoteOwner = false
    }
    if (parserProc.running)
      return
    parserProc.command = capture.parserCommand(capture.parserOwned || capture.parserActive)
    capture.parserOwned = true
    parserProc.running = true
  }

  FileView {
    id: configFile
    path: capture.configPath
    watchChanges: true
    onLoaded: {
      var enabled = false
      try {
        var parsed = JSON.parse(configFile.text())
        enabled = !!(parsed && parsed.agent_summaries)
      } catch (e) {
        enabled = false
      }
      if (capture.summariesEnabled && !enabled)
        capture.stopCaptureWork()
      capture.summariesEnabled = enabled
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
      if (capture.summariesEnabled)
        capture.pumpCapture()
      else
        capture.stopCaptureWork()
    }
  }

  Process {
    id: parserProc
    stdout: StdioCollector {}
    stderr: StdioCollector {}
    onExited: function (exitCode) {
      if (exitCode === 2) {
        capture.singletonElsewhere = true
        capture.seenRemoteOwner = capture.parserActive
        capture.heldSession = capture.sessionId
        return
      }
      if (!capture.shouldRunParser()) {
        capture.parserOwned = false
        return
      }
      capture.parserOwned = true
      capture.syncParser()
    }
  }
}
