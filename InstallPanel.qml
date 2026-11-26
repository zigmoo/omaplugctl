import QtQuick
import QtQuick.Controls as Controls
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui

Column {
  id: root
  required property var host
  property var entries: []
  property var sourceEntries: []
  property string evaluatedInput: ""
  property var repositoryDetails: ({})
  property var hoveredEntry: null
  property bool autoRefreshed: false
  property string detailsRequested: ""
  readonly property bool urlInput: /^https?:\/\//i.test(search.text.trim())
  property string fetchedAt: ""
  property string message: ""
  property bool failed: false
  property bool loaded: false
  property bool needsLoad: false
  property bool verifiedOnly: true
  property string action: ""
  property string pendingId: ""
  property string failedInstallId: ""
  property bool working: false
  readonly property bool busy: working || process.running
  readonly property bool installing: action === "catalog-install" || action === "source-install"
  readonly property bool showInstallErrorInRow: failedInstallId !== "" && results.some(entry => actionId(entry) === failedInstallId)
  readonly property Item focusTarget: search
  readonly property var results: {
    if (urlInput) return sourceEntries
    var terms = search.text.toLowerCase().trim().split(/\s+/).filter(function(term) { return term !== "" })
    var eligible = entries.filter(function(entry) { return !root.verifiedOnly || entry.verified })
    if (!terms.length) return eligible
    // Platform descriptions say "Omarchy" on nearly every entry. Prefer the
    // identity fields so "Oma" surfaces Oma-named plugins immediately.
    var direct = eligible.filter(function(entry) {
      var identity = [entry.name, entry.id, entry.author, entry.category || ""].concat(entry.tags || []).join(" ").toLowerCase()
      return terms.every(function(term) { return identity.indexOf(term) !== -1 })
    })
    var matches = direct.length ? direct : eligible.filter(function(entry) {
      return terms.every(function(term) { return entry.searchText.toLowerCase().indexOf(term) !== -1 })
    })
    var phrase = terms.join(" ")
    function rank(entry) {
      var name = entry.name.toLowerCase()
      return name.indexOf(phrase) === 0 ? 0 : name.indexOf(phrase) !== -1 ? 1 : 2
    }
    return matches.sort(function(a, b) { return rank(a) - rank(b) || a.name.toLowerCase().localeCompare(b.name.toLowerCase()) })
  }
  signal pluginsChanged()
  spacing: Style.space(8)

  function actionId(entry) { return entry.directSource ? entry.evaluation : entry.id }
  function invoke(operation, pid, refresh) {
    if (busy || host.busy) return
    working = true
    action = operation
    pendingId = pid || ""
    failed = false
    failedInstallId = ""
    message = host.text(operation === "source-check" ? "install.evaluating" : installing ? "install.installing" : operation === "catalog-enable" || operation === "source-enable" ? "install.enabling" : operation === "open" ? "plugin.opening" : operation === "catalog-source" || operation === "source-open" ? "install.opening" : "install.loading")
    if (operation === "source-check") { sourceEntries = []; evaluatedInput = search.text.trim() }
    var argv = host.helperPrefix.concat([host.helper, operation])
    if (pid) argv.push(pid)
    if (refresh) argv.push("--refresh")
    process.command = argv
    process.running = true
  }
  function evaluateMarketplace(id) {
    search.text = "https://plugins.omarchy.org/plugin.html?id=" + encodeURIComponent(id)
    invoke("source-check", search.text, false)
  }
  function activate() {
    if (busy) return
    if (host.busy) { needsLoad = true; return }
    needsLoad = false
    invoke("catalog", "", false)
    Qt.callLater(function() { if (root.visible) search.forceActiveFocus() })
  }
  function loadDetails() {
    if (!visible || !hoveredEntry || !hoveredEntry.repo || detailsProcess.running) return
    let cached = repositoryDetails[hoveredEntry.repo]
    if (cached && Date.now() / 1000 - cached.checkedAt < 3600) return
    detailsRequested = hoveredEntry.repo
    detailsProcess.command = host.helperPrefix.concat([host.helper, "source-details", hoveredEntry.repo])
    detailsProcess.running = true
  }
  function detailsText(entry) {
    var details = repositoryDetails[entry.repo] || {}
    var date = details.lastCommitAt ? new Date(details.lastCommitAt).toLocaleString(Qt.locale(Commons.I18n.formatLocale), Locale.ShortFormat) : host.text(details.error || !entry.repo ? "install.commitUnavailable" : "install.commitLoading")
    var lines = [entry.name, host.text("install.author").arg(entry.author || host.text("install.unknown")), entry.description,
      host.text("install.lastCommit").arg(date)]
    if (details.commitSubject) lines.push(details.commitSubject)
    if (details.commit) lines.push(host.text("install.commit").arg(details.commit.slice(0, 12)))
    if (details.commitAuthor) lines.push(host.text("install.commitAuthor").arg(details.commitAuthor))
    if (entry.version) lines.push(host.text("install.version").arg(entry.version))
    if (entry.license) lines.push(host.text("install.license").arg(entry.license))
    if (entry.category) lines.push(host.text("install.category").arg(entry.category))
    if (entry.tags && entry.tags.length) lines.push(host.text("install.tags").arg(entry.tags.join(", ")))
    if (entry.stars) lines.push(host.text("install.stars").arg(Commons.I18n.formatNumber(entry.stars)))
    lines.push(entry.directSource ? entry.validation : host.text("install." + entry.coverage))
    if (entry.verifiedCommit) lines.push(host.text("install.evaluatedCommit").arg(entry.verifiedCommit.slice(0, 12)))
    lines.push(entry.repo || "")
    return lines.filter(function(line) { return !!line }).join("\n")
  }
  Timer { id: hoverDelay; interval: 400; onTriggered: root.loadDetails() }
  Process {
    id: detailsProcess
    stdout: StdioCollector { id: detailsOutput; waitForEnd: true }
    onExited: {
      let updated = Object.assign({}, root.repositoryDetails)
      try {
        let result = JSON.parse(detailsOutput.text)
        if (result.ok && result.repo) {
          updated[result.repo] = Object.assign({checkedAt: Math.floor(Date.now() / 1000)}, result.details)
        } else updated[root.detailsRequested] = {error: true, checkedAt: Math.floor(Date.now() / 1000)}
      } catch (error) { updated[root.detailsRequested] = {error: true, checkedAt: Math.floor(Date.now() / 1000)} }
      root.repositoryDetails = updated
      Qt.callLater(root.loadDetails)
    }
  }
  onVisibleChanged: if (visible) Qt.callLater(root.activate)
  Connections {
    target: root.host
    function onBusyChanged() { if (!root.host.busy && root.visible && root.needsLoad) root.activate() }
  }

  Process {
    id: process
    stdout: StdioCollector { id: output; waitForEnd: true }
    stderr: StdioCollector { id: errors; waitForEnd: true }
    onExited: function(exitCode, exitStatus) {
      try {
        var result = JSON.parse(output.text)
        root.failed = !result.ok
        root.message = result.message || ""
        if (result.sourceEntries && root.evaluatedInput === search.text.trim()) {
          if (root.action === "source-check") root.sourceEntries = result.sourceEntries
          else root.sourceEntries = root.sourceEntries.map(function(entry) {
            return result.sourceEntries.find(function(updated) { return updated.evaluation === entry.evaluation }) || entry
          })
        }
        if (result.entries) {
          root.entries = result.entries
          root.fetchedAt = result.fetchedAt || ""
          root.loaded = true
          if (result.catalogStale && !root.autoRefreshed) {
            root.autoRefreshed = true
            Qt.callLater(function() { if (root.visible && !root.urlInput) root.invoke("catalog", "", true) })
          }
        }
        if (result.ok && (root.action === "catalog-install" || root.action === "catalog-enable" || root.action === "source-install" || root.action === "source-enable")) root.pluginsChanged()
      } catch (error) {
        root.failed = true
        root.message = errors.text || root.host.text("install.failed")
      }
      if (root.failed && root.installing) root.failedInstallId = root.pendingId
      root.pendingId = ""
      root.working = false
    }
  }

  SearchField {
    id: search
    clearLabel: root.host.text("search.clear")
    objectName: "installSearchField"
    width: parent.width
    placeholderText: root.host.text("install.search")
    maximumLength: 2048
    font.family: root.host.themeFont
    foreground: Commons.Color.popups.text
    selectByMouse: true
    onTextChanged: {
      list.positionViewAtBeginning()
      if (text.trim() !== root.evaluatedInput) { root.sourceEntries = []; root.evaluatedInput = "" }
    }
    onAccepted: if (root.urlInput) root.invoke("source-check", text.trim(), false)
    Keys.onEscapePressed: {
      if (text !== "") clear()
      else root.host.close()
    }
    Keys.onDownPressed: { list.forceActiveFocus(); list.currentIndex = 0 }
  }
  Row {
    id: filters
    width: parent.width
    spacing: Style.space(8)
    Ui.Button {
      objectName: "verifiedOnlyButton"
      visible: !root.urlInput
      text: root.host.text("install.verifiedOnly")
      selected: root.verifiedOnly
      foreground: root.verifiedOnly ? Commons.Color.accent : Commons.Color.popups.text
      fontFamily: root.host.themeFont
      focusable: true
      onClicked: { root.verifiedOnly = !root.verifiedOnly; list.positionViewAtBeginning() }
    }
    Ui.Button {
      objectName: "refreshCatalogButton"
      visible: !root.urlInput
      text: root.host.text("install.refresh")
      foreground: Commons.Color.popups.text
      fontFamily: root.host.themeFont
      focusable: true
      enabled: !root.busy && !root.host.busy
      onClicked: root.invoke("catalog", "", true)
    }
    Ui.Button {
      objectName: "evaluateSourceButton"
      visible: root.urlInput
      text: root.host.text("install.evaluate")
      foreground: Commons.Color.accent
      fontFamily: root.host.themeFont
      focusable: true
      enabled: !root.busy && !root.host.busy
      onClicked: root.invoke("source-check", search.text.trim(), false)
    }

  }
  Text {
    id: summary
    width: parent.width
    text: root.host.countText("install.count", root.results.length).arg(Commons.I18n.formatNumber(root.results.length))
      + (root.fetchedAt ? " · " + root.host.text("install.refreshed").arg(new Date(root.fetchedAt).toLocaleString(Qt.locale(Commons.I18n.formatLocale), Locale.ShortFormat)) : "")
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    color: Qt.alpha(Commons.Color.popups.text, 0.7)
    font.family: root.host.themeFont
    font.pixelSize: Style.font.caption
  }
  Text {
    id: help
    width: parent.width
    text: root.host.text(root.urlInput ? "install.urlHelp" : "install.help")
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    color: Qt.alpha(Commons.Color.popups.text, 0.7)
    font.family: root.host.themeFont
    font.pixelSize: Style.font.caption
  }
  Ui.PanelSeparator { id: divider; width: parent.width; foreground: Commons.Color.popups.text }
  AcceleratedListView {
    id: list
    objectName: "installResultsList"
    wheelStep: Style.space(56)
    width: parent.width
    height: Math.max(0, root.height - search.height - filters.height - summary.height - help.height - divider.height - status.height - root.spacing * 6)
    clip: true
    spacing: Style.space(8)
    boundsBehavior: Flickable.StopAtBounds
    model: root.results
    Controls.ScrollBar.vertical: Controls.ScrollBar { id: scroll; policy: Controls.ScrollBar.AsNeeded }
    Keys.onEscapePressed: search.forceActiveFocus()
    delegate: Column {
      id: row
      required property var modelData
      readonly property bool canEvaluate: !modelData.directSource && !modelData.installed && !modelData.installable && !!modelData.repo
      readonly property bool canOpen: modelData.installed === true && modelData.enabled === true && modelData.opensWithoutBar === true
      readonly property bool installFailed: root.failedInstallId !== "" && root.actionId(modelData) === root.failedInstallId
      width: list.width - (scroll.visible ? scroll.width + Style.space(6) : 0)
      spacing: Style.space(3)
      HoverHandler {
        id: rowHover
        onHoveredChanged: {
          if (hovered) { root.hoveredEntry = row.modelData; hoverDelay.restart() }
          else if (root.hoveredEntry === row.modelData) { root.hoveredEntry = null; hoverDelay.stop() }
        }
      }
      Ui.PanelToolTip {
        id: detailsPopup
        objectName: "catalogDetailsPopup"
        visible: !root.busy && (rowHover.hovered || tooltipHover.hovered)
        width: Math.min(420, list.width)
        contentItem: Column {
          HoverHandler { id: tooltipHover }
          Controls.ScrollView {
            width: parent.width
            height: Math.min(tooltipText.implicitHeight, Math.max(160, root.height - Style.space(100)))
            contentWidth: availableWidth
            Text {
              id: tooltipText
              width: parent.width
              padding: Style.space(10)
              text: root.detailsText(row.modelData)
              textFormat: Text.PlainText
              wrapMode: Text.WordWrap
              color: Commons.Color.tooltip.text
              font.family: root.host.themeFont
              font.pixelSize: Style.font.caption
            }
          }
          Ui.Button {
            objectName: "catalogVisitButton"
            x: Style.space(10)
            text: root.host.text("install.visit")
            foreground: Commons.Color.tooltip.text
            fontFamily: root.host.themeFont
            enabled: !!row.modelData.repo && !root.busy && !root.host.busy
            onClicked: root.invoke(row.modelData.directSource ? "source-open" : "catalog-source", row.modelData.directSource ? row.modelData.repo : row.modelData.id, false)
          }
          Item { width: 1; height: Style.space(10) }
        }
      }
      Row {
        width: parent.width
        spacing: Style.space(6)
        Text {
          width: Math.max(0, parent.width - sourceButton.width - installButton.width - Style.space(12))
          anchors.verticalCenter: parent.verticalCenter
          text: row.modelData.name
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: Commons.Color.popups.text
          font.family: root.host.themeFont
          font.pixelSize: Style.font.body
          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            enabled: !!row.modelData.repo && !root.busy && !root.host.busy
            onClicked: root.invoke(row.modelData.directSource ? "source-open" : "catalog-source", row.modelData.directSource ? row.modelData.repo : row.modelData.id, false)
          }
        }
        Ui.Button {
          id: sourceButton
          objectName: "catalogSourceButton"
          text: root.host.text("install.source")
          fontFamily: root.host.themeFont
          foreground: Commons.Color.popups.text
          focusable: true
          enabled: !root.busy && !root.host.busy && row.modelData.repo !== ""
          onClicked: root.invoke(row.modelData.directSource ? "source-open" : "catalog-source", row.modelData.directSource ? row.modelData.repo : row.modelData.id, false)
        }
        Ui.Button {
          id: installButton
          objectName: "catalogInstallButton"
          text: root.pendingId === root.actionId(row.modelData) || (root.action === "open" && root.pendingId === row.modelData.id) ? root.host.text("install.working")
            : row.canOpen ? root.host.text("plugin.openAction")
            : row.modelData.installed ? root.host.text(row.modelData.enabled ? "install.installed" : "install.enable")
            : row.installFailed ? root.host.text("install.retry")
            : root.host.text(row.modelData.installable ? "install.action" : row.canEvaluate ? "install.evaluateSource" : row.modelData.directSource ? "install.blocked" : "install.manual")
          fontFamily: root.host.themeFont
          foreground: Commons.Color.accent
          focusable: true
          enabled: !root.busy && !root.host.busy && (row.canOpen || (row.modelData.installed ? !row.modelData.enabled : row.modelData.installable || row.canEvaluate))
          onClicked: {
            if (row.canOpen) root.invoke("open", row.modelData.id, false)
            else if (row.canEvaluate) root.evaluateMarketplace(row.modelData.id)
            else root.invoke(row.modelData.directSource ? (row.modelData.installed ? "source-enable" : "source-install") : (row.modelData.installed ? "catalog-enable" : "catalog-install"), root.actionId(row.modelData), false)
          }
        }
      }
      PluginKindBadges {
        width: parent.width
        host: root.host
        kinds: row.modelData.kinds || []
      }
      Text {
        width: parent.width
        text: row.modelData.description
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        maximumLineCount: 3
        elide: Text.ElideRight
        color: Qt.alpha(Commons.Color.popups.text, 0.85)
        font.family: root.host.themeFont
        font.pixelSize: Style.font.caption
      }
      Text {
        width: parent.width
        text: (row.modelData.directSource ? row.modelData.repo + " · " + row.modelData.validation : root.host.text("install." + row.modelData.coverage))
          + (row.modelData.author ? " · " + row.modelData.author : "")
          + (row.modelData.installed && !row.modelData.enabled ? " · " + root.host.text("install.disabled") : "")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: row.modelData.verified ? Commons.Color.accent : Qt.alpha(Commons.Color.popups.text, 0.65)
        font.family: root.host.themeFont
        font.pixelSize: Style.font.caption
      }
      Text {
        objectName: "installRowError"
        width: parent.width
        visible: row.installFailed
        text: visible ? root.message : ""
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: Commons.Color.urgent
        font.family: root.host.themeFont
        font.pixelSize: Style.font.caption
      }
      Text {
        objectName: "installSetupNote"
        width: parent.width
        visible: text !== ""
        text: row.modelData.directSource || !row.modelData.installable ? (row.modelData.installNote || "") : ""
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Qt.alpha(Commons.Color.popups.text, 0.85)
        font.family: root.host.themeFont
        font.pixelSize: Style.font.caption
      }
      Ui.PanelSeparator { width: parent.width; foreground: Qt.alpha(Commons.Color.popups.text, 0.3) }
    }
    Text {
      anchors.centerIn: parent
      width: parent.width
      visible: root.loaded && root.results.length === 0 && !root.busy
      text: root.host.text(root.urlInput ? "install.urlEmpty" : "install.empty")
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: Commons.Color.popups.text
      font.family: root.host.themeFont
      font.pixelSize: Style.font.body
    }
  }
  Text {
    id: status
    objectName: "installStatusText"
    width: parent.width
    text: (!root.showInstallErrorInRow && root.message) || root.host.text("install.footer")
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    maximumLineCount: 4
    elide: Text.ElideRight
    color: root.failed && !root.showInstallErrorInRow ? Commons.Color.urgent : Qt.alpha(Commons.Color.popups.text, 0.7)
    font.family: root.host.themeFont
    font.pixelSize: Style.font.caption
  }
}
