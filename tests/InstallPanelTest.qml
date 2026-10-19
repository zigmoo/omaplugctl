import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import qs.Commons
import qs.Commons as Commons

ShellRoot {
  Window {
    id: window
    visible: true
    width: 460
    height: 660
    color: Commons.Color.popups.background
    Item {
      id: testHost
      property bool busy: false
      property string helper: Qt.resolvedUrl("catalog_fixture.py").toString().replace(/^file:\/\//, "")
      property string themeFont: Style.font.family
      property bool closed: false
      function text(key) { return translations.t(key) }
      function countText(key, count) { return translations.tn(key, count) }
      function close() { closed = true }
      Commons.Translations { id: translations; directory: Qt.resolvedUrl("i18n") }
    }
    InstallPanel {
      id: panel
      x: 10
      y: 10
      width: window.width - 20
      height: window.height - 20
      host: testHost
    }
    TestCase {
      id: tests
      name: "InstallPanel"
      when: window.visible
      function initTestCase() { panel.activate(); tryCompare(panel, "loaded", true, 5000) }
      function init() {
        tryCompare(panel, "busy", false, 5000)
        panel.verifiedOnly = true
        panel.focusTarget.text = ""
        wait(30)
      }
      function list() { return findChild(panel, "installResultsList") }
      function typeText(value) {
        mouseClick(panel.focusTarget, panel.focusTarget.width / 2, panel.focusTarget.height / 2)
        for (let i = 0; i < value.length; i++) keyClick(value[i].toUpperCase().charCodeAt(0))
      }
      function test_01_verified_and_typeahead() {
        compare(panel.results.length, 2)
        typeText("jane music")
        compare(panel.results.length, 1)
        compare(panel.results[0].id, "example.radio")
        verify(!panel.busy)
        mouseClick(findChild(panel, "clearInstallSearchButton"))
        compare(panel.results.length, 2)
      }
      function test_02_verified_filter_and_empty_search() {
        mouseClick(findChild(panel, "verifiedOnlyButton"))
        compare(panel.results.length, 3)
        typeText("clocks")
        compare(panel.results.length, 1)
        compare(panel.results[0].coverage, "update-unverified")
        mouseClick(findChild(panel, "verifiedOnlyButton"))
        compare(panel.results.length, 0)
        panel.focusTarget.forceActiveFocus()
        keyClick(Qt.Key_Escape)
        compare(panel.focusTarget.text, "")
      }
      function test_03_install_and_enable_wait_for_readback() {
        typeText("radio")
        wait(50)
        let button = findChild(list().itemAtIndex(0), "catalogInstallButton")
        verify(button !== null)
        mouseClick(button)
        verify(panel.busy)
        verify(!panel.results[0].installed)
        tryVerify(function() { return !panel.busy && panel.results[0].installed }, 5000)
        verify(panel.results[0].installed)
        verify(!panel.results[0].enabled)
        wait(50)
        button = findChild(list().itemAtIndex(0), "catalogInstallButton")
        compare(button.text, "Enable")
        mouseClick(button)
        verify(panel.busy)
        verify(!panel.results[0].enabled)
        tryVerify(function() { return !panel.busy && panel.results[0].enabled }, 5000)
        verify(panel.results[0].enabled)
        wait(50)
        compare(findChild(list().itemAtIndex(0), "catalogInstallButton").enabled, false)
      }
      function test_04_source_and_refresh_pointer_actions() {
        typeText("radio")
        wait(50)
        mouseClick(findChild(list().itemAtIndex(0), "catalogSourceButton"))
        tryCompare(panel, "message", "Opened fixture source.", 5000)
        mouseClick(findChild(panel, "refreshCatalogButton"))
        tryCompare(panel, "message", "Fixture catalog refreshed.", 5000)
      }
      function test_05_error_preserves_results() {
        let helper = testHost.helper
        testHost.helper = "/missing/fixture.py"
        mouseClick(findChild(panel, "refreshCatalogButton"))
        tryCompare(panel, "failed", true, 5000)
        testHost.helper = helper
        verify(panel.failed)
        compare(panel.results.length, 2)
      }
      function test_06_literal_markup_and_layout() {
        panel.focusTarget.text = "markup"
        wait(50)
        compare(panel.results.length, 1)
        let row = list().itemAtIndex(0)
        let texts = []
        function collect(item) {
          if (item.text !== undefined && item.textFormat !== undefined) texts.push(item)
          for (let i = 0; i < item.children.length; i++) collect(item.children[i])
        }
        collect(row)
        verify(texts.some(function(item) { return item.text.indexOf("<img") !== -1 }))
        for (let i = 0; i < texts.length; i++) compare(texts[i].textFormat, Text.PlainText)
        verify(list().height > 200)
        let status = findChild(panel, "installStatusText")
        verify(status.y + status.height <= panel.height + 1)
        grabImage(panel).save(Qt.resolvedUrl("install-test.png").toString().replace(/^file:\/\//, ""))
      }
      function cleanup() { console.log("INSTALL TEST", qtest_results.functionName, qtest_results.failed) }
      function cleanupTestCase() {
        console.log("INSTALL UI FAIL COUNT", qtest_results.failCount)
        Qt.callLater(function() { Qt.quit() })
      }
    }
  }
}
