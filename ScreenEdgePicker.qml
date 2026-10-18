import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui

Item {
  id: root
  property string position: ""
  property string fontFamily: Style.font.family
  required property var translations
  readonly property Item focusTarget: edges.itemAt(0)
  signal positionRequested(string edge)
  implicitWidth: Style.space(96)
  implicitHeight: Style.space(54)

  Rectangle {
    id: screen
    anchors.fill: parent
    radius: Style.cornerRadius
    color: Qt.alpha(Commons.Color.popups.text, 0.025)
    border.width: Math.max(1, Style.space(1))
    border.color: Qt.alpha(Commons.Color.popups.text, 0.35)
  }

  Repeater {
    id: edges
    model: ["top", "bottom", "left", "right"]
    delegate: Ui.Button {
      id: edge
      required property string modelData
      readonly property bool verticalEdge: modelData === "left" || modelData === "right"
      objectName: "barPosition-" + modelData
      x: modelData === "right" ? root.width - width : 0
      y: modelData === "bottom" ? root.height - height : verticalEdge ? Style.space(16) : 0
      width: verticalEdge ? Style.space(16) : root.width
      height: verticalEdge ? Math.max(0, root.height - Style.space(32)) : Style.space(16)
      tooltipText: root.translations.t("bar.move", "%1").arg(root.translations.t("bar." + modelData))
      selected: root.position === modelData
      fontFamily: root.fontFamily
      fontSize: Style.font.caption
      foreground: Commons.Color.popups.text
      background: Qt.alpha(Commons.Color.popups.text, 0.08)
      horizontalPadding: Style.space(4)
      verticalPadding: Style.space(4)
      focusable: true
      Accessible.role: Accessible.Button
      Accessible.name: tooltipText
      onClicked: root.positionRequested(modelData)
    }
  }

  Repeater {
    model: ["top", "bottom", "left", "right"]
    delegate: Rectangle {
      required property string modelData
      readonly property bool verticalEdge: modelData === "left" || modelData === "right"
      readonly property bool selected: root.position === modelData
      x: modelData === "right" ? root.width - width : 0
      y: modelData === "bottom" ? root.height - height : 0
      width: verticalEdge ? Style.space(selected ? 3 : 1) : root.width
      height: verticalEdge ? root.height : Style.space(selected ? 3 : 1)
      color: selected ? Commons.Color.accent : Qt.alpha(Commons.Color.popups.text, 0.25)
    }
  }
}
