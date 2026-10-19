import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui

Column {
  id: root
  required property var host
  property bool ready: false
  property bool checked: false
  property bool watch: false
  property string detail: ""
  readonly property bool checking: probe.running
  // These fixed commands require no PHP to display or install the prerequisite.
  property var probeCommand: ["/bin/bash", "-c", "command -v php >/dev/null && exec php -n -r 'exit(PHP_VERSION_ID >= 80100 && function_exists(\"proc_open\") ? 0 : 1);'"]
  property var installCommand: ["omarchy", "launch", "terminal", "/bin/bash", "-c", "omarchy pkg add php; result=$?; if (( result != 0 )); then read -r -p 'PHP installation failed. Press Enter to close.'; fi; exit \"$result\""]
  signal available()
  spacing: Style.space(10)
  function check() { if (!probe.running) probe.running = true }
  Component.onCompleted: check()
  onVisibleChanged: if (visible) check()
  Process {
    id: probe
    command: root.probeCommand
    onExited: function(exitCode) {
      var wasReady = root.ready
      root.ready = exitCode === 0
      root.checked = true
      if (root.ready) { root.watch = false; root.detail = ""; if (!wasReady) root.available() }
    }
  }
  Process {
    id: installer
    command: root.installCommand
    onExited: function(exitCode) { if (exitCode !== 0) { root.watch = false; root.detail = root.host.text("runtime.launchFailed") } }
  }
  Timer {
    interval: 2000
    repeat: true
    running: root.watch && !root.ready && root.host.menuOpen
    onTriggered: root.check()
  }
  Text {
    width: parent.width
    text: root.host.text(root.checked ? "runtime.required" : "runtime.checking")
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    color: Commons.Color.popups.text
    font.family: root.host.themeFont
    font.pixelSize: Style.font.body
  }
  Row {
    spacing: Style.space(8)
    Ui.Button {
      objectName: "installPhpButton"
      text: root.host.text("runtime.install")
      tooltipText: root.host.text("runtime.installHelp")
      fontFamily: root.host.themeFont
      foreground: Commons.Color.accent
      focusable: true
      enabled: root.checked && !root.ready && !installer.running
      onClicked: { root.watch = true; root.detail = root.host.text("runtime.installHelp"); installer.running = true }
    }
    Ui.Button {
      objectName: "checkPhpButton"
      text: root.host.text("runtime.retry")
      fontFamily: root.host.themeFont
      foreground: Commons.Color.popups.text
      focusable: true
      enabled: !root.checking
      onClicked: root.check()
    }
  }
  Text {
    width: parent.width
    text: root.detail
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    color: Qt.alpha(Commons.Color.popups.text, 0.7)
    font.family: root.host.themeFont
    font.pixelSize: Style.font.caption
  }
}
