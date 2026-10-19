import QtQuick
import qs.Commons
import qs.Ui as Ui

Ui.TextField {
  id: root
  property string clearLabel: "Clear search"
  rightPadding: horizontalPadding + Border.right(_borderSpec) + (clearButton.visible ? clearButton.width + Style.space(4) : 0)

  Ui.PanelActionButton {
    id: clearButton
    objectName: "clearSearchButton"
    anchors.right: parent.right
    anchors.rightMargin: root.horizontalPadding
    anchors.verticalCenter: parent.verticalCenter
    visible: root.text.length > 0
    iconText: "×"
    tooltipText: root.clearLabel
    foreground: root.foreground
    fontFamily: root.font.family
    fontSize: root.font.pixelSize
    size: Math.max(Style.space(18), root.height - Style.space(6))
    focusable: true
    Accessible.name: root.clearLabel
    onClicked: { root.clear(); root.forceActiveFocus() }
  }
}
