import QtQuick
import Quickshell
import qs.Commons
import qs.Ui as Ui
import "BarServiceBridge.js" as BarServiceBridge

Ui.BarWidget {
  id: root
  moduleName: "moo.omaplugctl"
  property var bridgeService: null
  property var unsubscribeBridge: null
  property var attachedService: null
  readonly property var service: {
    var api = bar ? bar.shell : null
    var direct = api && typeof api.serviceFor === "function" ? api.serviceFor(moduleName) : null
    return direct || bridgeService
  }
  readonly property var hostWindow: icon.QsWindow.window
  implicitWidth: icon.implicitWidth
  implicitHeight: icon.implicitHeight

  function syncAttachment() {
    var next = hostWindow && bar ? service : null
    if (attachedService && attachedService !== next) attachedService.detach(icon)
    attachedService = next
    if (attachedService) attachedService.attach(icon, bar)
  }
  onServiceChanged: Qt.callLater(syncAttachment)
  onBarChanged: Qt.callLater(syncAttachment)
  onHostWindowChanged: Qt.callLater(syncAttachment)
  Component.onCompleted: {
    unsubscribeBridge = BarServiceBridge.subscribe(function(api) { root.bridgeService = api })
    Qt.callLater(syncAttachment)
  }
  Component.onDestruction: {
    if (unsubscribeBridge) unsubscribeBridge()
    if (attachedService) attachedService.detach(icon)
  }

  Ui.BarIconButton {
    id: icon
    anchors.fill: parent
    bar: root.bar
    iconComponent: Component { PluginIcon { pluginId: root.moduleName; ink: icon.foreground } }
    tooltipText: root.service ? "OmaPlugCtl — manage bar plugins" : "OmaPlugCtl — service unavailable"
    active: root.service && root.service.menuOpen && root.service.anchorItem === icon
    onPressed: function(button) {
      if (button !== Qt.LeftButton || !root.service || !root.bar || !root.hostWindow) return
      if (root.service.menuOpen && root.service.anchorItem === icon) root.service.close()
      else root.service.showFor(icon, root.bar)
    }
  }
}
