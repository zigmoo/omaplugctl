import QtQuick
import QtQuick.Controls as Controls
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui

Controls.ComboBox {
  id: root
  property var pluginIds: []
  property string fontFamily: Style.font.family
  readonly property color ink: Commons.Color.popups.text
  font.family: fontFamily
  font.pixelSize: Style.font.body
  implicitHeight: Style.spacing.controlHeight
  leftPadding: Style.spacing.controlPaddingX
  rightPadding: Style.spacing.controlPaddingX + Style.font.body
  topPadding: Style.spacing.controlPaddingY
  bottomPadding: Style.spacing.controlPaddingY

  background: Ui.BorderSurface {
    color: Style.controlFill(root.activeFocus, root.hovered, root.ink, Commons.Color.accent)
    borderSpec: Border.controlSpec(root.activeFocus ? "focus" : root.hovered ? "hover-cursor" : "normal", root.ink, Commons.Color.accent)
    radius: Style.cornerRadius
  }
  contentItem: Item {
    implicitHeight: Style.font.body
    PluginIcon {
      id: selectedIcon
      visible: root.pluginIds.length > 0 && root.currentIndex >= 0
      pluginId: visible ? root.pluginIds[root.currentIndex] || "" : ""
      ink: root.ink
      fontFamily: root.fontFamily
      width: Style.font.icon; height: width
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
    }
    Text {
      anchors.left: selectedIcon.visible ? selectedIcon.right : parent.left
      anchors.leftMargin: selectedIcon.visible ? Style.spacing.controlGap : 0
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      text: root.displayText
      color: root.ink
      font: root.font
      elide: Text.ElideRight
      textFormat: Text.PlainText
    }
  }
  indicator: Text {
    anchors.right: parent.right
    anchors.rightMargin: Style.spacing.controlPaddingX
    anchors.verticalCenter: parent.verticalCenter
    text: "󰅀"
    color: root.ink
    font: root.font
  }
  delegate: Controls.ItemDelegate {
    id: row
    required property int index
    required property var modelData
    width: root.width
    height: Style.spacing.popupRowHeight
    highlighted: root.highlightedIndex === index
    background: Rectangle {
      color: row.highlighted ? Style.hoverFillFor(root.ink, Commons.Color.accent) : "transparent"
      radius: Style.cornerRadius
    }
    contentItem: Item {
      PluginIcon {
        id: rowIcon
        visible: root.pluginIds.length > 0
        pluginId: root.pluginIds[row.index] || ""
        ink: root.ink
        fontFamily: root.fontFamily
        width: Style.font.icon; height: width
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
      }
      Text {
        anchors.left: rowIcon.visible ? rowIcon.right : parent.left
        anchors.leftMargin: rowIcon.visible ? Style.spacing.controlGap : 0
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: row.modelData
        color: root.ink
        font: root.font
        elide: Text.ElideRight
        textFormat: Text.PlainText
      }
    }
  }
  popup: Controls.Popup {
    y: root.height + Style.spacing.xxs
    width: root.width
    implicitHeight: Math.min(list.contentHeight + padding * 2, Style.spacing.popupRowHeight * 8 + padding * 2)
    padding: Style.space(3)
    background: Ui.BorderSurface {
      color: Commons.Color.popups.background
      borderSpec: Border.localOrSurfaceSpec("popups", "border", Commons.Color.popups.border, Commons.Color.popups.border, Style.normalBorderWidth)
      radius: Style.cornerRadius
    }
    contentItem: ListView {
      id: list
      clip: true
      implicitHeight: contentHeight
      model: root.popup.visible ? root.delegateModel : null
      currentIndex: root.highlightedIndex
      boundsBehavior: Flickable.StopAtBounds
      Controls.ScrollBar.vertical: Controls.ScrollBar {}
    }
  }
}
