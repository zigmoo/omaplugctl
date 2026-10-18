import QtQuick
import Quickshell
import qs.Commons
import qs.Ui as Ui

Ui.BarWidget {
  id: root
  moduleName: "moo.omaplugctl"
  readonly property var service: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
  readonly property var hostWindow: icon.QsWindow.window
  implicitWidth: icon.implicitWidth
  implicitHeight: icon.implicitHeight

  function attach() {
    if (service && hostWindow) service.attach(icon, bar)
  }
  onServiceChanged: Qt.callLater(attach)
  onBarChanged: Qt.callLater(attach)
  onHostWindowChanged: Qt.callLater(attach)
  Component.onCompleted: Qt.callLater(attach)
  Component.onDestruction: if (service) service.detach(icon)

  Ui.BarIconButton {
    id: icon
    anchors.fill: parent
    bar: root.bar
    iconComponent: Component { PluginIcon { pluginId: root.moduleName; ink: icon.foreground } }
    tooltipText: "OmaPlugCtl — manage bar plugins"
    active: root.service && root.service.menuOpen && root.service.anchorItem === icon
    onPressed: function(button) {
      if (button !== Qt.LeftButton || !root.service) return
      if (root.service.menuOpen && root.service.anchorItem === icon) root.service.close()
      else root.service.showFor(icon, root.bar)
    }
  }
}
