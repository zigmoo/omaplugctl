import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui
import "PluginKinds.js" as Kinds

Flow {
  id: root
  required property var host
  property var kinds: []
  property color foreground: Commons.Color.popups.text
  readonly property bool hovered: areaHover.hovered
  HoverHandler { id: areaHover }
  objectName: "pluginKindBadges"
  spacing: Style.space(4)
  Repeater {
    model: Kinds.normalized(root.kinds)
    delegate: Rectangle {
      id: badge
      required property string modelData
      objectName: "kindBadge_" + modelData
      width: label.implicitWidth + Style.space(10)
      height: label.implicitHeight + Style.space(4)
      radius: Style.cornerRadius
      color: Qt.alpha(root.foreground, 0.05)
      border.color: Qt.alpha(root.foreground, 0.3)
      border.width: Math.max(1, Style.space(1))
      Accessible.role: Accessible.StaticText
      Accessible.name: root.host.text("kind." + modelData + ".label")
      Text {
        id: label
        anchors.centerIn: parent
        text: Kinds.icons[badge.modelData] + " " + root.host.text("kind." + badge.modelData + ".label")
        textFormat: Text.PlainText
        color: root.foreground
        font.family: root.host.themeFont
        font.pixelSize: Style.font.caption
      }
      HoverHandler { id: hover }
      Ui.PanelToolTip {
        objectName: "kindHelp_" + badge.modelData
        visible: hover.hovered
        text: root.host.text("kind." + badge.modelData + ".help")
        fontFamily: root.host.themeFont
        width: Math.min(Style.space(300), root.width)
      }
    }
  }
}
