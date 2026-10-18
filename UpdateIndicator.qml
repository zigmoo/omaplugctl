import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui

Ui.PanelActionButton {
  id: root
  required property var plugin
  required property var host
  objectName: "pluginUpdateButton"
  iconText: "\uf021"
  fontFamily: host.themeFont
  foreground: Commons.Color.accent
  focusable: true
  Accessible.role: Accessible.Button
  Accessible.name: host.updateActionLabel(plugin)

  HoverHandler { id: hover }
  Ui.PanelToolTip {
    id: tip
    objectName: "pluginUpdateTooltip"
    visible: hover.hovered && root.enabled
    text: root.host.updateTooltip(root.plugin)
    fontFamily: root.host.themeFont
    width: Style.space(340)
    contentItem: Text {
      objectName: "pluginUpdateNotes"
      text: tip.text
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: tip.panelForeground
      font.family: tip.fontFamily
      font.pixelSize: tip.fontSize
      leftPadding: Border.left(tip.panelBorderSpec) + Style.spacing.controlPaddingX
      rightPadding: Border.right(tip.panelBorderSpec) + Style.spacing.controlPaddingX
      topPadding: Border.top(tip.panelBorderSpec) + Style.spacing.controlPaddingY
      bottomPadding: Border.bottom(tip.panelBorderSpec) + Style.spacing.controlPaddingY
    }
  }
}
