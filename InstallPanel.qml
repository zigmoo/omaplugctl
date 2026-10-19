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
  property string fetchedAt: ""
  property string message: ""
  property bool failed: false
  property bool loaded: false
  property bool needsLoad: false
  property bool verifiedOnly: true
  property string action: ""
  property string pendingId: ""
  property bool working: false
  readonly property bool busy: working || process.running
  readonly property Item focusTarget: search
  readonly property var results: {
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

  function invoke(operation, pid, refresh) {
    if (busy || host.busy) return
    working = true
    action = operation
    pendingId = pid || ""
    failed = false
    message = host.text(operation === "catalog-install" ? "install.installing" : operation === "catalog-enable" ? "install.enabling" : operation === "catalog-source" ? "install.opening" : "install.loading")
    var argv = host.helperPrefix.concat([host.helper, operation])
    if (pid) argv.push(pid)
    if (refresh) argv.push("--refresh")
    process.command = argv
    process.running = true
  }
  function activate() {
    if (busy) return
    if (host.busy) { needsLoad = true; return }
    needsLoad = false
    invoke("catalog", "", false)
    Qt.callLater(function() { if (root.visible) search.forceActiveFocus() })
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
        if (result.entries) {
          root.entries = result.entries
          root.fetchedAt = result.fetchedAt || ""
          root.loaded = true
        }
        if (result.ok && (root.action === "catalog-install" || root.action === "catalog-enable")) root.pluginsChanged()
      } catch (error) {
        root.failed = true
        root.message = errors.text || root.host.text("install.failed")
      }
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
    maximumLength: 200
    font.family: root.host.themeFont
    foreground: Commons.Color.popups.text
    selectByMouse: true
    onTextChanged: list.positionViewAtBeginning()
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
      text: root.host.text("install.verifiedOnly")
      selected: root.verifiedOnly
      foreground: root.verifiedOnly ? Commons.Color.accent : Commons.Color.popups.text
      fontFamily: root.host.themeFont
      focusable: true
      onClicked: { root.verifiedOnly = !root.verifiedOnly; list.positionViewAtBeginning() }
    }
    Ui.Button {
      objectName: "refreshCatalogButton"
      text: root.host.text("install.refresh")
      foreground: Commons.Color.popups.text
      fontFamily: root.host.themeFont
      focusable: true
      enabled: !root.busy && !root.host.busy
      onClicked: root.invoke("catalog", "", true)
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
    text: root.host.text("install.help")
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    color: Qt.alpha(Commons.Color.popups.text, 0.7)
    font.family: root.host.themeFont
    font.pixelSize: Style.font.caption
  }
  Ui.PanelSeparator { id: divider; width: parent.width; foreground: Commons.Color.popups.text }
  ListView {
    id: list
    objectName: "installResultsList"
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
      width: list.width - (scroll.visible ? scroll.width + Style.space(6) : 0)
      spacing: Style.space(3)
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
        }
        Ui.Button {
          id: sourceButton
          objectName: "catalogSourceButton"
          text: root.host.text("install.source")
          fontFamily: root.host.themeFont
          foreground: Commons.Color.popups.text
          focusable: true
          enabled: !root.busy && !root.host.busy && row.modelData.repo !== ""
          onClicked: root.invoke("catalog-source", row.modelData.id, false)
        }
        Ui.Button {
          id: installButton
          objectName: "catalogInstallButton"
          text: root.pendingId === row.modelData.id ? root.host.text("install.working")
            : row.modelData.installed ? root.host.text(row.modelData.enabled ? "install.installed" : "install.enable")
            : root.host.text(row.modelData.installable ? "install.action" : "install.manual")
          fontFamily: root.host.themeFont
          foreground: Commons.Color.accent
          focusable: true
          enabled: !root.busy && !root.host.busy && (row.modelData.installed ? !row.modelData.enabled : row.modelData.installable)
          onClicked: root.invoke(row.modelData.installed ? "catalog-enable" : "catalog-install", row.modelData.id, false)
        }
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
        text: root.host.text("install." + row.modelData.coverage)
          + (row.modelData.author ? " · " + row.modelData.author : "")
          + (row.modelData.installed && !row.modelData.enabled ? " · " + root.host.text("install.disabled") : "")
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: row.modelData.verified ? Commons.Color.accent : Qt.alpha(Commons.Color.popups.text, 0.65)
        font.family: root.host.themeFont
        font.pixelSize: Style.font.caption
      }
      Ui.PanelSeparator { width: parent.width; foreground: Qt.alpha(Commons.Color.popups.text, 0.3) }
    }
    Text {
      anchors.centerIn: parent
      width: parent.width
      visible: root.loaded && root.results.length === 0 && !root.busy
      text: root.host.text("install.empty")
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
    text: root.message || root.host.text("install.footer")
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    maximumLineCount: 4
    elide: Text.ElideRight
    color: root.failed ? Commons.Color.urgent : Qt.alpha(Commons.Color.popups.text, 0.7)
    font.family: root.host.themeFont
    font.pixelSize: Style.font.caption
  }
}
