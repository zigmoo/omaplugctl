import QtQuick
import QtQml.Models
import qs.Commons as Commons
import "BarWidgetScene.js" as Scene

Instantiator {
  id: root
  property Item barContent: null
  property string pluginId: ""
  model: {
    let slots = []
    if (barContent && pluginId) Scene.visitHosts(barContent, true, function(host) {
      if (host.pluginApiId === root.pluginId) slots.push(host)
    })
    return slots
  }

  delegate: Rectangle {
    required property Item modelData
    objectName: "omaPlugCtlBarHighlight"
    parent: modelData
    anchors.fill: parent
    visible: parent !== null && parent.width > 0 && parent.height > 0
    z: 10
    radius: Commons.Style.cornerRadius
    color: Qt.alpha(Commons.Color.accent, 0.22)
    border.color: Commons.Color.accent
    border.width: Math.max(1, Commons.Style.space(1))
  }
}
