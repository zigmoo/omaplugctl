import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import qs.Commons as Commons
import "Plugin" as Plugin

ShellRoot {
  QtObject {
    id: host
    property bool busy: false
    property string confirmingId: ""
    property string themeFont: "JetBrainsMono Nerd Font"
    property string noDescriptionText: "No description"
    property var calls: []
    function invoke(action, id) { calls = calls.concat([{action: action, id: id}]) }
    function pluginFooter(p) { return "Fixture author" }
    function updateLabel(p) { return "Up to date" }
    function updateTooltip(p) { return "" }
    function updateActionLabel(p) { return "Update" }
    function text(key) { return translations.t(key) }
    property var translations: Commons.Translations { directory: Qt.resolvedUrl("i18n") }
  }
  Window {
    id: win
    visible: true
    width: 640
    height: 360
    color: Commons.Color.popups.background
    Plugin.PluginRow {
      id: row; x: 10; y: 20; width: win.width - 20; host: host
      plugin: ({id: "example.machine", name: "Machine Mark", description: "Overlay fixture",
        kinds: ["overlay"], isBarWidget: false, canOpen: true, enabled: true, isSelf: false,
        canDisable: true, canRemove: true, instances: [], update: {status: "current", kind: "plugin"}})
    }
    TestCase {
      name: "PluginKinds"
      when: win.visible
      function init() {
        host.busy = false; host.calls = []; host.confirmingId = ""; row.expanded = false
        row.plugin = ({id: "example.machine", name: "Machine Mark", description: "Overlay fixture",
          kinds: ["overlay"], isBarWidget: false, canOpen: true, enabled: true, isSelf: false,
          canDisable: true, canRemove: true, instances: [], update: {status: "current", kind: "plugin"}})
        mouseMove(win.contentItem, 1, 1)
        wait(50)
      }
      function test_overlay_visible_and_openable() {
        compare(findChild(row, "pluginPositionStatus").text, "Enabled · overlay")
        let open = findChild(row, "pluginOpenButton")
        verify(open.visible); verify(open.enabled)
        mouseClick(open)
        compare(host.calls.length, 1); compare(host.calls[0].action, "open")
        compare(host.calls[0].id, "example.machine")
        verify(row.plugin.enabled)
        grabImage(win.contentItem).save(Qt.resolvedUrl("overlay-row.png").toString().replace(/^file:\/\//, ""))
      }
      function test_disabled_overlay_requires_enable_before_open() {
        row.plugin = Object.assign({}, row.plugin, {enabled: false}); wait(30)
        compare(findChild(row, "pluginPositionStatus").text, "Disabled · overlay")
        let open = findChild(row, "pluginOpenButton"); verify(!open.enabled)
        mouseClick(open); compare(host.calls.length, 0)
        mouseClick(findChild(row, "pluginEnableButton"))
        compare(host.calls[0].action, "enable"); verify(!row.plugin.enabled)
      }
      function test_busy_blocks_open() {
        host.busy = true; wait(30)
        let open = findChild(row, "pluginOpenButton"); verify(!open.enabled)
        mouseClick(open); compare(host.calls.length, 0)
      }
      function test_services_have_no_open_or_move_controls() {
        row.plugin = Object.assign({}, row.plugin, {kinds: ["service"], canOpen: false})
        row.expanded = true; wait(30)
        verify(!findChild(row, "pluginOpenButton").visible)
        compare(findChild(row, "pluginMoveInstance"), null)
        compare(findChild(row, "pluginPositionStatus").text, "Enabled · service")
      }
      function test_bar_widgets_retain_placement_controls() {
        row.plugin = Object.assign({}, row.plugin, {kinds: ["bar-widget"], canOpen: false,
          isBarWidget: true, instances: [{section: "right", index: 0}]})
        row.expanded = true; wait(30)
        verify(!findChild(row, "pluginOpenButton").visible)
        verify(findChild(row, "pluginMoveInstance") !== null)
        verify(findChild(row, "pluginPositionStatus").text.indexOf("Position: Right") === 0)
      }
      function cleanup() { console.log("PLUGIN KINDS TEST", qtest_results.functionName, qtest_results.failed) }
      function cleanupTestCase() {
        console.log("PLUGIN KINDS FAIL COUNT", qtest_results.failCount)
        Qt.callLater(function() { Qt.quit() })
      }
    }
  }
}
