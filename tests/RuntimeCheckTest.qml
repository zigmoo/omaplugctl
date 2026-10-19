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
    width: 500
    height: 400
    color: Commons.Color.popups.background
    Item {
      id: testHost
      property bool menuOpen: true
      property string themeFont: Style.font.family
      function text(key) { return strings.t(key) }
      Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
    }
    RuntimeCheck {
      id: panel
      width: 480
      x: 10; y: 10
      host: testHost
      property int availabilityCount: 0
      property string fixturePath: Qt.resolvedUrl("runtime-ready").toString().replace(/^file:\/\//, "")
      probeCommand: ["/bin/bash","-c","test -f \"$1\"","probe",fixturePath]
      installCommand: ["/bin/bash","-c","sleep 0.2; printf ready > \"$1\"","install",fixturePath]
      onAvailable: availabilityCount++
    }
    TestCase {
      name: "RuntimeCheck"
      when: window.visible
      function test_01_missing_runtime_offers_install_without_php() {
        tryCompare(panel,"checked",true,3000);verify(!panel.ready)
        var button=findChild(panel,"installPhpButton");verify(button.enabled)
        mouseClick(button);verify(!panel.ready);verify(panel.watch)
        tryCompare(panel,"ready",true,6000);compare(panel.availabilityCount,1)
        panel.check();tryCompare(panel,"checking",false,3000);compare(panel.availabilityCount,1)
      }
      function cleanup() { console.log("RUNTIME TEST",qtest_results.functionName,qtest_results.failed) }
      function cleanupTestCase() { console.log("RUNTIME FAIL COUNT",qtest_results.failCount);Qt.quit() }
    }
  }
}
