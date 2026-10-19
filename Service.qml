import QtQuick
import QtQuick.Controls as Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui

Item {
  id: root
  readonly property string moduleName: "moo.omaplugctl"
  property QtObject bar: null
  property Item anchorItem: null
  property string screenName: ""
  property var widgetAnchors: []
  property bool menuOpen: false
  property var plugins: []
  property string message: ""
  property bool failed: false
  property string confirmingId: ""
  property string pendingId: ""
  property string pendingName: ""
  property string pendingAction: ""
  property string barPosition: ""
  property string sortOrder: "screen"
  property string currentTab: "plugins"
  property bool refreshPending: false
  property bool scanBeforeUpdate: true
  property string scannerStatus: ""
  property int barIconScale: 100
  property bool iconSettingsLoaded: false
  property var workspaceSettings: null
  readonly property bool busy: controller.running || installPanel.busy
  readonly property string helper: decodeURIComponent(Qt.resolvedUrl("controller.php").toString().replace(/^file:\/\//, ""))
  readonly property var helperPrefix: ["php", "-n"]
  readonly property string themeFont: bar && bar.fontFamily ? bar.fontFamily : Style.font.family

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
  readonly property string noDescriptionText: strings.t("plugin.noDescription")
  function pluginFooter(plugin) {
    var date = plugin.updatedDate ? strings.t("plugin.updatedLocal").arg(plugin.updatedDate) : strings.t("plugin.updateUnknown")
    var author = plugin.author ? (["first-commit", "upstream-first-commit"].indexOf(plugin.authorSource) !== -1 ? strings.t(plugin.authorSource === "upstream-first-commit" ? (plugin.authorHistoryShallow ? "plugin.upstreamAuthorShallow" : "plugin.upstreamAuthor") : plugin.authorHistoryShallow ? "plugin.authorShallow" : "plugin.authorFirstCommit").arg(plugin.author).arg((plugin.authorCommit || "").slice(0, 8)) : plugin.author) : strings.t("plugin.authorUnknown")
    var footer = strings.t(plugin.firstParty && !plugin.clonedFrom ? "plugin.footerDefault" : "plugin.footer").arg(date).arg(author)
    if (plugin.sourceCommit) footer += "\n" + strings.t("plugin.sourceCommit").arg(plugin.sourceCommit.slice(0, 12))
    if (plugin.customizedBy) footer += "\n" + strings.t("plugin.customizedBy").arg(plugin.customizedBy)
    return footer
  }
  function updateLabel(plugin) {
    var update = plugin.update || {}
    if (update.dirty && update.status === "current") return strings.t("updates.localEdits")
    return strings.t(update.status === "available" && update.dirty ? "updates.dirty" : "updates." + (update.status || "unchecked"))
  }
  function updateActionLabel(plugin) {
    return strings.t(plugin.firstParty && !plugin.clonedFrom ? "updates.omarchyAction" : "updates.action")
  }
  function updateTooltip(plugin) {
    var update = plugin.update || {}
    var lines = [strings.t("updates.available")]
    if (update.latestDate) lines.push(strings.t("updates.latest").arg(update.latestDate))
    for (var i = 0; i < (update.notes || []).length; i++) lines.push("• " + update.notes[i])
    if (update.status === "diverged") lines.push(strings.t("updates.divergedHelp"))
    else if (update.status === "rewritten") lines.push(strings.t("updates.rewrittenHelp"))
    else if (update.dirty) lines.push(strings.t("updates.dirtyHelp"))
    else lines.push(update.kind === "omarchy" ? strings.t("updates.omarchyHelp") : strings.t("updates.updateHelp"))
    return lines.join("\n")
  }
  function updatePlugin(plugin) {
    if (plugin.operation && plugin.operation.status === "working") return
    if (plugin.update && ["available", "rewritten", "diverged"].indexOf(plugin.update.status) !== -1) invoke("update", plugin.id)
    else { failed = true; message = strings.t(plugin.update && plugin.update.status === "diverged" ? "updates.divergedHelp" : "updates.dirtyHelp") }
  }
  function text(key) { return strings.t(key) }
  function countText(key, count) { return strings.tn(key, count) }
  function selectTab(name) {
    currentTab = name
    Qt.callLater(function() {
      if (name === "install" && runtime.ready) installPanel.activate()
      else if (name === "config") configSortPicker.forceActiveFocus()
    })
  }

  function applyBarIconScale() {
    var values = Object.assign({}, Commons.Color.shellValues)
    if (barIconScale !== 100) {
      function token(name, fallback) {
        var value = parseInt(values["bar." + name], 10)
        return isFinite(value) && value > 0 ? value : fallback
      }
      var ratio = barIconScale / 100
      var originalCanvas = token("icon-canvas", 16)
      var originalSize = Math.min(originalCanvas, token("icon-size", 12))
      var canvas = Math.max(1, Math.round(originalCanvas * ratio))
      values["bar.icon-size"] = Math.max(1, Math.round(originalSize * ratio))
      values["bar.icon-canvas"] = canvas
      values["bar.icon-font"] = Math.max(1, Math.round(token("icon-font", 13) * ratio))
      values["bar.icon-slot"] = Math.max(canvas, token("icon-slot", 27) + canvas - originalCanvas)
      values["bar.status-slot"] = Math.max(canvas, token("status-slot", 21) + canvas - originalCanvas)
      // Keep text-bearing widgets readable when shrinking; grow the bar to fit larger icons.
      values["bar.size-horizontal"] = token("size-horizontal", 26) + Math.max(0, canvas - originalCanvas)
      values["bar.size-vertical"] = token("size-vertical", 28) + Math.max(0, canvas - originalCanvas)
    }
    Style.applyShellValues(values)
  }
  onBarIconScaleChanged: applyBarIconScale()
  Component.onDestruction: Style.applyShellValues(Commons.Color.shellValues)
  Connections {
    target: Commons.Color
    function onShellValuesChanged() { Qt.callLater(root.applyBarIconScale) }
  }
  Process {
    id: settingsReader
    command: root.helperPrefix.concat([root.helper, "settings"])
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var result = JSON.parse(text)
          if (result.ok && !root.iconSettingsLoaded) {
            root.barIconScale = result.barIconScale || 100
            root.iconSettingsLoaded = true
            root.applyBarIconScale()
          }
        } catch (error) { /* A normal menu refresh can retry a failed startup read. */ }
      }
    }
  }

  Connections {
    target: root.bar
    function onPositionChanged() {
      if (!root.busy) root.barPosition = root.bar.position
    }
  }

  function close() { menuOpen = false; confirmingId = "" }
  function attach(item, host) {
    var window = item ? item.QsWindow.window : null
    if (!window || !window.screen) return
    var name = window.screen.name
    widgetAnchors = widgetAnchors.filter(function(entry) { return entry.item && entry.item !== item }).concat([{item: item, bar: host, screen: name}])
    if (!menuOpen || !screenName || screenName === name) {
      anchorItem = item
      bar = host
      if (menuOpen && bar) bar.requestPopout(root)
    }
  }
  function detach(item) {
    widgetAnchors = widgetAnchors.filter(function(entry) { return entry.item && entry.item !== item })
    // Replacing an orientation's icon must not close the service-owned menu
    // or interrupt its in-flight controller process.
  }
  function showFor(item, host) {
    attach(item, host)
    anchorItem = item
    bar = host
    var window = item ? item.QsWindow.window : null
    screenName = window && window.screen ? window.screen.name : ""
    menuOpen = true
    refresh()
  }
  function openMenu() {
    if (anchorItem && bar) showFor(anchorItem, bar)
    else if (widgetAnchors.length) showFor(widgetAnchors[0].item, widgetAnchors[0].bar)
  }
  function refresh() {
    if (busy) { refreshPending = true; return }
    refreshPending = false
    invoke("list", "")
  }
  onBusyChanged: if (!busy && refreshPending) Qt.callLater(root.refresh)
  function moveBar(edge) {
    if (!busy && edge !== barPosition) invoke("position", edge)
  }
  function invoke(action, pluginId, section, source, index, confirmed) {
    if (!runtime.ready || busy || (action !== "list" && action !== "check-updates" && !pluginId)) return
    pendingAction = action
    pendingId = action === "position" || action === "sort" || action === "check-updates" ? "" : (pluginId || "")
    pendingName = ""
    for (var i = 0; i < plugins.length; i++) if (plugins[i].id === pendingId) pendingName = plugins[i].name
    var argv = helperPrefix.concat([helper, action])
    if (action === "position") argv.push("--edge", pluginId)
    else if (action === "sort") argv.push(pluginId)
    else if (action !== "list" && action !== "check-updates") argv.push(pendingId)
    if (action === "move") argv.push("--section", section, "--source", source, "--index", String(index))
    if (confirmed) argv.push("--confirmed")
    message = action === "icon-scale" ? strings.t("config.iconSaving") : action === "workspace-count" ? strings.t("config.workspaceSaving") : action === "position" ? strings.t("bar.moving") : action === "sort" ? strings.t("sort.saving") : action === "check-updates" ? strings.t("updates.checking") : action === "list" ? "Loading plugins…" : "Working on " + pendingName + "…"
    failed = false
    confirmingId = ""
    controller.command = argv
    controller.running = true
  }

  IpcHandler {
    target: root.moduleName
    function show(): void { root.openMenu() }
    function browse(): void { root.openMenu() }
    function hide(): void { root.close() }
    function position(edge: string): void { root.moveBar(edge) }
    function sort(order: string): void { root.invoke("sort", order) }
    function tab(name: string): void { if (["plugins", "config", "install"].indexOf(name) !== -1) root.selectTab(name) }
    function status(): string {
      return JSON.stringify({open: root.menuOpen, visible: panel.visible, runtimeReady: runtime.ready, position: root.barPosition, busy: root.busy, anchored: !!root.anchorItem, screen: root.screenName, sortOrder: root.sortOrder, sortIndex: sortPicker.currentIndex, tab: root.currentTab, catalogLoaded: installPanel.loaded, catalogResults: installPanel.results.length, barIconScale: root.barIconScale, barIconSize: Style.bar.iconSize, workspaceCount: root.workspaceSettings ? root.workspaceSettings.count : null, firstPlugins: root.plugins.slice(0, 5).map(function(plugin) { return plugin.id })})
    }
  }
  Process {
    id: updateStatusReader
    command: root.helperPrefix.concat([root.helper, "update-status"])
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var result = JSON.parse(text)
          if (result.ok) {
            var changed = root.plugins.some(function(p) { return JSON.stringify(p.operation || {}) !== JSON.stringify(result.operations[p.id] || {}) })
            if (changed) root.refresh()
          }
        } catch (e) { console.warn("OmaPlugCtl could not read update progress: " + e) }
      }
    }
  }
  Timer {
    interval: 2000
    repeat: true
    running: root.menuOpen
    onTriggered: if (runtime.ready && !updateStatusReader.running && !root.busy) updateStatusReader.running = true
  }
  Process {
    id: controller
    stdout: StdioCollector { id: output; waitForEnd: true }
    stderr: StdioCollector { id: errors; waitForEnd: true }
    onExited: function(exitCode, exitStatus) {
      try {
        var result = JSON.parse(output.text)
        root.failed = !result.ok
        root.message = (root.pendingName ? root.pendingName + ": " : "") + (result.message || "")
        if (result.ok) {
          var oldY = root.pendingAction === "sort" ? 0 : pluginList.contentY
          root.plugins = result.plugins
          root.barPosition = result.barPosition
          root.sortOrder = result.sortOrder || "screen"
          root.scanBeforeUpdate = result.scanBeforeUpdate !== false
          root.scannerStatus = result.scannerStatus || ""
          root.barIconScale = result.barIconScale || 100
          root.iconSettingsLoaded = true
          root.workspaceSettings = result.workspaceSettings || null
          Qt.callLater(function() { pluginList.contentY = Math.min(oldY, Math.max(0, pluginList.contentHeight - pluginList.height)) })
        }
      } catch (e) {
        root.failed = true
        root.message = errors.text || "Could not read plugin state. Try Refresh."
      }
    }
  }
  Ui.KeyboardPanel {
    id: panel
    bar: root.bar
    owner: root
    anchorItem: root.anchorItem
    open: root.menuOpen
    focusTarget: !runtime.ready ? runtime : root.currentTab === "install" ? installPanel.focusTarget : root.currentTab === "config" ? configSortPicker : edgePicker.focusTarget
    contentWidth: fittedContentWidth(Style.space(420))
    contentHeight: fittedContentHeight(Style.space(600))
    Column {
      id: frame
      objectName: "managerFrame"
      anchors.fill: parent
      spacing: Style.space(14)
      RuntimeCheck {
        id: runtime
        host: root
        width: parent.width
        visible: !ready
        onAvailable: { if (!settingsReader.running) settingsReader.running = true; if (root.menuOpen) { root.refresh(); if (root.currentTab === "install") installPanel.activate() } }
      }
      Row {
        id: tabs
        width: parent.width
        spacing: Style.space(8)
        Ui.Button {
          objectName: "pluginsTabButton"
          text: strings.t("tabs.plugins")
          foreground: root.currentTab === "plugins" ? Commons.Color.accent : Commons.Color.popups.text
          fontFamily: root.themeFont
          focusable: true
          onClicked: root.selectTab("plugins")
        }
        Ui.Button {
          objectName: "configTabButton"
          text: strings.t("tabs.config")
          foreground: root.currentTab === "config" ? Commons.Color.accent : Commons.Color.popups.text
          fontFamily: root.themeFont
          focusable: true
          onClicked: root.selectTab("config")
        }
        Ui.Button {
          objectName: "installTabButton"
          text: strings.t("tabs.install")
          foreground: root.currentTab === "install" ? Commons.Color.accent : Commons.Color.popups.text
          fontFamily: root.themeFont
          focusable: true
          onClicked: root.selectTab("install")
        }
      }
      Column {
        objectName: "managerConfigPanel"
        width: parent.width
        spacing: Style.space(14)
        visible: runtime.ready && root.currentTab === "config"
        Text {
          width: parent.width
          text: strings.t("config.title")
          textFormat: Text.PlainText
          color: Commons.Color.popups.text
          font.family: root.themeFont
          font.pixelSize: Style.font.body
        }
        Row {
          width: parent.width
          spacing: Style.space(12)
          Ui.NumberField {
            id: iconScaleControl
            objectName: "barIconScaleControl"
            label: strings.t("config.iconSize")
            value: root.barIconScale
            from: 50
            to: 200
            stepSize: 5
            fontFamily: root.themeFont
            foreground: Commons.Color.popups.text
            fieldWidth: Style.space(140)
            enabled: !root.busy && root.iconSettingsLoaded
            onModified: function(value) {
              field.value = Qt.binding(function() { return root.barIconScale })
              root.invoke("icon-scale", String(value))
            }
          }
          Ui.Button {
            objectName: "resetBarIconScaleButton"
            anchors.bottom: parent.bottom
            text: strings.t("config.reset")
            fontFamily: root.themeFont
            foreground: Commons.Color.popups.text
            focusable: true
            enabled: !root.busy && root.barIconScale !== 100
            onClicked: root.invoke("icon-scale", "100")
          }
        }
        Column {
          id: workspaceControls
          width: parent.width
          spacing: Style.space(6)
          HoverHandler { id: workspaceHover }
          Ui.PanelToolTip {
            objectName: "workspaceRequirementTooltip"
            visible: workspaceHover.hovered
            text: strings.t(root.workspaceSettings ? "config.workspaceHelp" : "config.workspaceUnsupported")
            fontFamily: root.themeFont
            width: Math.min(workspaceControls.width, Style.space(360))
            y: workspaceCountControl.height + Style.space(4)
          }
          Ui.NumberField {
            id: workspaceCountControl
            objectName: "workspaceCountControl"
            label: strings.t("config.workspaceCount")
            Accessible.name: strings.t("config.workspaceCount")
            Accessible.description: strings.t(root.workspaceSettings ? "config.workspaceHelp" : "config.workspaceUnsupported")
            value: root.workspaceSettings ? root.workspaceSettings.count : 0
            from: 0
            to: 10
            fontFamily: root.themeFont
            foreground: Commons.Color.popups.text
            fieldWidth: Style.space(140)
            enabled: !root.busy && root.workspaceSettings !== null
            onModified: function(value) {
              field.value = Qt.binding(function() { return root.workspaceSettings ? root.workspaceSettings.count : 0 })
              root.invoke("workspace-count", String(value))
            }
          }
          Text {
            width: parent.width
            text: strings.t(root.workspaceSettings ? "config.workspaceHelp" : "config.workspaceUnsupported")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: Qt.darker(Commons.Color.popups.text, 1.4)
            font.family: root.themeFont
            font.pixelSize: Style.font.caption
          }
        }
        Text {
          width: parent.width
          text: strings.t("config.sort")
          textFormat: Text.PlainText
          color: Commons.Color.popups.text
          font.family: root.themeFont
          font.pixelSize: Style.font.caption
        }
        ThemedPicker {
          id: configSortPicker
          objectName: "configSortPicker"
          width: parent.width
          model: [strings.t("sort.screen"), strings.t("sort.name"), strings.t("sort.updates")]
          currentIndex: ["screen", "name", "updates"].indexOf(root.sortOrder)
          fontFamily: root.themeFont
          enabled: !root.busy
          onActivated: function(index) {
            var choice = ["screen", "name", "updates"][index]
            currentIndex = Qt.binding(function() { return ["screen", "name", "updates"].indexOf(root.sortOrder) })
            root.invoke("sort", choice)
          }
        }
        Text {
          width: parent.width
          text: strings.t("config.updateHelp")
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          color: Commons.Color.popups.text
          font.family: root.themeFont
          font.pixelSize: Style.font.caption
        }
        Ui.Toggle {
          objectName: "scanBeforeUpdateToggle"
          width: parent.width
          label: strings.t("config.scanBeforeUpdate")
          description: root.scannerStatus
          fontFamily: root.themeFont
          foreground: Commons.Color.popups.text
          checked: root.scanBeforeUpdate
          enabled: !root.busy
          onClicked: root.invoke("set-scan", root.scanBeforeUpdate ? "false" : "true")
        }
        Text {
          width: parent.width
          text: strings.t("config.scanHelp")
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          color: Commons.Color.popups.text
          font.family: root.themeFont
          font.pixelSize: Style.font.caption
        }
      }
      InstallPanel {
        id: installPanel
        objectName: "managerInstallPanel"
        host: root
        width: parent.width
        height: Math.max(0, frame.height - tabs.height - frame.spacing)
        visible: runtime.ready && root.currentTab === "install"
        onPluginsChanged: Qt.callLater(root.refresh)
      }
      Ui.PanelHero {
        id: hero
        visible: runtime.ready && root.currentTab === "plugins"
        width: parent.width
        title: "OmaPlugCtl"
        meta: root.plugins.length + " plugins · " + root.plugins.filter(function(p) { return p.enabled }).length + " enabled"
        foreground: Commons.Color.popups.text
        fontFamily: root.themeFont
        iconComponent: Component {
          PluginIcon { pluginId: root.moduleName; ink: Commons.Color.popups.text; width: Style.font.display; height: width }
        }
        trailingControl: Component {
          Row {
            spacing: Style.space(4)
            Ui.Button {
              objectName: "checkUpdatesButton"
              anchors.verticalCenter: parent.verticalCenter
              text: strings.t("updates.check")
              fontFamily: root.themeFont
              foreground: Commons.Color.popups.text
              enabled: !root.busy && root.confirmingId === ""
              focusable: true
              onClicked: root.invoke("check-updates", "")
            }
            Ui.PanelActionButton {
              objectName: "refreshPluginsButton"
              anchors.verticalCenter: parent.verticalCenter
              iconText: "󰑐"
              tooltipText: "Refresh"
              fontFamily: root.themeFont
              foreground: Commons.Color.popups.text
              enabled: !root.busy && root.confirmingId === ""
              focusable: true
              onClicked: root.refresh()
            }
          }
        }
      }
      Row {
        id: barControls
        visible: runtime.ready && root.currentTab === "plugins"
        objectName: "barPositionControls"
        width: parent.width
        spacing: Style.space(20)
        Column {
          width: Style.space(140)
          spacing: Style.space(6)
          Text {
            text: strings.t("bar.position")
            textFormat: Text.PlainText
            color: Commons.Color.popups.text
            font.family: root.themeFont
            font.pixelSize: Style.font.caption
          }
          ScreenEdgePicker {
            id: edgePicker
            width: Math.min(parent.width, implicitWidth)
            height: implicitHeight
            position: root.barPosition
            translations: strings
            fontFamily: root.themeFont
            enabled: !root.busy && root.confirmingId === ""
            onPositionRequested: function(edge) { root.moveBar(edge) }
          }
        }
        Column {
          width: Math.max(0, barControls.width - Style.space(160))
          spacing: Style.space(6)
          Text {
            text: strings.t("sort.label")
            textFormat: Text.PlainText
            color: Commons.Color.popups.text
            font.family: root.themeFont
            font.pixelSize: Style.font.caption
          }
          ThemedPicker {
            id: sortPicker
            objectName: "pluginSortPicker"
            width: parent.width
            model: [strings.t("sort.screen"), strings.t("sort.name"), strings.t("sort.updates")]
            currentIndex: ["screen", "name", "updates"].indexOf(root.sortOrder)
            fontFamily: root.themeFont
            enabled: !root.busy && root.confirmingId === ""
            onActivated: function(index) {
              var choice = ["screen", "name", "updates"][index]
              currentIndex = Qt.binding(function() { return ["screen", "name", "updates"].indexOf(root.sortOrder) })
              root.invoke("sort", choice)
            }
          }
        }
      }
      Ui.PanelSeparator { visible: runtime.ready && root.currentTab === "plugins"; width: parent.width; foreground: Commons.Color.popups.text }
      ListView {
        id: pluginList
        objectName: "managerPluginsList"
        visible: runtime.ready && root.currentTab === "plugins"
        width: parent.width
        height: Math.max(0, frame.height - tabs.height - hero.height - barControls.height - status.height - Style.space(1) - frame.spacing * 5)
        clip: true
        spacing: Style.space(5)
        model: root.plugins
        boundsBehavior: Flickable.StopAtBounds
        Controls.ScrollBar.vertical: Controls.ScrollBar { id: scroll; policy: Controls.ScrollBar.AsNeeded }
        Keys.onEscapePressed: root.close()
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Down || event.key === Qt.Key_Up) {
            contentY = Util.clamp(contentY + (event.key === Qt.Key_Down ? 1 : -1) * Style.space(56), 0, Math.max(0, contentHeight - height))
            event.accepted = true
          }
        }
        delegate: PluginRow {
          required property var modelData
          width: pluginList.width - (scroll.visible ? scroll.width + Style.space(6) : 0)
          height: implicitHeight
          plugin: modelData
          host: root
        }
        Text {
          visible: root.plugins.length === 0 && !root.busy
          text: "No bar plugins found"
          color: Commons.Color.popups.text
          font.family: root.themeFont
          font.pixelSize: Style.font.body
        }
      }
      Text {
        id: status
        width: parent.width
        visible: runtime.ready && root.currentTab !== "install" && (root.message !== "" || root.currentTab === "plugins")
        text: root.message || "Scroll to see all plugins"
        color: root.failed ? Commons.Color.urgent : Qt.darker(Commons.Color.popups.text, 1.4)
        font.family: root.themeFont
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
      }
    }
  }
}
