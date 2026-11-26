import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import qs.Commons as Commons
import qs.Ui as Ui
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
      liveIcon: liveBarIcons.forPlugin(plugin.id)
      captureArtwork: true
      plugin: ({id: "example.machine", name: "Machine Mark", description: "Overlay fixture",
        kinds: ["overlay"], isBarWidget: false, canOpen: true, enabled: true, isSelf: false,
        canDisable: true, canRemove: true, instances: [], update: {status: "current", kind: "plugin"}})
    }
    Item {
      id: fixtureBar
      property string glyph: "󰋎"
      y: 280
      width: win.width
      height: 30
      Repeater {
        id: barSlots
        model: ["example.machine", "example.machine", "example.other"]
        Item {
          required property int index
          required property string modelData
          readonly property string pluginApiId: modelData
          readonly property Item owner: fixtureBar
          readonly property Item activeItem: icon
          x: index * width
          width: 30
          height: fixtureBar.height
          Ui.BarIconButton {
            id: icon
            anchors.fill: parent
            text: index < 2 ? fixtureBar.glyph : ""
            iconComponent: index === 2 ? customArt : null
          }
        }
      }
    }
    Component { id: customArt; Rectangle { width: 12; height: 12; color: "tomato"; radius: 3 } }
    Plugin.LiveBarIcons { id: liveBarIcons; barContent: fixtureBar }
    Plugin.BarIconHighlight {
      id: highlights
      barContent: fixtureBar
      pluginId: row.barHovered ? row.plugin.id : ""
    }
    FontMetrics {
      id: iconMetrics
      font.family: host.themeFont
      font.pixelSize: Commons.Style.font.icon
    }
    TestCase {
      name: "PluginKinds"
      when: win.visible
      function init() {
        host.busy = false; host.calls = []; host.confirmingId = ""; row.expanded = false; row.barHidden = false
        fixtureBar.glyph = "󰋎"
        row.plugin = ({id: "example.machine", name: "Machine Mark", description: "Overlay fixture",
          kinds: ["overlay"], isBarWidget: false, canOpen: true, enabled: true, isSelf: false,
          canDisable: true, canRemove: true, instances: [], update: {status: "current", kind: "plugin"}})
        mouseMove(win.contentItem, 1, 1)
        wait(50)
      }
      function test_overlay_visible_and_openable() {
        compare(findChild(row, "pluginPositionStatus").text, "Enabled · no bar icon")
        let open = findChild(row, "pluginOpenButton")
        verify(open.visible); verify(open.enabled)
        compare(open.text, "Open")
        mouseClick(open)
        compare(host.calls.length, 1); compare(host.calls[0].action, "open")
        compare(host.calls[0].id, "example.machine")
        verify(row.plugin.enabled)
        grabImage(win.contentItem).save(Qt.resolvedUrl("overlay-row.png").toString().replace(/^file:\/\//, ""))
      }
      function test_panel_open_label_and_existing_widget_icon() {
        row.plugin = Object.assign({}, row.plugin, {id: "example.panel", kinds: ["panel"]})
        let open = findChild(row, "pluginOpenButton")
        verify(open.visible && open.enabled)
        compare(open.text, "Open")
        mouseClick(open)
        compare(host.calls[0].action, "open")
        compare(host.calls[0].id, "example.panel")
        row.plugin = Object.assign({}, row.plugin, {kinds: ["panel", "bar-widget"], isBarWidget: true})
        verify(!open.visible)
        verify(findChild(row, "pluginOpenIconButton").visible)
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
        compare(findChild(row, "pluginPositionStatus").text, "Enabled · no bar icon")
      }
      function test_bar_widgets_retain_placement_controls() {
        row.plugin = Object.assign({}, row.plugin, {kinds: ["bar-widget"], canOpen: false,
          isBarWidget: true, instances: [{section: "right", index: 0}]})
        row.expanded = true; wait(30)
        verify(!findChild(row, "pluginOpenButton").visible)
        verify(findChild(row, "pluginMoveInstance") !== null)
        verify(findChild(row, "pluginPositionStatus").text.indexOf("Position: Right") === 0)
      }
      function test_hidden_bar_widget_has_its_own_status() {
        row.plugin = Object.assign({}, row.plugin, {kinds: ["bar-widget"], isBarWidget: true})
        let status = findChild(row, "pluginPositionStatus")
        compare(status.text, "Enabled · no bar slot")
        row.barHidden = true
        compare(status.text, "Enabled · hidden from bar")
        row.plugin = Object.assign({}, row.plugin, {isBarWidget: false, kinds: ["overlay"]})
        compare(status.text, "Enabled · no bar icon")
      }
      function test_row_uses_live_glyph_and_follows_changes() {
        let icon = findChild(row, "pluginIdentityIcon")
        verify(icon !== null)
        tryCompare(icon, "liveGlyph", "󰋎")
        fixtureBar.glyph = "󰋐"
        tryCompare(icon, "liveGlyph", "󰋐")
        liveBarIcons.barContent = null
        compare(icon.liveGlyph, "󰋐")
        liveBarIcons.barContent = Qt.binding(function() { return fixtureBar })
      }
      function test_row_can_preview_custom_widget_artwork() {
        row.plugin = Object.assign({}, row.plugin, {id: "example.other", kinds: ["bar-widget"], isBarWidget: true})
        let image = findChild(row, "pluginLiveArtwork")
        tryCompare(image, "visible", true, 3000)
        tryCompare(image, "status", Image.Ready, 3000)
      }
      function test_hover_highlights_only_visible_enabled_widget_instances() {
        row.plugin = Object.assign({}, row.plugin, {kinds: ["bar-widget"], isBarWidget: true})
        mouseMove(row, row.width / 2, 10)
        tryCompare(highlights, "count", 2)
        compare(highlights.objectAt(0).parent, barSlots.itemAt(0))
        compare(highlights.objectAt(1).parent, barSlots.itemAt(1))
        verify(highlights.objectAt(0).visible)
        barSlots.itemAt(1).visible = false
        tryCompare(highlights, "count", 1)
        barSlots.itemAt(1).visible = true
        mouseMove(win.contentItem, 1, 1)
        tryCompare(highlights, "count", 0)

        row.plugin = Object.assign({}, row.plugin, {enabled: false})
        mouseMove(row, row.width / 2, 10)
        verify(!row.barHovered)
        compare(highlights.count, 0)

        row.plugin = Object.assign({}, row.plugin, {id: "example.unplaced", enabled: true})
        tryCompare(row, "barHovered", true)
        compare(highlights.count, 0)
      }
      function test_expanded_menu_routes_source_and_author_links() {
        let more = findChild(row, "pluginMoreButton")
        mouseClick(more, more.width / 2, more.height / 2)
        tryCompare(row, "expanded", true)
        wait(50)
        for (let action of ["about", "author-github", "author-x"]) {
          let button = findChild(row, "pluginLink_" + action)
          verify(button !== null && button.visible && button.enabled)
          mouseClick(button, button.width / 2, button.height / 2)
          let copy = findChild(row, "pluginCopyLink_" + action)
          verify(copy !== null && copy.visible && copy.enabled)
          verify(copy.x > button.x)
          mouseClick(copy, copy.width / 2, copy.height / 2)
        }
        compare(host.calls.map(function(call) { return call.action }).join(","), "about,copy-about,author-github,copy-author-github,author-x,copy-author-x")
        verify(host.calls.every(function(call) { return call.id === "example.machine" }))
      }
      function test_favorite_and_reinstall_controls() {
        let star = findChild(row, "pluginFavoriteButton")
        compare(star.iconText, "󰓒")
        let outlineHeight = iconMetrics.tightBoundingRect(star.iconText).height
        let infoHeight = iconMetrics.tightBoundingRect("󰋽").height
        verify(Math.abs(outlineHeight - infoHeight) <= 1)
        mouseClick(star, star.width / 2, star.height / 2)
        compare(host.calls[0].action, "favorite")
        row.plugin = Object.assign({}, row.plugin, {favorite: true, installed: false, enabled: false, canReinstall: true, canOpen: false})
        wait(50)
        compare(star.iconText, "󰓎")
        compare(iconMetrics.tightBoundingRect(star.iconText).height, outlineHeight)
        verify(!findChild(row, "pluginEnableButton").visible)
        let reinstall = findChild(row, "pluginReinstallButton")
        verify(reinstall.visible && reinstall.enabled)
        mouseClick(reinstall, reinstall.width / 2, reinstall.height / 2)
        compare(host.calls[1].action, "reinstall")
        mouseClick(star, star.width / 2, star.height / 2)
        compare(host.calls[2].action, "unfavorite")
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
