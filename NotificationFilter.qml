import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons

Item {
  id: root

  property var shell: null
  property var manifest: null
  property string omarchyPath: ""

  readonly property string helperPath: localPath(Qt.resolvedUrl("distractions"))
  readonly property string membersPath: localPath(Qt.resolvedUrl("notification-members.json"))
  readonly property string xdgState: {
    var env = Quickshell.env("XDG_STATE_HOME")
    if (env && env.length)
      return env + "/omarchy/"
    return Quickshell.env("HOME") + "/.local/state/omarchy/"
  }
  readonly property string focusPath: xdgState + "distractions.focus"
  readonly property int bindRetryMs: 250
  readonly property int bindRetryLimit: 40
  readonly property int restoredRetryMs: 80
  readonly property int restoredRetryLimit: 10

  property var notifications: null
  property var members: []
  property bool bound: false
  property bool ready: false
  property bool armed: false
  property int pendingOps: 0
  property int bindAttempts: 0
  property var restoredQueue: []
  property bool restoredBusy: false
  property var countQueue: []
  property bool countBusy: false
  property string countLabel: ""
  property int countRetries: 0
  property int countRetryLimit: 2
  property bool countFailed: false

  function localPath(url) {
    var value = String(url)
    if (value.indexOf("file://") === 0)
      return decodeURIComponent(value.substring(7))
    return value
  }

  function popupFileName(row) {
    if (!row)
      return ""
    return String(row.timestamp || 0) + "-" + String(row.originalId || 0) + ".json"
  }

  function normalizeToken(value) {
    return String(value || "").trim().toLowerCase()
  }

  function isPluginToast(app) {
    var name = String(app || "")
    return name === "omarchy-action" || name === "notify-send"
  }

  function isGenericBrowserIdentity(value) {
    var token = normalizeToken(value)
    if (!token)
      return false
    if (token === "google chrome" || token === "google-chrome" || token === "chrome"
        || token === "chromium" || token === "chromium-browser"
        || token === "brave" || token === "brave-browser"
        || token === "com.google.chrome" || token === "org.chromium.Chromium")
      return true
    return false
  }

  function isChromiumDerived(app, appIcon) {
    var source = (String(app || "") + "\n" + String(appIcon || "")).toLowerCase()
    return source.indexOf("chrom") >= 0 || source.indexOf("brave") >= 0
        || source.indexOf("vivaldi") >= 0 || source.indexOf("microsoft-edge") >= 0
        || source.indexOf("opera") >= 0
  }

  function leadingOriginHost(body) {
    var text = String(body || "")
    var link = /^\s*<a\b[^>]*>\s*((?:https?:\/\/|www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:\/[^<\s]*)?)\s*<\/a>/i.exec(text)
    var bare = /^\s*((?:https?:\/\/|www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:\/\S*)?)(?:\s+|$)/i.exec(text)
    var token = (link && link[1]) || (bare && bare[1]) || ""
    if (!token)
      return ""
    var host = String(token).replace(/^https?:\/\//i, "").replace(/^www\./i, "")
    host = host.split("/")[0].split(":")[0].toLowerCase()
    return host
  }

  function listHas(values, candidate) {
    var needle = normalizeToken(candidate)
    if (!needle || !values)
      return false
    for (var i = 0; i < values.length; i++) {
      if (normalizeToken(values[i]) === needle)
        return true
    }
    return false
  }

  function memberLabelFor(row) {
    if (!row || isPluginToast(row.app))
      return ""
    var i
    if (isChromiumDerived(row.app, row.appIcon)) {
      var host = leadingOriginHost(row.body)
      if (!host)
        return ""
      for (i = 0; i < root.members.length; i++) {
        var chromium = root.members[i].chromium || null
        if (!chromium || !chromium.hosts)
          continue
        for (var h = 0; h < chromium.hosts.length; h++) {
          if (normalizeToken(chromium.hosts[h]) === host)
            return root.members[i].label
        }
      }
      return ""
    }
    for (i = 0; i < root.members.length; i++) {
      var native = root.members[i].native || null
      if (native && (listHas(native.app, row.app) || listHas(native.appIcon, row.appIcon)))
        return root.members[i].label
    }
    return ""
  }

  function hasRequiredApi(svc) {
    return !!svc
        && svc.popupModel
        && svc.liveRefs !== undefined
        && typeof svc.isRestoredRow === "function"
        && typeof svc.deletePopupFileFor === "function"
  }

  function findRow(originalId, timestamp) {
    if (!root.notifications || !root.notifications.popupModel)
      return -1
    var model = root.notifications.popupModel
    for (var i = 0; i < model.count; i++) {
      var row = model.get(i)
      if (row && row.originalId === originalId && row.timestamp === timestamp)
        return i
    }
    return -1
  }

  function findRowByFile(name) {
    if (!root.notifications || !root.notifications.popupModel)
      return -1
    var model = root.notifications.popupModel
    for (var i = 0; i < model.count; i++) {
      var row = model.get(i)
      if (row && popupFileName(row) === name)
        return i
    }
    return -1
  }

  function enqueueObserved(originalId, timestamp) {
    Qt.callLater(function () {
      root.onRowObserved(originalId, timestamp)
    })
  }

  function scanExistingRows() {
    if (!root.armed || !root.notifications || !root.notifications.popupModel)
      return
    var model = root.notifications.popupModel
    for (var i = 0; i < model.count; i++) {
      var row = model.get(i)
      if (!row)
        continue
      root.enqueueObserved(row.originalId, row.timestamp)
    }
  }

  function setArmed(next) {
    var became = next && !root.armed
    root.armed = next
    if (became) {
      root.countFailed = false
      root.scanExistingRows()
    }
  }

  function tryBind() {
    if (root.ready)
      return
    if (!root.shell || typeof root.shell.serviceFor !== "function") {
      root.bindAttempts += 1
      return
    }
    var svc = root.shell.serviceFor("omarchy.notifications")
    if (!hasRequiredApi(svc)) {
      root.bindAttempts += 1
      root.notifications = null
      root.bound = false
      root.ready = false
      return
    }
    root.notifications = svc
    root.bound = true
    root.ready = true
    bindTimer.stop()
    syncFocusArm()
  }

  function syncFocusArm() {
    if (!root.ready)
      return
    focusStatus.running = true
  }

  function onRowObserved(originalId, timestamp) {
    if (!root.armed || !root.notifications)
      return
    var idx = findRow(originalId, timestamp)
    if (idx < 0)
      return
    var row = root.notifications.popupModel.get(idx)
    if (!row || !memberLabelFor(row))
      return
    if (root.notifications.isRestoredRow(row)) {
      root.pendingOps += 1
      root.restoredQueue = root.restoredQueue.concat([{
        originalId: originalId,
        timestamp: timestamp,
        name: popupFileName(row),
        tries: 0
      }])
      pumpRestored()
      return
    }
    root.pendingOps += 1
    suppressLive(originalId, timestamp)
  }

  function enqueueCount(label) {
    if (!label)
      return false
    root.countQueue = root.countQueue.concat([String(label)])
    pumpCount()
    return true
  }

  function pumpCount() {
    if (root.countBusy)
      return
    if (!root.countLabel) {
      if (root.countQueue.length === 0)
        return
      root.countLabel = root.countQueue[0]
      root.countQueue = root.countQueue.slice(1)
      root.countRetries = 0
    }
    root.countBusy = true
    countProc.command = [root.helperPath, "count-increment", root.countLabel]
    countProc.running = true
  }

  function suppressLive(originalId, timestamp) {
    var counted = false
    try {
      if (!root.notifications)
        return
      var idx = findRow(originalId, timestamp)
      if (idx < 0)
        return
      var row = root.notifications.popupModel.get(idx)
      var label = memberLabelFor(row)
      if (!row || !label)
        return
      if (root.notifications.isRestoredRow(row))
        return
      var ref = root.notifications.liveRefs[originalId]
      if (!ref || root.notifications.liveRefs[originalId] !== ref)
        return
      root.notifications.deletePopupFileFor(row)
      idx = findRow(originalId, timestamp)
      if (idx < 0)
        return
      row = root.notifications.popupModel.get(idx)
      if (!row || root.notifications.isRestoredRow(row))
        return
      if (root.notifications.liveRefs[originalId] !== ref)
        return
      root.notifications.popupModel.remove(idx)
      try {
        if (ref.tracked && typeof ref.dismiss === "function")
          ref.dismiss()
      } catch (e) {
      }
      counted = root.enqueueCount(label)
    } finally {
      if (!counted)
        root.pendingOps = Math.max(0, root.pendingOps - 1)
    }
  }

  function pumpRestored() {
    if (root.restoredBusy || root.restoredQueue.length === 0)
      return
    var job = root.restoredQueue[0]
    if (!root.notifications || !root.notifications.popupStateDir) {
      finishRestored(false)
      return
    }
    root.restoredBusy = true
    existsProc.command = ["test", "-f", String(root.notifications.popupStateDir) + job.name]
    existsProc.running = true
  }

  function finishRestored(hit) {
    if (root.restoredQueue.length === 0) {
      root.restoredBusy = false
      return
    }
    var job = root.restoredQueue[0]
    if (hit) {
      suppressRestored(job.name)
      root.restoredQueue = root.restoredQueue.slice(1)
      root.pendingOps = Math.max(0, root.pendingOps - 1)
      root.restoredBusy = false
      pumpRestored()
      return
    }
    job.tries += 1
    if (job.tries >= root.restoredRetryLimit) {
      root.restoredQueue = root.restoredQueue.slice(1)
      root.pendingOps = Math.max(0, root.pendingOps - 1)
      root.restoredBusy = false
      pumpRestored()
      return
    }
    root.restoredQueue[0] = job
    root.restoredBusy = false
    restoredTimer.restart()
  }

  function suppressRestored(name) {
    if (!root.notifications)
      return
    var idx = findRowByFile(name)
    if (idx < 0)
      return
    var row = root.notifications.popupModel.get(idx)
    if (!row || !memberLabelFor(row))
      return
    if (!root.notifications.isRestoredRow(row))
      return
    root.notifications.deletePopupFileFor(row)
    idx = findRowByFile(name)
    if (idx < 0)
      return
    row = root.notifications.popupModel.get(idx)
    if (root.notifications.restoredPopups) {
      var next = ({})
      for (var key in root.notifications.restoredPopups) {
        if (key !== name)
          next[key] = root.notifications.restoredPopups[key]
      }
      root.notifications.restoredPopups = next
    }
    root.notifications.popupModel.remove(idx)
  }

  FileView {
    id: membersFile
    path: root.membersPath
    blockLoading: true
    onLoaded: {
      try {
        var parsed = JSON.parse(membersFile.text())
        root.members = (parsed && parsed.members) ? parsed.members : []
      } catch (e) {
        root.members = []
      }
    }
  }

  FileView {
    id: focusFile
    path: root.focusPath
    watchChanges: true
    onLoaded: root.syncFocusArm()
    onFileChanged: {
      focusFile.reload()
      root.syncFocusArm()
    }
  }

  Timer {
    id: bindTimer
    interval: root.bindRetryMs
    repeat: true
    running: false
    onTriggered: {
      if (root.bindAttempts >= root.bindRetryLimit) {
        running = false
        return
      }
      root.tryBind()
    }
  }

  Timer {
    id: restoredTimer
    interval: root.restoredRetryMs
    repeat: false
    onTriggered: root.pumpRestored()
  }

  Process {
    id: existsProc
    onExited: function (exitCode) {
      root.finishRestored(exitCode === 0)
    }
  }

  Process {
    id: countProc
    onExited: function (exitCode) {
      if (exitCode !== 0 && root.countRetries < root.countRetryLimit) {
        root.countRetries += 1
        root.countBusy = false
        root.pumpCount()
        return
      }
      if (exitCode !== 0)
        root.countFailed = true
      root.countLabel = ""
      root.pendingOps = Math.max(0, root.pendingOps - 1)
      root.countBusy = false
      root.pumpCount()
    }
  }

  Process {
    id: focusStatus
    command: [root.helperPath, "focus-status"]
    onExited: function (exitCode) {
      root.setArmed(root.ready && exitCode === 0)
    }
  }

  Instantiator {
    id: popupWatcher
    active: root.ready && root.notifications !== null
    model: root.notifications ? root.notifications.popupModel : null
    asynchronous: false
    delegate: Item {
      width: 0
      height: 0
      visible: false
    }
    onObjectAdded: function (index, object) {
      if (!root.notifications || !root.notifications.popupModel)
        return
      var row = root.notifications.popupModel.get(index)
      if (!row)
        return
      root.enqueueObserved(row.originalId, row.timestamp)
    }
  }

  IpcHandler {
    target: "distraction-space-notifications"
    function ping(): string {
      return root.ready ? "ready" : "pending"
    }
    function arm(): string {
      if (!root.ready)
        return "pending"
      root.setArmed(true)
      return "ok"
    }
    function disarm(): string {
      root.setArmed(false)
      if (root.countFailed)
        return "error"
      return root.pendingOps === 0 ? "drained" : "draining"
    }
    function drainState(): string {
      if (root.countFailed)
        return "error"
      return (!root.armed && root.pendingOps === 0) ? "drained" : "busy"
    }
  }

  Component.onCompleted: {
    root.bindAttempts = 0
    bindTimer.running = true
    root.tryBind()
  }
}
