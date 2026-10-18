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
  property string sortOrder: "name"
  readonly property bool busy: controller.running
  readonly property string helper: decodeURIComponent(Qt.resolvedUrl("controller.py").toString().replace(/^file:\/\//, ""))
  readonly property string themeFont: bar && bar.fontFamily ? bar.fontFamily : Style.font.family

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
  readonly property string noDescriptionText: strings.t("plugin.noDescription")
  function pluginFooter(plugin) {
    var date = plugin.updatedDate ? strings.t("plugin.updatedLocal").arg(plugin.updatedDate) : strings.t("plugin.updateUnknown")
    var author = plugin.author || strings.t("plugin.authorUnknown")
    return strings.t(plugin.firstParty && !plugin.clonedFrom ? "plugin.footerDefault" : "plugin.footer").arg(date).arg(author)
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
    else if (update.dirty) lines.push(strings.t("updates.dirtyHelp"))
    else lines.push(update.kind === "omarchy" ? strings.t("updates.omarchyHelp") : strings.t("updates.reviewHelp"))
    return lines.join("\n")
  }
  function reviewUpdate(plugin) {
    if (plugin.update && (plugin.update.status === "available" || plugin.update.status === "diverged")) invoke("update", plugin.id)
    else { failed = true; message = strings.t(plugin.update && plugin.update.status === "diverged" ? "updates.divergedHelp" : "updates.dirtyHelp") }
  }
  function text(key) { return strings.t(key) }

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
  function refresh() { invoke("list", "") }
  function moveBar(edge) {
    if (!busy && edge !== barPosition) invoke("position", edge)
  }
  function invoke(action, pluginId, section, source, index, confirmed) {
    if (busy || (action !== "list" && action !== "check-updates" && !pluginId)) return
    pendingAction = action
    pendingId = action === "position" || action === "sort" || action === "check-updates" ? "" : (pluginId || "")
    pendingName = ""
    for (var i = 0; i < plugins.length; i++) if (plugins[i].id === pendingId) pendingName = plugins[i].name
    var argv = ["python3", helper, action]
    if (action === "position") argv.push("--edge", pluginId)
    else if (action === "sort") argv.push(pluginId)
    else if (action !== "list" && action !== "check-updates") argv.push(pendingId)
    if (action === "move") argv.push("--section", section, "--source", source, "--index", String(index))
    if (confirmed) argv.push("--confirmed")
    message = action === "position" ? strings.t("bar.moving") : action === "sort" ? strings.t("sort.saving") : action === "check-updates" ? strings.t("updates.checking") : action === "list" ? "Loading plugins…" : "Working on " + pendingName + "…"
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
    function status(): string {
      return JSON.stringify({open: root.menuOpen, visible: panel.visible, position: root.barPosition, busy: root.busy, anchored: !!root.anchorItem, screen: root.screenName, sortOrder: root.sortOrder, sortIndex: sortPicker.currentIndex, firstPlugins: root.plugins.slice(0, 5).map(function(plugin) { return plugin.id })})
    }
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
          root.sortOrder = result.sortOrder || "name"
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
    focusTarget: edgePicker.focusTarget
    contentWidth: fittedContentWidth(Style.space(420))
    contentHeight: fittedContentHeight(Style.space(600))
    Column {
      id: frame
      anchors.fill: parent
      spacing: Style.space(14)
      Ui.PanelHero {
        id: hero
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
              text: strings.t("updates.check")
              fontFamily: root.themeFont
              foreground: Commons.Color.popups.text
              enabled: !root.busy && root.confirmingId === ""
              focusable: true
              onClicked: root.invoke("check-updates", "")
            }
            Ui.PanelActionButton {
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
            model: [strings.t("sort.name"), strings.t("sort.screen"), strings.t("sort.updates")]
            currentIndex: ["name", "screen", "updates"].indexOf(root.sortOrder)
            fontFamily: root.themeFont
            enabled: !root.busy && root.confirmingId === ""
            onActivated: function(index) {
              var choice = ["name", "screen", "updates"][index]
              currentIndex = Qt.binding(function() { return ["name", "screen", "updates"].indexOf(root.sortOrder) })
              root.invoke("sort", choice)
            }
          }
        }
      }
      Ui.PanelSeparator { width: parent.width; foreground: Commons.Color.popups.text }
      ListView {
        id: pluginList
        width: parent.width
        height: Math.max(0, frame.height - hero.height - barControls.height - status.height - Style.space(1) - frame.spacing * 4)
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
