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
    function invoke(action, id, section, source, index, confirmed) { calls = calls.concat([{action: action, id: id, confirmed: confirmed}]) }
    function showReplacementBars() { calls = calls.concat([{action: "show-replacements"}]) }
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
        compare(findChild(row, "pluginPositionStatus").text, "Enabled")
        let open = findChild(row, "pluginOpenButton")
        verify(open.visible); verify(open.enabled)
        mouseClick(open)
        compare(host.calls.length, 1); compare(host.calls[0].action, "open")
        compare(host.calls[0].id, "example.machine")
        verify(row.plugin.enabled)
        grabImage(win.contentItem).save(Qt.resolvedUrl("overlay-row.png").toString().replace(/^file:\/\//, ""))
      }
      function test_full_bar_pause_and_play_switch_bars() {
        row.plugin = Object.assign({}, row.plugin, {id: "example.replacement", name: "Replacement",
          kinds: ["bar", "bar-widget", "service"], isBarWidget: true, canOpen: false,
          canDisable: false, active: true})
        wait(30)
        compare(findChild(row, "pluginPositionStatus").text, "Active bar")
        let button = findChild(row, "pluginEnableButton")
        verify(button.visible && button.enabled)
        compare(button.iconText, "󰏤")
        compare(button.tooltipText, "Pause Replacement and switch to Omarchy bar")
        mouseClick(button)
        compare(host.calls[0].action, "reset-bar")
        compare(host.calls[0].id, "example.replacement")

        row.plugin = Object.assign({}, row.plugin, {active: false, enabled: false})
        compare(findChild(row, "pluginPositionStatus").text, "Inactive bar")
        compare(button.iconText, "󰐊")
        compare(button.tooltipText, "Use Replacement bar")
        mouseClick(button)
        compare(host.calls[1].action, "use-bar")
        compare(host.calls[1].id, "example.replacement")

        row.plugin = Object.assign({}, row.plugin, {id: "omarchy.bar", isDefaultBar: true, active: true})
        verify(button.visible && button.enabled)
        compare(button.iconText, "󰏤")
        mouseClick(button)
        compare(host.calls[2].action, "show-replacements")
        row.plugin = Object.assign({}, row.plugin, {active: false})
        verify(button.visible)
        compare(button.tooltipText, "Switch to Omarchy bar")
        host.busy = true
        verify(!button.enabled)
      }
      function test_manager_has_pause_with_confirmation() {
        row.plugin = Object.assign({}, row.plugin, {id: "moo.omaplugctl", name: "OmaPlugCtl",
          kinds: ["bar-widget", "service"], isBarWidget: true, isSelf: true,
          canDisable: true, canRemove: false, canOpen: false})
        wait(30)
        let button = findChild(row, "pluginEnableButton")
        verify(button.visible && button.enabled)
        compare(button.iconText, "󰏤")
        mouseClick(button)
        compare(host.confirmingId, "moo.omaplugctl")
        compare(host.calls.length, 0)
        let confirm = findChild(row, "pluginConfirmAction")
        compare(confirm.text, "Confirm pause")
        wait(50)
        verify(confirm.visible && confirm.enabled)
        mouseClick(confirm)
        compare(host.calls[0].action, "disable")
        compare(host.calls[0].id, "moo.omaplugctl")
        verify(host.calls[0].confirmed)
      }
      function test_disabled_overlay_requires_enable_before_open() {
        row.plugin = Object.assign({}, row.plugin, {enabled: false}); wait(30)
        compare(findChild(row, "pluginPositionStatus").text, "Disabled")
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
        compare(findChild(row, "pluginPositionStatus").text, "Enabled")
      }
      function test_bar_widgets_retain_placement_controls() {
        row.plugin = Object.assign({}, row.plugin, {kinds: ["bar-widget"], canOpen: false,
          isBarWidget: true, instances: [{section: "right", index: 0}]})
        row.expanded = true; wait(30)
        verify(!findChild(row, "pluginOpenButton").visible)
        verify(findChild(row, "pluginMoveInstance") !== null)
        verify(findChild(row, "pluginPositionStatus").text.indexOf("Position: Right") === 0)
      }
      function test_default_plugin_shows_brand_and_custom_icon() {
        row.plugin = Object.assign({}, row.plugin, {id: "omarchy.audio", firstParty: true, clonedFrom: "", kinds: ["bar-widget"], isBarWidget: true, canOpen: false})
        wait(50)
        let icon = findChild(row, "pluginIdentityIcon")
        verify(findChild(icon, "omarchyIdentityIcon").visible)
        verify(findChild(icon, "pluginOwnIdentityIcon").visible)
        compare(findChild(icon, "omarchyIdentityIcon").font.family, "omarchy")
        verify(icon.width > icon.height)
        grabImage(win.contentItem).save(Qt.resolvedUrl("default-icon-pair.png").toString().replace(/^file:\/\//, ""))
      }
      function test_default_without_custom_icon_shows_brand_only() {
        row.plugin = Object.assign({}, row.plugin, {id: "omarchy.background", firstParty: true, clonedFrom: "", kinds: ["service"], canOpen: false})
        wait(30)
        let icon = findChild(row, "pluginIdentityIcon")
        verify(findChild(icon, "omarchyIdentityIcon").visible)
        verify(!findChild(icon, "pluginOwnIdentityIcon").visible)
        compare(icon.width, icon.height)
        row.plugin = Object.assign({}, row.plugin, {id: "omarchy.menu"}); wait(30)
        verify(!findChild(icon, "pluginOwnIdentityIcon").visible) // Do not duplicate the logo.
      }
      function test_user_clone_is_not_branded_as_default() {
        row.plugin = Object.assign({}, row.plugin, {id: "user.clock", firstParty: false, clonedFrom: "omarchy.clock", kinds: ["bar-widget"], isBarWidget: true})
        wait(30)
        let icon = findChild(row, "pluginIdentityIcon")
        verify(!findChild(icon, "omarchyIdentityIcon").visible)
        verify(findChild(icon, "pluginOwnIdentityIcon").visible)
      }
      function test_combined_kinds_have_all_badges() {
        row.plugin = Object.assign({}, row.plugin, {kinds: ["bar-widget", "service", "panel"], isBarWidget: true})
        wait(30)
        verify(findChild(row, "kindBadge_bar-widget") !== null)
        verify(findChild(row, "kindBadge_service") !== null)
        verify(findChild(row, "kindBadge_panel") !== null)
      }
      function cleanup() { console.log("PLUGIN KINDS TEST", qtest_results.functionName, qtest_results.failed) }
      function cleanupTestCase() {
        console.log("PLUGIN KINDS FAIL COUNT", qtest_results.failCount)
        Qt.callLater(function() { Qt.quit() })
      }
    }
  }
}
